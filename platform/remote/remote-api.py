#!/usr/bin/env python3
"""本机操作 —— 远程执行小服务（功能③ · P2）

绑 127.0.0.1:8792，由 Caddy 经 handle_path /api/remote/* 反代（会剥掉前缀）。
所以本服务看到的路径是裸的 /hosts、/exec、/approve。

设计要点：
  · 多线程（ThreadingHTTPServer）—— 一条 30s 的 ssh 不能卡住 /hosts 轮询。
  · 无本地 shell 拼串：host 只能是 hosts.json 的 key（查表），命令作为单个 argv
    交给 ssh，由**远端** shell 解释（这是命令框应有的语义）。
  · 确认门：只读直跑；写/危险先入待批队列，用户在前端点「确认」才执行。
    这是**安全网，不是安全边界**（hub 本身无认证，靠隧道隔离）。
  · 审计：JSONL 写 ~/stack/remote/audit.log（只记大小、不记输出正文）。

端到端：见 ~/stack/docs/PROGRESS.md「功能③」节。
"""
import glob
import json
import os
import posixpath
import re
import secrets
import shlex
import socket
import subprocess
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guga_exec import (DEF_TIMEOUT, MAX_TIMEOUT, SSH_BASE, classify,   # noqa: E402
                       run_ssh_alias)

HOME = os.path.expanduser("~")
HOSTS_JSON = os.path.join(HOME, "stack", "remote", "hosts.json")
AUDIT_LOG = os.path.join(HOME, "stack", "remote", "audit.log")
MEM_DIR = os.path.join(HOME, "stack", "remote", "memories")     # 每台机器一份专属记忆
SESSIONS_JSON = os.path.join(HOME, "stack", "remote", "sessions.json")  # 机器 → 它的对话 id
SITES_JSON = os.path.join(HOME, "stack", "remote", "sites.json")        # 站点地图（hub 第④ tab）
HUB_DIR = os.path.join(HOME, "stack", "hub")                            # 前端目录（扫 preview-*.html）
PORT = 8792

MEM_TEMPLATE = """# {name}（{alias}）

> 这台机器的**专属记忆**。只写与它有关的事（环境、路径、习惯、踩过的坑）；
> 通用的偏好/规矩写进总记忆（`~/.hermes/memories/MEMORY.md`），别混进来。

## 环境
- 系统：
- 用户名：
- 常用路径：

## 做过的事 / 约定

## 坑
"""

# 执行/判定相关的常量与逻辑统一在 guga_exec.py（与 join 服务共用，避免漂移）
PENDING_TTL = 120             # 待批有效期（秒）
PENDING_MAX = 32
TUNNEL_PORTS = list(range(22022, 22026))   # 反向隧道可用的回环端口（sshd 已放行这几个）
SERVER_HOST = "106.55.38.108"              # 本机公网 IP（目标机反连用）
TUNNEL_USER = "tunnel"                     # 服务器上那个受限隧道账户


