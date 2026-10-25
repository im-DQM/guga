#!/usr/bin/env python3
"""主人的个人模型：条目库（唯一真源）+ 自动生成的画像。

用法：
  profile.py add --cat 性格 --fact "……" [--evidence "原话"] [--conf 确认|推测]
  profile.py list [--cat 性格] [--conf 推测]
  profile.py grep 关键词
  profile.py render          # 重新生成 ~/.hermes/knowledge/主人画像.md
  profile.py stale [--days 90]
  profile.py cats
"""
import argparse, json, os, sys, datetime

BASE = os.path.expanduser("~/.hermes/knowledge/profile")
ENTRIES = os.path.join(BASE, "entries.jsonl")
RULES = os.path.join(BASE, "service-rules.md")
OUT = os.path.expanduser("~/.hermes/knowledge/主人画像.md")

CATS = ["目标", "动机", "性格", "偏好", "雷区", "习惯", "学习", "健康", "兴趣", "观念", "关系"]
CONFS = ["确认", "推测"]


def load():
    if not os.path.exists(ENTRIES):
        return []
    out = []
    with open(ENTRIES, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def save_all(entries):
    tmp = ENTRIES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, ENTRIES)


def today():
    return datetime.date.today().isoformat()


def next_id(entries):
    nums = [int(e["id"][1:]) for e in entries if e["id"][1:].isdigit()]
    return "P%03d" % ((max(nums) + 1) if nums else 1)


def cmd_add(a):
    if a.cat not in CATS:
        sys.exit("未知类别 %s；可选：%s" % (a.cat, "、".join(CATS)))
    if a.conf not in CONFS:
        sys.exit("conf 只能是 确认 / 推测")
    entries = load()
    for e in entries:  # 去重：同类别同事实不重复记
        if e["fact"].strip() == a.fact.strip():
            print("已存在 %s，未重复写入" % e["id"])
            return
    e = {"id": next_id(entries), "date": a.date or today(), "cat": a.cat,
         "fact": a.fact.strip(), "evidence": (a.evidence or "").strip(), "conf": a.conf}
    entries.append(e)
    save_all(entries)
    print("已记 %s [%s] %s" % (e["id"], e["cat"], e["fact"]))
    cmd_render(argparse.Namespace(dry=False))


def cmd_list(a):
    entries = load()
    rows = [e for e in entries
            if (not a.cat or e["cat"] == a.cat) and (not a.conf or e["conf"] == a.conf)]
    for e in sorted(rows, key=lambda x: (CATS.index(x["cat"]) if x["cat"] in CATS else 99, x["id"])):
        mark = "" if e["conf"] == "确认" else "（推测）"
        print("%s %s [%s]%s %s" % (e["id"], e["date"], e["cat"], mark, e["fact"]))
    print("—— %d 条" % len(rows), file=sys.stderr)


def cmd_grep(a):
    kw = a.keyword.lower()
    hits = [e for e in load() if kw in (e["fact"] + e["evidence"] + e["cat"]).lower()]
    for e in hits:
        print("%s [%s] %s" % (e["id"], e["cat"], e["fact"]))
    if not hits:
        print("没有相关条目")


def cmd_cats(a):
    counts = {}
    for e in load():
        counts[e["cat"]] = counts.get(e["cat"], 0) + 1
    for c in CATS:
        if c in counts:
            print("%s：%d" % (c, counts[c]))
    print("合计 %d 条" % sum(counts.values()))


def cmd_stale(a):
    cut = (datetime.date.today() - datetime.timedelta(days=a.days)).isoformat()
    rows = [e for e in load() if e["date"] < cut]
    for e in rows:
        print("%s %s [%s] %s" % (e["id"], e["date"], e["cat"], e["fact"]))
    print("—— %d 条超过 %d 天没复核" % (len(rows), a.days), file=sys.stderr)


def cmd_render(a):
    entries = load()
    lines = ["# 主人画像（孟庆达）", "",
             "> 本文件由 `profile.py render` 生成，**别手改**。要改：`profile.py add --cat … --fact …`，",
             "> 条目真源在 `knowledge/profile/entries.jsonl`；服务规矩在同目录 `service-rules.md`。",
             "> 共 %d 条，最后更新 %s。" % (len(entries), today()), ""]
    for c in CATS:
        rows = [e for e in entries if e["cat"] == c]
        if not rows:
            continue
        lines += ["## %s" % c, ""]
        for e in sorted(rows, key=lambda x: (x["conf"] != "确认", x["id"])):
            tail = "" if e["conf"] == "确认" else "（推测）"
            ev = ("　← %s" % e["evidence"]) if e["evidence"] else ""
            lines.append("- %s%s%s" % (e["fact"], tail, ev))
        lines.append("")
    if os.path.exists(RULES):
        with open(RULES, encoding="utf-8") as f:
            lines += ["---", "", f.read().strip(), ""]
    text = "\n".join(lines).rstrip() + "\n"
    if getattr(a, "dry", False):
        sys.stdout.write(text)
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("已生成 %s（%d 条）" % (OUT, len(entries)))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("--cat", required=True); s.add_argument("--fact", required=True)
    s.add_argument("--evidence"); s.add_argument("--conf", default="确认"); s.add_argument("--date")
    s.set_defaults(func=cmd_add)
    s = sub.add_parser("list"); s.add_argument("--cat"); s.add_argument("--conf"); s.set_defaults(func=cmd_list)
    s = sub.add_parser("grep"); s.add_argument("keyword"); s.set_defaults(func=cmd_grep)
    s = sub.add_parser("render"); s.set_defaults(func=cmd_render)
    s = sub.add_parser("stale"); s.add_argument("--days", type=int, default=90); s.set_defaults(func=cmd_stale)
    s = sub.add_parser("cats"); s.set_defaults(func=cmd_cats)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
