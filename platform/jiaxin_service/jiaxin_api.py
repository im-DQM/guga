#!/usr/bin/env python3
"""jiaxin_api.py — 《我的夹心》的数据接口（单文件网页的服务器端存储）。

绑 127.0.0.1:8794，由 Caddy 经 handle_path /api/jiaxin/* 反代（会剥掉前缀），
所以本服务看到的路径是裸的 /data、/health。

设计要点：
  · 整包读、整包写：前端把整个 state 当一份 JSON 发上来（几十 KB），
    服务端不解析结构、只认 rev 号，改动逻辑仍在前端 migrate() 里。
  · 原子写：先写 data.json.tmp 再 os.replace，断电/并发不会读到半截文件。
  · 留一份 data.json.bak：每次成功写入前把上一版挪过去，出问题能捞回来。
  · LWW（后写覆盖）：多设备同时改时以最后到达的为准；rev 只做「有人抢先了」的提示。
  · 无认证 —— 与 hub 其它接口（todos / remote / join）一致：只绑回环，靠隧道隔离。

接口：
  GET  /api/jiaxin/data            -> {"rev":int,"updated_at":iso|null,"data":{...}|null}
  PUT  /api/jiaxin/data  {...}      -> {"ok":true,"rev":int,"updated_at":iso,"conflict":bool}
  POST /api/jiaxin/data  {...}      -> 同上（sendBeacon 只能发 POST，卸载时用）
  GET  /api/jiaxin/health          -> {"ok":true}
"""
import json
import os
import shutil
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
DATA_BAK = os.path.join(HERE, "data.json.bak")
PORT = 8794
MAX_BODY = 2 * 1024 * 1024          # 2MB；日记会越长越长，比 remote 的 64KB 放宽
_lock = threading.Lock()


def _load():
    """读整包。返回 (rev, updated_at, data)；文件缺失/损坏 → (0, None, None)。"""
    try:
        with open(DATA, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("data"), (dict, list)):
            return int(d.get("rev") or 0), d.get("updated_at"), d["data"]
    except Exception:
        pass
    return 0, None, None


def _save(data, client_rev):
    """原子写整包，返回 (new_rev, updated_at, conflict)。"""
    with _lock:
        cur_rev, _, _ = _load()
        conflict = client_rev is not None and client_rev < cur_rev
        new_rev = cur_rev + 1
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = {"rev": new_rev, "updated_at": now, "data": data}
        tmp = DATA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        try:
            if os.path.exists(DATA):
                shutil.copyfile(DATA, DATA_BAK)      # 上一版留底
            os.replace(tmp, DATA)                    # 原子替换
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return new_rev, now, conflict


class Handler(BaseHTTPRequestHandler):
    server_version = "guga-jiaxin/1.0"

    def log_message(self, *a):
        pass

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
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return None

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/data", "/"):
            rev, ts, data = _load()
            return self._json({"rev": rev, "updated_at": ts, "data": data})
        if path == "/health":
            return self._json({"ok": True})
        return self._json({"error": "not found", "code": 404}, 404)

    def _put(self):
        body = self._body()
        if body is None or not isinstance(body.get("data"), (dict, list)):
            return self._json({"error": "bad json body", "code": 400}, 400)
        try:
            rev = int(body.get("rev")) if body.get("rev") is not None else None
        except (TypeError, ValueError):
            rev = None
        new_rev, ts, conflict = _save(body["data"], rev)
        return self._json({"ok": True, "rev": new_rev, "updated_at": ts, "conflict": conflict})

    do_PUT = _put
    do_POST = _put


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print(f"guga-jiaxin-api listening on 127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