def ops_pubkey():
    """服务器→目标机那把 ops 公钥（公开信息，给新机器装 authorized_keys 用）。"""
    try:
        with open(os.path.join(HOME, ".ssh", "guga_ops.pub"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

ENV = {
    "HOME": HOME,
    "PATH": "/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
}

# SSH_BASE 见 guga_exec.py（与 join 服务共用）

# 注：服务器本身不列入机器列表 —— 它自己就是「咕嘎一号」（管家住在上面），
# 要操作服务器直接跟管家说即可，不必在「本机操作」页里再出现一份。

_state_lock = threading.Lock()
_pending = {}                                 # id -> dict
_probe_cache = {}                             # alias -> (ts, online, rtt_ms, note)


# ────────────────────────── 主机 ──────────────────────────

def load_hosts():
    try:
        with open(HOSTS_JSON, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _probe_one(alias, h):
    """探一台机器是否可达。返回 (online, rtt_ms, note)。"""
    if h.get("via") == "reverse":
        port = int(h.get("listen_port", 22022))
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1.5).close()
        except OSError:
            return (False, 0, "隧道未监听")
    t0 = time.monotonic()
    try:
        r = subprocess.run(SSH_BASE + [alias, "exit"],
                           capture_output=True, text=True, timeout=8, env=ENV)
        ms = int((time.monotonic() - t0) * 1000)
        return (r.returncode == 0, ms, "" if r.returncode == 0 else "ssh 失败")
    except subprocess.TimeoutExpired:
        return (False, 0, "ssh 超时")
    except Exception as e:
        return (False, 0, f"探测异常: {type(e).__name__}")


def list_hosts():
    """机器列表 + 在线状态（20s 缓存；多台并发探）。"""
    hosts = load_hosts()
    now = time.time()
    todo = []
    out = []
    with _state_lock:
        for alias, h in hosts.items():
            if h.get("kind") != "own":
                continue                     # guest 不落盘、不列出
            c = _probe_cache.get(alias)
            if c and now - c[0] < 20:
                out.append((alias, h, c[1], c[2], c[3]))
            else:
                todo.append((alias, h))

    if todo:
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(lambda t: (t[0], t[1], *_probe_one(t[0], t[1])), todo))
        with _state_lock:
            for alias, h, on, ms, note in results:
                _probe_cache[alias] = (now, on, ms, note)
                out.append((alias, h, on, ms, note))

    items = [{"alias": a, "name": h.get("name", a), "kind": "own",
              "os": h.get("os", "linux"), "local": False,
              "listen_port": h.get("listen_port"),
              "online": on, "rtt_ms": ms, "note": note}
             for (a, h, on, ms, note) in sorted(out)]
    used = {int(h["listen_port"]) for h in load_hosts().values()
            if h.get("via") == "reverse" and h.get("listen_port")}
    return {"hosts": items, "checked_at": int(now),
            "tunnel_ports": TUNNEL_PORTS,
            "next_port": next((p for p in TUNNEL_PORTS if p not in used), None)}


# ────────────────── 每台机器的专属记忆 + 会话 ──────────────────

def _known_alias(alias):
    """别名必须是 hosts.json 里的自有机器。"""
    h = load_hosts().get(alias)
    if not h or h.get("kind") != "own":
        return None
    return h


def _safe(alias):
    return "".join(c for c in alias if c.isalnum() or c in "-_.")[:64]


def memo_path(alias):
    return os.path.join(MEM_DIR, _safe(alias) + ".md")


def load_memo(alias, name):
    """读机器记忆；没有就建一份模板。"""
    p = memo_path(alias)
    if not os.path.exists(p):
        try:
            os.makedirs(MEM_DIR, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(MEM_TEMPLATE.format(name=name, alias=alias))
        except OSError:
            return ""
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def load_sessions():
    try:
        with open(SESSIONS_JSON, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_session(alias, sid):
    with _state_lock:
        d = load_sessions()
        if sid:
            d[alias] = sid
        else:
            d.pop(alias, None)
        try:
            os.makedirs(os.path.dirname(SESSIONS_JSON), exist_ok=True)
            tmp = SESSIONS_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SESSIONS_JSON)
        except OSError:
            pass
    return d


# ────────────────────────── 站点地图（hub 第④ tab） ──────────────────────────
# 一份「本网站所有页面入口」的清单：主人自己登记，每条自带颜色与说明。
# 存 ~/stack/remote/sites.json；前端经 /api/remote/sites 读写（Caddy 路由已有，零基础设施改动）。

SITES_MAX = 200
SITE_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


# 手机版地址的默认配对（只给种子用；活数据在 sites.json，主人随时可改）
# 空字符串 = 只适合电脑（桌面站点地图里收在「Only PC」那节，手机端列表不列）
_MOB_DEFAULT = {"/": "/m.html", "/group.html": "/group.html",
                "/join.html": "/join.html", "/jiaxin/": "/jiaxin/"}


def _new_site_id():
    return secrets.token_hex(4)


def _site_seed():
    """首次运行写入的种子（主人可随意改删）。"""
    rows = [
        ("咕嘎 Hub", "/", "#7C8CFF", "管家聊天 · 编码 · 本机操作", True, False),
        ("管家终端", "/hermes", "#C6A15B", "直接跟咕嘎一号对话的终端（ttyd + tmux）", False, False),
        ("编码终端 claude", "/claude", "#C6A15B", "Claude Code 编码终端", False, False),
        ("编码终端 claude2", "/claude2", "#C6A15B", "Claude Code 编码终端（第二路）", False, False),
        ("编码终端 claude3", "/claude3", "#C6A15B", "Claude Code 编码终端（第三路）", False, False),
        ("工作区 shell", "/shell", "#30D158", "服务器上的工作区 shell", False, False),
        ("code-server", "http://localhost:8081/", "#2F6BE4", "VS Code 网页版（编码页左边那块）", False, False),
        ("Gitea", "http://localhost:3000/", "#2F6BE4", "自建 Git 仓库", False, False),
        ("咕嘎六号接入页", "/join.html", "#FF9F0A",
         "常驻入口：谁都能打开，把你这台电脑接入咕嘎六号（点同意 → 跑一条命令）", False, False),
    ]
    return [{"id": _new_site_id(), "name": n, "url": u, "color": c, "desc": d,
             "pinned": p, "temp": t, "murl": _MOB_DEFAULT.get(u, "")}
            for (n, u, c, d, p, t) in rows]


def load_sites():
    """读站点地图；文件不存在/坏了就写一份种子。"""
    try:
        with open(SITES_JSON, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("sites"), list):
            return d["sites"]
    except Exception:
        pass
    seed = _site_seed()
    save_sites(seed)
    return seed


def save_sites(lst):
    """原子写（tmp + replace），照 save_session 的写法。"""
    with _state_lock:
        try:
            os.makedirs(os.path.dirname(SITES_JSON), exist_ok=True)
            tmp = SITES_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"sites": lst}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SITES_JSON)
        except OSError:
            pass
    return lst


