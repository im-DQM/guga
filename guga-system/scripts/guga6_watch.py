#!/usr/bin/env python3
"""guga6_watch.py —— 咕嘎六号的记账手（常驻服务）。

六号管的就是一件事：**谁接进来过、怎么连的、干了什么**。
接入服务（join_api）本身不落盘，但 2026-10-13 起它会往
`/var/lib/guga-join/log/access.jsonl` 追加流水（connect / disconnect / exec_request /
exec_ran / exec_denied / exec_blocked）。这个进程只管读那条流水，把它变成六号自己的记录：

1. 流水 → `~/.hermes/guga6/events.jsonl`（原样一条条存下来，机器可读）
2. 人话日记 → `~/.hermes/guga6/journal/<日期>.md`（一号和六号自己看的）
3. 台账 → `~/.hermes/guga6/machines.md`（每台机器来过几次、最近一次、什么权限）
4. 有事就在咕嘎群说一句（**有人接进来 / 断开 / 命令跑失败** 时才说，别刷屏）

由 systemd `guga6-watch.service` 常驻（20 秒一轮）。只读流水，不碰接入服务本身。
"""
import json
import os
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
AUDIT = os.environ.get("GUGA6_AUDIT", "/var/lib/guga-join/log/access.jsonl")
NOSAY = os.environ.get("GUGA6_NOSAY") == "1"          # 自检用：不往群里发
G6 = os.path.join(HOME, ".hermes", "guga6")
EVENTS = os.path.join(G6, "events.jsonl")
JOURNAL_DIR = os.path.join(G6, "journal")
MACHINES = os.path.join(G6, "machines.md")
STATE = os.path.join(G6, "state.json")
GROUP_API = "http://127.0.0.1:8792/group"
LOG = os.path.join(HOME, ".hermes", "logs", "guga6_watch.log")
POLL_SEC = 20
KIND_LABEL = {
    "connect": "接进来",
    "disconnect": "断开",
    "exec_request": "请求执行",
    "exec_ran": "执行了",
    "exec_denied": "没放行",
    "exec_blocked": "被只读限制挡住",
}


def log(msg):
    line = "%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if os.path.getsize(LOG) > 300_000:
            with open(LOG, encoding="utf-8") as f:
                tail = f.readlines()[-500:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(tail)
    except OSError:
        pass


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(d):
    try:
        os.makedirs(G6, exist_ok=True)
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)
    except OSError:
        pass


def say(text, kind="汇报"):
    """在咕嘎群里说一句（以六号自己的名义）。"""
    if NOSAY:
        log("（自检模式，没发群）%s" % text)
        return False
    body = json.dumps({"action": "post", "who": "咕嘎六号", "text": text,
                       "via": "本人", "kind": kind}).encode("utf-8")
    req = urllib.request.Request(GROUP_API, data=body, method="POST")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:  # noqa: BLE001
        log("贴群失败：%s" % e)
        return False


def append_journal(rec):
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    day = time.strftime("%Y-%m-%d", time.localtime(rec.get("ts") or time.time()))
    path = os.path.join(JOURNAL_DIR, day + ".md")
    new = not os.path.exists(path)
    line = describe(rec)
    try:
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write("# 咕嘎六号 · 接入日记 %s\n\n" % day)
            f.write("- %s  %s\n" % (time.strftime("%H:%M:%S", time.localtime(rec.get("ts") or time.time())), line))
    except OSError as e:
        log("写日记失败：%s" % e)


def describe(rec):
    """一条流水 → 一句人话。"""
    kind = rec.get("kind")
    name = rec.get("name") or rec.get("id") or "某台机器"
    os_ = rec.get("os") or "?"
    mode = "完整协助" if rec.get("mode") == "full" else "只读协助"
    if kind == "connect":
        return "%s 接进来了（%s · %s · 走%s · 端口 %s）" % (
            name, os_, mode, rec.get("how") or "?", rec.get("port"))
    if kind == "disconnect":
        m, s = divmod(int(rec.get("lasted_s") or 0), 60)
        return "%s 断开了（%s，待了 %d 分 %d 秒）" % (name, rec.get("why") or "结束", m, s)
    if kind == "exec_request":
        return "%s 请求执行：%s" % (name, (rec.get("cmd") or "").strip()[:120])
    if kind == "exec_ran":
        return "%s 上跑完了（退出码 %s，%sms）：%s" % (
            name, rec.get("exit_code"), rec.get("duration_ms"), (rec.get("cmd") or "").strip()[:120])
    if kind == "exec_denied":
        return "%s 那条命令没放行：%s" % (name, (rec.get("cmd") or "").strip()[:120])
    if kind == "exec_blocked":
        return "%s 那条命令被挡（%s）：%s" % (name, rec.get("why") or "", (rec.get("cmd") or "").strip()[:120])
    return json.dumps(rec, ensure_ascii=False)[:160]


