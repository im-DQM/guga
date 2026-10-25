#!/usr/bin/env python3
"""today-plan-card.py —— 生成「今天完整计划」的可视化图（早报用）。

做的事：
1. 读 http://127.0.0.1:8790/api/todos（today / long）。
2. 按 上午 / 下午 / 晚上 分组，拼一张**窄卡**（420px 宽）——聊天里图片被限宽 420px，按这个宽度渲染才不会缩到看不清。
3. 用 headless chromium 截成 PNG，落到 hub 静态目录（每天换文件名，避免缓存）。
4. 把今天的计划快照追加进长期记录 ~/.hermes/knowledge/plan-log.md（同一天只写一次）。
5. stdout 打印**图片公网地址**（早报把它单独一行贴出去，hub 会当场渲染成图）。

无参数。任何一步失败都不抛异常给 cron（打印一句说明即可）。
"""
import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

API = "http://127.0.0.1:8790/api/todos"
HUB = Path("/home/ubuntu/stack/hub")
SCRATCH = Path("/home/ubuntu/.hermes/cache/scratch")
RANKS = Path("/home/ubuntu/.hermes/state/plan-ranks.json")
LOG = Path("/home/ubuntu/.hermes/knowledge/plan-log.md")
CHROME = "/home/ubuntu/.hermes/tools/chromium-1208/chrome-linux64/chrome"
WK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WK1 = ["一", "二", "三", "四", "五", "六", "日"]
TIER_COLOR = {
    "黑铁": "#9aa1b1", "青铜": "#c08552", "白银": "#cfd6e4", "黄金": "#e8b64c", "铂金": "#5eead4",
    "翡翠": "#34d399", "钻石": "#6aa8ff", "大师": "#b18cff", "宗师": "#ff7a9c", "王者": "#ff5f56",
}
PHASES = [("断链", date(2026, 11, 15)), ("登岸", date(2027, 1, 15)), ("夺旗", date(2027, 4, 15))]
WIDTH = 420


def fetch(key: str):
    with urllib.request.urlopen(f"{API}?date={key}", timeout=10) as r:
        return json.load(r)


def clean(text: str) -> str:
    t = str(text or "")
    for marker in ("⏰", "📅"):
        if marker in t:
            t = t.split(marker)[0]
    return t.split("@")[0].strip()


def block_of(text: str, due) -> str:
    if "吃药" in text:
        return "晚上"
    if any(k in text for k in ("学习项目", "项目开发", "求职动作", "简历", "内推", "投递", "算法题", "刷题")):
        return "上午"
    if any(k in text for k in ("八股", "口述", "健身", "散步", "拉伸", "面试", "复盘")):
        return "下午"
    hm = str(due or "")[11:16]
    if hm and hm >= "18:00":
        return "晚上"
    return "其他"


def phase_name(day: date) -> str:
    for name, until in PHASES:
        if day <= until:
            return name
    return "夺旗"


