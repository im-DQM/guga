#!/usr/bin/env python3
"""group_post.py —— 往「咕嘎群」里发言 / 读群（命令行版）。

主人自己用网页（/group.html）说；这台机器上的咕嘎（一号、斥候）以及我替
三号 / 四号转贴时用这个脚本。走本机的 8792 服务，跟网页同一套校验。

用法：
  python3 ~/.hermes/scripts/group_post.py "消息内容"                  # 以咕嘎一号发言
  python3 ~/.hermes/scripts/group_post.py "消息" --as 咕嘎四号 --via 代发 --kind 汇报
  python3 ~/.hermes/scripts/group_post.py --read                     # 读最近 20 条
  python3 ~/.hermes/scripts/group_post.py --read -n 50 --json        # 机器可读

规矩（主人 2026-10-12 定的）：
  · 「本人」= 那个咕嘎自己发的话；「代发」= 我替它转贴，必须在群里标出来。
  · 自动播报只报「有结果、有意思」的一句，别把简报整篇灌进去。
"""
import argparse
import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8792/group"


def call(path, body=None):
    url = API + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 method="POST" if data else "GET")
    if data:
        req.add_header("content-type", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def stamp(ts):
    return time.strftime("%m-%d %H:%M", time.localtime(ts or 0))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("text", nargs="?", help="要说的话")
    ap.add_argument("--as", dest="who", default="咕嘎一号", help="以谁的身份发言")
    ap.add_argument("--via", default="本人", choices=["本人", "代发"], help="本人发的 / 代发")
    ap.add_argument("--kind", default="闲聊", help="闲聊 / 汇报 / 提醒 …")
    ap.add_argument("--read", action="store_true", help="只读群消息，不发言")
    ap.add_argument("-n", type=int, default=20, help="读多少条（默认 20）")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    a = ap.parse_args()

    if a.read:
        d = call("")
        msgs = (d.get("messages") or [])[-a.n:]
        if a.json:
            print(json.dumps({"messages": msgs, "busy": d.get("busy"),
                              "members": [m["who"] for m in d.get("members", [])]},
                             ensure_ascii=False, indent=1))
            return 0
        if not msgs:
            print("（群里还没有消息）")
            return 0
        for m in msgs:
            via = "（代发）" if m.get("via") == "代发" else ""
            kind = "" if m.get("kind") in (None, "", "闲聊") else "[%s]" % m["kind"]
            print("%s  %s%s%s：%s" % (stamp(m.get("ts")), m.get("who"), via, kind,
                                      (m.get("text") or "").replace("\n", " ")))
        if d.get("busy"):
            print("（%s 正在想…）" % d["busy"].get("who"))
        return 0

    if not a.text:
        ap.print_help()
        return 2
    d = call("", {"action": "post", "who": a.who, "text": a.text,
                  "via": a.via, "kind": a.kind})
    if not d.get("ok"):
        print("没发出去：%s" % d.get("error"), file=sys.stderr)
        return 1
    m = d["message"]
    print("已进群 #%d  %s%s：%s" % (m["id"], m["who"],
                                    "（代发）" if m["via"] == "代发" else "",
                                    m["text"][:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
