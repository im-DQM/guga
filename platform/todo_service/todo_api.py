#!/usr/bin/env python3
"""todo_api.py — 给「咕嘎 · Agent」前端提供待办清单的读写接口。

复用 ~/.hermes/scripts/todo.py 的解析逻辑，保证与聊天/定时任务看到的是同一份数据。
监听 127.0.0.1:8790，由 caddy 通过 /api/todos 反代。

接口：
  GET  /api/todos?date=YYYY-MM-DD|today|tomorrow
       -> {"date": d, "items": [{"n":1,"done":false,"text":"..."}], "counts": {...}}
  POST /api/todos   {"action":"add","text":"...","date":d}
                    {"action":"done"|"undone"|"rm","n":1,"date":d}
       -> 返回更新后的同一结构
"""
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

TODO_PY = "/home/ubuntu/.hermes/scripts/todo.py"
CRON_OUTPUT = Path("/home/ubuntu/.hermes/cron/output")
SEEN_FILE = Path("/home/ubuntu/stack/todo_service/seen.json")
STATE_DB = "/home/ubuntu/.hermes/state.db"

SOURCE_LABELS = {
    "api_server": "对话", "cron": "定时任务", "subagent": "子代理",
    "cli": "命令行", "tui": "终端界面", "desktop": "桌面端",
}
TASK_LABELS = {
    "": "主对话", "compression": "上下文压缩", "background_review": "后台回顾",
    "approval": "审批判定", "title_generation": "会话命名", "auxiliary": "辅助调用",
}

_spec = importlib.util.spec_from_file_location("todo_mod", TODO_PY)
todo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(todo)

_spec_pr = importlib.util.spec_from_file_location(
    "plan_ranks_mod", "/home/ubuntu/stack/todo_service/plan_ranks.py")
plan_ranks = importlib.util.module_from_spec(_spec_pr)
_spec_pr.loader.exec_module(plan_ranks)

_ranks_cache = {"ts": 0.0, "data": None}


def ranks_data():
    """四条成就线的段位（60 秒缓存；算完顺手落盘给早报图用）。"""
    global _ranks_cache
    if _ranks_cache["data"] is not None and time.time() - _ranks_cache["ts"] < 60:
        return _ranks_cache["data"]
    try:
        c = plan_ranks.compute()
        plan_ranks.write(c)
        _ranks_cache = {"ts": time.time(), "data": c}
    except Exception as exc:  # noqa: BLE001
        _ranks_cache = {"ts": time.time(), "data": _ranks_cache["data"] or {"error": str(exc)}}
    return _ranks_cache["data"]


def resolve_date(v):
    if not v or v == "today":
        return todo.today()
    if v == "tomorrow":
        return todo.tomorrow()
    return v


def snapshot(d):
    """某天（或「长期」栏）的清单快照。d == 'long' 时读「## 长期」节，不播种每日项。"""
    if d != todo.LONG_KEY:
        todo.ensure_daily(d)
    lines = todo.load()
    s, e = todo.find_section(lines, d)
    items = []
    if s != -1:
        n = 0
        for i in todo.items_in(lines, s, e):
            m = todo.ITEM_RE.match(lines[i])
            body, due = todo.split_due(m.group(2))
            n += 1
            items.append({
                "n": n,
                "done": m.group(1).lower() == "x",
                "text": body + (f"  ⏰{due[5:]}" if due else ""),
                "due": due,
            })
    done = sum(1 for it in items if it["done"])
    ck = todo.checkin_of(todo.today()) or {}
    ck_dl = todo.checkin_deadline(todo.today())
    return {
        "date": d,
        "today": todo.today(),
        "tomorrow": todo.tomorrow(),
        "eod": (todo.eod_of(d) if d != todo.LONG_KEY else None),
        "checkin": {"time": ck.get("time"), "at": ck.get("at"), "src": ck.get("src"),
                    "deadline": ck_dl,
                    "late": (ck.get("time") or "") > ck_dl if ck.get("time") else None},
        "items": items,
        "counts": {"total": len(items), "done": done, "open": len(items) - done},
        "ranks": (ranks_data() if d != todo.LONG_KEY else None),
    }