def _clean_url(u):
    """网址只接受 http(s):// 或站内相对路径 —— 挡 javascript:/data:（它会进 <a href>）。"""
    u = str(u or "").strip()[:500]
    if u.startswith("//"):
        return None            # 协议相对 → 也挡掉（会被当成外站）
    if u.startswith("/"):
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return None


def _clean_color(c):
    """颜色只收 #RRGGBB —— 它会进 style.background。"""
    c = str(c or "").strip()
    return c if SITE_COLOR_RE.match(c) else None


def _auto_sites():
    """自动发现的临时入口（只读，不落盘）：夜间小工程生成的预览页。"""
    out = []
    try:
        names = sorted(os.path.basename(p)
                       for p in glob.glob(os.path.join(HUB_DIR, "preview-*.html")))
    except Exception:
        names = []
    for n in names[:50]:
        short = n[len("preview-"):-len(".html")] if n.endswith(".html") else n
        out.append({"id": "auto:" + n, "name": "夜间预览 · " + short,
                    "url": "/" + n, "desc": "夜间小工程生成的预览页（自动发现 · 只读）",
                    "pinned": False, "temp": True, "auto": True})
    return out


def _site_from(body, cur):
    """从请求里取站点字段（缺省沿用 cur）；url 不合规 → None；手机版地址填了就必须合规。"""
    def pick(key, default=""):
        v = body.get(key)
        return cur.get(key, default) if v is None else v

    name = str(pick("name") or "").strip()[:60]
    url = _clean_url(pick("url"))
    if not name or not url:
        return None
    murl = str(pick("murl") or "").strip()
    if murl:
        murl = _clean_url(murl)
        if not murl:
            return None            # 手机版地址不合规：整条拒掉（别悄悄丢字段）
    color = _clean_color(pick("color")) or _clean_color(cur.get("color")) or "#7C8CFF"
    desc = str(pick("desc") or "").strip()[:200]
    temp = bool(pick("temp", False))
    return {"name": name, "url": url, "murl": murl, "color": color, "desc": desc, "temp": temp}


# ────────────────────────── 咕嘎群（多智能体聊天站） ──────────────────────────
# 主人 2026-10-12 定的口径：这是他「玩」的地方 —— 消息只要「发言人 + 时间 + 正文」，
# 不做任务卡片 / 状态机 / 待办流转。唯一要严谨的一笔：每条标清「本人发的」还是「代发」。
# 存 ~/stack/remote/group.json；前端经 /api/remote/group 读写（Caddy 路由已有，零基础设施改动）。
# 群信使（~/.hermes/scripts/group_relay.py）盯着这个文件：主人说完话，它叫醒对应的咕嘎回一句。

GROUP_JSON = os.path.join(HOME, "stack", "remote", "group.json")
GROUP_MAX = 2000                       # 只保留最近这么多条
GROUP_TEXT_MAX = 4000
GROUP_KEEP_GET = 400                   # 一次 GET 最多回这么多条

