#!/usr/bin/env python3
"""咕嘎周账：每个咕嘎这一周干了什么、烧了多少 token、值不值。

数据来源（都是真数，不估算）：
  · 本机 Hermes 的 state.db（default + remote 两套 profile）：每个会话的 token / 费用 / 调用次数 / 来源
  · cron 会话的标题里带作业名 → 归属到对应咕嘎
  · 零号（Claude Code）读 ~/.claude/projects/*.jsonl 里的 usage 字段
  · 三号/四号/五号在别的机器上，只能记工作量，费用标「未计费」

用法：
  guga-weekly.py                 # 最近 7 天
  guga-weekly.py --days 14
  guga-weekly.py --print         # 只打印，不写文件
"""
import argparse, glob, json, os, sqlite3, sys, datetime as dt

HOME = os.path.expanduser("~")
DBS = [os.path.join(HOME, ".hermes/state.db"),
       os.path.join(HOME, ".hermes/profiles/remote/state.db")]
CLAUDE_DIR = os.path.join(HOME, ".claude/projects")
OUTDIR = os.path.join(HOME, ".hermes/guga/guga1/state/weekly")

# 哪个 cron 作业算谁的活（没列到的一律算一号）
JOB2GUGA = {
    "night-scan": "七号", "scout-hotsearch": "七号",
    "night-watch": "八号", "swap-patrol": "八号", "browser-daemon-reaper": "八号",
}
NAMES = {"零号": "编码咕嘎", "一号": "管家（服务器）", "二号": "飞书（停用）",
         "三号": "WorkBuddy", "四号": "LightVela", "五号": "ASUS 笔记本",
         "六号": "接入记录官", "七号": "斥候", "八号": "保安咕嘎"}
ORDER = ["零号", "一号", "六号", "七号", "八号", "三号", "四号", "五号", "二号"]
NOLOCAL = {"三号", "四号", "五号", "二号"}          # 拿不到 token 的
GAKU = os.path.join(HOME, ".hermes/guga")


def blank():
    return {"sessions": 0, "api_calls": 0, "in": 0, "out": 0, "cache_read": 0,
            "cache_write": 0, "reasoning": 0, "usd": 0.0, "jobs": {}, "notes": [],
            "runs": {}, "fails": {}}


def kfmt(n):
    if n >= 1_000_000:
        return "%.1fM" % (n / 1_000_000)
    if n >= 1000:
        return "%.1fk" % (n / 1000)
    return str(n)


def read_state_db(path, start, end, agg):
    if not os.path.exists(path):
        return
    db = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute("""select id, source, title, started_at, message_count, tool_call_count,
                                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                                reasoning_tokens, estimated_cost_usd, model
                         from sessions where started_at >= ? and started_at < ?""",
                      (start, end)).fetchall()
    calls = {r[0]: r[1] for r in db.execute("select session_id, sum(api_call_count) from session_model_usage group by session_id")}
    for r in rows:
        src, title = (r["source"] or ""), (r["title"] or "")
        job = title.split(" · ")[0].strip()
        g = JOB2GUGA.get(job, "一号")
        a = agg[g]
        a["sessions"] += 1
        a["api_calls"] += calls.get(r["id"], 0) or 0
        for f in ("in", "out", "cache_read", "cache_write", "reasoning"):
            a[f] += r[{"in": "input_tokens", "out": "output_tokens", "cache_read": "cache_read_tokens",
                       "cache_write": "cache_write_tokens", "reasoning": "reasoning_tokens"}[f]] or 0
        a["usd"] += r["estimated_cost_usd"] or 0.0
        key = (title.split(" · ")[0].strip() if src == "cron" and title else (src or "会话"))
        a["jobs"][key] = a["jobs"].get(key, 0) + 1
        if src != "cron" and title:
            a.setdefault("titles", []).append(title.split(" · ")[0].strip())
    db.close()