def do_add(d, text):
    text = (text or "").strip()
    if not text:
        return
    lines = todo.load()
    if d == todo.LONG_KEY:
        lines, s, e = todo.ensure_long(lines)
    else:
        lines, s, e = todo.ensure_date(lines, d)
    todo.append_item(lines, s, e, text)
    todo.save(lines)


def do_mark(d, n, action):
    lines = todo.load()
    s, e = todo.find_date(lines, d)
    if s == -1:
        return
    try:
        n = int(n)
    except (TypeError, ValueError):
        return
    idxs = todo.items_in(lines, s, e)
    if n < 1 or n > len(idxs):
        return
    i = idxs[n - 1]
    m = todo.ITEM_RE.match(lines[i])
    text = m.group(2)
    if action == "rm":
        del lines[i]
    elif action == "done":
        lines[i] = f"- [x] {text}"
    elif action == "undone":
        lines[i] = f"- [ ] {text}"
    else:
        return
    todo.save(lines)


def do_move(d, n):
    """向右滑挪一条：日期节的条目 → 第二天；长期清单的条目 → 明天。到期时刻跟着改到目标日期。"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return
    if d == todo.LONG_KEY:
        target = todo.tomorrow()          # 长期 → 落到明天，deadline 不动
    else:
        try:
            target = (datetime.fromisoformat(d) + timedelta(days=1)).date().isoformat()
        except (TypeError, ValueError):
            return
    lines = todo.load()
    s, e = todo.find_date(lines, d)
    if s == -1:
        return
    idxs = todo.items_in(lines, s, e)
    if n < 1 or n > len(idxs):
        return
    i = idxs[n - 1]
    m = todo.ITEM_RE.match(lines[i])
    body, due = todo.split_due(m.group(2))
    del lines[i]
    if due and d != todo.LONG_KEY:
        body = f"{body} @{target} {due[11:]}" if len(due) > 10 else f"{body} @{target}"
    elif due:
        body = f"{body} @{due}"          # 长期项的截止日保持原样
    lines, s2, e2 = todo.ensure_date(lines, target)
    todo.append_item(lines, s2, e2, body)
    todo.save(lines)


def _load_seen():
    try:
        return set(json.loads(SEEN_FILE.read_text("utf-8")))
    except Exception:  # noqa: BLE001
        return None


def _save_seen(s):
    try:
        SEEN_FILE.write_text(json.dumps(sorted(s), ensure_ascii=False), "utf-8")
    except Exception:  # noqa: BLE001
        pass


def _all_outputs():
    """Yield (key, job_name, time_label, response_text) for every cron output file."""
    if not CRON_OUTPUT.is_dir():
        return
    for job_dir in sorted(CRON_OUTPUT.iterdir()):
        if not job_dir.is_dir():
            continue
        for f in sorted(job_dir.glob("*.md")):
            key = f"{job_dir.name}/{f.name}"
            try:
                text = f.read_text("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            if "## Response" in text:
                body = text.split("## Response", 1)[1].strip()
            else:  # no_agent（纯脚本）：正文在第一个 --- 分隔线之后
                parts = re.split(r"^---\s*$", text, maxsplit=1, flags=re.M)
                body = parts[1].strip() if len(parts) > 1 else ""
            if not body or body == "[SILENT]":
                continue
            name = job_dir.name
            m = re.search(r"^# Cron Job:\s*(.+)$", text, re.M)
            if m:
                name = m.group(1).strip()
            yield key, name, f.stem.replace("_", " "), body


def list_inbox():
    seen = _load_seen()
    if seen is None:  # 首次运行：把已有输出标记为已读，避免一上来刷屏
        _save_seen({k for k, *_ in _all_outputs()})
        return {"items": [], "count": 0}
    items = [
        {"id": k, "job": n, "time": t, "text": b}
        for k, n, t, b in _all_outputs() if k not in seen
    ]
    items.sort(key=lambda x: x["id"])
    return {"items": items[-20:], "count": len(items)}


def ack_inbox(payload):
    seen = _load_seen() or set()
    if payload.get("all"):
        seen |= {k for k, *_ in _all_outputs()}
    else:
        for i in payload.get("ids") or []:
            if isinstance(i, str) and i:
                seen.add(i)
    _save_seen(seen)
    return list_inbox()


def _human(nbytes):
    for unit in ("B", "K", "M", "G", "T"):
        if nbytes < 1024 or unit == "T":
            return f"{nbytes:.0f}{unit}" if unit in ("B", "K") else f"{nbytes:.1f}{unit}"
        nbytes /= 1024.0


# ── 附件投递（hub 两端的「回形针」）────────────────────────────────
# 主人从浏览器选文件/图片 → 前端把原始字节 POST 到 /api/inbox/upload
# → 落到 stack/hub/uploads/<日期>/（hub 目录本身由 caddy 静态提供，故图片可直接当缩略图用）
# → 返回宿主绝对路径，前端把「【附件】路径」拼进消息，一号就能 read_file / 看图。
UPLOAD_ROOT = Path("/home/ubuntu/stack/hub/uploads")
UPLOAD_INDEX = UPLOAD_ROOT / "index.jsonl"
UPLOAD_MAX = 64 * 1024 * 1024            # 单文件上限 64 MB
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic", ".avif"}


def _safe_upload_name(raw):
    name = unquote(raw or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().lstrip(".").strip()
    if not name:
        return "file"
    if len(name.encode("utf-8")) > 150:                     # 太长就截，保留扩展名
        stem, dot, ext = name.rpartition(".")
        keep = 60
        name = (stem[:keep] + dot + ext[:12]) if dot else name[:keep]
    return name


def _upload_kind(name):
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md",
               ".csv", ".json", ".yaml", ".yml", ".py", ".c", ".cpp", ".h", ".hpp", ".rs",
               ".go", ".java", ".js", ".ts", ".sh", ".sql", ".html", ".xml", ".zip", ".epub"}:
        return "doc"
    return "file"


def save_upload(raw_name, data, ctype=""):
    if not data:
        raise ValueError("空的文件")
    if len(data) > UPLOAD_MAX:
        raise ValueError("文件太大（上限 64 MB）")
    name = _safe_upload_name(raw_name)
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    folder = UPLOAD_ROOT / day
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{now.strftime('%H%M%S')}-{name}"
    n = 1
    while target.exists():
        target = folder / f"{now.strftime('%H%M%S')}-{n}-{name}"
        n += 1
    target.write_bytes(data)
    rec = {
        "ok": True,
        "name": name,
        "path": str(target),
        "url": f"/uploads/{day}/{target.name}",
        "size": len(data),
        "size_h": _human(len(data)),
        "kind": _upload_kind(name),
        "type": ctype or "",
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with UPLOAD_INDEX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: rec[k] for k in
                                 ("name", "path", "url", "size", "size_h", "kind", "time")},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass
    return rec


def recent_uploads(limit=50):
    out = []
    if UPLOAD_INDEX.exists():
        try:
            for line in UPLOAD_INDEX.read_text(encoding="utf-8").splitlines()[-limit * 2:]:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        except (OSError, ValueError):
            pass
    return out[-limit:]


def sysinfo():
    """服务器资源快照：磁盘 / 内存 / Swap / 负载 / 最占内存的进程。"""
    info = {}
    # 内存
    mi = {}
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            k, _, v = line.partition(":")
            mi[k] = int(v.strip().split()[0]) * 1024
    except Exception:  # noqa: BLE001
        mi = {}
    total = mi.get("MemTotal", 0)
    avail = mi.get("MemAvailable", mi.get("MemFree", 0))
    used = max(total - avail, 0)
    info["mem"] = {
        "total": _human(total), "used": _human(used), "avail": _human(avail),
        "pct": round(used / total * 100) if total else 0,
    }
    # Swap
    st, sf = mi.get("SwapTotal", 0), mi.get("SwapFree", 0)
    info["swap"] = {
        "total": _human(st), "used": _human(max(st - sf, 0)), "free": _human(sf),
        "pct": round((st - sf) / st * 100) if st else 0,
    }
    # 磁盘
    try:
        v = os.statvfs("/")
        dt = v.f_blocks * v.f_frsize
        dfree = v.f_bavail * v.f_frsize
        dused = dt - dfree
        info["disk"] = {
            "total": _human(dt), "used": _human(dused), "free": _human(dfree),
            "pct": round(dused / dt * 100) if dt else 0,
        }
    except Exception:  # noqa: BLE001
        info["disk"] = {"total": "-", "used": "-", "free": "-", "pct": 0}
    # 负载
    try:
        info["load"] = open("/proc/loadavg", encoding="utf-8").read().split()[:3]
    except Exception:  # noqa: BLE001
        info["load"] = []
    info["cores"] = os.cpu_count() or 1
    # 最占内存的进程
    top = []
    try:
        out = subprocess.run(["ps", "-eo", "comm,rss", "--sort=-rss"],
                             capture_output=True, text=True, timeout=10).stdout.splitlines()[1:6]
        for line in out:
            parts = line.split(None, 1)
            if len(parts) == 2:
                top.append({"name": parts[0], "mb": round(int(parts[1]) / 1024, 1)})
    except Exception:  # noqa: BLE001
        pass
    info["top"] = top
    # 服务健康（顶栏小圆点）
    try:
        info["health"] = health()
    except Exception:  # noqa: BLE001
        pass
    return info


# ── 服务健康探针（给顶栏那排小圆点用；平时安静，挂了变红） ──

_HEALTH_TTL = 10          # 秒：同一时间窗口内复用上次结果，避免前端轮询反复探
_health_cache = {"ts": 0.0, "data": None}

HEALTH_TARGETS = [
    ("hub", "hub 前端", "http://127.0.0.1:8080/"),
    ("api", "Hermes API", "http://127.0.0.1:8642/health"),
    ("caddy", "Caddy", None),                       # 探 docker 容器运行状态
    ("code", "code-server", "http://127.0.0.1:8081/"),
    ("gitea", "Gitea", "http://127.0.0.1:3000/"),
]


def _probe_http(url, timeout=2.0):
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "guga-health"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
        return code < 500, "HTTP %s" % code
    except urllib.error.HTTPError as exc:               # 4xx 也算活着
        return exc.code < 500, "HTTP %s" % exc.code
    except Exception as exc:  # noqa: BLE001
        return False, (str(exc) or "无响应")[:60]


def _probe_caddy(timeout=5):
    try:
        out = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", "caddy"],
                             capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            return False, "容器不存在"
        running = out.stdout.strip() == "true"
        return running, ("容器运行中" if running else "容器已退出")
    except Exception as exc:  # noqa: BLE001
        return False, (str(exc) or "无响应")[:60]


def health(force=False):
    """并发探一遍五个服务，返回 {services:[{id,label,ok,ms,note}],down,checked_at}。带 10s 缓存。"""
    global _health_cache
    now = time.time()
    if not force and _health_cache["data"] and now - _health_cache["ts"] < _HEALTH_TTL:
        return _health_cache["data"]

    def one(t):
        sid, label, url = t
        t0 = time.perf_counter()
        ok, note = _probe_http(url) if url else _probe_caddy()
        return {"id": sid, "label": label, "ok": bool(ok),
                "ms": int(round((time.perf_counter() - t0) * 1000)), "note": note}

    with ThreadPoolExecutor(max_workers=len(HEALTH_TARGETS)) as pool:
        services = list(pool.map(one, HEALTH_TARGETS))
    data = {
        "checked_at": datetime.now().strftime("%H:%M:%S"),
        "down": sum(1 for s in services if not s["ok"]),
        "services": services,
    }
    _health_cache = {"ts": now, "data": data}
    return data


# ── Token 消耗（读 hermes state.db，用于「每次对话 / 任务」的可视化） ──

def _blank_usage():
    return {
        "tokens": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0, "reasoning_tokens": 0,
        "cost_usd": 0.0, "api_calls": 0, "sessions": 0, "messages": 0,
    }


def _acc(acc, row):
    acc["input_tokens"] += int(row["input_tokens"] or 0)
    acc["output_tokens"] += int(row["output_tokens"] or 0)
    acc["cache_read_tokens"] += int(row["cache_read_tokens"] or 0)
    acc["cache_write_tokens"] += int(row["cache_write_tokens"] or 0)
    acc["reasoning_tokens"] += int(row["reasoning_tokens"] or 0)
    acc["api_calls"] += int(row["api_call_count"] or 0)
    acc["messages"] += int(row["message_count"] or 0)
    acc["sessions"] += 1
    acc["cost_usd"] += float(row["estimated_cost_usd"] or 0.0) or float(row["actual_cost_usd"] or 0.0)


def _seal(acc):
    acc["tokens"] = acc["input_tokens"] + acc["output_tokens"]
    acc["cost_usd"] = round(acc["cost_usd"], 6)
    return acc


def _job_name(title):
    t = (title or "").strip()
    if " · " in t:
        t = t.split(" · ", 1)[0]
    return t or "定时任务"


# ── 编码侧用量：读 Claude Code 的会话记录（~/.claude/projects/**/*.jsonl） ──
# 每条 assistant 消息带 message.usage（input/output/cache_read/cache_creation）。
# 同一 message.id 会被重复写入多行（流式），必须按 id 去重，否则约 3 倍高估。

CLAUDE_PROJECTS = Path("/home/ubuntu/.claude/projects")
LOCAL_TZ = timezone(timedelta(hours=8))          # 站点在 +08:00，"今日"按本地算
_coding_cache = {}                               # 路径 -> (mtime,size,[条目])
_coding_lock = threading.Lock()


def _parse_transcript(path):
    """解析一个 transcript，按 message.id 去重，返回条目列表。"""
    entries = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if o.get("type") != "assistant":
                    continue
                msg = o.get("message") or {}
                u = msg.get("usage")
                if not u:
                    continue
                mid = msg.get("id")
                if not mid or mid in entries:
                    continue
                model = msg.get("model") or ""
                if model == "<synthetic>":      # 报错占位条目，非真实调用
                    continue
                try:
                    dt = datetime.fromisoformat(str(o.get("timestamp")).replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    continue
                entries[mid] = {
                    "id": mid, "ts": dt.timestamp(), "model": model,
                    "session": o.get("sessionId") or "",
                    "project": path.parent.name,
                    "in": int(u.get("input_tokens") or 0),
                    "out": int(u.get("output_tokens") or 0),
                    "cr": int(u.get("cache_read_input_tokens") or 0),
                    "cw": int(u.get("cache_creation_input_tokens") or 0),
                }
    except Exception:  # noqa: BLE001
        return []
    return list(entries.values())


def _coding_entries():
    """遍历 transcripts（带 mtime 缓存），全局按 message.id 去重后返回。"""
    try:
        files = sorted(CLAUDE_PROJECTS.glob("*/*.jsonl"))
    except Exception:  # noqa: BLE001
        return []
    with _coding_lock:
        live = set()
        for p in files:
            key = str(p)
            live.add(key)
            try:
                st = p.stat()
            except OSError:
                continue
            sig = (st.st_mtime, st.st_size)
            c = _coding_cache.get(key)
            if not c or c[0] != sig:
                _coding_cache[key] = (sig, _parse_transcript(p))
        for k in list(_coding_cache):
            if k not in live:
                del _coding_cache[k]
        merged = {}
        for k in sorted(_coding_cache):
            for e in _coding_cache[k][1]:
                merged.setdefault(e["id"], e)
    return list(merged.values())


def _acc_coding(acc, e):
    acc["input_tokens"] += e["in"]
    acc["output_tokens"] += e["out"]
    acc["cache_read_tokens"] += e["cr"]
    acc["cache_write_tokens"] += e["cw"]
    acc["api_calls"] += 1


def coding_usage():
    """编码（Claude Code）用量：今日 / 累计 / 分模型 / 分项目。"""
    today0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    entries = _coding_entries()
    out = {
        "generated_at": time.time(), "today": _blank_usage(), "all": _blank_usage(),
        "models": [], "projects": [],
    }
    models, projects, today_sessions, all_sessions = {}, {}, set(), set()
    for e in entries:
        tok = e["in"] + e["out"]
        _acc_coding(out["all"], e)
        all_sessions.add(e["session"])
        m = models.setdefault(e["model"] or "(未知)", {"model": e["model"] or "(未知)", "tokens": 0, "api_calls": 0})
        m["tokens"] += tok
        m["api_calls"] += 1
        p = projects.setdefault(e["project"], {"project": e["project"], "tokens": 0, "api_calls": 0, "last": 0})
        p["tokens"] += tok
        p["api_calls"] += 1
        p["last"] = max(p["last"], e["ts"])
        if e["ts"] >= today0:
            _acc_coding(out["today"], e)
            today_sessions.add(e["session"])
    out["today"]["sessions"] = len(today_sessions)
    out["all"]["sessions"] = len(all_sessions)
    _seal(out["today"])
    _seal(out["all"])
    out["models"] = sorted(models.values(), key=lambda x: x["tokens"], reverse=True)
    out["projects"] = sorted(projects.values(), key=lambda x: x["last"], reverse=True)[:8]
    return out


def usage(session_id=None):
    """汇总 state.db 里的 token / 花费：今日、累计、分来源、分用途、会话榜、定时任务榜。

    带 session_id 时额外返回该会话的库内累计值（session_totals），
    前端用它做差算出「本轮」消耗——SSE 里的 usage 是运行期累计，不能直接当一轮用。
    """
    today0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    out = {
        "generated_at": time.time(), "today": _blank_usage(), "all": _blank_usage(),
        "by_source": [], "by_task": [], "sessions": [], "jobs": [],
    }
    if not session_id:                       # 编码侧独立算，别被 state.db 的故障拖累
        try:
            out["coding"] = coding_usage()
        except Exception as exc:  # noqa: BLE001
            out["coding"] = {"error": str(exc)}
    if not os.path.exists(STATE_DB):
        out["error"] = "state.db 不存在"
        return out
    try:
        con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id,source,title,model,message_count,api_call_count,input_tokens,output_tokens,"
            "cache_read_tokens,cache_write_tokens,reasoning_tokens,estimated_cost_usd,actual_cost_usd,"
            "started_at,last_activity_at FROM sessions").fetchall()
        task_rows = con.execute(
            "SELECT task, SUM(api_call_count) AS calls, SUM(input_tokens) AS i, SUM(output_tokens) AS o,"
            " SUM(cache_read_tokens) AS c, SUM(reasoning_tokens) AS r,"
            " SUM(estimated_cost_usd) AS cost FROM session_model_usage GROUP BY task").fetchall()
        con.close()
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out

    src_today, src_all, jobs = {}, {}, {}
    sess = []
    for r in rows:
        _acc(out["all"], r)
        ts = r["last_activity_at"] or r["started_at"] or 0
        src = r["source"] or "other"
        s_all = src_all.setdefault(src, _blank_usage())
        _acc(s_all, r)
        if ts >= today0:
            _acc(out["today"], r)
            _acc(src_today.setdefault(src, _blank_usage()), r)
            if src == "cron":
                j = jobs.setdefault(_job_name(r["title"]), _blank_usage() | {"last": 0})
                _acc(j, r)
                j["last"] = max(j["last"], ts)
        sess.append({
            "id": r["id"], "title": (r["title"] or "").strip() or "(未命名)",
            "source": src, "source_label": SOURCE_LABELS.get(src, src),
            "model": r["model"] or "", "messages": int(r["message_count"] or 0),
            "api_calls": int(r["api_call_count"] or 0),
            "tokens": int(r["input_tokens"] or 0) + int(r["output_tokens"] or 0),
            "input_tokens": int(r["input_tokens"] or 0),
            "output_tokens": int(r["output_tokens"] or 0),
            "cache_read_tokens": int(r["cache_read_tokens"] or 0),
            "reasoning_tokens": int(r["reasoning_tokens"] or 0),
            "cost_usd": round(float(r["estimated_cost_usd"] or 0.0) or float(r["actual_cost_usd"] or 0.0), 6),
            "started_at": r["started_at"] or 0, "last_active": ts,
        })

    sess.sort(key=lambda s: s["last_active"], reverse=True)
    out["sessions"] = sess[:14]
    out["by_source"] = sorted(
        (_seal(v) | {"source": k, "label": SOURCE_LABELS.get(k, k)} for k, v in src_today.items()),
        key=lambda x: x["tokens"], reverse=True)
    out["all"]["by_source"] = sorted(
        (_seal(v) | {"source": k, "label": SOURCE_LABELS.get(k, k)} for k, v in src_all.items()),
        key=lambda x: x["tokens"], reverse=True)
    out["by_task"] = sorted((
        {"task": r["task"] or "", "label": TASK_LABELS.get(r["task"] or "", r["task"] or "其他"),
         "tokens": int(r["i"] or 0) + int(r["o"] or 0), "input_tokens": int(r["i"] or 0),
         "output_tokens": int(r["o"] or 0), "cache_read_tokens": int(r["c"] or 0),
         "reasoning_tokens": int(r["r"] or 0), "api_calls": int(r["calls"] or 0),
         "cost_usd": round(float(r["cost"] or 0.0), 6)}
        for r in task_rows), key=lambda x: x["tokens"], reverse=True)
    out["jobs"] = sorted(
        (_seal(v) | {"job": k, "last": v["last"]} for k, v in jobs.items()),
        key=lambda x: x["last"], reverse=True)
    _seal(out["today"])
    _seal(out["all"])
    if session_id:
        row = next((r for r in rows if r["id"] == session_id), None)
        if row is None:
            out["session_totals"] = None
        else:
            out["session_totals"] = {
                "id": row["id"], "title": (row["title"] or "").strip(),
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "cache_read_tokens": int(row["cache_read_tokens"] or 0),
                "reasoning_tokens": int(row["reasoning_tokens"] or 0),
                "api_calls": int(row["api_call_count"] or 0),
                "messages": int(row["message_count"] or 0),
                "cost_usd": round(float(row["estimated_cost_usd"] or 0.0) or float(row["actual_cost_usd"] or 0.0), 6),
            }
    return out


# ── 门卫（公网站点的登录页 / cookie 校验）──────────────────────────────
# 公网站点用 Caddy forward_auth 打 /api/gate/verify；登录页 POST /api/gate/login。
# 账号存在 ~/.hermes/secrets/hub-gate-users.json（只存 pbkdf2 哈希），签名密钥 hub-gate.key。
GATE_USERS_FILE = Path("/home/ubuntu/.hermes/secrets/hub-gate-users.json")
GATE_KEY_FILE = Path("/home/ubuntu/.hermes/secrets/hub-gate.key")
GATE_COOKIE = "guga_gate"
GATE_PERSIST_MAXAGE = 315360000        # mqd：10 年，等于「长期不用再验证」
GATE_ITER = 120000


def _gate_key() -> bytes:
    try:
        return GATE_KEY_FILE.read_bytes().strip()
    except Exception:  # noqa: BLE001
        return b""


def _gate_users() -> dict:
    try:
        return json.loads(GATE_USERS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _gate_hash(pw: str, salt_hex: str) -> str:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt_hex), GATE_ITER).hex()


def _gate_sign(raw: str) -> str:
    import base64
    import hashlib
    import hmac as _hmac
    return base64.urlsafe_b64encode(
        _hmac.new(_gate_key(), raw.encode("utf-8"), hashlib.sha256).digest()).decode().rstrip("=")


def gate_make_cookie(user: str) -> str:
    import base64
    import time as _t
    body = {"u": user, "p": 1 if (_gate_users().get(user) or {}).get("persist") else 0, "t": int(_t.time())}
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
    return raw + "." + _gate_sign(raw)


def gate_user_from_cookie(value: str) -> str:
    """校验 cookie，返回用户名；无效返回空串。"""
    import base64
    import hmac as _hmac
    if not value or "." not in value:
        return ""
    raw, sig = value.rsplit(".", 1)
    if not _hmac.compare_digest(sig, _gate_sign(raw)):
        return ""
    try:
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception:  # noqa: BLE001
        return ""
    u = str(body.get("u") or "")
    return u if u in _gate_users() else ""


def gate_check_login(user: str, pw: str) -> bool:
    import hmac as _hmac
    rec = (_gate_users() or {}).get(user or "")
    if not rec:
        return False
    try:
        return _hmac.compare_digest(_gate_hash(pw or "", rec["salt"]), rec["hash"])
    except Exception:  # noqa: BLE001
        return False


def _gate_cookie_value(header: str) -> str:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == GATE_COOKIE:
            return v.strip()
    return ""


def _gate_cookie_header(value: str, persist: bool) -> str:
    parts = [f"{GATE_COOKIE}={value}", "Path=/", "HttpOnly", "SameSite=Lax", "Secure"]
    if persist:
        parts.append(f"Max-Age={GATE_PERSIST_MAXAGE}")
    return "; ".join(parts)


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # 静音
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if "gate/verify" in path:
            u = gate_user_from_cookie(_gate_cookie_value(self.headers.get("Cookie") or ""))
            if u:
                self._send({"ok": True, "u": u})
                return
            orig = self.headers.get("X-Orig-Uri") or ""
            if orig.startswith("/"):
                from urllib.parse import quote
                loc = "/login.html?next=" + quote(orig, safe="/")
                body = b""
                self.send_response(302)
                self.send_header("Location", loc)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._send({"ok": False}, 401)
            return
        if "sysinfo" in path:
            try:
                self._send(sysinfo())
            except Exception as exc:  # noqa: BLE001
                self._send({"error": str(exc)}, 500)
            return
        if "usage" in path:
            try:
                q = parse_qs(urlparse(self.path).query)
                self._send(usage((q.get("session") or [None])[0]))
            except Exception as exc:  # noqa: BLE001
                self._send({"error": str(exc)}, 500)
            return
        if path.rstrip("/").endswith("/inbox/uploads"):
            try:
                self._send({"ok": True, "items": recent_uploads(50)})
            except Exception as exc:  # noqa: BLE001
                self._send({"error": str(exc)}, 500)
            return
        if "inbox" in path:
            try:
                self._send(list_inbox())
            except Exception as exc:  # noqa: BLE001
                self._send({"error": str(exc)}, 500)
            return
        q = parse_qs(urlparse(self.path).query)
        d = resolve_date((q.get("date") or [None])[0])
        try:
            self._send(snapshot(d))
        except Exception as exc:  # noqa: BLE001
            self._send({"error": str(exc)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        # 附件上传：前端发原始字节（Content-Type: 文件本身的类型，X-File-Name: percent-encoded 文件名）
        if path.rstrip("/").endswith("/inbox/upload"):
            try:
                ln = int(self.headers.get("Content-Length") or 0)
                if ln <= 0:
                    raise ValueError("没有收到文件内容")
                if ln > UPLOAD_MAX:
                    # 先把请求体读掉再回 400，否则客户端还在发、我们已关连接 → 浏览器只看到网络错误
                    remain = min(ln, 512 * 1024 * 1024)
                    while remain > 0:
                        chunk = self.rfile.read(min(65536, remain))
                        if not chunk:
                            break
                        remain -= len(chunk)
                    raise ValueError("文件太大（上限 64 MB）")
                data = self.rfile.read(ln)
                self._send(save_upload(self.headers.get("X-File-Name") or "",
                                       data, self.headers.get("Content-Type") or ""))
            except Exception as exc:  # noqa: BLE001
                self._send({"ok": False, "error": str(exc)}, 400)
            return
        try:
            ln = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:  # noqa: BLE001
            payload = {}
        if "gate/login" in urlparse(self.path).path:
            u = str(payload.get("u") or "").strip()
            p = str(payload.get("p") or "")
            if not gate_check_login(u, p):
                time.sleep(0.6)                      # 拖一下暴力试
                self._send({"ok": False, "error": "用户名或密码不对"}, 401)
                return
            persist = bool((_gate_users().get(u) or {}).get("persist"))
            self._send({"ok": True, "u": u, "persist": persist},
                       200, [("Set-Cookie", _gate_cookie_header(gate_make_cookie(u), persist))])
            return
        if "gate/logout" in urlparse(self.path).path:
            self._send({"ok": True}, 200,
                       [("Set-Cookie", f"{GATE_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=0")])
            return
        if "inbox" in urlparse(self.path).path:
            try:
                self._send(ack_inbox(payload))
            except Exception as exc:  # noqa: BLE001
                self._send({"error": str(exc)}, 500)
            return
        d = resolve_date(payload.get("date"))
        action = payload.get("action")
        try:
            if action == "add":
                do_add(d, payload.get("text"))
            elif action in ("done", "undone", "rm"):
                do_mark(d, payload.get("n"), action)
            elif action == "tomorrow":
                do_move(d, payload.get("n"))
            elif action == "badges_seen":
                plan_ranks.badges_ack(payload.get("items"))
                _ranks_cache["ts"] = 0.0            # 让下一次快照重新算 is_new
            elif action == "eod":
                todo.record_eod()
            elif action == "eod_undo":
                todo.clear_eod()
            elif action == "checkin":
                todo.record_checkin(src=str(payload.get("src") or ""))
            else:
                self._send({"error": "unknown action"}, 400)
                return
            self._send(snapshot(d))
        except Exception as exc:  # noqa: BLE001
            self._send({"error": str(exc)}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 8790), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
