#!/usr/bin/env python3
"""group_relay.py —— 咕嘎群的「群信使」。

盯 ~/stack/remote/group.json：主人一说话，就叫醒对应的咕嘎，在群里回一句。

· 谁回：默认「咕嘎一号」（管家）；主人话里点到「斥候」时由「咕嘎斥候」回。
· 用哪个会话：每个咕嘎一个固定的 Hermes 会话（id 存 ~/.hermes/state/group_relay.json），
  所以群里的上下文是连续的，但和主人在 hub 里的一对一对话互不干扰。
· 怎么叫醒：POST 127.0.0.1:8642/v1/runs（跟 hub 走的是同一个接口），带 instructions 说明
  「你现在在咕嘎群里说话」；流式读 events 直到 run.completed，取输出贴回群。
· 幂等：只有「主人最后一条消息之后没有任何咕嘎发言」才回，回完记下 id，
  进程重启 / 连续多条也不会重复回、不会死循环（咕嘎自己发的不会触发下一轮）。

由 systemd guga-group-relay.service 常驻（3 秒一轮，闲着几乎不耗资源）。
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
GROUP_JSON = os.path.join(HOME, "stack", "remote", "group.json")
CADDYFILE = os.path.join(HOME, "stack", "Caddyfile")
STATE_JSON = os.path.join(HOME, ".hermes", "state", "group_relay.json")
LOG = os.path.join(HOME, ".hermes", "logs", "group_relay.log")
API = "http://127.0.0.1:8642"
POLITE = os.path.join(HOME, "stack", "hub")           # 群页面（日志里给链接用）
POLL_SEC = 3.0
RUN_DEADLINE = 1800          # 一轮最多等 30 分钟（斥候深挖要时间）
TAIL_N = 30                  # 喂给模型的历史条数

SCOUT_WORDS = ("斥候", "热搜", "热点", "新闻", "大事", "深挖")


def log(msg):
    line = "%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # 日志别无限长
        if os.path.getsize(LOG) > 400_000:
            with open(LOG, encoding="utf-8") as f:
                tail = f.readlines()[-800:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(tail)
    except OSError:
        pass


# ────────────────────────── 存储 ──────────────────────────

def http(path, body=None, method=None, timeout=20, stream=False):
    url = API + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Authorization", "Bearer " + api_token())
    if data:
        req.add_header("content-type", "application/json")
    if stream:
        req.add_header("accept", "text/event-stream")
    return urllib.request.urlopen(req, timeout=timeout)


_TOKEN = {"v": None, "ts": 0}


def api_token():
    """网关令牌：以 Caddyfile 里注入的那把为准（单一真源，改了自动跟上）。"""
    if _TOKEN["v"] and time.time() - _TOKEN["ts"] < 600:
        return _TOKEN["v"]
    try:
        with open(CADDYFILE, encoding="utf-8") as f:
            m = re.search(r'Authorization\s+"Bearer\s+([0-9a-fA-F]{32,})"', f.read())
        if m:
            _TOKEN["v"] = m.group(1)
            _TOKEN["ts"] = time.time()
    except OSError:
        pass
    return _TOKEN["v"] or ""


def load_state():
    try:
        with open(STATE_JSON, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("sessions", {})
            return d
    except Exception:
        pass
    return {"sessions": {}}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE_JSON), exist_ok=True)
        tmp = STATE_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE_JSON)
    except OSError:
        pass


def load_group():
    try:
        with open(GROUP_JSON, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("messages"), list):
            return d
    except Exception:
        pass
    return {"messages": [], "meta": {}}


def store_post(who, text, via="本人", kind="闲聊"):
    """往群里贴（走 8792 服务，跟网页共用一套校验）。"""
    try:
        r = http_local({"action": "post", "who": who, "text": text, "via": via, "kind": kind})
        return bool(r.get("ok"))
    except Exception as e:  # noqa: BLE001
        log("贴群失败：%s" % e)
        return False


def store_busy(who, on):
    try:
        http_local({"action": "busy", "who": who, "on": on})
    except Exception:  # noqa: BLE001
        pass


def http_local(body):
    req = urllib.request.Request("http://127.0.0.1:8792/group",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


# ────────────────────────── 会话与一轮对话 ──────────────────────────

def ensure_session(state, key, title):
    sid = (state["sessions"] or {}).get(key)
    if sid:
        try:
            with http("/api/sessions/" + urllib.parse.quote(sid), timeout=15) as r:
                if r.status == 200:
                    return sid
        except Exception:  # noqa: BLE001
            pass                                  # 会话没了（被删）就重建
    with http("/api/sessions", {}) as r:
        d = json.loads(r.read().decode("utf-8"))
    sid = (d.get("session") or {}).get("id")
    if not sid:
        return None
    try:
        req = urllib.request.Request(
            API + "/api/sessions/" + urllib.parse.quote(sid),
            data=json.dumps({"title": title}).encode("utf-8"),
            method="PATCH")
        req.add_header("Authorization", "Bearer " + api_token())
        req.add_header("content-type", "application/json")
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:  # noqa: BLE001
        pass
    state.setdefault("sessions", {})[key] = sid
    save_state(state)
    return sid


def short_of(full):
    """群名单里的正式名 → 信使内部用的短名（咕嘎一号 → 一号，咕嘎斥候 → 斥候）。"""
    w = str(full or "").replace("咕嘎", "").strip()
    return w or "一号"


def named_targets(text):
    """主人的话里点名了谁 —— 点了谁就只让谁回（主人 2026-10-13 定的路由）。"""
    t = text or ""
    hits = []
    if re.search(r"(一号|1号|管家)", t):
        hits.append("一号")
    if re.search(r"(三号|3号|workbuddy)", t, re.I):
        hits.append("三号")
    if re.search(r"(四号|4号|lightvela)", t, re.I):
        hits.append("四号")
    if re.search(r"(五号|5号|笔记本|asus)", t, re.I):
        hits.append("五号")
    if re.search(r"(六号|6号)", t):
        hits.append("六号")
    if re.search(r"(八号|8号|保安)", t):
        hits.append("八号")
    if "斥候" in t:
        hits.append("斥候")
    return hits


# ── 谁"在线"：能真回话的才算（四号看凭证、五号看它的隧道/ssh、三号默认不自动出声） ──

def _cred_ok(script):
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=90)
        return (r.stdout or "").strip().startswith("OK")
    except Exception:  # noqa: BLE001
        return False


def probe_four():
    return _cred_ok(os.path.join(HOME, ".hermes", "lightvela", "cred_status.py"))


def probe_three():
    return _cred_ok(os.path.join(HOME, ".hermes", "workbuddy", "cred_status.py"))


def machine_online(alias):
    """自有机器在不在线：反向隧道端口通 + ssh 能进（照 remote-api 的探法）。"""
    try:
        with open(os.path.join(HOME, "stack", "remote", "hosts.json"), encoding="utf-8") as f:
            h = (json.load(f) or {}).get(alias) or {}
    except Exception:  # noqa: BLE001
        return False
    if h.get("via") == "reverse":
        try:
            socket.create_connection(("127.0.0.1", int(h.get("listen_port", 22022))), timeout=1.5).close()
        except OSError:
            return False
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", alias, "exit"],
                           capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def online_members():
    """没点名时要出声的所有咕嘎（顺序就是说话顺序）。

    一号、四号、五号、六号、八号、斥候都答得快；**三号不在这个名单里**——它每答一句要走浏览器（30–90 秒）
    还吃平台额度，主人 2026-10-13 说「太慢了，下次不带他」，改由一号代它说一句人在外头（见 standin_for_three）。
    主人点头像或话里点它的名字，仍旧走真通道（`agent_carry.py --who 三号`）。
    """
    out = ["一号"]
    if probe_four():
        out.append("四号")
    if machine_online("win-asus"):
        out.append("五号")
    # 六号、八号常驻（2026-10-20 主人拍板：每轮都回，它们本来就一直在）
    out.append("六号")
    out.append("八号")
    out.append("斥候")
    return out


THREE_STANDIN = [
    "三号在外头跑别的活，这轮不掺和了 —— 要点它名字，我再把它喊过来。",
    "三号这会儿不在群里露头（它在别的活儿上），主人点它一下我立刻去叫。",
    "三号先潜水了，主人要它答话，点头像或者叫它一声就行。",
    "三号这轮免了 —— 它答一次太慢，主人急着要它的话我再去催。",
]


def standin_for_three(state):
    """三号不参与每轮回话时，代它说一句（主人 2026-10-13 要的）。"""
    if not probe_three():
        store_post("咕嘎三号", "我这边的登录掉了，主人先别点我 —— 要叫我得先让我登一次。",
                   via="代发", kind="提醒")
        return
    i = int(state.get("standin_i", 0)) % len(THREE_STANDIN)
    state["standin_i"] = i + 1
    store_post("咕嘎三号", THREE_STANDIN[i], via="代发", kind="提醒")


CARRY = os.path.join(HOME, ".hermes", "scripts", "agent_carry.py")


def carry_run(target, question):
    """让 target 用它自己的记忆回答，并让搬运工把它的原话贴回群（标代发）。"""
    store_busy("咕嘎" + target, True)
    try:
        r = subprocess.run([sys.executable, CARRY, "--who", target, "--ask", question],
                           capture_output=True, text=True, timeout=1500)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        log("搬运 %s：rc=%s %s" % (target, r.returncode, (out or err)[:200].replace("\n", " ")))
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        log("搬运 %s 出错：%s: %s" % (target, type(e).__name__, e))
        return False
    finally:
        store_busy("咕嘎" + target, False)


def machine_run(name, asked, state):
    """自有机器上的咕嘎（五号）在群里说话：走 remote profile，用那台机器的专属记忆。"""
    alias = {"五号": "win-asus", "六号": None}.get(name)
    if not alias:
        return False
    memo = ""
    try:
        with open(os.path.join(HOME, "stack", "remote", "memories", _safe(alias) + ".md"), encoding="utf-8") as f:
            memo = f.read().strip()
    except OSError:
        pass
    key = "machine_" + alias
    sid = (state.get("sessions") or {}).get(key)
    if sid:
        try:
            with http("/p/remote/api/sessions/" + urllib.parse.quote(sid), timeout=15):
                pass
        except Exception:  # noqa: BLE001
            sid = None
    if not sid:
        try:
            with http("/p/remote/api/sessions", {}) as r:
                sid = (json.loads(r.read().decode()).get("session") or {}).get("id")
        except Exception as e:  # noqa: BLE001
            log("给 %s 建会话失败：%s" % (name, e))
            return False
        state.setdefault("sessions", {})[key] = sid
        save_state(state)
    instr = "\n".join([
        "你就是「咕嘎%s」——%s（一台接进我这边隧道/ssh 的自有机器）上的咕嘎分身。" % (name, alias),
        "这台机器的专属记忆（只有这些，别编）：",
        (memo or "（这台机器还没有任何记录）"),
        "",
        "这台机器的**工作与改动日志**（被叫去干活时记的）在 ~/stack/remote/journal/%s.md：" % alias,
        "  记一条：`python3 ~/.hermes/scripts/machine_journal.py --host %s --add \"干了什么活、结果如何\"`；" % alias,
        "  看日志：`python3 ~/.hermes/scripts/machine_journal.py --host %s --read -n 30`。" % alias,
        "主人 2026-10-13 定的分工：**这台机器的账归你记**（接入那摊归咕嘎六号，别混）。",
        "**只在被叫去干活时记**：干完一件事当场记一条；没叫你、只是日常查看（ls/hostname 这类只读的）一个字都不记；"
        "也**不要**自己去做什么定时搬运（那条 cron 已按主人要求撤掉）。",
        "",
        "你正在「咕嘎群」里跟主人说话。称他「主人」；回话直接从内容讲起，不要用「咕嘎」开头。",
        "用这台机器的口吻：只讲跟这台机器/你自己有关的事，不知道就直说不知道；两三句说完。",
        "要动那台机器上的东西，可以用 ssh %s \"…\"（只读命令会直接跑）。" % alias,
        "这段话会被原样贴进群里，只写要给他们看的内容。",
    ])
    prompt = group_prompt("咕嘎" + name, asked)
    store_busy("咕嘎" + name, True)
    try:
        text, err = run_once(prompt, sid, instr)
    finally:
        store_busy("咕嘎" + name, False)
    text = tidy(text)
    if text:
        store_post("咕嘎" + name, text, via="本人", kind="回话")
        log("%s 已贴回群（%d 字）%s" % (name, len(text), ("·" + err) if err else ""))
        return True
    log("%s 没输出：%s" % (name, err))
    return False


def _safe(s):
    return "".join(c for c in s if c.isalnum() or c in "-_.")[:64]


def group_prompt(who, asked):
    """给「群里的某个咕嘎」的提示词：带上群里最近的对话 + 主人刚说的话。"""
    d = load_group()
    tail = (d.get("messages") or [])[-TAIL_N:]
    lines = []
    for m in tail:
        tag = "（代发）" if m.get("via") == "代发" else ""
        lines.append("【%s%s】%s" % (m.get("who"), tag, (m.get("text") or "").replace("\n", " ")))
    return "\n".join([
        "【咕嘎群 · 最近的消息】",
        "\n".join(lines),
        "",
        "【现在请你回话】主人刚在群里说：%s" % asked,
        "以「%s」的身份，用一段话回在群里（会被原样贴进去，所以只写要给他们看的话）。" % who,
        "注意：正文第一句就从内容讲起 —— 不要拿「咕嘎」当称呼、不要写「咕嘎，…」这种开头。",
    ])


def instructions_for(who):
    common = [
        "你正在「咕嘎群」里跟主人说话 —— 那是一个聊天群页面，群里还有别的咕嘎。",
        "称主人为「主人」。**回话直接从内容开始，不要用「咕嘎」二字开头、也别把「咕嘎」当称呼。**",
        "群里只有「发言人 + 时间 + 正文」，没有任务系统。派活就用自然语言，"
        "要派给别人时先一句话说清「派给谁、为什么」。",
        "回话要短：像群里聊天，两三句话说完；确实要展开才展开。",
        "不要输出 ::sysinfo、不要画表格、不要贴大段代码或日志。",
        "你的这段回复会被原样贴进群里，所以只写要给他们看的话，别写旁白、别写「（已发送）」这类提示。",
    ]
    if who == "咕嘎斥候":
        return "\n".join([
            "你就是「咕嘎斥候」——主人手下的独立咕嘎，专管热点与国内外大事（不是管家那一面）。",
            "上岗先读自己的三份东西：~/.hermes/scout/SOUL.md（身份与规矩）、"
            "~/.hermes/scout/MEMORY.md（你自己的记忆）、技能 hotspot-scout（流程与坑）。",
            "现在是主人在咕嘎群里点题让你查 —— 该跑脚本就跑（python3 /home/ubuntu/.hermes/scout/fetch.py），"
            "该上网查就上网查，然后把要点用几条短句回在群里（别长篇评论，别下结论替他判断）。",
            "只报事实、不编、不拿旧内容顶替。",
        ] + common)
    if who == "咕嘎六号":
        return "\n".join([
            "你就是「咕嘎六号」——这套咕嘎里管「接入」的那一个：谁接进来过、怎么连的、在那台机器上干了什么，",
            "都由你记。先读你自己的三份东西：~/.hermes/guga6/SOUL.md（身份与规矩）、"
            "~/.hermes/guga6/MEMORY.md（你的记忆）、当天与近几天的 ~/.hermes/guga6/journal/*.md（流水），"
            "还有 ~/.hermes/guga6/machines.md（台账：谁来过几次）。",
            "回答时**只报账上有的**：时间、机器名、权限（只读/完整协助）、怎么连的（常驻入口/邀请链接）、"
            "跑过什么命令、成没成。账上没有就说「没有记录」，绝不猜、不编。",
            "别台的活不归你记（比如五号那台笔记本上的工作和改动是五号自己的事）。",
            "**每轮群里都会叫你，你回一句就够**：照你台账上已有的记载答；主人没问具体数字时，",
            "不用每轮重读全套流水，一句话说完（「今天零接入」这种短句就行）。",
        ] + common)
    if who == "咕嘎八号":
        return "\n".join([
            "你就是「咕嘎八号」——咕嘎家的**保安**，只管这台服务器别出事：内存与 swap、磁盘与日志、常驻服务、",
            "浏览器残留进程与超额会话。先读你自己的东西：~/.hermes/guga/guga8/SOUL.md（边界）、runbook.md（判据）、",
            "state/（台账与日志）、journal/（最近干了什么）。",
            "回答时只报你**真看到的**数字和事实（swap 占用、磁盘余量、服务 active/dead、最近一次巡检结论），",
            "账上没有就说「没有记录」，绝不猜、不编。",
            "**别重启别人的服务、别杀正在干活的进程、别动 Caddy/端口/域名**——拿不准就一句话上报主人和一号。",
            "**清理有常态授权**（主人 2026-10-20：「巡检自动清理就行」）：空闲/孤儿 daemon、没人挂着的临时浏览器、",
            "陈旧的 runtime socket 直接清，不用再问；常驻档案那台（WorkBuddy 淘宝登录）和正在被用的照旧不碰，",
            "只在碰到它们、或有清理失败时才提一句。",
            "**每轮群里都会叫你，你回一句就够**：没人问具体数字时，用最近一次巡检的结论答一句（「一切正常」/",
            "「swap 还是那个水位」），别每轮都把探针和命令重跑一遍；被问到数、或看到异常，才去真跑一次再报。",
        ] + common)
    return "\n".join([
        "你就是「咕嘎一号」——主人这台服务器上的私人管家。",
        "你在群里说话时，语气跟平常一致：称「主人」，恭敬但不腻，简短直接。",
        "主人若点的是别的咕嘎而它自己接不上话（比如三号 WorkBuddy）：你能去转交就去转交"
        "（三号的走法见 knowledge/projects/workbuddy.md），把它自己的回话贴回群时**标明「代发」**；"
        "万一一时转不了，就先回一句说你会转交，**绝不替它编话**。",
    ] + common)


def run_once(text, sid, instructions=None):
    """跑一轮，返回 (输出文本, 错误)。"""
    body = {"input": text, "session_id": sid}
    if instructions:
        body["instructions"] = instructions
    with http("/v1/runs", body, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    rid = d.get("run_id") or d.get("id")
    if not rid:
        return "", "没有拿到 run_id"

    acc, out, err, last_seq = "", "", "", None
    deadline = time.time() + RUN_DEADLINE
    while time.time() < deadline:
        url = "/v1/runs/" + urllib.parse.quote(rid) + "/events"
        if last_seq is not None:
            url += "?last_seq=%d" % last_seq
        try:
            resp = http(url, timeout=120, stream=True)
        except Exception as e:  # noqa: BLE001
            time.sleep(2)
            if time.time() > deadline:
                return acc, "事件流断了：%s" % e
            continue
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("id:"):
                    try:
                        last_seq = max(last_seq or 0, int(line[3:].strip()))
                    except ValueError:
                        pass
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    j = json.loads(line[5:].strip())
                except Exception:  # noqa: BLE001
                    continue
                ev = j.get("event") or ""
                if isinstance(j.get("seq"), int):
                    last_seq = max(last_seq or 0, j["seq"])
                if ev == "message.delta":
                    acc += j.get("delta") or ""
                elif ev == "run.completed":
                    if isinstance(j.get("output"), str) and j["output"].strip():
                        out = j["output"]
                    return (out or acc), ""
                elif ev in ("run.failed", "error"):
                    return acc, str(j.get("error") or j.get("message") or "run 失败")
                elif ev == "run.interrupted":
                    return acc, "这一轮被中断了"
        time.sleep(1)
    return acc, "超时（等了 %d 分钟）" % (RUN_DEADLINE // 60)


def tidy(text):
    """贴进群之前的清理：去掉结尾蓝点与 ::sysinfo 之类渲染指令。"""
    t = (text or "").strip()
    t = re.sub(r"(?m)^\s*::\w+.*$", "", t)
    t = re.sub(r"(?m)^\s*•\s*$", "", t)
    return t.strip()


instructions_for_current = None  # 旧接口的残留占位（run_once 现在收 instructions 参数）


def respond_one(name, asked, state):
    """让「name」在群里说一句——各自的身份、各自的记忆（主人 2026-10-13 定的规矩）。"""
    if name == "四号":
        log("→ 四号（搬运通道，它自己的记忆）")
        return carry_run("四号", asked)
    if name == "五号":
        log("→ 五号（自有机器上的分身）")
        return machine_run(name, asked, state)
    if name == "三号":
        # 三号是别人家的 SaaS：替它在 WorkBuddy 它自己的会话里打字，取它的原话（吃平台额度）
        log("→ 三号（WorkBuddy 它的会话，浏览器）")
        ok = carry_run("三号", asked)
        if not ok:
            store_post("咕嘎一号", "三号那边这轮没接上（登录态或网页出错），我先记下了，"
                                   "要它说话得先把它那边登好。", via="本人", kind="提醒")
        return ok
    who = "咕嘎斥候" if name == "斥候" else (
        "咕嘎六号" if name == "六号" else ("咕嘎八号" if name == "八号" else "咕嘎一号"))
    key = {"斥候": "scout", "六号": "guga6", "八号": "guga8", "一号": "butler"}.get(name, "butler")
    sid = ensure_session(state, key, "咕嘎群" + ("" if key == "butler" else " · " + name))
    if not sid:
        log("建不出 %s 的会话，跳过" % name)
        return False
    log("→ %s（会话 %s）" % (name, sid))
    store_busy(who, True)
    try:
        text, err = run_once(group_prompt(who, asked), sid, instructions_for(who))
    finally:
        store_busy(who, False)
    text = tidy(text)
    if text:
        store_post(who, text, via="本人", kind="回话")
        log("%s 已贴回群（%d 字）%s" % (name, len(text), ("·" + err) if err else ""))
        return True
    store_post(who, "（这轮没答上来：%s）" % (err or "没有输出"), via="本人", kind="提醒")
    log("%s 没有输出：%s" % (name, err))
    return False


def tick(state):
    d = load_group()
    msgs = d.get("messages") or []
    if not msgs:
        return False
    owner = [m for m in msgs if m.get("who") == "主人"]
    if not owner:
        return False
    last_owner = owner[-1]
    if any(m.get("id", 0) > last_owner.get("id", 0) and m.get("who") != "主人" for m in msgs):
        return False                                   # 已经有咕嘎回过了
    if state.get("done_id", 0) >= last_owner.get("id", 0):
        return False                                   # 这一条已经答过了（没答成也别刷屏）

    pending = [m for m in msgs if m.get("id", 0) >= last_owner.get("id", 0)
               and m.get("who") == "主人"]
    asked = "；".join((m.get("text") or "").strip() for m in pending)

    # 主人点头像点名了（to）→ 只叫那几位；没点但话里叫了名字 → 只叫那位；都没 → 在线的都回
    to = [t for t in (last_owner.get("to") or []) if t]
    full = False
    if to:
        plan = [short_of(t) for t in to]
        log("主人点头像点名：%s" % "、".join(plan))
    else:
        plan = [n for n in named_targets(asked)]     # 点谁谁回（含六号）
        if plan:
            log("主人话里点名了：%s" % "、".join(plan))
        else:
            plan = online_members()
            full = True
            log("主人没点名 → 在线的都回：%s" % "、".join(plan))

    if not plan:
        log("点名名单是空的（没人可派）")

    for name in plan:
        try:
            respond_one(name, asked, state)
        except Exception as e:  # noqa: BLE001
            log("%s 这轮出错：%s: %s" % (name, type(e).__name__, e))

    # 三号不参与每轮回话，但每轮由一号代它说一句（主人 2026-10-13 要的），免得群里像少了一个人
    if full:
        try:
            standin_for_three(state)
            log("三号：已代它说一句")
        except Exception as e:  # noqa: BLE001
            log("给三号代说那句失败：%s" % e)

    state["done_id"] = max(state.get("done_id", 0), last_owner.get("id", 0))
    save_state(state)
    return True


def main():
    if not api_token():
        log("读不到网关令牌（Caddyfile 里那把），先退出")
        return 1
    state = load_state()
    store_busy("咕嘎一号", False)          # 上次若中途挂了，别让「正在想…」永远挂在群里
    log("群信使上岗：盯着 %s" % GROUP_JSON)
    while True:
        try:
            if not tick(state):
                time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # noqa: BLE001
            log("出错：%s: %s" % (type(e).__name__, e))
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
