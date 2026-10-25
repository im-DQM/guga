#!/usr/bin/env python3
"""workbuddy_ask.py —— 让「咕嘎三号」（WorkBuddy 网页版）自己回答一句话。

它是别人家的 SaaS，没有 API，只有网页。所以这里的做法是：
用它的常驻浏览器（`~/.hermes/workbuddy/chrome-profile`，端口 9333，wb.py 那套）**替它打字**，
让它自己的会话里跑完，再把它的原话取回来。它那段会话就是它在群里的记忆（记录留在它那边）。

用法：
  workbuddy_ask.py --ask "主人的话"            # 提交并等它跑完，打印它的原话
  workbuddy_ask.py --ask "…" --timeout 900     # 等更久
  workbuddy_ask.py --new                       # 丢掉本机记的会话 id（下次开一段新的）
  workbuddy_ask.py --whoami                    # 看它现在停在哪个页面 / 登录态还在不在

注意：**每问一次都要吃掉它平台的一次智能体调用额度**（免费版每月 30 次）。主人 2026-10-13 知情。
"""
import argparse
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
WB_DIR = os.path.join(HOME, ".hermes", "workbuddy")
STATE = os.path.join(HOME, ".hermes", "state", "carry.json")
APP = "https://www.workbuddy.cn/app"
POLL_SEC = 12
MAX_WAIT = 900

sys.path.insert(0, WB_DIR)
import wb  # noqa: E402  （它负责起/接常驻浏览器）


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


def conversation():
    return (load_state().get("三号") or {}).get("conversation")


def set_conversation(cid):
    st = load_state()
    st.setdefault("三号", {})["conversation"] = cid
    st["三号"]["updated"] = int(time.time())
    save_state(st)


def hx(code):
    """跑一段 browser-harness 代码，返回它的 stdout。"""
    rc, out, err = wb.run(code, timeout=300)
    if rc != 0 and not out.strip():
        raise RuntimeError("harness 失败 rc=%s %s" % (rc, (err or "").strip()[:300]))
    return out.strip()


STATUS_JS = """JSON.stringify((()=>{
  const a=document.querySelectorAll('.cr-agent');
  const login=/\\/login/.test(location.pathname);
  if(!a.length) return {login:login, n:0, url:location.href.slice(0,80)};
  const last=a[a.length-1];
  const s=last.querySelector('.cr-agent__completion-status');
  return {login:login, n:a.length, url:location.href.slice(0,80),
          status: s ? (s.innerText||'').trim() : '',
          len: ((last.innerText||'').length)};
})())"""

TEXT_JS = """JSON.stringify((()=>{
  const a=document.querySelectorAll('.cr-agent');
  if(!a.length) return {text:''};
  const last=a[a.length-1].cloneNode(true);
  const rm=last.querySelectorAll('.cr-agent__completion-status, .cr-agent__foot, .cr-agent__tools');
  rm.forEach(e=>e.remove());
  return {text:(last.innerText||'')};
})())"""


def clean(text):
    """掐掉网页上的标签与时间戳，只留它说的话。"""
    t = (text or "").strip()
    t = re.sub(r"^WorkBuddy\s*", "", t)                       # 页面标签常和正文粘在一起
    t = re.sub(r"(?m)^\s*(WorkBuddy|快速|深度|复制|分享|产物|概览|引用来源)\s*$", "", t)
    t = re.sub(r"\s*(快速|深度)\s*\d{1,2}:\d{2}\s*$", "", t)   # 结尾的「快速 11:40」
    t = re.sub(r"(?m)^\s*(已完成|思考中|生成中|执行中)(\s*\d+s)?\s*$", "", t)
    t = re.sub(r"(?m)^\s*\d{1,2}:\d{2}\s*$", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def ask(question, timeout=MAX_WAIT, new=False):
    cid = None if new else conversation()
    prompt = question
    code = """
import json, time
ensure_real_tab()
goto_url(%s)
wait_for_load()
time.sleep(4)
el = js("(()=>{const e=document.querySelector('div[contenteditable=true]'); if(!e) return 'no-input'; e.focus(); return 'ok';})()")
print('focus:', el)
if el != 'ok':
    print(json.dumps({'err': 'no-input'}))
else:
    cdp('Input.insertText', text=%s)
    time.sleep(1.2)
    js("(()=>{const e=document.querySelector('div[contenteditable=true]'); e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true})); return 'sent';})()")
    time.sleep(8)
    print(json.dumps({'url': js('location.href')}))
""" % (json.dumps(APP if not cid else APP + "/conversation/" + cid), json.dumps(prompt))
    out = hx(code)
    if "no-input" in out:
        raise RuntimeError("进不去它的输入框（可能登录态掉了）：%s" % out[:200])

    m = re.search(r"\{.*\}", out, re.S)
    url = ""
    if m:
        try:
            url = json.loads(m.group(0)).get("url") or ""
        except Exception:  # noqa: BLE001
            pass
    cid_new = url.split("/conversation/")[-1].split("?")[0] if "/conversation/" in url else None
    if cid_new and cid_new != cid:
        set_conversation(cid_new)
        cid = cid_new

    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        time.sleep(POLL_SEC)
        try:
            st = _read_js(STATUS_JS)
        except Exception as e:  # noqa: BLE001
            print("（读状态失败，继续等：%s）" % e, file=sys.stderr)
            continue
        last = st
        if st.get("login"):
            raise RuntimeError("WorkBuddy 登录态掉了（页面回到 /login），要主人重扫一次")
        if st.get("status", "").startswith("已完成") and st.get("len", 0) > 0:
            break
        if st.get("status", "") and ("失败" in st["status"] or "停止" in st["status"]):
            break

    try:
        text = _read_js(TEXT_JS).get("text", "")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("抽不出它的回话：%s" % e)
    return clean(text), cid, last


def _read_js(js_expr):
    """跑一句 JS 并把它的结果解析成 Python 对象。

    注意：必须写成 print(js("…")) —— 直接把 JS 源码 json.dumps 进去只会打印那句话本身，
    解析不出来（踩过一次：状态永远读不到，白等到超时）。
    """
    out = hx('print(js(%s))' % json.dumps(js_expr))
    txt = out.strip().splitlines()[-1] if out.strip() else ""
    try:
        return json.loads(txt)
    except Exception:  # noqa: BLE001
        return json.loads(json.loads(txt))          # 万一被多包了一层引号


def whoami():
    out = hx("""
import json
ensure_real_tab()
print(json.dumps({'url': js('location.href'), 'title': js('document.title'),
                  'agents': js("document.querySelectorAll('.cr-agent').length")}))
""")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask")
    ap.add_argument("--timeout", type=int, default=MAX_WAIT)
    ap.add_argument("--new", action="store_true")
    ap.add_argument("--whoami", action="store_true")
    a = ap.parse_args()

    if a.whoami:
        print(whoami())
        print("本机记的会话 id：%s" % (conversation() or "（还没有）"))
        return 0
    if a.new and not a.ask:
        st = load_state()
        st.pop("三号", None)
        save_state(st)
        print("已丢掉三号在本机记的会话 id")
        return 0
    if not a.ask:
        ap.print_help()
        return 2

    text, cid, st = ask(a.ask, timeout=a.timeout, new=a.new)
    print("会话：%s  状态：%s" % (cid, st.get("status", "")))
    print("----- 咕嘎三号的原话 -----")
    print(text or "（没拿到内容）")
    print("--------------------------")
    return 0 if text else 1


if __name__ == "__main__":
    sys.exit(main())
