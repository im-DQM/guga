#!/usr/bin/env python3
"""深夜 swap / 内存巡检（cron `40 3 * * *`，主人要求在大晚上跑）：先清会话、再记账，只在值得打扰主人时出声。

1. 先跑 `browser-daemon-reaper.py --max-sessions N --quiet`：浏览器会话数超过 N（默认 10）
   就从最旧的开始收掉超出的部分（幂等，没超标就什么都不做）。
2. 把现量追加进台账 ~/.hermes/state/swap-watch.jsonl（供「现量现比」）。
3. 写状态文件 ~/.hermes/state/swap-status.json（晚报等可读）。
4. 出声条件：swap 占用 >= 70%（含最大占用者），或第 1 步真清了会话；否则完全静默。
用法：swap-patrol.py
"""
import datetime
import json
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
LEDGER = os.path.join(HOME, ".hermes", "guga", "guga8", "state", "swap-watch.jsonl")
STATUS = os.path.join(HOME, ".hermes", "guga", "guga8", "state", "swap-status.json")
LOG = os.path.join(HOME, ".hermes", "guga", "guga8", "state", "swap-patrol.log")
REAPER = os.path.join(HOME, ".hermes", "guga", "guga8", "scripts", "browser-daemon-reaper.py")
MAX_SESSIONS = int(os.environ.get("SWAP_PATROL_MAX_SESSIONS", "10"))


def reap_sessions(limit):
    """会话数超过 limit 就收掉超出的（最旧的先）。返回脚本的话术（无动作时为空）。"""
    try:
        done = subprocess.run([sys.executable or "/usr/bin/python3", REAPER,
                               "--max-sessions", str(limit), "--quiet"],
                              capture_output=True, text=True, timeout=180)
        return (done.stdout or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return "会话清理没跑起来：%s" % exc


def meminfo():
    vals = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            k, _, v = line.partition(":")
            try:
                vals[k] = int(v.split()[0])
            except (ValueError, IndexError):
                pass
    return vals


def swap_by_name(top=4):
    totals = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/status" % entry) as fh:
                name = None
                swap = 0
                for line in fh:
                    if line.startswith("Name:"):
                        name = line.split(None, 1)[1].strip()
                    elif line.startswith("VmSwap:"):
                        swap = int(line.split()[1])
                if name and swap > 0:
                    totals[name] = totals.get(name, 0) + swap
        except (OSError, ValueError, IndexError):
            continue
    return sorted(totals.items(), key=lambda kv: -kv[1])[:top]


def main():
    cleanup = reap_sessions(MAX_SESSIONS)
    m = meminfo()
    total_mb = m.get("SwapTotal", 0) / 1024.0
    free_mb = m.get("SwapFree", 0) / 1024.0
    used_mb = total_mb - free_mb
    pct = (used_mb / total_mb * 100) if total_mb else 0.0
    avail_mb = m.get("MemAvailable", 0) / 1024.0
    culprits = swap_by_name()
    now = datetime.datetime.now().astimezone()

    row = {
        "ts": now.isoformat(timespec="seconds"),
        "note": "每日巡检",
        "swap_total_mb": round(total_mb),
        "swap_used_mb": round(used_mb),
        "swap_free_pct": round(100 - pct, 1),
        "mem_total_mb": round(m.get("MemTotal", 0) / 1024.0),
        "mem_avail_mb": round(avail_mb),
        "top_swap_mb": {k: round(v / 1024.0) for k, v in culprits},
    }
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    level = "crit" if pct >= 85 else ("warn" if pct >= 70 else "ok")
    status = dict(row)
    status["level"] = level
    with open(STATUS, "w") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=1)

    try:
        with open(LOG, "a") as fh:
            fh.write("%s %s swap %.0f/%.0fMB (%.0f%%) avail %.0fMB top=%s%s\n"
                     % (row["ts"], level, used_mb, total_mb, pct, avail_mb,
                        ", ".join("%s %dMB" % (k, v / 1024.0) for k, v in culprits),
                        (" | 清理：" + cleanup.replace("\n", " ; ")) if cleanup else ""))
    except OSError:
        pass

    if level == "ok":
        if cleanup:  # 没到阈值，但今晚真清了会话——说一句就好
            print(cleanup)
        return  # 其余情况静默
    top = "、".join("%s %dMB" % (k, v / 1024.0) for k, v in culprits)
    if level == "crit":
        head = "主人，swap 已用到 %.0f%%（%.0f/%.0fMB，可用内存 %.0fMB），快见底了。" % (pct, used_mb, total_mb, avail_mb)
        tail = "建议清一轮残留进程或扩容，我可以直接动手。"
    else:
        head = "主人，swap 用到 %.0f%%（%.0f/%.0fMB，可用内存 %.0fMB），还宽裕但该留意。" % (pct, used_mb, total_mb, avail_mb)
        tail = "真到 85% 我再提醒你清。"
    line = head + "\n占得最多的是：" + (top or "—") + "。" + tail
    if cleanup:
        line += "\n" + cleanup
    print(line)


if __name__ == "__main__":
    main()
