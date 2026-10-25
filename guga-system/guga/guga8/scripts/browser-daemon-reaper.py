#!/usr/bin/env python3
"""浏览器侧残留清理：守护进程（browser_harness.daemon）空闲自退 + 临时浏览器进程树回收。

背景：每次带 BU_NAME 的浏览器调用都会留下一个常驻 daemon（每个名字一个），与其临时
浏览器（agent-browser + 它拉起的 chrome）。浏览器先退、daemon 却永不退出，实测已累积
到 19 个 / 340MB swap；而 daemon 退出也不会带走浏览器（实测杀 daemon 后浏览器照旧活着）。

判定（安全第一，宁可不收）：
  * 有客户端连接（其 IPC unix socket 上有 ESTAB）-> 一律不动。
  * daemon 孤儿：CDP 目标端口已死 + 无连接 + 存活 > 5 分钟 -> 直接收。
  * daemon 空闲：连续巡检 CPU 时间为 0、无连接、空闲累计 >= TTL（默认 2h）-> 收。
  * 浏览器进程树：没有任何存活 daemon 指向它的调试端口 + CPU 空闲 >= TTL + 存活 > 5 分钟 -> 收整棵树。
  * 刚启动（< 60 秒）的一概不动；常驻工作档案（~/.hermes/workbuddy/chrome-profile）永不碰。
  * 任何一项探测失败 -> 当「在用」，保守放过。

输出：收掉一个打一行；无事发生完全静默（cron no_agent 下不打扰主人）。
日志：~/.hermes/state/browser-daemon-reaper.log
用法：browser-daemon-reaper.py [--dry-run]
环境：REAPER_TTL_SECONDS（daemon，默认 7200）、REAPER_BROWSER_TTL_SECONDS（浏览器，默认 7200）
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
RUNTIME = os.path.join(HOME, ".config", "browser-harness", "runtime")
STATE = os.path.join(HOME, ".hermes", "guga", "guga8", "state", "browser-daemon-idle.json")
LOG = os.path.join(HOME, ".hermes", "guga", "guga8", "state", "browser-daemon-reaper.log")
TTL = int(os.environ.get("REAPER_TTL_SECONDS", "7200"))
BROWSER_TTL = int(os.environ.get("REAPER_BROWSER_TTL_SECONDS", "7200"))
MAX_SESSIONS = None
if "--max-sessions" in sys.argv:
    try:
        MAX_SESSIONS = int(sys.argv[sys.argv.index("--max-sessions") + 1])
    except (IndexError, ValueError):
        MAX_SESSIONS = None
elif os.environ.get("REAPER_MAX_SESSIONS", "").isdigit():
    MAX_SESSIONS = int(os.environ["REAPER_MAX_SESSIONS"])
DRY = "--dry-run" in sys.argv
QUIET = "--quiet" in sys.argv  # cron 专用：例行清理不吭声，只写日志；有失败才出声
MIN_AGE_ORPHAN = 300
MIN_AGE_ANY = 60
PROTECTED_PROFILES = (os.path.join(HOME, ".hermes", "workbuddy", "chrome-profile"),)
AGENT_BROWSER_MARK = ".hermes/tools/agent-browser-"


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write("%s %s\n" % (time.strftime("%F %T"), msg))
    except OSError:
        pass


def load_state():
    try:
        with open(STATE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = STATE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(st, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)
    except OSError:
        pass


def proc_env(pid):
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            raw = fh.read()
    except OSError:
        return {}
    out = {}
    for chunk in raw.split(b"\0"):
        if b"=" in chunk:
            k, _, v = chunk.partition(b"=")
            out[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return out


def cmdline(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def cpu_ticks(pid):
    try:
        with open("/proc/%d/stat" % pid) as fh:
            data = fh.read()
        tail = data[data.rindex(")") + 2:].split()
        return int(tail[11]) + int(tail[12])  # utime + stime
    except (OSError, ValueError, IndexError):
        return None


def rss_kb(pid):
    try:
        with open("/proc/%d/status" % pid) as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def age_seconds(pid):
    """进程真实存活秒数：/proc/<pid>/stat 的 starttime 换算出启动时刻，与当前 uptime 相减。
    （不能用 /proc/<pid> 目录的 mtime —— 那个会被进程的日常活动刷新，实测刚起几分钟的
    进程可能显示只有几十秒。）"""
    try:
        with open("/proc/%d/stat" % pid) as fh:
            data = fh.read()
        starttime = int(data[data.rindex(")") + 2:].split()[19])
        hz = os.sysconf("SC_CLK_TCK") or 100
        with open("/proc/uptime") as fh:
            uptime = float(fh.read().split()[0])
        return max(0.0, uptime - starttime / float(hz))
    except (OSError, ValueError, IndexError):
        return 1e9


def all_pids():
    return [int(e) for e in os.listdir("/proc") if e.isdigit()]


def parent_map():
    out = {}
    for pid in all_pids():
        try:
            with open("/proc/%d/stat" % pid) as fh:
                data = fh.read()
            out[pid] = int(data[data.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
    return out


def is_daemon_cmd(cmd):
    """精确匹配 `python -m browser_harness.daemon`，避免把命令行里刚好提到这个名字的
    其它进程（shell、编辑器、本脚本自己）一起收掉。"""
    parts = [p for p in cmd.split("\0") if p]
    if len(parts) < 3:
        return False
    if not os.path.basename(parts[0]).startswith("python"):
        return False
    return any(parts[i] == "-m" and parts[i + 1] == "browser_harness.daemon"
               for i in range(len(parts) - 1))


def daemons():
    found = []
    for pid in all_pids():
        cmd = cmdline(pid)
        if not is_daemon_cmd(cmd):
            continue
        env = proc_env(pid)
        found.append({
            "pid": pid,
            "name": env.get("BU_NAME", "default"),
            "cdp_url": env.get("BU_CDP_URL", ""),
            "cdp_ws": env.get("BU_CDP_WS", ""),
            "cloud": env.get("BU_BROWSER_ID", ""),
        })
    return found


def port_of(spec):
    for prefix in ("ws://", "http://", "https://"):
        if spec.startswith(prefix):
            spec = spec[len(prefix):]
            break
    host, _, port = spec.split("/", 1)[0].rpartition(":")
    return int(port) if port.isdigit() else None


def socket_has_client(name):
    """该 daemon 的 IPC socket 上是否有活连接（有 = 正在被用，别碰）。"""
    path = os.path.join(RUNTIME, "bu-%s.sock" % name)
    if not os.path.exists(path):
        return False
    try:
        out = subprocess.run(["ss", "-xp"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True  # 探测不了就当成在用，保守
    return any(path in line and "ESTAB" in line for line in out.splitlines())


def port_alive(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def listening_ports():
    """pid -> set(监听端口)，一次 ss 取全。"""
    out = {}
    try:
        text = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return out
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 4 or cols[0] not in ("LISTEN", "LISTENING"):
            continue
        port = cols[3].rpartition(":")[2]
        if not port.isdigit():
            continue
        for part in line.split("pid="):
            num = part.split(",")[0].strip()
            if num.isdigit():
                out.setdefault(int(num), set()).add(int(port))
    return out


def cdp_target_alive(d):
    """CDP 目标（浏览器）还活着吗；判不了返回 None（不据此杀）。"""
    if d["cloud"]:
        return None
    ws = d["cdp_ws"]
    if ws:
        port = port_of(ws)
        return None if port is None else port_alive("127.0.0.1", port)
    url = d["cdp_url"]
    if url:
        port = port_of(url)
        if port is None:
            return None
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2).read()
            return True
        except Exception:
            return False
    return None  # local 型：不按目标判孤儿


def kill(pid, sig=15):
    try:
        os.kill(pid, sig)
    except OSError:
        return False
    return True


def kill_tree(pids):
    """先 SIGTERM 整棵树，仍活着再 SIGKILL。返回真实消失的 pid 数与释放的 RSS。"""
    freed = 0
    gone = 0
    ordered = list(pids)
    for pid in ordered:
        freed += rss_kb(pid)
        kill(pid, 15)
    deadline = time.time() + 6
    while time.time() < deadline:
        if not [p for p in ordered if os.path.exists("/proc/%d" % p)]:
            break
        time.sleep(0.5)
    for pid in [p for p in ordered if os.path.exists("/proc/%d" % p)]:
        kill(pid, 9)
    time.sleep(0.4)
    for pid in ordered:
        if not os.path.exists("/proc/%d" % pid):
            gone += 1
    return gone, freed / 1024.0


def subtree(root, parents):
    children = {}
    for pid, ppid in parents.items():
        children.setdefault(ppid, []).append(pid)
    out, stack = set(), [root]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def agent_browsers():
    """临时浏览器（agent-browser 二进制）进程：pid + 它拉起的整棵树。"""
    parents = parent_map()
    found = []
    for pid in all_pids():
        parts = [p for p in cmdline(pid).split("\0") if p]
        if not parts or "/bin/agent-browser" not in parts[0]:
            continue
        tree = subtree(pid, parents)
        profile = ""
        for member in tree:
            text = cmdline(member)
            if "--user-data-dir=" in text:
                profile = text.split("--user-data-dir=", 1)[1].split("\0", 1)[0].split(" ", 1)[0]
                break
        found.append({"pid": pid, "tree": tree, "profile": profile})
    return found


def swap_used_mb():
    try:
        with open("/proc/meminfo") as fh:
            vals = {}
            for line in fh:
                k, _, v = line.partition(":")
                vals[k] = int(v.split()[0])
        return (vals["SwapTotal"] - vals["SwapFree"]) / 1024.0
    except (OSError, ValueError, KeyError):
        return None


def protected_ports():
    """常驻档案（PROTECTED_PROFILES）那台浏览器监听的端口——挂着它的 daemon 也算受保护会话。"""
    listened = listening_ports()
    ports = set()
    for pid in all_pids():
        cmd = cmdline(pid)
        if "chrome" not in cmd and "chromium" not in cmd:
            continue
        if any(p in cmd for p in PROTECTED_PROFILES):
            ports |= listened.get(pid, set())
    return ports


def session_units():
    """把「浏览器会话」归一成单元，供数量上限使用。

    一个单元 = 一台临时浏览器（agent-browser 进程树）+ 挂着它的 daemon；
    指向常驻浏览器（如 workbuddy 的 9333）的 daemon 各自算一个单元。
    带 busy / protected 标记的单元永不自动清理。
    """
    live = daemons()
    browsers = agent_browsers()
    listened = listening_ports()
    tcp = tcp_estab()
    prot_ports = protected_ports()
    known_daemon_pids = {d["pid"] for d in live}
    active_daemon_pids = {d["pid"] for d in live if socket_has_client(d["name"])}
    units = []
    port_index = {}
    for b in browsers:
        ports = set()
        for member in b["tree"]:
            ports |= listened.get(member, set())
        profile = b["profile"]
        protected = bool(profile) and any(profile.startswith(p) for p in PROTECTED_PROFILES)
        # 只有「非本树、且不是纯挂着不用的 daemon」的连接才算正在被驱动
        busy = any(pid not in b["tree"] and (pid not in known_daemon_pids or pid in active_daemon_pids)
                   for port in ports for pid in tcp.get(port, set()))
        units.append({
            "key": "b%d" % b["pid"],
            "age": age_seconds(b["pid"]),
            "pids": set(b["tree"]),
            "ports": ports,
            "label": "浏览器会话 %s (pid %d)" % (profile.rsplit("/", 1)[-1] if profile else "?", b["pid"]),
            "protected": protected,
            "busy": busy,
        })
        for port in ports:
            port_index[port] = units[-1]
    for d in live:
        port = port_of(d["cdp_ws"]) or port_of(d["cdp_url"])
        unit = port_index.get(port) if port else None
        if unit is not None:
            unit["pids"].add(d["pid"])
            if socket_has_client(d["name"]):
                unit["busy"] = True
            continue
        units.append({
            "key": "d%d" % d["pid"],
            "age": age_seconds(d["pid"]),
            "pids": {d["pid"]},
            "ports": {port} if port else set(),
            "label": "守护 %s (pid %d)" % (d["name"], d["pid"]),
            "protected": bool(port and port in prot_ports),
            "busy": socket_has_client(d["name"]),
        })
    return units


def enforce_cap(limit, now):
    """会话数超过 limit 时，从最旧的开始收，直到剩 limit 个。
    有客户端连接、常驻档案、或刚起不到 60 秒的一概跳过。"""
    units = session_units()
    if len(units) <= limit:
        return [], [], len(units)
    units.sort(key=lambda u: u["age"])  # 最旧在前
    doomed = []
    for u in units:
        if len(units) - len(doomed) <= limit:
            break
        if u["protected"] or u["busy"] or u["age"] < MIN_AGE_ANY:
            continue
        doomed.append(u)
    killed, failures = [], []
    for u in doomed:
        if DRY:
            killed.append("%s：逾额清理 [干跑]" % u["label"])
            continue
        gone, freed = kill_tree(u["pids"])
        log("reap session-cap %s procs=%d/%d freed=%.0fMB"
            % (u["label"], gone, len(u["pids"]), freed))
        if gone:
            killed.append("%s：逾额清理，释放约 %.0fMB" % (u["label"], freed))
        else:
            failures.append("%s 没杀干净（%d/%d 仍在）" % (u["label"], len(u["pids"]) - gone, len(u["pids"])))
    return killed, failures, len(units)


def tcp_estab():
    """端口 -> 与该端口有 ESTAB 连接的进程 pid 集合（用来判断浏览器是否正被外部驱动）。"""
    out = {}
    try:
        text = subprocess.run(["ss", "-tnp"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return out
    for line in text.splitlines():
        if "ESTAB" not in line:
            continue
        cols = line.split()
        if len(cols) < 6:
            continue
        for field in (cols[3], cols[4]):
            port = field.rpartition(":")[2]
            if not port.isdigit():
                continue
            for part in line.split("pid="):
                num = part.split(",")[0].strip()
                if num.isdigit():
                    out.setdefault(int(port), set()).add(int(num))
    return out


def clean_stale_runtime(now):
    """跑完留下的 bu-*.pid / bu-*.sock：进程早就不在了就删。

    只动「pid 已死」且文件存在超过 MIN_AGE_ANY 的（防止和生产进程抢刚建好的 socket）。
    这些文件不影响功能，但会话多了会堆几十个，看着像还有一堆浏览器在跑。
    """
    removed = []
    try:
        names = os.listdir(RUNTIME)
    except OSError:
        return removed
    for entry in names:
        if not entry.startswith("bu-") or not entry.endswith(".sock"):
            continue
        base = entry[:-5]
        sock = os.path.join(RUNTIME, base + ".sock")
        pidf = os.path.join(RUNTIME, base + ".pid")
        try:
            pid = int(open(pidf).read().strip())
            os.kill(pid, 0)
            continue                        # daemon 还活着，别碰
        except Exception:                   # noqa: BLE001
            pass
        try:
            if now - os.path.getmtime(sock) < MIN_AGE_ANY:
                continue
        except OSError:
            continue
        for f in (sock, pidf):
            try:
                os.remove(f)
                removed.append(os.path.basename(f))
            except OSError:
                pass
    if removed:
        log("clean stale runtime: %d 个文件（%s）" % (len(removed), "、".join(removed[:10])))
    return removed


def main():
    now = time.time()
    st = load_state()
    live = daemons()
    live_pids = {d["pid"] for d in live}
    referenced = {p for p in (port_of(d["cdp_ws"]) or port_of(d["cdp_url"]) for d in live) if p}
    listened = listening_ports()
    killed, killed_bytes = [], 0.0
    failures = []
    before = swap_used_mb()
    prot_ports = protected_ports()          # 常驻档案浏览器的端口：挂在它上面的 daemon 永不自动收

    stale = clean_stale_runtime(now)
    if stale:
        killed.append("清掉陈旧 runtime 文件 %d 个（daemon 早就不在了）" % len(stale))

    # ---- 1) 守护进程 ----
    for d in live:
        pid, name = d["pid"], d["name"]
        rec = st.get("d%d" % pid) or {}
        ticks = cpu_ticks(pid)
        busy = socket_has_client(name)
        changed = rec.get("cpu") is not None and ticks is not None and ticks != rec.get("cpu")
        if changed or busy:
            rec["idle_since"] = None
        elif not rec.get("idle_since"):
            rec["idle_since"] = now
        rec["cpu"] = ticks

        age = age_seconds(pid)
        idle_for = (now - rec["idle_since"]) if rec.get("idle_since") else 0
        target = cdp_target_alive(d)
        dport = port_of(d["cdp_ws"]) or port_of(d["cdp_url"])
        protected_session = bool(dport and dport in prot_ports)   # 挂在常驻档案浏览器上 -> 永不自动收
        reason = None
        if age < MIN_AGE_ANY or busy or protected_session:
            reason = None
        elif target is False and age > MIN_AGE_ORPHAN:
            reason = "孤儿（CDP 目标已死）"
        elif name != "default" and idle_for >= TTL:
            reason = "空闲 %.1f 小时" % (idle_for / 3600)
        if reason and not DRY:
            ok = kill(pid, 15)
            time.sleep(0.5)
            if ok and (os.path.exists("/proc/%d" % pid) or True):
                gone = not os.path.exists("/proc/%d" % pid)
                if not gone:
                    kill(pid, 9)
                    time.sleep(0.3)
                    gone = not os.path.exists("/proc/%d" % pid)
                if gone:
                    log("reap daemon pid=%d name=%s %s" % (pid, name, reason))
                    killed.append("守护 %s (pid %d)：%s" % (name, pid, reason))
                    st.pop("d%d" % pid, None)
                    continue
                failures.append("守护 %s (pid %d) 没杀掉：%s" % (name, pid, reason))
        st["d%d" % pid] = rec
        if reason and DRY:
            killed.append("守护 %s (pid %d)：%s [干跑]" % (name, pid, reason))

    # ---- 2) 临时浏览器进程树 ----
    for b in agent_browsers():
        key = "b%d" % b["pid"]
        rec = st.get(key) or {}
        ports = set()
        for member in b["tree"]:
            ports |= listened.get(member, set())
        if ports & referenced:  # 还有 daemon 指着它 -> 在用
            st[key] = {"cpu": None, "idle_since": None}
            continue
        protected = any(p and p.startswith(PROTECTED_PROFILES) for p in [b["profile"]])
        ticks = sum(t for t in (cpu_ticks(p) for p in b["tree"]) if t is not None)
        elapsed = (now - rec["ts"]) if rec.get("ts") else 0
        # 浏览器后台总有微量 CPU（实测约 5 tick/分钟），所以用容差判定「基本空闲」
        tolerance = max(30, int(15 * elapsed / 60.0))
        changed = rec.get("cpu") is not None and abs(ticks - rec["cpu"]) > tolerance
        rec["ts"] = now
        if changed or protected or not ports:
            rec["idle_since"] = None
        elif not rec.get("idle_since"):
            rec["idle_since"] = now
        rec["cpu"] = ticks
        idle_for = (now - rec["idle_since"]) if rec.get("idle_since") else 0
        age = age_seconds(b["pid"])
        if protected or age < MIN_AGE_ANY or not ports or idle_for < BROWSER_TTL:
            st[key] = rec
            continue
        if DRY:
            killed.append("浏览器树 (pid %d, %d 个进程, 端口 %s)：空闲 %.1f 小时 [干跑]"
                          % (b["pid"], len(b["tree"]), ",".join(sorted(ports)), idle_for / 3600))
            st[key] = rec
            continue
        gone, freed = kill_tree(b["tree"])
        log("reap browser pid=%d procs=%d gone=%d freed=%.0fMB idle=%.1fh profile=%s"
            % (b["pid"], len(b["tree"]), gone, freed, idle_for / 3600, b["profile"]))
        if gone:
            killed.append("浏览器树 (pid %d, %d 个进程)：空闲 %.1f 小时，释放约 %.0fMB"
                          % (b["pid"], gone, idle_for / 3600, freed))
            killed_bytes += freed
            st.pop(key, None)
        else:
            failures.append("浏览器树 (pid %d) 没杀干净：%d/%d 个进程仍在"
                            % (b["pid"], len(b["tree"]) - gone, len(b["tree"])))
            st[key] = rec

    for key in [k for k in st if (k.isdigit() or (k.startswith("d") and k[1:].isdigit()))
                and int(k.lstrip("d")) not in live_pids]:
        st.pop(key, None)
    for key in [k for k in st if k.startswith("b") and k[1:].isdigit()
                and not os.path.exists("/proc/" + k[1:])]:
        st.pop(key, None)
    save_state(st)

    # ---- 3) 会话数量上限（超过就收最旧的，默认关闭，靠 --max-sessions N 打开）----
    cap_happened = False
    if MAX_SESSIONS:
        cap_killed, cap_failed, total = enforce_cap(MAX_SESSIONS, now)
        if cap_killed:
            cap_happened = True
            killed.append("会话数量 %d > %d，收掉最旧的 %d 个" % (total, MAX_SESSIONS, len(cap_killed)))
            killed.extend(cap_killed)
        failures.extend(cap_failed)

    if killed or failures:
        out = "清理浏览器侧残留 %d 项" % len(killed) if killed else "浏览器侧清理有异常"
        for line in killed[:12]:
            out += "\n  " + line
        for line in failures[:6]:
            out += "\n  " + line
        after = swap_used_mb()
        if killed and before is not None and after is not None and not DRY:
            out += "\nswap 占用 %.0fMB → %.0fMB" % (before, after)
        if QUIET and not failures and not cap_happened:
            log(out.replace("\n", " | "))
            return
        print(out)


if __name__ == "__main__":
    main()
