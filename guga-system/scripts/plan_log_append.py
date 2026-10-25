#!/usr/bin/env python3
"""plan_log_append.py —— 把当天的计划/结果写进长期记录 ~/.hermes/knowledge/plan-log.md。

用法：
  plan_log_append.py --phase evening [--note "今天的一句话记录"]

- morning 那一半由 today-plan-card.py 负责（写「### 计划」）。
- evening 由晚报那一班调用：写「### 结果」+「备注」（备注里放主人今天新冒出的想法/人生需求/身体与情绪/求职进展）。
- 同一天同一 phase 只写一次（cron 重跑不会重复）。
"""
import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

API = "http://127.0.0.1:8790/api/todos"
LOG = Path("/home/ubuntu/.hermes/knowledge/plan-log.md")
WK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def fetch(key: str):
    with urllib.request.urlopen(f"{API}?date={key}", timeout=10) as r:
        return json.load(r)


def clean(t: str) -> str:
    s = str(t or "")
    for marker in ("⏰", "📅"):
        if marker in s:
            s = s.split(marker)[0]
    return s.split("@")[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["morning", "evening"], default="evening")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    day = date.today()
    try:
        today = fetch("today")
        items = today.get("items", [])
        done = [clean(i.get("text", "")) for i in items if i.get("done")]
        open_ = [clean(i.get("text", "")) for i in items if not i.get("done")]
    except Exception as e:
        print(f"（长期记录跳过：读不到计划数据 {e}）")
        return 0

    LOG.parent.mkdir(parents=True, exist_ok=True)
    text = LOG.read_text(encoding="utf-8") if LOG.exists() else "# 计划与人生记录（长期）\n\n> 每天早报写「计划」，晚报写「结果」；周六复盘读它做趋势。由咕嘎自动追加，人工不动。\n"
    head = f"## {day.isoformat()}（{WK[day.weekday()]}）"
    if head not in text:
        text = text.rstrip("\n") + f"\n\n{head}\n"

    if a.phase == "evening":
        if "### 结果" in text.split(head)[-1]:
            print("今天的记录已经写过了，跳过。")
            return 0
        block = [f"### 结果（{len(done)}/{len(items)}）"]
        block.append(f"- 已完成：{'、'.join(done) if done else '无'}")
        block.append(f"- 未完成：{'、'.join(open_) if open_ else '无'}")
        note = (a.note or "").strip() or "无特别记录"
        block.append(f"- 备注：{note}")
        text = text.rstrip("\n") + "\n" + "\n".join(block) + "\n"
        LOG.write_text(text, encoding="utf-8")
        print("已写入长期记录（结果）：" + LOG.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
