#!/usr/bin/env python3
"""plan_ranks.py —— 四条成就线的段位自动判定（只升不降）。

数据源（都是主人自己在用的真文件，只读）：
  ~/.hermes/todos.md                       每日清单，[x] 才算事实
  ~/.hermes/state/eod.json                 「结束一天」打卡 = 上床时间
  ~/.hermes/job-tracker.md                 投递明细表
  ~/.hermes/state/plan-ranks-manual.json   手动置位（offer / 体能有变化这类算不出来的）

产物：
  state/plan-ranks.json   早报那张「今日计划」图读它（顶层四个键保持中文段位名，兼容旧读取）
  compute()              给 /api/todos 的 ranks 字段，页面直接渲染

语义（与 page 上的段位阶梯一致）：当前段位 = 1 + 从第一条起连续达成的目标数；
页面上标 now 的那一行就是「当前段位正在打的目标」，完成它即升到下一段。

用法：
  python3 plan_ranks.py            # 打印 json
  python3 plan_ranks.py --write    # 写盘 state/plan-ranks.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERMES = Path("/home/ubuntu/.hermes")
TODOS = HERMES / "todos.md"
EOD = HERMES / "state/eod.json"
JOB = HERMES / "job-tracker.md"
MANUAL = HERMES / "state/plan-ranks-manual.json"
SEEN = HERMES / "state/badges-seen.json"          # 徽章已读水位 {id: level}，只增不减
CHECKIN = HERMES / "state/checkin.json"           # 早晨到教室打卡 {日期: {time, at, src}}
OUT = HERMES / "state/plan-ranks.json"

TIERS = ["黑铁", "青铜", "白银", "黄金", "铂金", "翡翠", "钻石", "大师", "宗师", "王者"]

PHASES = [
    ("断链", date(2026, 10, 17), date(2026, 11, 15), 30),
    ("登岸", date(2026, 11, 16), date(2027, 1, 15), 61),
    ("夺旗", date(2027, 1, 16), date(2027, 4, 15), 90),
]

DAY_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
ITEM_RE = re.compile(r"^-\s*\[([ xX])\]\s*(.+?)\s*$")


# ───────────────────────── 事实抽取 ─────────────────────────
def daily_items(today: date | None = None) -> dict[date, list[tuple[bool, str]]]:
    """{日期: [(done, text)]}，只取已过去到今天为止的日期（明天那种不参与判定）。"""
    today = today or date.today()
    out: dict[date, list[tuple[bool, str]]] = {}
    if not TODOS.exists():
        return out
    cur = None
    for line in TODOS.read_text(encoding="utf-8").splitlines():
        m = DAY_RE.match(line.strip())
        if m:
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                cur = None
                continue
            cur = d if d <= today else None
            if cur:
                out.setdefault(cur, [])
            continue
        if line.strip().startswith("## "):
            cur = None            # ## 长期 等其它节不算
            continue
        if cur is None:
            continue
        mi = ITEM_RE.match(line.strip())
        if mi:
            out[cur].append((mi.group(1).lower() == "x", mi.group(2)))
    return out


def days_with(items: dict[date, list[tuple[bool, str]]], *keys: str) -> set[date]:
    got = set()
    for d, rows in items.items():
        for done, text in rows:
            if done and any(k in text for k in keys):
                got.add(d)
    return got


def eod_days() -> dict[date, str]:
    """{日期: 上床时间 HH:MM}"""
    out: dict[date, str] = {}
    try:
        raw = json.loads(EOD.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    for k, v in (raw or {}).items():
        if isinstance(v, dict) and v.get("time"):
            try:
                out[datetime.strptime(k, "%Y-%m-%d").date()] = str(v["time"])[:5]
            except ValueError:
                continue
    return out


# 与 todo.py 的 checkin_deadline() 保持一致：周一到周五 8:00、周日 9:00，周六整休不打卡
CK_DEADLINE = "08:00"
CK_DEADLINE_SUNDAY = "09:00"
CK_DEADLINE_LEGACY = "09:00"          # 2026-10-22 及以前按旧口径判，旧账不翻
CK_DEADLINE_LEGACY_SUNDAY = "07:00"
CK_RULE_FROM = date(2026, 10, 23)


def _ck_deadline(d: date) -> str:
    """当天截止 HH:MM；周六整休返回 ""。"""
    legacy = d < CK_RULE_FROM
    if d.weekday() == 6:
        return CK_DEADLINE_LEGACY_SUNDAY if legacy else CK_DEADLINE_SUNDAY
    if d.weekday() == 5:
        return CK_DEADLINE_LEGACY if legacy else ""
    return CK_DEADLINE_LEGACY if legacy else CK_DEADLINE


def checkin_ontime() -> set[date]:
    """准时到教室打卡的日子（当天截止时间前）。来源 state/checkin.json。"""
    out: set[date] = set()
    try:
        raw = json.loads(CHECKIN.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    for k, v in (raw or {}).items():
        if isinstance(v, dict) and v.get("time"):
            try:
                dd = datetime.strptime(k, "%Y-%m-%d").date()
                dl = _ck_deadline(dd)
                if dl and str(v["time"])[:5] <= dl:
                    out.add(dd)
            except ValueError:
                continue
    return out


JOB_STATUS = ("待投", "已投", "笔试", "一面", "二面", "终面", "已挂", "offer")


def job_facts() -> dict[str, int]:
    facts = {"applied": 0, "interviews": 0, "second": 0, "offer": 0}
    if not JOB.exists():
        return facts
    for line in JOB.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or s.count("|") < 5:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if set("".join(cells[:2])) <= set("-: "):        # 表格分隔行
            continue
        status = cells[4]
        if status not in JOB_STATUS:                     # 表头 / 说明行
            continue
        if status != "待投":
            facts["applied"] += 1
        if status in ("一面", "二面", "终面"):
            facts["interviews"] += 1
        if status in ("二面", "终面"):
            facts["second"] += 1
        if status == "offer":
            facts["offer"] += 1
    return facts


def manual_raw() -> dict:
    try:
        v = json.loads(MANUAL.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ───────────────────────── 小工具 ─────────────────────────
def streak(days: set[date], today: date) -> int:
    """以今天（或昨天）为锚，往回数连续天数。"""
    anchor = today if today in days else (today - timedelta(days=1) if (today - timedelta(days=1)) in days else None)
    if anchor is None:
        return 0
    n, d = 0, anchor
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n


def best_run(days: set[date]) -> int:
    """历史上最长的一段连续天数。"""
    best = cur = 0
    prev = None
    for d in sorted(days):
        cur = cur + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, cur)
        prev = d
    return best


def badges_seen() -> dict:
    """徽章已读水位 {id: level}。读不到就当从没解锁过。"""
    try:
        raw = json.loads(SEEN.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def badges_ack(pairs) -> dict:
    """前端弹过提示后回来登记：只抬高水位，不降。"""
    seen = badges_seen()
    for p in pairs or []:
        if not isinstance(p, dict) or p.get("id") is None:
            continue
        try:
            lv = int(p.get("level") or 0)
        except (TypeError, ValueError):
            continue
        k = str(p["id"])
        try:
            old = int(seen.get(k, 0) or 0)
        except (TypeError, ValueError):
            old = 0
        seen[k] = max(old, lv)
    try:
        SEEN.parent.mkdir(parents=True, exist_ok=True)
        SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return seen


def week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso[0], iso[1])


def weekly_counts(days: set[date]) -> dict[tuple[int, int], int]:
    out: dict[tuple[int, int], int] = {}
    for d in days:
        out[week_key(d)] = out.get(week_key(d), 0) + 1
    return out


def best_week_run(counts: dict[tuple[int, int], int], need: int) -> int:
    """连续多少周达到每周 need 次（取最长的一段）。"""
    if not counts:
        return 0
    keys = sorted(counts)
    best = run = 0
    prev = None
    for k in keys:
        ok = counts[k] >= need
        near = prev is not None and (prev[0] == k[0] and k[1] - prev[1] == 1) or \
               (prev is not None and prev[0] == k[0] - 1 and prev[1] >= 52 and k[1] == 1)
        run = (run + 1) if (ok and near) else (1 if ok else 0)
        best = max(best, run)
        prev = k
    return best


def month_count(days: set[date]) -> tuple[str, int]:
    """返回达标天数最多的那个月与天数。"""
    out: dict[str, int] = {}
    for d in days:
        k = d.strftime("%Y-%m")
        out[k] = out.get(k, 0) + 1
    if not out:
        return ("", 0)
    return max(out.items(), key=lambda kv: kv[1])


# ───────────────────────── 判定 ─────────────────────────
def compute(today: date | None = None) -> dict:
    today = today or date.today()
    items = daily_items(today)
    gym = days_with(items, "健身")
    oral = days_with(items, "口述")
    eod = eod_days()
    ontime = {d for d, t in eod.items() if t and t <= "23:45"}
    jf = job_facts()
    man = manual_raw()

    def man_done(line: str) -> set[int]:
        v = man.get(line)
        if isinstance(v, dict):
            return {int(x) for x in (v.get("targets_done") or []) if str(x).isdigit()}
        return set()

    def man_tier(line: str) -> int:
        v = man.get(line)
        tier = v.get("tier") if isinstance(v, dict) else (v if isinstance(v, str) else None)
        return TIERS.index(tier) + 1 if tier in TIERS else 0

    best_month, best_month_n = month_count(ontime)
    gym_week = weekly_counts(gym)
    gym_best = max(gym_week.values()) if gym_week else 0
    eod_week = weekly_counts(ontime)

    lines = {
        "破阵": {
            "color": "voc", "desc": "求职线 · 把简历真正交出去",
            "targets": [
                {"txt": "项目完工后投出首批 10 家", "done": jf["applied"] >= 10, "prog": f"投出 {jf['applied']} / 10 家"},
                {"txt": "累计投出 40 家", "done": jf["applied"] >= 40, "prog": f"投出 {jf['applied']} / 40 家"},
                {"txt": "拿到 3 个面试", "done": jf["interviews"] >= 3, "prog": f"面试 {jf['interviews']} / 3 个"},
                {"txt": "首次进入二面", "done": jf["second"] >= 1, "prog": f"二面 {jf['second']} 次"},
                {"txt": "日常实习 offer（1/15 前）", "done": jf["offer"] >= 1, "prog": f"offer {jf['offer']} 个"},
                {"txt": "暑期实习 offer（2027/4 前）", "done": False, "prog": "阶段未到"},
                {"txt": "秋招拿到心仪 offer", "done": False, "prog": "阶段未到"},
                {"txt": "转正 / 第一笔自己的收入", "done": False, "prog": "阶段未到"},
            ],
            "facts": f"投出 {jf['applied']} 家 · 面试 {jf['interviews']} 个 · 二面 {jf['second']} 次",
        },
        "千锤": {
            "color": "body", "desc": "身体线 · 肌肉是附属品，收获是自控力",
            "targets": [
                {"txt": "健身连续 3 天", "done": streak(gym, today) >= 3, "prog": f"连续 {streak(gym, today)} 天"},
                {"txt": "单周健身 3 次", "done": gym_best >= 3, "prog": f"最好一周 {gym_best} 次"},
                {"txt": "累计健身 20 次", "done": len(gym) >= 20, "prog": f"累计 {len(gym)} / 20 次"},
                {"txt": "连续 4 周每周 3 次", "done": best_week_run(gym_week, 3) >= 4, "prog": f"连 {best_week_run(gym_week, 3)} 周"},
                {"txt": "体能有可指的变化（体重 / 力量）", "done": False, "prog": "在晚报里跟我说一声"},
                {"txt": "半年不间断，训练成为默认", "done": best_week_run(gym_week, 3) >= 26, "prog": f"连 {best_week_run(gym_week, 3)} 周"},
                {"txt": "体成分与体能达到你自己的标准", "done": False, "prog": "在晚报里跟我说一声"},
            ],
            "facts": f"本周 {gym_week.get(week_key(today), 0)} 次 · 累计 {len(gym)} 次 · 连续 {streak(gym, today)} 天",
        },
        "破壁": {
            "color": "mind", "desc": "输出线 · 把脑子里的东西搬到别人眼前",
            "targets": [
                {"txt": "连续 3 天录 60 秒口述", "done": streak(oral, today) >= 3, "prog": f"连续 {streak(oral, today)} 天"},
                {"txt": "连续 7 天", "done": streak(oral, today) >= 7, "prog": f"连续 {streak(oral, today)} 天"},
                {"txt": "累计 30 条录音", "done": len(oral) >= 30, "prog": f"累计 {len(oral)} / 30 条"},
                {"txt": "第一次公开发布（IP 第一步）", "done": False, "prog": "在晚报里跟我说一声"},
                {"txt": "公开内容累计 25 条", "done": False, "prog": "在晚报里跟我说一声"},
                {"txt": "内容带来机会（面试 / 合作 / 认可）", "done": False, "prog": "在晚报里跟我说一声"},
                {"txt": "有一套被外部持续校验的输出", "done": False, "prog": "在晚报里跟我说一声"},
            ],
            "facts": f"口述累计 {len(oral)} 条 · 连续 {streak(oral, today)} 天",
        },
        "守夜": {
            "color": "spirit", "desc": "作息线 · 一切的地基",
            "targets": [
                {"txt": "连续 3 天 23:45 前上床", "done": streak(ontime, today) >= 3, "prog": f"连续 {streak(ontime, today)} 天"},
                {"txt": "连续 7 天", "done": streak(ontime, today) >= 7, "prog": f"连续 {streak(ontime, today)} 天"},
                {"txt": "单月 ≥20 天达标", "done": bool(best_month) and best_month_n >= 20, "prog": f"最好一月 {best_month_n} 天"},
                {"txt": "连续 4 周每周 ≥5 天", "done": best_week_run(eod_week, 5) >= 4, "prog": f"连 {best_week_run(eod_week, 5)} 周"},
                {"txt": "起床时间稳定在 08:00 前后", "done": False, "prog": "在晚报里跟我说一声"},
                {"txt": "不再需要提醒，作息成为默认", "done": False, "prog": "在晚报里跟我说一声"},
                {"txt": "精力曲线稳定：晚上不用靠刺激续命", "done": False, "prog": "在晚报里跟我说一声"},
            ],
            "facts": f"达标 {len(ontime)} 天 · 连续 {streak(ontime, today)} 天 · 本月 {sum(1 for d in ontime if d.month == today.month and d.year == today.year)} 天",
        },
    }

    for name, ln in lines.items():
        forced = man_done(name)
        for i, t in enumerate(ln["targets"], start=1):
            if i in forced:
                t["done"] = True
                t["prog"] = t["prog"] + "（手动）"
        auto_i = 1
        for t in ln["targets"]:
            if t["done"]:
                auto_i += 1
            else:
                break
        tier_i = max(auto_i, man_tier(name))
        tier_i = min(tier_i, len(TIERS))
        ln["tier_i"] = tier_i
        ln["tier"] = TIERS[tier_i - 1]
        ln["manual"] = man_tier(name) > auto_i
        for i, t in enumerate(ln["targets"], start=1):
            t["now"] = (i == tier_i)
            t["tier"] = TIERS[min(i - 1, len(TIERS) - 1)]
        ln["next"] = next((t["txt"] for t in ln["targets"] if t["now"]), "—")

    ph = None
    for name, start, until, days in PHASES:
        if today <= until:
            ph = {"name": name, "index": PHASES.index((name, start, until, days)) + 1,
                  "start": start.isoformat(), "until": until.isoformat(),
                  "days_left": (until - today).days, "days_total": (until - start).days + 1}
            break
    if ph is None:
        ph = {"name": "夺旗", "index": 3, "start": PHASES[-1][1].isoformat(),
              "until": PHASES[-1][2].isoformat(), "days_left": 0, "days_total": PHASES[-1][3]}
    ph["passed"] = max(0, (today - date.fromisoformat(ph["start"])).days)

    # ── 成就徽章（小反馈，铜 / 银 / 金三档；全自动，只升不降） ──
    def mk(bid, name, icon, unit, metric, levels):
        lv = sum(1 for x in levels if metric >= x)
        nxt = levels[lv] if lv < len(levels) else None
        return {"id": bid, "name": name, "icon": icon, "unit": unit,
                "metric": metric, "levels": levels, "level": lv,
                "level_name": (["铜", "银", "金"][lv - 1] if lv else ""),
                "prog": (f"{metric} / {nxt}" if nxt is not None else f"{metric} · 满级")}

    all_clear = {d for d, rows in items.items() if len(rows) >= 3 and all(ok for ok, _ in rows)}
    done_total = sum(1 for rows in items.values() for ok, _ in rows if ok)
    zero_debt = {d for d, rows in items.items() if len(rows) - sum(1 for ok, _ in rows if ok) <= 1}
    badges = [
        mk("all_clear", "全清日", "清", "次", len(all_clear), [3, 10, 25]),
        mk("all_clear_run", "连清", "连", "天", best_run(all_clear), [2, 4, 7]),
        mk("meds", "药不能停", "药", "天", best_run(days_with(items, "吃药")), [7, 21, 60]),
        mk("gym", "举铁", "铁", "次", len(gym), [3, 20, 40]),
        mk("oral", "开口", "口", "条", len(oral), [3, 10, 30]),
        mk("alg", "刷题", "题", "天", len(days_with(items, "算法")), [10, 30, 60]),
        mk("bagu", "八股", "八", "天", len(days_with(items, "八股")), [10, 30, 60]),
        mk("proj", "项目", "项", "天", len(days_with(items, "学习项目", "项目开发")), [5, 15, 30]),
        mk("sleep", "早睡", "睡", "天", best_run(ontime), [3, 7, 14]),
        mk("sleep_week", "稳周", "周", "周", best_week_run(eod_week, 5), [1, 2, 4]),
        mk("punctual", "守时", "时", "天", best_run(checkin_ontime()), [3, 7, 14]),
        mk("volume", "百条功", "百", "条", done_total, [50, 150, 300]),
        mk("zero_debt", "零拖欠", "零", "天", best_run(zero_debt), [3, 7, 14]),
    ]
    seen = badges_seen()
    for b in badges:
        b["is_new"] = b["level"] > int(seen.get(b["id"], 0) or 0)

    return {"date": today.isoformat(), "computed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "phase": ph, "lines": lines, "badges": badges}


def write(computed: dict | None = None) -> dict:
    c = computed or compute()
    flat = {name: ln["tier"] for name, ln in c["lines"].items()}
    flat["_detail"] = c
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")
    return flat


if __name__ == "__main__":
    c = compute()
    if "--write" in sys.argv:
        write(c)
    print(json.dumps(c, ensure_ascii=False, indent=2))