def bump_machines(rec):
    """台账：每台机器来过几次、最近一次、什么权限。"""
    name = rec.get("name")
    if not name:
        return
    st = load_state()
    mm = st.setdefault("machines", {})
    cur = mm.setdefault(name, {"first": rec.get("ts"), "count": 0, "mode": rec.get("mode"),
                               "os": rec.get("os"), "how": rec.get("how")})
    if rec.get("kind") == "connect":
        cur["count"] = int(cur.get("count") or 0) + 1
        cur["how"] = rec.get("how") or cur.get("how")
        cur["mode"] = rec.get("mode") or cur.get("mode")
    cur["last"] = rec.get("ts")
    cur["last_kind"] = rec.get("kind")
    save_state(st)
    write_machines(mm)


def write_machines(mm):
    rows = ["# 咕嘎六号 · 机器台账", "",
            "> 谁接进来过、来过几次、最近一次是什么时候、给的什么权限。由 `guga6_watch.py` 自动维护。", ""]
    for name, v in sorted(mm.items(), key=lambda kv: -(kv[1].get("last") or 0)):
        rows.append("- **%s**：来过 %s 次 · 最近 %s · %s · %s · %s" % (
            name, v.get("count") or 0,
            time.strftime("%m-%d %H:%M", time.localtime(v.get("last") or 0)),
            "完整协助" if v.get("mode") == "full" else "只读协助",
            v.get("os") or "?", v.get("how") or "?"))
    try:
        os.makedirs(G6, exist_ok=True)
        with open(MACHINES, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
    except OSError:
        pass


def read_new(state):
    """从上次的位置往后读流水；文件被轮转/截断就从 0 重来。"""
    if not os.path.exists(AUDIT):
        return []
    try:
        size = os.path.getsize(AUDIT)
    except OSError:
        return []
    off = int(state.get("audit_offset") or 0)
    if off > size:
        off = 0
    out = []
    try:
        with open(AUDIT, encoding="utf-8") as f:
            f.seek(off)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
            state["audit_offset"] = f.tell()
    except OSError as e:
        log("读流水失败：%s" % e)
    return out


def handle(rec, state):
    line = describe(rec)
    append_journal(rec)
    try:
        os.makedirs(G6, exist_ok=True)
        with open(EVENTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    kind = rec.get("kind")
    if kind == "connect":
        bump_machines(rec)
        say("有人接进来了：%s —— %s，走的是%s。我记在册子上了。" % (
            rec.get("name"), "完整协助" if rec.get("mode") == "full" else "只读协助",
            rec.get("how") or "?"), kind="汇报")
    elif kind == "disconnect":
        bump_machines(rec)
        m, s = divmod(int(rec.get("lasted_s") or 0), 60)
        say("%s 断开了（%s，待了 %d 分 %d 秒）。" % (rec.get("name"), rec.get("why") or "结束", m, s),
            kind="汇报")
    elif kind in ("exec_ran",):
        bump_machines(rec)
        if rec.get("exit_code") not in (0, None):
            say("提醒一句：刚才在 %s 上那条命令没跑成（退出码 %s）：%s" % (
                rec.get("name"), rec.get("exit_code"), (rec.get("cmd") or "").strip()[:80]),
                kind="提醒")
    log(line)


def reconcile_guests(state):
    """兜底：万一流水丢了一行，用在线名单核对一下（现在有几台连着）。"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/api/join/guests", timeout=10) as r:
            guests = (json.loads(r.read().decode()) or {}).get("guests") or []
    except Exception:  # noqa: BLE001
        return
    now = {g.get("id"): g for g in guests}
    prev = state.get("online") or {}
    for gid, g in now.items():
        if gid not in prev:
            state.setdefault("online", {})[gid] = {"name": g.get("name"), "since": int(time.time())}
    for gid in list(prev):
        if gid not in now:
            state["online"].pop(gid, None)
    state["online_count"] = len(now)


def main():
    os.makedirs(G6, exist_ok=True)
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    state = load_state()
    once = "--once" in sys.argv
    log("咕嘎六号上岗：盯着 %s%s" % (AUDIT, "（跑一遍就退）" if once else ""))
    while True:
        try:
            for rec in read_new(state):
                handle(rec, state)
            if int(time.time()) % 60 < POLL_SEC:      # 一分钟核对一次在线名单就够
                reconcile_guests(state)
            save_state(state)
            if once:
                return 0
        except KeyboardInterrupt:
            return 0
        except Exception as e:  # noqa: BLE001
            log("出错：%s: %s" % (type(e).__name__, e))
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
