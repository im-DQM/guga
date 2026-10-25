#!/usr/bin/env python3
"""test_group_api.py —— 「咕嘎群」后端接口自测（只用 stdlib）。

对着本机 127.0.0.1:8792/group 真发真删，覆盖：
  1. 发言 → 读回一致（含 kind / via / 特殊字符）
  2. 未知发言人被 400 拒
  3. 空正文被拒
  4. via 非法值被收敛成「本人」
  5. busy 置位 / 清零
  6. delete 生效（删存在的 removed=1，删不存在的不报错）
  7. group.json 连续写入后仍是合法 JSON，且 id 单调递增、next_id 领先

规矩：这些用例会真的往群里写消息 —— 脚本开头记下 last_id，测试消息统一用
      「咕嘎六号」（名单里的占位成员）+ 前缀标记 [自测]，结束时把自己造的 id 全删掉；
      只删自己造的（不碰主人 / 其它咕嘎在这期间发的），跑完群里不留垃圾。

用法：python3 test_group_api.py        # 退出码 0=全过，1=有失败
"""
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8792/group"
GROUP_JSON = "/home/ubuntu/stack/remote/group.json"
TEST_WHO = "咕嘎六号"          # 名单里的占位成员，别用「主人」（会触发群信使回话）
MARK = "[自测]"

_results = []
_made_ids = []                 # 本次测试自己造出来的消息 id，收尾全删


def req(method, body=None):
    """返回 (status, payload)。4xx/5xx 不抛异常，拿来断言。"""
    data = None if body is None else json.dumps(body).encode("utf-8")
    r = urllib.request.Request(API, data=data, method=method)
    if data:
        r.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"_raw": raw}


def get():
    return req("GET")


def post_text(text, who=TEST_WHO, via="本人", kind="闲聊"):
    return req("POST", {"action": "post", "who": who, "text": text, "via": via, "kind": kind})


def post(body):
    return req("POST", body)


def check(name, ok, detail=""):
    _results.append((name, bool(ok), detail))
    print("  %s %s%s" % ("PASS" if ok else "FAIL", name, ("  — " + detail) if detail else ""))


def read_json_file():
    with open(GROUP_JSON, encoding="utf-8") as f:
        return json.load(f)


# ────────────────────────── 用例 ──────────────────────────

def t_post_readback():
    """1. 发言 → 读回一致。"""
    text = MARK + " 读回一致 · 特殊字符 <b>&\"' 换行下一条"
    st, d = post_text(text, kind="汇报")
    if st != 200 or not d.get("ok"):
        return check("发言→读回：POST 成功", False, "status=%s body=%s" % (st, d))
    msg = d["message"]
    _made_ids.append(msg["id"])
    check("发言→读回：POST 成功", True, "id=%s" % msg["id"])

    st2, g = get()
    got = next((m for m in g.get("messages", []) if m.get("id") == msg["id"]), None)
    check("发言→读回：GET 能查到该 id", got is not None)
    if got:
        check("发言→读回：text 一致", got.get("text") == text,
              "期望 %r 实得 %r" % (text, got.get("text")))
        check("发言→读回：who 一致", got.get("who") == TEST_WHO, got.get("who"))
        check("发言→读回：kind 一致", got.get("kind") == "汇报", got.get("kind"))
        check("发言→读回：via 一致", got.get("via") == "本人", got.get("via"))
        check("发言→读回：ts 是秒级整数", isinstance(got.get("ts"), int) and got["ts"] > 1_600_000_000,
              str(got.get("ts")))


def t_unknown_who():
    """2. 未知发言人被 400 拒。"""
    st, d = post_text(MARK + " 未知发言人", who="不存在咕嘎")
    check("未知发言人：返回 400", st == 400, "status=%s body=%s" % (st, d))
    check("未知发言人：没落库", "message" not in d)


def t_empty_text():
    """3. 空正文被拒（'' 与纯空白都算空）。"""
    for label, val in [("空串", ""), ("纯空白", "   \n  ")]:
        st, d = post_text(val)
        check("空正文(%s)：返回 400" % label, st == 400, "status=%s body=%s" % (st, d))


def t_via_coerce():
    """4. via 非法值被收敛成「本人」。"""
    st, d = post_text(MARK + " via 非法值", via="代理转发")
    if st != 200 or not d.get("ok"):
        return check("via 非法值：POST 成功", False, "status=%s body=%s" % (st, d))
    _made_ids.append(d["message"]["id"])
    check("via 非法值：收敛成「本人」", d["message"].get("via") == "本人", d["message"].get("via"))

    st2, d2 = post_text(MARK + " via 代发", via="代发")
    if st2 == 200 and d2.get("ok"):
        _made_ids.append(d2["message"]["id"])
        check("via 合法值：代发保留", d2["message"].get("via") == "代发", d2["message"].get("via"))


