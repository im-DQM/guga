#!/usr/bin/env python3
"""agent_carry.py —— 「代发」的搬运工（主人的要求：话是他们自己说的，收发由我跑腿）。

规矩（2026-10-13 主人定）：
  · **记忆各归各家**：四号的记忆在它那台机器上（它自己的 Hermes 记忆 + 它自己的群会话），
    三号的记忆是它在 WorkBuddy 里的项目记录；我只搬运，既不改写、也不把它们的记忆抄到本机。
  · 群里那条一律标「代发」——主人一眼能分清是谁说的、谁带的。
  · 它们的口吻是它们自己的（四号就是那只猫腔），不替它们改。

能干什么：
  四号（自动通道，走 LightVela exec）：
    agent_carry.py --who 四号 --ask "主人的话"          # 它用它的记忆回答 → 贴群（代发）
    agent_carry.py --who 四号 --ask "…" --no-post       # 只把原话打给我看
    agent_carry.py --who 四号 --read                    # 只读它自己的记忆（看它记得什么）
    agent_carry.py --who 四号 --forget-session          # 丢掉本机记的"它的群会话 id"（下次重开一段）
  三号（手工通道，WorkBuddy 的活我在浏览器里跑）：
    agent_carry.py --who 三号 --brief "主人的话"        # 生成一段可直接贴进它项目的简报
    agent_carry.py --who 三号 --answer "它的回话"        # 把它的回话贴进群（代发）
    agent_carry.py --who 三号 --answer-file /tmp/x.txt
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
GROUP_API = "http://127.0.0.1:8792/group"
STATE = os.path.join(HOME, ".hermes", "state", "carry.json")
LV_EXEC = os.path.join(HOME, ".hermes", "lightvela", "lv_exec.py")
LV_HOME = "/home/agentuser/.hermes"
TAIL_N = 20


# ────────────────────────── 群 ──────────────────────────

def group(messages=None, body=None):
    d = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(GROUP_API, data=d, method="POST" if d else "GET")
    if d:
        req.add_header("content-type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def group_tail(n=TAIL_N):
    d = group()
    msgs = (d.get("messages") or [])[-n:]
    lines = []
    for m in msgs:
        via = "（代发）" if m.get("via") == "代发" else ""
        lines.append("【%s%s】%s" % (m["who"], via, (m.get("text") or "").replace("\n", " ")))
    return "\n".join(lines) or "（群里还没有消息）"


def full_name(who):
    """把「四号」「斥候」这类短名补成群名单里的正式名（接口只认正式名）。"""
    w = (who or "").strip()
    if w in ("一号", "二号", "三号", "四号", "五号", "六号"):
        return "咕嘎" + w
    if w in ("斥候", "咕嘎斥候"):
        return "咕嘎斥候"
    if w in ("主人", "owner"):
        return "主人"
    return w


def post(who, text, kind="回话"):
    d = group(body={"action": "post", "who": full_name(who), "text": text,
                    "via": "代发", "kind": kind})
    return d.get("ok"), d


# ────────────────────────── 本机状态 ──────────────────────────

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)
    except OSError:
        pass


# ────────────────────────── 四号：真跑它的实例 ──────────────────────────

def lv_shell(cmd, timeout=900):
    """在四号那台机器上跑一条命令，返回合并后的输出。"""
    out = subprocess.run([sys.executable, LV_EXEC, cmd],
                         capture_output=True, text=True, timeout=timeout)
    txt = (out.stdout or "") + (out.stderr or "")
    # lv_exec 的包装：exit_code: N 之后才是内容
    m = re.match(r"\s*exit_code:\s*(\d+)\s*", txt)
    code = int(m.group(1)) if m else None
    body = txt[m.end():] if m else txt
    return code, body.strip()


def four_prompt(question, with_context=True):
    head = [
        "你在「咕嘎群」里 —— 那是主人（孟庆达）和几个咕嘎一起的聊天群页面。",
        "你在群里的名字是「咕嘎四号」（你是 LightVela 那台轻量云上的 Hermes）。",
        "说话用你自己记得的事、你自己的口吻，不必改成别的腔调。",
        "这段话会被**原样**贴进群里（标着「代发」——收发由一号跑腿，话是你说的），",
        "所以只写要给他们看的内容：两三句，别写旁白、别写「（已发送）」这类提示。",
    ]
    if with_context:
        head += ["", "【群里最近的消息】", group_tail(), ""]
    else:
        head += [""]
    head += [
        "【现在请你回话】主人刚在群里说：%s" % question,
        "直接给要贴进群的那段话。",
    ]
    return "\n".join(head)


def _clean_cli(body):
    """掐掉 CLI 的界面噪声（续会话提示、空行），只留它说的话。"""
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("↻") or "Resumed session" in s or s.startswith("Session:") \
           or s.startswith("Resume this session") or s.startswith("Messages:") \
           or s.startswith("Title:") or s.startswith("Duration:"):
            continue
        out.append(s)
    return "\n".join(out).strip()


def ask_four(question, timeout=900, with_context=True):
    """跑四号一轮，返回 (它的原话, session_id, 备注)。"""
    st = load_state()
    rec = st.get("四号") or {}
    sid = rec.get("session")
    prompt = four_prompt(question, with_context)
    b64 = base64.b64encode(prompt.encode("utf-8")).decode()
    resume = ("--resume %s" % sid) if sid else ""
    cmd = (
        "export HERMES_HOME=%s; "
        "echo %s | base64 -d > /tmp/guga_group_q.txt; "
        "hermes -p default chat -Q --pass-session-id %s --query-file /tmp/guga_group_q.txt 2>&1 | tail -60"
        % (LV_HOME, b64, resume)
    )
    code, body = lv_shell(cmd, timeout=timeout)
    new_sid, text = None, ""
    for line in body.splitlines():
        m = re.match(r"\s*session_id:\s*(\S+)", line)
        if m:
            new_sid = m.group(1)
        else:
            text += line + "\n"
    text = _clean_cli(text)
    note = ""
    if not text:                                   # 会话可能没了 / 掉线，重开一段再来一次
        note = "resume 失败（或空输出），重开一段会话重试"
        code, body = lv_shell(cmd.replace(("--resume %s " % sid), ""), timeout=timeout)
        new_sid, text = None, ""
        for line in body.splitlines():
            m = re.match(r"\s*session_id:\s*(\S+)", line)
            if m:
                new_sid = m.group(1)
            else:
                text += line + "\n"
        text = _clean_cli(text)
    if new_sid:
        st.setdefault("四号", {})["session"] = new_sid
        st["四号"]["updated"] = int(time.time())
        save_state(st)
    return text, new_sid, note


def four_memory():
    code, body = lv_shell("cat %s/memories/MEMORY.md %s/memories/USER.md 2>/dev/null" % (LV_HOME, LV_HOME), timeout=180)
    return body


# ────────────────────────── 三号：手工通道 ──────────────────────────

def three_prompt(question):
    return "\n".join([
        "【咕嘎群转来的话 —— 请用你自己的口吻回两三句，直接给要贴进群的内容】",
        "（群里最近的消息）",
        group_tail(),
        "",
        "主人刚说：%s" % question,
        "只写要贴进群的那两三句话，别做别的任务、别输出标题或说明。",
    ])


def ask_three(question, timeout=900):
    """三号（WorkBuddy 网页版）自己回答：替它在它自己的会话里打字，再取它的原话。"""
    sys.path.insert(0, os.path.join(HOME, ".hermes", "scripts"))
    import workbuddy_ask as wa                       # 它负责浏览器那一套
    text, cid, st = wa.ask(three_prompt(question), timeout=timeout)
    if not text:
        raise RuntimeError("三号没回话（页面状态：%s）" % (st or {}))
    return text


def three_brief(question):
    return "\n".join([
        "【咕嘎群转来的活 · 来自主人】",
        group_tail(),
        "",
        "【主人这次要的】%s" % question,
        "",
        "（请照你一贯的做法把活做了；做完给我一段能贴回群里的回话：两三句说清你做了什么、成品在哪。）",
    ])


# ────────────────────────── 主 ──────────────────────────

def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--who", choices=["四号", "三号", "五号", "六号", "斥候", "一号"], default="四号")
    ap.add_argument("--ask", help="要转达给它的话（主人的原话最好）")
    ap.add_argument("--timeout", type=int, default=900, help="（三号）最多等它跑多久")
    ap.add_argument("--no-post", action="store_true", help="只把它的原话打出来，不贴群")
    ap.add_argument("--read", action="store_true", help="只读它自己的记忆")
    ap.add_argument("--forget-session", action="store_true", help="丢掉本机记的它的群会话 id")
    ap.add_argument("--brief", help="（三号）生成可贴进它项目的简报")
    ap.add_argument("--answer", help="（三号）把它的回话贴进群，标代发")
    ap.add_argument("--answer-file", help="（三号）从文件读它的回话")
    ap.add_argument("--kind", default="回话")
    a = ap.parse_args()

    if a.forget_session:
        st = load_state()
        st.pop(a.who, None)
        save_state(st)
        print("已丢掉「%s」在本机记的群会话 id" % a.who)
        return 0

    if a.brief:
        print(three_brief(a.brief))
        return 0

    answer = a.answer
    if a.answer_file:
        answer = open(a.answer_file, encoding="utf-8").read()
    if answer:
        ok, d = post(a.who, answer, kind=a.kind)
        print(("已贴回群 #%d：%s" % (d["message"]["id"], answer[:60])) if ok
              else "没贴进去：%s" % d)
        return 0 if ok else 1

    if a.read:
        if a.who == "四号":
            print(four_memory())
        else:
            print("「%s」的记忆不在本机（各归各家）—— 四号可以直接读，三号要去它的项目里看。" % a.who)
        return 0

    if not a.ask:
        ap.print_help()
        return 2

    if a.who == "三号":
        # 三号：替它在 WorkBuddy 它自己的会话里打字，取它的原话（要吃平台额度）
        print("→ 去三号那边（WorkBuddy 网页，它的会话）跑一轮…", file=sys.stderr)
        try:
            text = ask_three(a.ask, timeout=a.timeout)
        except Exception as e:  # noqa: BLE001
            print("三号那条路没通：%s" % e, file=sys.stderr)
            return 1
        print("----- 咕嘎三号的原话 -----")
        print(text)
        print("--------------------------")
        if not a.no_post:
            ok, d = post("咕嘎三号", text, kind=a.kind)
            print(("已贴进群 #%d（标着代发）" % d["message"]["id"]) if ok
                  else "贴群失败：%s" % d, file=sys.stderr)
            return 0 if ok else 1
        return 0

    if a.who != "四号":
        print("「%s」没有自动通道：请用 --brief 生成简报去转交，再用 --answer \"它的回话\" 贴回群。" % a.who)
        return 2

    print("→ 去四号那边跑一轮（它自己的记忆、它自己的会话）…", file=sys.stderr)
    text, sid, note = ask_four(a.ask)
    if note:
        print("（%s）" % note, file=sys.stderr)
    if not text:
        print("四号没回话（可能凭证过期或那边出错）。", file=sys.stderr)
        return 1
    print("----- 咕嘎四号的原话 -----")
    print(text)
    print("--------------------------")
    if not a.no_post:
        ok, d = post("咕嘎四号", text, kind=a.kind)
        if ok:
            print("已贴进群 #%d（标着代发）" % d["message"]["id"], file=sys.stderr)
        else:
            print("贴群失败：%s" % d, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