def ranks():
    """段位：优先现算（plan_ranks 与页面同一套规则），算不出来再读落盘的那份。"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plan_ranks_mod", "/home/ubuntu/stack/todo_service/plan_ranks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        c = mod.compute()
        mod.write(c)
        return {name: ln["tier"] for name, ln in c["lines"].items()}
    except Exception:
        pass
    try:
        return json.loads(RANKS.read_text(encoding="utf-8"))
    except Exception:
        return {"破阵": "黑铁", "千锤": "黑铁", "破壁": "黑铁", "守夜": "黑铁"}


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_html(day: date, items, longitems, height: int) -> str:
    groups = {"上午": [], "下午": [], "晚上": [], "其他": []}
    for it in items:
        groups[block_of(clean(it.get("text", "")), it.get("due"))].append(it)
    done = sum(1 for it in items if it.get("done"))
    rk = ranks()
    wd = day.weekday()

    rows = []
    for g in ("上午", "下午", "晚上", "其他"):
        if not groups[g]:
            continue
        chips = []
        for it in groups[g]:
            ok = it.get("done")
            txt = esc(clean(it.get("text", "")))
            chips.append(f'<span class="c{" ok" if ok else ""}">{"✓" if ok else "○"} {txt}</span>')
        rows.append(f'<div class="blk"><span class="when">{g}</span><div class="chips">{"".join(chips)}</div></div>')

    wk = []
    for i, name in enumerate(WK1):
        cls = " on" if i == wd else ""
        if i in (0, 2, 4):
            cls += " gym"
        label = "休" if i == 5 else ("健" if i in (0, 2, 4) else "")
        wk.append(f'<span class="d{cls}">{name}<i>{label}</i></span>')

    ach = []
    for name in ("破阵", "千锤", "破壁", "守夜"):
        t = rk.get(name, "黑铁")
        c = TIER_COLOR.get(t, "#9aa1b1")
        ach.append(f'<span class="a" style="--c:{c}">{name} <i>{t}</i></span>')

    longs = [clean(it.get("text", "")) for it in longitems if not it.get("done")][:3]
    longline = " · ".join(longs) if longs else "（暂时没有）"

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
  *{{box-sizing:border-box}}
  html,body{{margin:0;padding:0}}
  body{{width:{WIDTH}px;height:{height}px;overflow:hidden;background:
    radial-gradient(360px 220px at 8% -12%,rgba(109,124,255,.22),transparent 60%),
    radial-gradient(320px 200px at 96% 0%,rgba(192,139,255,.14),transparent 62%),#090a0e;
    color:#e7e9ef;font:13px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:15px 16px}}
  .top{{display:flex;align-items:baseline;gap:8px}}
  .t1{{font-size:19px;font-weight:700;letter-spacing:-.01em}}
  .t2{{color:#8b93a3;font-size:12px}}
  .prog{{margin-left:auto;color:#4ec9a7;font-weight:700;font-size:13px}}
  .sub{{display:flex;align-items:center;gap:8px;margin-top:6px}}
  .phase{{font-size:11px;color:#9aa7ff;border:1px solid rgba(109,124,255,.5);background:rgba(109,124,255,.14);
    border-radius:999px;padding:2px 9px}}
  .hint{{color:#6b7280;font-size:11px}}
  .card{{background:linear-gradient(180deg,#161922,#12141b);border:1px solid rgba(255,255,255,.08);
    border-radius:12px;box-shadow:inset 0 1px 0 rgba(255,255,255,.05);padding:11px 12px;margin-top:10px}}
  .blk{{display:grid;grid-template-columns:34px 1fr;gap:9px;padding:5px 0;border-bottom:1px dashed rgba(255,255,255,.07)}}
  .blk:last-child{{border-bottom:none}}
  .blk .when{{color:#e8b64c;font-size:12px;letter-spacing:.04em;padding-top:3px}}
  .chips{{display:flex;flex-wrap:wrap;gap:5px}}
  .chips .c{{font-size:12.5px;border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:2px 8px;
    background:rgba(255,255,255,.03);color:#d3d7e0}}
  .chips .c.ok{{color:#5c6472;text-decoration:line-through;border-color:rgba(78,201,167,.28);background:rgba(78,201,167,.06)}}
  h3{{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#6b7280;margin:0 0 7px;font-weight:600}}
  .wkline{{display:flex;gap:5px}}
  .wkline .d{{flex:1;text-align:center;font-size:11px;color:#9aa1b1;border:1px solid rgba(255,255,255,.1);
    border-radius:8px;padding:4px 0;background:rgba(255,255,255,.02)}}
  .wkline .d i{{font-style:normal;font-size:9.5px;color:#6b7280;display:block}}
  .wkline .d.on{{border-color:rgba(232,182,76,.65);color:#e8b64c;background:rgba(232,182,76,.1)}}
  .wkline .d.on i{{color:#e8b64c;opacity:.9}}
  .wkline .d.gym{{border-color:rgba(78,201,167,.42)}}
  .wkline .d.gym i{{color:#4ec9a7;opacity:.9}}
  .achline{{display:flex;gap:6px;flex-wrap:wrap}}
  .achline .a{{font-size:11.5px;border:1px solid var(--c);border-radius:8px;padding:3px 9px;color:var(--c);
    background:color-mix(in srgb,var(--c) 11%,transparent)}}
  .achline .a i{{font-style:normal;font-size:10px;opacity:.85}}
  .long{{font-size:11.5px;color:#9aa1b1}}
  .foot{{margin-top:8px;color:#5b6270;font-size:10.5px}}
  .foot b{{color:#c99b3f}}
</style></head><body>
  <div class="top">
    <span class="t1">{day.month}月{day.day}日 {WK[wd]}</span>
    <span class="t2">今天的计划</span>
    <span class="prog">完成 {done} / {len(items)}</span>
  </div>
  <div class="sub">
    <span class="phase">当前阶段 · {phase_name(day)}</span>
    <span class="hint">勾选以 hub 右侧「计划」为准</span>
  </div>

  <div class="card">{''.join(rows) if rows else '<div class="long">今天还没有条目</div>'}</div>

  <div class="card"><h3>本周节奏</h3><div class="wkline">{''.join(wk)}</div></div>

  <div class="card"><h3>成就段位</h3><div class="achline">{''.join(ach)}</div></div>

  <div class="foot">长期清单：{esc(longline)}<br>完整规划与成就说明：<b>dqmguga.site/plan.html</b></div>
</body></html>"""


def main() -> int:
    day = date.today()
    try:
        today = fetch("today")
        long_ = fetch("long")
    except Exception as e:
        print(f"（计划卡片生成失败：读不到计划数据 {e}）")
        return 0

    items = today.get("items", [])
    height = 480 + 26 * max(0, len(items) - 6)
    height = max(480, min(500, height))
    html = build_html(day, items, long_.get("items", []), height)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    html_path = SCRATCH / f"today-plan-{day.isoformat()}.html"
    html_path.write_text(html, encoding="utf-8")

    png_name = f"today-plan-{day.isoformat()}.png"
    png_path = HUB / png_name
    try:
        subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--hide-scrollbars",
                        f"--window-size={WIDTH},{height}", "--virtual-time-budget=5000",
                        f"--screenshot={png_path}", f"file://{html_path}"],
                       check=True, capture_output=True, timeout=90)
    except Exception as e:
        print(f"（计划卡片截图失败：{e}）")
        return 0

    # 长期记录：当天计划快照只写一次
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        text = LOG.read_text(encoding="utf-8") if LOG.exists() else "# 计划与人生记录（长期）\n\n> 每天早报写「计划」，晚报写「结果」；周六复盘读它做趋势。由咕嘎自动追加，人工不动。\n"
        head = f"## {day.isoformat()}（{WK[day.weekday()]}）"
        if head not in text:
            lines = ["", head, "", "### 计划"]
            for g in ("上午", "下午", "晚上", "其他"):
                got = [clean(i.get("text", "")) for i in items
                       if block_of(clean(i.get("text", "")), i.get("due")) == g]
                if got:
                    lines.append(f"- {g}：{'、'.join(got)}")
            longs = [clean(i.get("text", "")) for i in long_.get("items", []) if not i.get("done")]
            lines.append(f"- 长期清单未完成：{'、'.join(longs) or '无'}")
            LOG.write_text(text.rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass

    print(f"https://dqmguga.site/{png_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