GROUP_MEMBERS = [
    {"id": "owner", "who": "主人", "color": "#E6B450", "note": "你本人"},
    {"id": "guga1", "who": "咕嘎一号", "color": "#2F6BE4", "note": "服务器管家（住在这台机器上）"},
    {"id": "guga3", "who": "咕嘎三号", "color": "#9AE6A0", "note": "WorkBuddy · 文件级成品"},
    {"id": "guga4", "who": "咕嘎四号", "color": "#A06BFF", "note": "LightVela · 轻量云上的 Hermes"},
    {"id": "guga5", "who": "咕嘎五号", "color": "#FFFFFF", "note": "ASUS 笔记本"},
    {"id": "guga6", "who": "咕嘎六号", "color": "#5AC8FA", "note": "接入记录官 · 常驻（接进别的机器时记账）"},
    {"id": "scout", "who": "咕嘎斥候", "color": "#1F7A45", "note": "热点与国内外大事"},
    {"id": "guga8", "who": "咕嘎八号", "color": "#F2764A", "note": "保安咕嘎 · 常驻（巡检与维护）"},
]
GROUP_WHOS = [m["who"] for m in GROUP_MEMBERS]


def _group_default():
    return {"messages": [], "meta": {"busy": None, "next_id": 1}, "updated_at": 0}


def load_group():
    try:
        with open(GROUP_JSON, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("messages"), list):
            d.setdefault("meta", {})
            d["meta"].setdefault("busy", None)
            d["meta"].setdefault("next_id", len(d["messages"]) + 1)
            return d
    except Exception:
        pass
    return _group_default()


def save_group(d):
    """原子写（tmp + replace），照 save_sites 的写法。"""
    with _state_lock:
        try:
            os.makedirs(os.path.dirname(GROUP_JSON), exist_ok=True)
            tmp = GROUP_JSON + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, GROUP_JSON)
        except OSError:
            pass
    return d


def group_post(who, text, via="本人", kind="闲聊", to=None):
    """往群里放一条。who 必须是名单里的；via 只收「本人」/「代发」；
    to = 点名器（主人点了谁的头像）——只让这些人回，空列表/缺省＝在线的都回。"""
    text = str(text or "").strip()[:GROUP_TEXT_MAX]
    if not text or who not in GROUP_WHOS:
        return None
    via = "代发" if str(via or "").strip() == "代发" else "本人"
    kind = str(kind or "闲聊").strip()[:12] or "闲聊"
    to = [t for t in (to or []) if isinstance(t, str) and t in GROUP_WHOS and t != "主人"]
    d = load_group()
    msgs = d["messages"]
    nid = int(d["meta"].get("next_id") or (len(msgs) + 1))
    msg = {"id": nid, "ts": int(time.time()), "who": who, "via": via,
           "kind": kind, "text": text}
    if to:
        msg["to"] = to[:len(GROUP_WHOS)]           # 只在真点了名时才带上，历史里干净
    msgs.append(msg)
    d["meta"]["next_id"] = nid + 1
    d["meta"]["busy"] = None            # 有人说话 —— 清掉「正在输入」
    if len(msgs) > GROUP_MAX:
        d["messages"] = msgs[-GROUP_MAX:]
    d["updated_at"] = int(time.time())
    save_group(d)
    return msg


def group_set_busy(who, on=True):
    d = load_group()
    d["meta"]["busy"] = {"who": who, "since": int(time.time())} if on else None
    save_group(d)
    return d["meta"]["busy"]


# 只读判定（classify）与执行（run / run_ssh_alias）都在 guga_exec.py，两个服务共用。


def _resolve(alias):
    """把别名解析成 host_info；未知 → KeyError。"""
    hosts = load_hosts()
    if alias not in hosts or hosts[alias].get("kind") != "own":
        raise KeyError(alias)
    return {"alias": alias, **hosts[alias]}


def _audit(alias, cmd, verdict, decision, res, client):
    rec = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "epoch": int(time.time()),
        "alias": alias, "cmd": cmd, "verdict": verdict, "decision": decision,
        "exit_code": res.get("exit_code"), "duration_ms": res.get("duration_ms"),
        "stdout_bytes": len(res.get("stdout") or ""),
        "stderr_bytes": len(res.get("stderr") or ""),
        "truncated": res.get("truncated", False),
        "timed_out": res.get("timed_out", False),
        "client": client,
    }
    line = json.dumps(rec, ensure_ascii=False)
    with _state_lock:
        try:
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    print(line, flush=True)


