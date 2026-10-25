#!/usr/bin/env python3
"""todo.py — 简单的一行一条待办清单。

存储：/home/ubuntu/.hermes/todos.md（按日期分小节，另有一节「## 长期」放不挂日期的长期待办）
用法：
  add TEXT [--date YYYY-MM-DD]     追加一条待办（默认今天）
  add TEXT --list long             追加一条长期待办（一段时间内完成，不必今天做完）
  done N   [--date ...]            勾掉第 N 条（未完成项按显示序号）
  undone N [--date ...]            取消勾选
  rm N     [--date ...]            删除第 N 条
  edit N --text NEW [--date ...]   改第 N 条内容
  show     [--date ...]            列出某天（默认今天）
  show     --list long             列出长期待办
  all                              列出所有日期 + 长期
  dates                            列出有哪些日期

done / undone / rm / edit / show 都接受 --list long，作用在「## 长期」那一节上。
"""
import json
import re
import sys
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

FILE = Path("/home/ubuntu/.hermes/todos.md")
HEADER = "# 待办清单\n"
SEED_FILE = Path("/home/ubuntu/.hermes/.todo_seeded.json")
# 每日固定项：(内容, 到期时刻或 None)。有到点时间的会在播种时写成 '正文 @YYYY-MM-DD HH:MM'，
# 到点由 todo-due-check 巡检推提醒。主人的节奏：吃药 22:00（2026-10-13 定）。
DAILY_ALL = [("吃药", "22:00")]                                  # 每天都播种（健康类，不休息）
DAILY_WEEKDAY = [("学习项目", None), ("刷四道算法题", None), ("看八股文", None),
                 ("60 秒口述录制", None), ("健身", None)]        # 工作日锚点：周六整休，不播种
DAILY_SAT = [("早晨复盘", None)]                                  # 周六只有早晨那场复盘
DAILY_ITEMS = DAILY_ALL + DAILY_WEEKDAY                           # 兼容旧引用（顺序＝工作日顺序）

# ── 2026-10-22 主人定的新节奏，从下周一起播种 ───────────────────────────
# 7:00 起床、到教室打卡周一到周五 8:00 前（周日 9:00、周六不打卡）、23:00 睡；上午复习项目 + 算法；下午第一件事健身
# （周日 / 周二 / 周三 / 周五）；下午八股、投递；晚上口述 + 22:00 吃药。周六仍整休。
NEW_SINCE = "2026-10-26"
GYM_WEEKDAYS = {6, 1, 2, 4}          # 周日 / 周二 / 周三 / 周五（date.weekday()）
DAILY_NEW = [("喝蛋白粉 + 肌酸", None), ("复习项目", None), ("刷四道算法题", None),
             ("健身", None), ("看八股文", None), ("投递岗位", None), ("60 秒口述录制", None)]


def items_for(d: str):
    """按日期给播种清单：周六只吃药 + 早晨复盘；其余日子加上工作日锚点。"""
    try:
        day = date.fromisoformat(d)
        wd = day.weekday()
    except Exception:
        day, wd = date.today(), 0
    if d >= NEW_SINCE:
        if wd == 5:
            return DAILY_ALL + DAILY_SAT
        return [it for it in DAILY_NEW if it[0] != "健身" or wd in GYM_WEEKDAYS] + DAILY_ALL
    return DAILY_ALL + (DAILY_SAT if wd == 5 else DAILY_WEEKDAY)
# 项目完工后主人会告知，再加回 ("求职动作 30 分钟", None)（2026-10-16 主人要求：项目做完前不做求职动作）
ITEM_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.*)$")
DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
HEADING_RE = re.compile(r"^##\s+\S")           # 任何二级标题（日期节 / 长期节）
DUE_RE = re.compile(r"\s*@\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})\s*$")
DUE_DATE_RE = re.compile(r"\s*@\s*(\d{4}-\d{2}-\d{2})\s*$")   # 只有日期（长期清单的 deadline）
NOTIFIED_FILE = Path("/home/ubuntu/.hermes/.todo_notified.json")
EOD_FILE = Path("/home/ubuntu/.hermes/state/eod.json")        # 「结束一天」打卡：{日期: {"time": "HH:MM", "at": iso}}
PLAN_LOG = Path("/home/ubuntu/.hermes/knowledge/plan-log.md") # 计划与人生记录（长期）