def read_claude(start, end, agg):
    """零号在 Claude Code 里的用量（订阅制，只知道 token，没有价格）。"""
    a = agg["零号"]
    sessions = set()
    for p in glob.glob(os.path.join(CLAUDE_DIR, "*", "*.jsonl")):
        try:
            f = open(p, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in f:
            if '"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            ts = d.get("timestamp")
            if not ts:
                continue
            try:
                t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if not (start <= t < end):
                continue
            m = d.get("message") or {}
            u = m.get("usage") or {}
            if not u:
                continue
            a["sessions"] = 1 if not sessions else a["sessions"]
            sessions.add(p)
            a["api_calls"] += 1
            a["in"] += u.get("input_tokens", 0) or 0
            a["out"] += u.get("output_tokens", 0) or 0
            a["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
            a["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
        f.close()
    a["sessions"] = len(sessions)


def read_cron_runs(start, end, agg):
    """作业运行次数（含 no_agent 的纯脚本作业，这类不产生会话）。"""
    jobs_path = os.path.join(HOME, ".hermes/cron/jobs.json")
    ex_path = os.path.join(HOME, ".hermes/cron/executions.db")
    if not (os.path.exists(jobs_path) and os.path.exists(ex_path)):
        return
    try:
        jobs = {j["id"]: j.get("name", "") for j in json.load(open(jobs_path, encoding="utf-8"))["jobs"]}
    except Exception:
        return
    db = sqlite3.connect("file:%s?mode=ro" % ex_path, uri=True)
    for job_id, status, ts in db.execute("select job_id, status, started_at from executions"):
        if not ts:
            continue
        try:
            t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if not (start <= t < end):
            continue
        name = jobs.get(job_id, job_id[:8])
        g = JOB2GUGA.get(name, "一号")
        agg[g].setdefault("runs", {})
        agg[g]["runs"][name] = agg[g]["runs"].get(name, 0) + 1
        if status not in ("ok", "success", "completed"):
            agg[g].setdefault("fails", {})
            agg[g]["fails"][name] = agg[g]["fails"].get(name, 0) + 1
    db.close()


def journal_lines(guga, start, end, limit=6):
    """该咕嘎 journal/ 里本周写下的条目（按文件 mtime 粗筛）。"""
    idx = {"零号": "0", "一号": "1", "二号": "2", "三号": "3", "四号": "4",
           "五号": "5", "六号": "6", "七号": "7", "八号": "8"}[guga]
    d = os.path.join(GAKU, "guga" + idx, "journal")
    if not os.path.isdir(d):
        return []
    hits = []
    for p in sorted(glob.glob(os.path.join(d, "*.md"))):
        try:
            if not (start <= os.path.getmtime(p) < end + 86400):
                continue
            for line in open(p, encoding="utf-8", errors="ignore"):
                s = line.strip()
                if s.startswith("- ") or s.startswith("* "):
                    hits.append(s[:80])
        except OSError:
            continue
    return hits[-limit:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--print", dest="only_print", action="store_true")
    a = ap.parse_args()

    now = dt.datetime.now()
    end = now.timestamp()
    start = (now - dt.timedelta(days=a.days)).timestamp()
    s_date = (now - dt.timedelta(days=a.days)).strftime("%Y-%m-%d")
    e_date = now.strftime("%Y-%m-%d")

    agg = {g: blank() for g in ORDER}
    for p in DBS:
        read_state_db(p, start, end, agg)
    read_claude(start, end, agg)
    read_cron_runs(start, end, agg)

    iso = now.isocalendar()
    week = "%d-W%02d" % (iso[0], iso[1])
    L = ["# 咕嘎周账 · %s（%s ~ %s）" % (week, s_date, e_date), "",
         "> 数据：本机 state.db 真实 token 与费用 + 零号 Claude Code 日志；三/四/五号无本地计数。", "",
         "| 咕嘎 | 会话 | API 调用 | 输入 | 输出 | 缓存读 | 估算费用 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for g in ORDER:
        x = agg[g]
        if not x["sessions"] and g not in NOLOCAL:
            continue
        usd = "—" if (g in NOLOCAL or g == "零号") else "$%.3f" % x["usd"]
        L.append("| %s %s | %s | %s | %s | %s | %s | %s |" % (
            g, NAMES[g], x["sessions"] or "—", x["api_calls"] or "—",
            kfmt(x["in"]), kfmt(x["out"]), kfmt(x["cache_read"]), usd))

    total_usd = sum(agg[g]["usd"] for g in ORDER)
    total_in = sum(agg[g]["in"] for g in ORDER)
    total_out = sum(agg[g]["out"] for g in ORDER)
    L += ["", "**合计**：输入 %s、输出 %s、本机可计费 $%.3f（零号为订阅制，未计费）。"
          % (kfmt(total_in), kfmt(total_out), total_usd), ""]

    for g in ORDER:
        x = agg[g]
        jl = journal_lines(g, start, end)
        if not x["sessions"] and not jl:
            continue
        L.append("## %s %s" % (g, NAMES[g]))
        acts = dict(x["runs"])
        for k, v in x["jobs"].items():          # 人聊出来的会话（标题即话题）
            if k not in ("api_server", "cli", "gateway", "会话"):
                acts[k] = acts.get(k, 0) + v
        chat = x["jobs"].get("api_server", 0) + x["jobs"].get("cli", 0) + x["jobs"].get("gateway", 0) + x["jobs"].get("会话", 0)
        if acts:
            top = sorted(acts.items(), key=lambda i: -i[1])
            more = len(top) - 6
            L.append("- 干了什么：%s%s" % ("、".join("%s×%d" % kv for kv in top[:6]),
                                          "…等 %d 项" % len(top) if more > 0 else ""))
            if chat:
                L.append("- 主人在聊天里提了 %d 件事（标题即话题，见下）" % chat)
        elif g == "零号" and x["in"]:
            L.append("- 干了什么：在 `~/workspace` 用 Claude Code 写代码（%d 次调用）" % x["api_calls"])
        elif not jl:
            L.append("- 干了什么：本周没有活动记录")
        if x.get("fails"):
            L.append("- 失败：%s" % "、".join("%s×%d" % kv for kv in x["fails"].items()))
        tl = x.get("titles") or []
        if tl:
            seen, uniq = set(), []
            for t in tl:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            L.append("- 聊天里做过的事（去重，最多 8 条）：%s%s"
                     % ("；".join(uniq[:8]), "…" if len(uniq) > 8 else ""))
        if x["sessions"] and g not in NOLOCAL:
            L.append("- 用量：%d 会话 / %d 次 API 调用 / 输入 %s、输出 %s、缓存读 %s / %s"
                     % (x["sessions"], x["api_calls"], kfmt(x["in"]), kfmt(x["out"]),
                        kfmt(x["cache_read"]), "订阅制未计费" if g == "零号" else "$%.3f" % x["usd"]))
        if jl:
            L.append("- 日记摘录：")
            L += ["  - %s" % s for s in jl]
        L.append("")

    L += ["## 未接入计数", "",
          "三号 WorkBuddy、四号 LightVela、五号 ASUS 在别的机器上，本机看不到 token 与费用；本周只有它们的产出与日记可查，费用一律标「未计费」。"
          "要给它们上账，得在各自那边加一条「跑完回报用量」的通道。", "",
          "> 口径提醒：cron 执行记录只保留最近 1000 条，跑得最勤的作业（如每分钟的 claude-done-notify）次数会被少记；token 与费用取自会话表，不受这个限制。", ""]

    text = "\n".join(L).rstrip() + "\n"
    if a.only_print:
        print(text)
        return
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, "%s.md" % week)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(OUTDIR, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"week": week, "window": [s_date, e_date],
                            "by_guga": {g: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                                            for kk, vv in agg[g].items() if kk != "jobs"}
                                        for g in ORDER},
                            "jobs": {g: agg[g]["jobs"] for g in ORDER}}, ensure_ascii=False) + "\n")
    print(text)
    print("已写入 %s" % path, file=sys.stderr)


if __name__ == "__main__":
    main()
