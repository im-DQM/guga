#!/usr/bin/env python3
"""把一号的早报/晚报正文推给咕嘎四号（LightVela），由四号原样发飞书。

- 正文来源：`~/.hermes/cron/output/<job_id>/<今天>_*.md` 的「## Response」段
  （morning = morning-todo-brief，evening = evening-todo-review）
- 只滤掉网页专用指令（整行 `::xxx`）和末尾那个 `•` 蓝点；其余一字不改
- 推到四号 `/home/agentuser/.hermes/brief/<日期>-<morning|evening>.txt`（base64 过桥，免转义）
- 同一天同一条只推一次（按内容哈希判断，状态存 ~/.hermes/state/brief_to_lv.json）
- 没生成就静默退出 —— 定时任务每 5 分钟重试，等 Run 落盘即推
用法： python3 brief_to_lv.py [morning|evening]   # 省略则按当前钟点判断
"""
import base64
import hashlib
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))
JOBS = {"morning": "8a16d1435b90", "evening": "1222f2e58b9b"}
OUT = pathlib.Path("/home/ubuntu/.hermes/cron/output")
STATE = pathlib.Path("/home/ubuntu/.hermes/state/brief_to_lv.json")
LV_EXEC = "/home/ubuntu/.hermes/lightvela/lv_exec.py"
REMOTE = "/home/agentuser/.hermes/brief"
KEEP_DAYS = 7


def clean(body: str) -> str:
    lines = [ln for ln in body.strip().splitlines() if not ln.strip().startswith("::")]
    while lines and (not lines[-1].strip() or lines[-1].strip() in ("•", "·")):
        lines.pop()
    out = []
    for ln in lines:
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln.rstrip())
    return ("\n".join(out).strip() + "\n") if out else ""


def response_text(which: str):
    job = JOBS[which]
    today = datetime.now(CST).strftime("%Y-%m-%d")
    files = sorted(OUT.glob(f"{job}/{today}_*.md"))
    if not files:
        return None
    raw = files[-1].read_text(encoding="utf-8")
    if "## Response" not in raw:
        return None
    text = clean(raw.split("## Response", 1)[1])
    return text if len(text) > 30 else None


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def push(which: str, text: str) -> str:
    today = datetime.now(CST).strftime("%Y-%m-%d")
    remote = f"{REMOTE}/{today}-{which}.txt"
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    cmd = (
        f"mkdir -p {REMOTE} && printf '%s' '{b64}' | base64 -d > {remote}.part && "
        f"mv {remote}.part {remote} && wc -c < {remote} && "
        f"find {REMOTE} -type f -name '*.txt' -mtime +{KEEP_DAYS} -delete"
    )
    r = subprocess.run(["python3", LV_EXEC, cmd], capture_output=True, text=True, timeout=180)
    return (r.stdout or "").strip() + ((" | " + r.stderr.strip()) if r.stderr.strip() else "")


def main() -> int:
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    which = arg if arg in JOBS else ("morning" if datetime.now(CST).hour < 12 else "evening")
    text = response_text(which)
    if not text:
        return 0                                   # 今天还没生成 → 静默等下一轮
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    today = datetime.now(CST).strftime("%Y-%m-%d")
    state = load_state()
    if (state.get(today) or {}).get(which) == digest:
        return 0                                   # 已推过、内容没变
    out = push(which, text)
    if "exit_code: 0" not in out:
        print(f"brief_to_lv：推给四号失败（{which} {today}）\n{out[:800]}")
        return 1
    state.setdefault(today, {})[which] = digest
    for day in sorted(state)[:-14]:                # 只留最近两周状态
        state.pop(day, None)
    save_state(state)
    return 0                                       # 成功不吭声


if __name__ == "__main__":
    sys.exit(main())