# 「长期」清单：一段时间内要完成、不必当天做完的事。与日期节并列，
# 不参与每日播种，也不挂到期时间（所以不进 todo-due-alert 巡检）。
LONG_KEY = "long"
LONG_HEADING = "## 长期"
LONG_LABEL = "长期"


def split_due(text: str):
    """把条目文本拆成 (正文, 到期时刻或 None)。到期写法定为 '正文 @YYYY-MM-DD HH:MM'。"""
    m = DUE_RE.search(text or "")
    if m:
        return text[: m.start()].strip(), f"{m.group(1)} {m.group(2)}"
    m2 = DUE_DATE_RE.search(text or "")
    if m2:                                   # 长期清单：只有日期，没有时刻
        return text[: m2.start()].strip(), m2.group(1)
    return (text or "").strip(), None


def _load_notified() -> set:
    try:
        return set(json.loads(NOTIFIED_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_notified(s: set) -> None:
    try:
        NOTIFIED_FILE.write_text(json.dumps(sorted(s), ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_eod() -> dict:
    try:
        return json.loads(EOD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _log_eod(d: str, hhmm: str) -> None:
    """把「结束一天」的时刻写进长期记录 plan-log.md **当天那节**（只动这一天，别的日期一行不碰）。"""
    try:
        text = PLAN_LOG.read_text(encoding="utf-8") if PLAN_LOG.exists() else "# 计划与人生记录（长期）\n"
        line = f"- 结束一天（不看手机上床）：{hhmm}"
        head = f"## {d}"
        i = text.find(head)
        eol = text.find("\n", i) if i != -1 else -1          # 标题必须整行匹配（## 2026-10-22 也能对上「## 2026-10-22（周四）」）
        if i == -1 or eol == -1 or not text[i:].startswith(head):
            text = text.rstrip("\n") + f"\n\n## {d}\n" + line + "\n"
            i = -1
        else:
            j = text.find("\n## ", i + 1)
            block = text[i:j if j != -1 else len(text)].rstrip("\n")
            block = re.sub(r"\n?- 结束一天（不看手机上床）：\d{2}:\d{2}\s*(?=\n|$)", "", block)
            text = text[:i] + block + "\n" + line + "\n" + (text[j:] if j != -1 else "")
        PLAN_LOG.parent.mkdir(parents=True, exist_ok=True)
        PLAN_LOG.write_text(text, encoding="utf-8")
    except Exception:
        pass


def record_eod(now: datetime = None) -> dict:
    """记录「今天结束一天（不看手机上床）」的时刻。

    当天第一次为准；30 分钟内再点一次算改时间（点错了能纠）；之后不再改也不用重复记。
    """
    now = now or datetime.now()
    d = now.date().isoformat()
    hhmm = now.strftime("%H:%M")
    data = _load_eod()
    prev = data.get(d)
    if prev:
        try:
            first_dt = datetime.strptime(f"{d} {prev.get('time')}", "%Y-%m-%d %H:%M")
        except Exception:
            first_dt = now
        if (now - first_dt).total_seconds() > 1800:
            return {"date": d, "time": prev.get("time"), "already": True, "first": prev.get("time")}
    data[d] = {"time": hhmm, "at": now.isoformat(timespec="seconds")}
    try:
        EOD_FILE.parent.mkdir(parents=True, exist_ok=True)
        EOD_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    _log_eod(d, hhmm)
    return {"date": d, "time": hhmm, "already": False, "first": (prev or {}).get("time")}


def eod_of(d: str):
    return _load_eod().get(d)


def clear_eod(now: datetime = None) -> dict:
    """撤回今天的「结束一天」：删记录 + 把 plan-log 当天那节里的对应行去掉（误点可救）。"""
    now = now or datetime.now()
    d = now.date().isoformat()
    data = _load_eod()
    prev = data.pop(d, None)
    if prev is not None:
        try:
            EOD_FILE.parent.mkdir(parents=True, exist_ok=True)
            EOD_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        try:
            if PLAN_LOG.exists():
                text = PLAN_LOG.read_text(encoding="utf-8")
                head = f"## {d}（"
                hhmm = str((prev or {}).get("time") or "")
                if hhmm:
                    # 按「时刻」精确删，防止旧代码把行写串到别的日期节里
                    pat = r"\n?- 结束一天（不看手机上床）：" + re.escape(hhmm) + r"\s*(?=\n|$)"
                    text2 = re.sub(pat, "", text)
                    if text2 != text:
                        PLAN_LOG.write_text(text2.rstrip("\n") + "\n", encoding="utf-8")
        except Exception:
            pass
    return {"date": d, "removed": prev is not None, "prev": prev}


# ───────────────────────── 早晨打卡（到教室） ─────────────────────────
# 规则（2026-10-23 主人定）：周一到周五 8:00 前、周日 9:00 前算准时；周六整休不打卡；
# 过了算迟到但照记；每天第一次为准，再点只回显第一次的时刻。数据独立于待办：~/.hermes/state/checkin.json
CHECKIN_FILE = Path("/home/ubuntu/.hermes/state/checkin.json")
CHECKIN_DEADLINE = "08:00"            # 周一到周五
CHECKIN_DEADLINE_SUNDAY = "09:00"     # 周日
# 2026-10-22 及以前按旧口径（平时 9:00 / 周日 7:00）判，旧账不翻成迟到
CHECKIN_DEADLINE_LEGACY = "09:00"
CHECKIN_DEADLINE_LEGACY_SUNDAY = "07:00"
CHECKIN_RULE_FROM = "2026-10-23"


def checkin_deadline(d: str = None) -> str:
    """当天的打卡截止时刻 HH:MM；周六整休返回 ""，表示这天不用打卡。"""
    d = d or today()
    try:
        wd = date.fromisoformat(d).weekday()
    except Exception:
        return CHECKIN_DEADLINE
    legacy = d < CHECKIN_RULE_FROM
    if wd == 6:
        return CHECKIN_DEADLINE_LEGACY_SUNDAY if legacy else CHECKIN_DEADLINE_SUNDAY
    if wd == 5:
        return CHECKIN_DEADLINE_LEGACY if legacy else ""
    return CHECKIN_DEADLINE_LEGACY if legacy else CHECKIN_DEADLINE


def _load_checkin() -> dict:
    try:
        return json.loads(CHECKIN_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def record_checkin(now: datetime = None, src: str = "") -> dict:
    """当天第一次为准：再点只返回已记的时刻，不改第一次的记录（打卡时间就是要准）。"""
    now = now or datetime.now()
    d = now.date().isoformat()
    hhmm = now.strftime("%H:%M")
    dl = checkin_deadline(d)
    data = _load_checkin()
    prev = data.get(d)
    if not dl:  # 周六整休：这天不用打卡，点也只回显
        return {"date": d, "time": (prev or {}).get("time"), "already": bool(prev),
                "late": False, "first": (prev or {}).get("time"), "deadline": "", "noduty": True}
    if prev:
        return {"date": d, "time": prev.get("time"), "already": True,
                "late": str(prev.get("time") or "") > dl, "first": prev.get("time"), "deadline": dl}
    data[d] = {"time": hhmm, "at": now.isoformat(timespec="seconds"), "src": src or "unknown"}
    try:
        CHECKIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHECKIN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return {"date": d, "time": hhmm, "already": False, "late": hhmm > dl,
            "first": None, "deadline": dl}


def checkin_of(d: str = None):
    return _load_checkin().get(d or today())


def cmd_checkin(a) -> int:
    r = record_checkin(src="cli")
    if r["already"]:
        print(f"今天已经打过卡：{r['time']}" + ("（迟到了）" if r["late"] else "（准时）"))
    else:
        print(f"已打卡 {r['time']}" + (" —— 迟到了，不过记上了。" if r["late"] else " —— 准时，到教室了。"))
    return 0


def cmd_eod(a) -> int:
    r = record_eod()
    if r["already"]:
        print(f"今天已经记过结束一天：{r['time']}（30 分钟内再点一次可以改时间）")
    else:
        print(f"已记录：今天 {r['time']} 结束一天，不看手机上床。")
    return 0


def today() -> str:
    return date.today().isoformat()


def tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def load() -> list[str]:
    if not FILE.exists():
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(HEADER, encoding="utf-8")
    return FILE.read_text(encoding="utf-8").splitlines()


def save(lines: list[str]) -> None:
    text = "\n".join(lines).rstrip("\n") + "\n"
    FILE.write_text(text, encoding="utf-8")


def find_section(lines: list[str], key: str) -> tuple[int, int]:
    """Return (heading_index, end_index) for section `key`. (-1, -1) if absent.

    key 可以是日期（YYYY-MM-DD），也可以是 LONG_KEY（「## 长期」节）。
    节的边界一律是下一个 '## ' 标题 —— 这样长期节和日期节并存时不会互相吞掉。
    """
    start = -1
    for i, ln in enumerate(lines):
        if key == LONG_KEY:
            if ln.strip() == LONG_HEADING:
                start = i
                break
        else:
            m = DATE_RE.match(ln)
            if m and m.group(1) == key:
                start = i
                break
    if start == -1:
        return -1, -1
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if HEADING_RE.match(lines[j]):
            end = j
            break
    return start, end


find_date = find_section                 # todo_api.py 等调用方沿用旧名


def ensure_date(lines: list[str], d: str) -> tuple[list[str], int, int]:
    s, e = find_section(lines, d)
    if s != -1:
        return lines, s, e
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(f"## {d}")
    s, e = len(lines) - 1, len(lines)
    return lines, s, e


def ensure_long(lines: list[str]) -> tuple[list[str], int, int]:
    """确保「## 长期」节存在；不存在就插在文件里第一个日期节之前（日期节顺序不受影响）。"""
    s, e = find_section(lines, LONG_KEY)
    if s != -1:
        return lines, s, e
    idx = next((i for i, ln in enumerate(lines) if HEADING_RE.match(ln)), None)
    block = [LONG_HEADING, ""]
    if idx is None:                                   # 文件里还没有任何节
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
    else:
        if idx > 0 and lines[idx - 1].strip():
            block.insert(0, "")
        lines[idx:idx] = block
    s, e = find_section(lines, LONG_KEY)
    return lines, s, e


def items_in(lines: list[str], s: int, e: int) -> list[int]:
    return [i for i in range(s + 1, e) if ITEM_RE.match(lines[i])]


def append_item(lines: list[str], s: int, e: int, body: str) -> None:
    """在节内最后一条之后（节内为空则紧贴标题）插入一条未完成待办。"""
    entry = body if body.startswith("- [") else f"- [ ] {body}"
    idxs = items_in(lines, s, e)
    if idxs:
        lines.insert(idxs[-1] + 1, entry)
    else:
        lines.insert(s + 1, entry)


def target_key(a) -> str:
    """把命令行参数解析成节名：--list long → 'long'；--date 还认 today/tomorrow；其余按日期（默认今天）。"""
    if (getattr(a, "list", None) or "").strip().lower() in (LONG_KEY, LONG_LABEL):
        return LONG_KEY
    d = (getattr(a, "date", None) or "").strip().lower()
    if d in ("", "today"):
        return today()
    if d == "tomorrow":
        return tomorrow()
    return d


def label_of(key: str) -> str:
    return LONG_LABEL if key == LONG_KEY else key


def _missing_msg(key: str) -> str:
    return "长期还没有清单。" if key == LONG_KEY else f"{key} 没有清单。"


def _load_seeded() -> set:
    try:
        return set(json.loads(SEED_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seeded(s: set) -> None:
    try:
        SEED_FILE.write_text(json.dumps(sorted(s), ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def ensure_daily(d: str = None) -> bool:
    """每个日期只会播种一次：确保该日清单里存在固定的每日事项（如「吃药」）。

    用 ~/.hermes/.todo_seeded.json 记录已播种的日期，所以用户手动删掉后不会当天又被塞回来。
    """
    d = d or today()
    seeded = _load_seeded()
    if d in seeded:
        return False
    lines = load()
    lines, s, e = ensure_date(lines, d)
    existing = [ITEM_RE.match(lines[i]).group(2).strip() for i in range(s + 1, e) if ITEM_RE.match(lines[i])]
    changed = False
    for item, due in reversed(items_for(d)):
        if any(item in t for t in existing):
            continue
        entry = f"- [ ] {item}"
        if due:
            entry += f" @{d} {due}"
        lines.insert(s + 1, entry)
        changed = True
    if changed:
        save(lines)
    seeded.add(d)
    _save_seeded(seeded)
    return changed


def fmt(lines: list[str], s: int, e: int, d: str) -> str:
    idxs = items_in(lines, s, e)
    if not idxs:
        return f"{d}：暂无待办。"
    out = [f"{d}："]
    n = 0
    for i in idxs:
        m = ITEM_RE.match(lines[i])
        mark = "x" if m.group(1).lower() == "x" else " "
        body, due = split_due(m.group(2))
        n += 1
        if due and len(due) == 10:                     # 只有日期（长期 deadline）
            try:
                delta = (date.fromisoformat(due) - date.today()).days
                tag = f"  📅{due}（剩 {delta} 天）" if delta >= 0 else f"  📅{due}（已过期 {-delta} 天）"
            except ValueError:
                tag = f"  📅{due}"
        else:
            tag = f"  ⏰{due[5:]}" if due else ""      # 只显示 MM-DD HH:MM
        out.append(f"  {n}. [{'✓' if mark == 'x' else ' '}] {body}{tag}")
    return "\n".join(out)


def cmd_add(a) -> int:
    key = target_key(a)
    text = a.text.strip()
    due = (getattr(a, "due", None) or "").strip()
    if key == LONG_KEY:
        entry_text = text
        if due:
            d_only = due.split()[0]                      # 长期只认日期，给了时刻就截到日
            try:
                date.fromisoformat(d_only)
            except ValueError:
                print(f"--due 格式不对（要 YYYY-MM-DD，或 YYYY-MM-DD HH:MM）：{due}")
                return 1
            if not DUE_DATE_RE.search(entry_text):
                entry_text = f"{entry_text} @{d_only}"
        lines = load()
        lines, s, e = ensure_long(lines)
        append_item(lines, s, e, entry_text)
        save(lines)
        print(f"已加入长期：{entry_text}")
        return 0
    d = key
    ensure_daily(d)
    lines = load()
    lines, s, e = ensure_date(lines, d)
    entry = f"- [ ] {text}"
    if due:
        entry += f" @{due}"
    append_item(lines, s, e, entry)
    save(lines)
    if due:
        print(f"已加入 {d}：{text}（到期 {due}）")
    else:
        print(f"已加入 {d}：{text}")
    return 0


def _target_index(lines, s, e, n):
    idxs = items_in(lines, s, e)
    if n < 1 or n > len(idxs):
        return None
    return idxs[n - 1]


def cmd_done(a) -> int:
    key = target_key(a)
    lines = load()
    s, e = find_section(lines, key)
    if s == -1:
        print(_missing_msg(key))
        return 1
    i = _target_index(lines, s, e, a.n)
    if i is None:
        print(f"序号 {a.n} 不存在。")
        return 1
    m = ITEM_RE.match(lines[i])
    lines[i] = f"- [x] {m.group(2)}"
    save(lines)
    print(f"已完成：{m.group(2)}")
    return 0


def cmd_undone(a) -> int:
    key = target_key(a)
    lines = load()
    s, e = find_section(lines, key)
    if s == -1:
        print(_missing_msg(key))
        return 1
    i = _target_index(lines, s, e, a.n)
    if i is None:
        print(f"序号 {a.n} 不存在。")
        return 1
    m = ITEM_RE.match(lines[i])
    lines[i] = f"- [ ] {m.group(2)}"
    save(lines)
    print(f"已恢复未完成：{m.group(2)}")
    return 0


def cmd_rm(a) -> int:
    key = target_key(a)
    lines = load()
    s, e = find_section(lines, key)
    if s == -1:
        print(_missing_msg(key))
        return 1
    i = _target_index(lines, s, e, a.n)
    if i is None:
        print(f"序号 {a.n} 不存在。")
        return 1
    m = ITEM_RE.match(lines[i])
    del lines[i]
    save(lines)
    print(f"已删除：{m.group(2)}")
    return 0


def cmd_edit(a) -> int:
    key = target_key(a)
    lines = load()
    s, e = find_section(lines, key)
    if s == -1:
        print(_missing_msg(key))
        return 1
    i = _target_index(lines, s, e, a.n)
    if i is None:
        print(f"序号 {a.n} 不存在。")
        return 1
    m = ITEM_RE.match(lines[i])
    box = "x" if m.group(1).lower() == "x" else " "
    lines[i] = f"- [{box}] {a.text.strip()}"
    save(lines)
    print(f"已修改：{a.text.strip()}")
    return 0


def cmd_show(a) -> int:
    key = target_key(a)
    if key != LONG_KEY:
        ensure_daily(key)
    lines = load()
    s, e = find_section(lines, key)
    if s == -1:
        print("长期还没有清单。" if key == LONG_KEY else f"{key}：还没有清单。")
        return 0
    print(fmt(lines, s, e, label_of(key)))
    return 0


def cmd_ensure(a) -> int:
    d = a.date or today()
    changed = ensure_daily(d)
    if changed:
        print(f"{d} 已自动加入每日事项：{'、'.join(i for i, _ in items_for(d))}")
    else:
        print(f"{d} 的每日事项已就绪。")
    return 0


def cmd_all(a) -> int:
    lines = load()
    blocks = []
    s, e = find_section(lines, LONG_KEY)
    if s != -1:
        blocks.append(fmt(lines, s, e, LONG_LABEL))
    sections = [(i, DATE_RE.match(ln).group(1)) for i, ln in enumerate(lines) if DATE_RE.match(ln)]
    for k, (i, d) in enumerate(sections):
        e = sections[k + 1][0] if k + 1 < len(sections) else len(lines)
        blocks.append(fmt(lines, i, e, d))
    if not blocks:
        print("清单是空的。")
        return 0
    print("\n\n".join(blocks))
    return 0


def cmd_dates(a) -> int:
    lines = load()
    ds = [DATE_RE.match(ln).group(1) for ln in lines if DATE_RE.match(ln)]
    print("\n".join(ds) if ds else "（无）")
    return 0


def _due_rows(lines):
    """返回 [(due_datetime, 正文, 所在日期, 是否已完成, key)]，只含有到期时间的条目。

    只扫日期节：「长期」节不挂到期时间，也就不进 todo-due-alert 巡检。
    """
    rows = []
    sections = [(i, DATE_RE.match(ln).group(1)) for i, ln in enumerate(lines) if DATE_RE.match(ln)]
    for k, (i, d) in enumerate(sections):
        e = sections[k + 1][0] if k + 1 < len(sections) else len(lines)
        for j in items_in(lines, i, e):
            m = ITEM_RE.match(lines[j])
            body, due = split_due(m.group(2))
            if not due:
                continue
            try:
                dt = datetime.strptime(due, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            rows.append((dt, body, d, m.group(1).lower() == "x", f"{d}|{body}|{due}"))
    rows.sort()
    return rows


def cmd_due(a) -> int:
    """列出所有带时间的待办（未完成的在前）。"""
    rows = [r for r in _due_rows(load()) if not r[3]]
    if not rows:
        print("没有带时间的待办。")
        return 0
    now = datetime.now()
    for dt, body, d, done, key in rows:
        late = "  ⚠已过期" if dt < now else ""
        print(f"{dt:%m-%d %H:%M}  {body}{late}")
    return 0


def cmd_due_check(a) -> int:
    """巡检查询：到期而未完成、且还没提醒过的条目，输出提醒文案（无则什么都不输出）。

    安静档策略：同一件事只提醒一次，之后只在早报里出现。用 ~/.hermes/.todo_notified.json 去重。
    """
    now = datetime.now()
    notified = _load_notified()
    hits = []
    for dt, body, d, done, key in _due_rows(load()):
        if done or dt > now or key in notified:
            continue
        if (now - dt).total_seconds() > 86400:   # 过期超过一天的不再补提醒，交给早报
            continue
        hits.append((dt, body, key))
    if not hits:
        return 0
    out = ["⏰ 到点了："]
    for dt, body, key in hits:
        out.append(f"· {body}（该在 {dt:%m-%d %H:%M} 完成）")
        notified.add(key)
    print("\n".join(out))
    _save_notified(notified)
    return 0


def cmd_long_due(a) -> int:
    """长期清单里 7 天内到期（含已过期）的未完成条目 —— 给晚报与计划页用。无则什么都不输出。"""
    lines = load()
    s, e = find_section(lines, LONG_KEY)
    if s == -1:
        return 0
    now = date.today()
    hits = []
    for j in items_in(lines, s, e):
        m = ITEM_RE.match(lines[j])
        body, due = split_due(m.group(2))
        if not due or len(due) != 10 or m.group(1).lower() == "x":
            continue
        try:
            delta = (date.fromisoformat(due) - now).days
        except ValueError:
            continue
        if delta <= (a.days if a.days is not None else 7):
            hits.append((delta, due, body))
    if not hits:
        return 0
    hits.sort()
    print("📅 长期清单里快到期的事：")
    for delta, due, body in hits:
        when = f"剩 {delta} 天" if delta >= 0 else f"已过期 {-delta} 天"
        print(f"· {body}（{due}，{when}）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="todo", description="一行一条的待办清单")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_date(sp):
        sp.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天")
        sp.add_argument("--list", default=None, choices=[LONG_KEY, LONG_LABEL],
                        help="操作哪一栏：long/长期（不加则按 --date）")

    sp = sub.add_parser("add"); sp.add_argument("text"); sp.add_argument("--due", default=None, help="到期时刻 YYYY-MM-DD HH:MM"); add_date(sp); sp.set_defaults(fn=cmd_add)
    for name, fn in (("done", cmd_done), ("undone", cmd_undone), ("rm", cmd_rm)):
        sp = sub.add_parser(name); sp.add_argument("n", type=int); add_date(sp); sp.set_defaults(fn=fn)
    sp = sub.add_parser("edit"); sp.add_argument("n", type=int); sp.add_argument("--text", required=True); add_date(sp); sp.set_defaults(fn=cmd_edit)
    sp = sub.add_parser("show"); add_date(sp); sp.set_defaults(fn=cmd_show)
    sp = sub.add_parser("ensure-daily"); sp.add_argument("--date", default=None); sp.set_defaults(fn=cmd_ensure)
    sub.add_parser("all").set_defaults(fn=cmd_all)
    sub.add_parser("dates").set_defaults(fn=cmd_dates)
    sub.add_parser("due").set_defaults(fn=cmd_due)
    sub.add_parser("due-check").set_defaults(fn=cmd_due_check)
    sp = sub.add_parser("long-due"); sp.add_argument("--days", type=int, default=7); sp.set_defaults(fn=cmd_long_due)
    sub.add_parser("eod").set_defaults(fn=cmd_eod)
    sub.add_parser("checkin").set_defaults(fn=cmd_checkin)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
