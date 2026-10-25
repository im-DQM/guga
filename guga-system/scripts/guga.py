#!/usr/bin/env python3
"""咕嘎调度的小工具：把某个咕嘎的身份料拼出来，或者替它回写记忆与日记。

用法：
  guga.py list                 谁是谁（编号 / 名字 / 工作流有没有）
  guga.py brief 8              SOUL + MEMORY + WORKFLOW 全文（给子 agent 当上下文）
  guga.py log 8 "这次干了什么"   追加到 guga8/journal/<今天>.md
  guga.py remember 8 "要长期记住的事实"  追加到 guga8/MEMORY.md（带日期）
  guga.py workflow 8 "一句话经验"        追加到 guga8/WORKFLOW.md 的「经验」段

主人 2026-10-25 定的规矩：聊天里 /N 前缀派活给咕嘎N，一号负责调用与回写。
"""
import sys
import os
import datetime

BASE = os.path.expanduser("~/.hermes/guga")
NAMES = {
    0: "编码咕嘎（主力，跑在 ~/workspace）",
    1: "管家（服务器本体，日常辅助）",
    2: "飞书（已停用）",
    3: "WorkBuddy（文件级成品）",
    4: "LightVela（推飞书 / 建站）",
    5: "ASUS 笔记本（win-asus）",
    6: "接入记录官（谁接进来、干了什么）",
    7: "斥候（热点侦察、找料）",
    8: "保安（巡检与维护）",
}


def home(n):
    return os.path.join(BASE, "guga%d" % n)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def append(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def cmd_list():
    for n in sorted(NAMES):
        h = home(n)
        flow = "有" if os.path.exists(os.path.join(h, "WORKFLOW.md")) else "无"
        mem = len(read(os.path.join(h, "MEMORY.md")))
        print("%d  %-32s 工作流:%s 记忆:%dB" % (n, NAMES[n], flow, mem))


def cmd_brief(n):
    h = home(n)
    parts = [
        ("SOUL.md", "我是谁 / 边界"),
        ("MEMORY.md", "我的记忆（跨天要记的事实）"),
        ("WORKFLOW.md", "我的工作流（接活→干活→交付→收尾自评）"),
    ]
    print("【身份：咕嘎%d号 · %s】\n" % (n, NAMES[n]))
    for fn, label in parts:
        body = read(os.path.join(h, fn))
        print("===== %s（%s）=====" % (fn, label))
        print(body if body else "（无）")
        print()
    print("===== 收尾要求 =====")
    print("干完用 `python3 ~/.hermes/scripts/guga.py log %d \"<干了什么、结果>\"` 记账；" % n)
    print("发现要长期记住的事实用 `guga.py remember %d \"...\"`；" % n)
    print("发现可复用的改进（这次卡在哪、下次怎么做）用 `guga.py workflow %d \"...\"`。" % n)


def cmd_log(n, text):
    path = os.path.join(home(n), "journal", datetime.date.today().isoformat() + ".md")
    stamp = datetime.datetime.now().strftime("%H:%M")
    append(path, "- `%s` %s\n" % (stamp, text))


def cmd_remember(n, text):
    path = os.path.join(home(n), "MEMORY.md")
    append(path, "- [%s] %s\n" % (datetime.date.today().isoformat(), text))


def cmd_workflow(n, text):
    path = os.path.join(home(n), "WORKFLOW.md")
    body = read(path)
    if "## 经验（自己边干边长出来的）" not in body:
        append(path, "\n## 经验（自己边干边长出来的）\n\n")
    append(path, "- [%s] %s\n" % (datetime.date.today().isoformat(), text))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list()
        return 0
    if len(sys.argv) < 3:
        print("缺编号。用法见 %s" % sys.argv[0])
        return 2
    try:
        n = int(sys.argv[2])
    except ValueError:
        print("编号要数字 0-8")
        return 2
    if n not in NAMES:
        print("没有咕嘎%d号" % n)
        return 2
    if cmd == "brief":
        cmd_brief(n)
        return 0
    if len(sys.argv) < 4:
        print("缺内容")
        return 2
    text = " ".join(sys.argv[3:])
    if cmd == "log":
        cmd_log(n, text)
    elif cmd == "remember":
        cmd_remember(n, text)
    elif cmd == "workflow":
        cmd_workflow(n, text)
    else:
        print("不认识的子命令：%s" % cmd)
        return 2
    print("已写入咕嘎%d号" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
