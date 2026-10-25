#!/usr/bin/env python3
"""盯 hub「编码」页那个 claude 会话，收工后经咕嘎四号发飞书（一次性）。

由 cron no-agent 作业每分钟跑一次；未收工 → 无输出（静默）。
触发条件（保守，避免打断中间过程就报喜）：
  · 任务清单里没有 ◼ / ◻ 未完成标记，且至少有一个 ✔
  · 面板里没有 "esc to interrupt"（不在跑）
  · 输入框 ❯ 在，且整块面板与上一次逐字节一致（连续两分钟没动）
"""
import base64, hashlib, os, pathlib, re, subprocess, sys

HOME = pathlib.Path.home()
SESSION = os.environ.get("WATCH_SESSION", "claude")
STATE = HOME / ".hermes/state/claude-notify"
STATE.mkdir(parents=True, exist_ok=True)
FLAG = STATE / ("fired-" + SESSION)
HASHF = STATE / ("hash-" + SESSION)
MISSF = STATE / ("miss-" + SESSION)

sys.path.insert(0, str(HOME / ".hermes/lightvela"))


def send(msg):
    import lv_exec
    b64 = base64.b64encode(msg.encode()).decode()
    cmd = ("echo %s | base64 -d > /tmp/g1msg.txt && "
           "hermes send --to feishu --file /tmp/g1msg.txt" % b64)
    try:
        r = lv_exec.run(cmd)
        d = r.get("data", r)
        return (d.get("exit_code") == 0), str(d.get("stdout") or "")[:200]
    except Exception as e:  # 四号登录可能失效
        return False, "四号通道失败: %s" % e


if FLAG.exists():
    sys.exit(0)

p = subprocess.run(["tmux", "capture-pane", "-p", "-t", SESSION, "-S", "-80"],
                   capture_output=True, text=True)
if p.returncode != 0:
    n = int(MISSF.read_text() or "0") if MISSF.exists() else 0
    n += 1
    MISSF.write_text(str(n))
    if n >= 3:
        send("⚠️ 编码页那个会话（tmux %s）已经不在了，活可能被中断。" % SESSION)
        FLAG.write_text("session-gone")
        print("会话已消失，已通知")
    sys.exit(0)
MISSF.write_text("0")

pane = p.stdout
h = hashlib.md5(pane.encode()).hexdigest()
prev = HASHF.read_text().strip() if HASHF.exists() else ""
HASHF.write_text(h)

busy = ("\u25fc" in pane) or ("\u25fb" in pane) or ("esc to interrupt" in pane)
if busy or ("\u2714" not in pane) or ("\u276f" not in pane) or h != prev:
    sys.exit(0)

lines = [l.strip() for l in pane.splitlines()
         if re.match(r"^\s*[\u2714\u25fc\u25fb]\s*\S", l)]
body = "\n".join(lines[-6:])
msg = "\u2705 编码页那摊活收工了。\n" + (body + "\n" if body else "") + "—— 咕嘎一号"
ok, info = send(msg)
FLAG.write_text("done" if ok else "done-send-failed")
print(msg if ok else (msg + "\n[发送失败] " + info))
