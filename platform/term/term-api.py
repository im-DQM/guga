#!/usr/bin/env python3
"""咕嘎 · claude 窗口管理小服务（给 hub 的「+ 新建 claude」用）

一个 tmux 会话 = 一组 claude；每个 tmux 窗口 = 一个独立 claude 对话。
监听 127.0.0.1:8791，端点（经 Caddy /api/term/* 转发）：
  GET /list          -> {"windows":[{"i":0,"active":true}, ...]}
  GET /new           -> 新建一个跑 claude 的窗口，返回 {"i": <index>}
  GET /select?i=N    -> 切到窗口 N
  GET /kill?i=N      -> 关掉窗口 N（最后一个窗口不允许关）
"""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

SESSION = "claude"
STARGET = SESSION + ":"  # 显式会话目标（避免和同名的窗口冲突）
CWD = "/home/ubuntu/workspace"
CLAUDE = "/usr/bin/claude"
MAX_WINDOWS = 8
ENV = {**os.environ, "HOME": "/home/ubuntu",
       "PATH": "/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True, env=ENV)


def windows():
    r = tmux("list-windows", "-t", STARGET, "-F", "#{window_index}\t#{window_active}")
    out = []
    if r.returncode != 0:
        return out
    for ln in r.stdout.strip().splitlines():
        p = ln.split("\t")
        if len(p) >= 2:
            out.append({"i": int(p[0]), "active": p[1] == "1"})
    return out


def ensure_session(idx):
    """保证会话存在"""
    if tmux("has-session", "-t", STARGET).returncode != 0:
        return tmux("new-session", "-d", "-s", SESSION, "-c", CWD, CLAUDE).returncode == 0
    return True


class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        if p.endswith("/list"):
            return self._json({"windows": windows()})
        if p.endswith("/new"):
            if not ensure_session(0):
                return self._json({"error": "no session"}, 500)
            if len(windows()) >= MAX_WINDOWS:
                return self._json({"error": "max %d" % MAX_WINDOWS}, 400)
            r = tmux("new-window", "-t", STARGET, "-c", CWD, "-P", "-F", "#{window_index}", CLAUDE)
            if r.returncode != 0:
                return self._json({"error": r.stderr.strip()}, 500)
            idx = int(r.stdout.strip())
            tmux("select-window", "-t", "%s:%d" % (SESSION, idx))
            return self._json({"i": idx})
        if p.endswith("/select"):
            i = q.get("i", ["0"])[0]
            r = tmux("select-window", "-t", "%s:%s" % (SESSION, i))
            return self._json({"ok": r.returncode == 0})
        if p.endswith("/kill"):
            i = q.get("i", [None])[0]
            if i is None:
                return self._json({"error": "i required"}, 400)
            if len(windows()) <= 1:
                return self._json({"error": "keep one"}, 400)
            tmux("kill-window", "-t", "%s:%s" % (SESSION, i))
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8791), H).serve_forever()