def t_busy():
    """5. busy 置位 / 清零。"""
    st, d = post({"action": "busy", "who": TEST_WHO, "on": True})
    ok_set = st == 200 and (d.get("busy") or {}).get("who") == TEST_WHO
    check("busy：置位", ok_set, "status=%s body=%s" % (st, d))
    st2, g = get()
    check("busy：GET 能读到", (g.get("busy") or {}).get("who") == TEST_WHO, str(g.get("busy")))

    st3, d3 = post({"action": "busy", "who": TEST_WHO, "on": False})
    check("busy：清零(返回体)", st3 == 200 and d3.get("busy") is None, "body=%s" % d3)
    st4, g4 = get()
    check("busy：GET 确认为空", g4.get("busy") is None, str(g4.get("busy")))


def t_delete():
    """6. delete 生效。"""
    st, d = post_text(MARK + " 待删")
    if st != 200 or not d.get("ok"):
        return check("delete：准备一条", False, "status=%s body=%s" % (st, d))
    mid = d["message"]["id"]
    st2, d2 = post({"action": "delete", "id": mid})
    check("delete：删存在的 removed=1", st2 == 200 and d2.get("removed") == 1, "body=%s" % d2)
    st3, g = get()
    check("delete：GET 里已无该 id", all(m.get("id") != mid for m in g.get("messages", [])))

    st4, d4 = post({"action": "delete", "id": 99999999})
    check("delete：删不存在的不报错 removed=0", st4 == 200 and d4.get("removed") == 0, "body=%s" % d4)

    st5, d5 = post({"action": "delete", "id": "不是数字"})
    check("delete：id 非数字被 400 拒", st5 == 400, "status=%s body=%s" % (st5, d5))


def t_file_integrity():
    """7. 连续写入后 group.json 仍是合法 JSON，id 单调递增、next_id 领先。"""
    for i in range(5):
        st, d = post_text(MARK + " 压力写入 #%d" % (i + 1))
        if st == 200 and d.get("ok"):
            _made_ids.append(d["message"]["id"])
    try:
        data = read_json_file()
        check("group.json：仍是合法 JSON", True)
    except Exception as e:  # noqa: BLE001
        return check("group.json：仍是合法 JSON", False, str(e))
    msgs = data.get("messages", [])
    ids = [m.get("id") for m in msgs]
    check("group.json：messages 是数组", isinstance(msgs, list) and len(msgs) > 0)
    check("group.json：id 严格单调递增", all(b > a for a, b in zip(ids, ids[1:])),
          "样本 %s…%s" % (ids[:3], ids[-3:]))
    nid = (data.get("meta") or {}).get("next_id")
    check("group.json：next_id 领先最大 id", isinstance(nid, int) and nid > max(ids or [0]),
          "next_id=%s max=%s" % (nid, max(ids or [0])))


# ────────────────────────── 收尾：删掉自己造的 ──────────────────────────

def cleanup(start_last_id):
    print("\n【收尾】删掉本次测试造出来的消息…")
    deleted, missed = 0, []
    # 1) 按记录的 id 删
    for mid in sorted(set(_made_ids)):
        st, d = post({"action": "delete", "id": mid})
        if st == 200 and d.get("removed") == 1:
            deleted += 1
        # 404/0 都算没删到
    # 2) 兜底：扫一遍测试期间新增的、带标记的（只扫自己的标记 + 自家成员，绝不碰别的发言）
    _, g = get()
    for m in g.get("messages", []):
        if m.get("id", 0) > start_last_id and (m.get("text") or "").startswith(MARK):
            st, d = post({"action": "delete", "id": m["id"]})
            if st == 200 and d.get("removed") == 1:
                deleted += 1
    # 3) 复查
    _, g2 = get()
    leftover = [m["id"] for m in g2.get("messages", [])
                if m.get("id", 0) > start_last_id and (m.get("text") or "").startswith(MARK)]
    others = [m["id"] for m in g2.get("messages", []) if m.get("id", 0) > start_last_id]
    print("  已删 %d 条；残留带标记的 %d 条；测试期间他人新增（保留不动）%d 条"
          % (deleted, len(leftover), len(others)))
    if leftover:
        missed = leftover
    return len(leftover) == 0


def main():
    print("咕嘎群后端自测  %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("目标 %s\n" % API)

    st, g0 = get()
    if st != 200:
        print("拿不到群数据，直接退出：status=%s %s" % (st, g0))
        return 1
    start_last_id = g0.get("last_id") or 0
    print("起点 last_id=%s（count=%s, members=%s）\n"
          % (start_last_id, g0.get("count"), len(g0.get("members") or [])))

    tests = [t_post_readback, t_unknown_who, t_empty_text, t_via_coerce,
             t_busy, t_delete, t_file_integrity]
    try:
        for t in tests:
            print("· %s" % t.__doc__.strip().splitlines()[0])
            t()
            print()
    finally:
        clean_ok = cleanup(start_last_id)

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = [(n, d) for n, ok, d in _results if not ok]
    print("\n==== 结果：%d/%d 通过 ====" % (passed, len(_results)))
    if failed:
        for n, d in failed:
            print("  FAIL %s  %s" % (n, d))
    print("清场：%s" % ("干净，没留垃圾" if clean_ok else "⚠️ 还有残留，请看上面"))
    return 0 if (not failed and clean_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