# ────────────────────────── HTTP ──────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "guga-remote/1.0"

    def log_message(self, *a):
        pass                                   # 静音（对齐 term-api.py）

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 64 * 1024:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return None

    def _client(self):
        return self.client_address[0] if self.client_address else ""

    # ---- GET ----
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/hosts":
            return self._json(list_hosts())
        if path == "/sites":
            return self._json({"sites": load_sites(), "auto": _auto_sites()})
        if path == "/group":
            d = load_group()
            return self._json({
                "members": GROUP_MEMBERS,
                "messages": d["messages"][-GROUP_KEEP_GET:],
                "busy": d["meta"].get("busy"),
                "last_id": d["messages"][-1]["id"] if d["messages"] else 0,
                "count": len(d["messages"]),
                "updated_at": d.get("updated_at", 0),
            })
        if path == "/machine":
            return self._machine_get()
        if path == "/enroll":
            return self._json({
                "ops_pubkey": ops_pubkey(),
                "server_host": SERVER_HOST,
                "tunnel_user": TUNNEL_USER,
                "tunnel_ports": TUNNEL_PORTS,
                "next_port": list_hosts().get("next_port"),
            })
        if path == "/health":
            return self._json({"ok": True})
        return self._json({"error": "not found", "code": 404}, 404)

    def _machine_get(self):
        """某台机器的专属记忆 + 它自己的对话 id。"""
        q = parse_qs(urlparse(self.path).query)
        alias = (q.get("alias") or [""])[0].strip()
        info = _known_alias(alias)
        if not info:
            return self._json({"error": "unknown host", "code": 400}, 400)
        name = info.get("name", alias)
        return self._json({
            "alias": alias, "name": name, "os": info.get("os", "linux"),
            "memory": load_memo(alias, name),
            "memo_path": memo_path(alias),
            "session_id": (load_sessions() or {}).get(alias),
        })

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        body = self._body()
        if body is None:
            return self._json({"error": "bad json body", "code": 400}, 400)
        if path == "/exec":
            return self._exec(body)
        if path == "/approve":
            return self._approve(body)
        if path == "/sites":
            return self._sites_post(body)
        if path == "/group":
            return self._group_post(body)
        if path == "/machine":
            alias = (body.get("alias") or "").strip()
            if not _known_alias(alias):
                return self._json({"error": "unknown host", "code": 400}, 400)
            save_session(alias, (body.get("session_id") or "").strip() or None)
            return self._json({"ok": True, "alias": alias})
        return self._json({"error": "not found", "code": 404}, 404)

    def _exec(self, body):
        alias = (body.get("host") or "").strip()
        cmd = (body.get("cmd") or "").strip()
        if not cmd:
            return self._json({"error": "empty cmd", "code": 400}, 400)
        try:
            info = _resolve(alias)
        except KeyError:
            return self._json({"error": "unknown host", "code": 400}, 400)

        os_ = info.get("os", "linux")
        verdict, reason = classify(cmd, os_)
        timeout = body.get("timeout", DEF_TIMEOUT)
        try:
            timeout = max(1, min(MAX_TIMEOUT, int(timeout)))
        except (TypeError, ValueError):
            timeout = DEF_TIMEOUT

        if verdict == "read":
            res = run_ssh_alias(info["alias"], cmd, timeout, env=ENV)
            _audit(alias, cmd, verdict, "auto", res, self._client())
            return self._json({"verdict": verdict, "ran": True, "host": alias,
                               "cmd": cmd, **res})

        pid = secrets.token_hex(4)
        now = time.time()
        with _state_lock:
            for k in [k for k, v in _pending.items() if v["expires_at"] < now]:
                _pending.pop(k, None)
            if len(_pending) >= PENDING_MAX:
                return self._json({"error": "too many pending", "code": 429}, 429)
            _pending[pid] = {"host": alias, "cmd": cmd, "verdict": verdict,
                             "reason": reason, "expires_at": now + PENDING_TTL,
                             "timeout": timeout}
        return self._json({"verdict": verdict, "ran": False, "need_confirm": True,
                           "id": pid, "reason": reason, "host": alias, "cmd": cmd,
                           "expires_at": int(now + PENDING_TTL)})

    def _approve(self, body):
        pid = (body.get("id") or "").strip()
        decision = (body.get("decision") or "").strip().lower()
        with _state_lock:
            item = _pending.pop(pid, None)
        if item is None:
            return self._json({"error": "expired or unknown id", "code": 410}, 410)
        if time.time() > item["expires_at"]:
            return self._json({"error": "expired or unknown id", "code": 410}, 410)

        alias, cmd = item["host"], item["cmd"]
        if decision not in ("yes", "y", "approve", "ok", "1", "true"):
            _audit(alias, cmd, item["verdict"], "denied",
                   {"exit_code": None, "duration_ms": None}, self._client())
            return self._json({"ok": True, "denied": True, "id": pid,
                               "host": alias, "cmd": cmd})
        try:
            info = _resolve(alias)
        except KeyError:
            return self._json({"error": "unknown host", "code": 400}, 400)
        res = run_ssh_alias(info["alias"], cmd, item["timeout"], env=ENV)
        _audit(alias, cmd, item["verdict"], "approved", res, self._client())
        return self._json({"ok": True, "denied": False, "id": pid, "verdict": item["verdict"],
                           "host": alias, "cmd": cmd, **res})

    # ---- 站点地图：增 / 改 / 删 / 重排 / 置顶（每次都回整份列表） ----
    def _sites_post(self, body):
        action = (body.get("action") or "").strip()
        sites = load_sites()                       # 注意：此处不持锁（save_sites 自己会加）
        if action == "add":
            if len(sites) >= SITES_MAX:
                return self._json({"error": "站点太多啦（上限 %d）" % SITES_MAX, "code": 429}, 429)
            item = _site_from(body, {})
            if item is None:
                return self._json({"error": "名称和网址都要填；网址要 http(s):// 或以 / 开头",
                                   "code": 400}, 400)
            item["id"] = _new_site_id()
            item["pinned"] = False
            sites.append(item)
        elif action == "update":
            cur = self._find_site(sites, body)
            if cur is None:
                return self._json({"error": "unknown id", "code": 404}, 404)
            upd = _site_from(body, cur)
            if upd is None:
                return self._json({"error": "名称和网址都要填；网址要 http(s):// 或以 / 开头",
                                   "code": 400}, 400)
            cur.update(upd)
        elif action == "delete":
            sid = (body.get("id") or "").strip()
            sites = [s for s in sites if s.get("id") != sid]
        elif action == "pin":
            cur = self._find_site(sites, body)
            if cur is None:
                return self._json({"error": "unknown id", "code": 404}, 404)
            cur["pinned"] = not bool(cur.get("pinned"))
            if cur["pinned"]:                      # 置顶 = 挪到最前
                sites.remove(cur)
                sites.insert(0, cur)
        elif action == "reorder":
            order = body.get("ids")
            if not isinstance(order, list):
                return self._json({"error": "ids 必须是数组", "code": 400}, 400)
            rank = {str(x): i for i, x in enumerate(order)}
            sites.sort(key=lambda s: rank.get(str(s.get("id")), len(rank) + 1))
        else:
            return self._json({"error": "unknown action", "code": 400}, 400)

        save_sites(sites)
        return self._json({"ok": True, "sites": sites, "auto": _auto_sites()})

    @staticmethod
    def _find_site(sites, body):
        sid = (body.get("id") or "").strip()
        return next((s for s in sites if s.get("id") == sid), None)

    # ---- 咕嘎群：发言 / 删一条 / 「正在输入」态（每次都回整份最近消息） ----
    def _group_post(self, body):
        action = (body.get("action") or "post").strip()
        if action == "post":
            who = (body.get("who") or "").strip()
            if who not in GROUP_WHOS:
                return self._json({"error": "发言人要是群名单里的：%s" % "、".join(GROUP_WHOS),
                                   "code": 400}, 400)
            msg = group_post(who, body.get("text"), body.get("via", "本人"),
                             body.get("kind", "闲聊"), body.get("to"))
            if msg is None:
                return self._json({"error": "正文不能是空的", "code": 400}, 400)
            return self._json({"ok": True, "message": msg})
        if action == "busy":
            who = (body.get("who") or "咕嘎一号").strip()
            if who not in GROUP_WHOS:
                who = "咕嘎一号"
            return self._json({"ok": True, "busy": group_set_busy(who, bool(body.get("on", True)))})
        if action == "delete":
            try:
                mid = int(body.get("id"))
            except (TypeError, ValueError):
                return self._json({"error": "id 要是个数字", "code": 400}, 400)
            d = load_group()
            n0 = len(d["messages"])
            d["messages"] = [m for m in d["messages"] if m.get("id") != mid]
            save_group(d)
            return self._json({"ok": True, "removed": n0 - len(d["messages"])})
        return self._json({"error": "unknown action", "code": 400}, 400)


def main():
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print(f"guga-remote-api listening on 127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
