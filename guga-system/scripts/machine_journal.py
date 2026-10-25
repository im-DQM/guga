#!/usr/bin/env python3
"""machine_journal.py —— 每台自有机器的「工作和改动」流水。

主人 2026-10-13 定的分工：**五号只记它自己那台笔记本（ASUS）上的工作和改动**；
接入那摊（谁接进来过）归咕嘎六号，两边不串。

两台来源：
  · 手记（我和那台机器的咕嘎干完活儿各写一条）—— `--add`
  · 自动：从 `~/stack/remote/audit.log` 里搬「改动类」的命令（写了/危险命令且被放行的），
    只读命令不搬（不然日志全是 ls、cat）。`--auto` 由 cron 每 15 分钟跑一次。

存：`~/stack/remote/journal/<alias>.md`（人话，按天分节）＋ `journal/state.json`（自动搬的偏移）

用法：
  machine_journal.py --host win-asus --add "在五号上装了 node 并验证版本"
  machine_journal.py --host win-asus --read -n 30
  machine_journal.py --auto                # 所有自有机器，从审计里搬改动
"""
import argparse
import json
import os
import sys
import time

HOME = os.path.expanduser("~")
JDIR = os.path.join(HOME, "stack", "remote", "journal")
STATE = os.path.join(JDIR, "state.json")
AUDIT = os.path.join(HOME, "stack", "remote", "audit.log")
HOSTS = os.path.join(HOME, "stack", "remote", "hosts.json")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except Exception:  # noqa: BLE001
        return default


def save_json(path, d):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def journal_path(alias):
    safe = "".join(c for c in alias if c.isalnum() or c in "-_.")[:64]
    return os.path.join(JDIR, safe + ".md")


def append(alias, text, who="一号", kind="手记"):
    text = (text or "").strip()
    if not text:
        return False
    os.makedirs(JDIR, exist_ok=True)
    p = journal_path(alias)
    day = time.strftime("%Y-%m-%d")
    hdr = "# %s · 工作与改动\n\n> 这台机器上做过什么、改过什么。主人定的：**这台机器的账归它自己的咕嘎（五号）记**。\n" % alias
    body = open(p, encoding="utf-8").read() if os.path.exists(p) else hdr
    stamp = time.strftime("%H:%M")
    line = "- `%s` **%s**：%s" % (stamp, who, text) if kind == "手记" else "- `%s` **改动**：`%s`" % (stamp, text)
    if ("## " + day) in body:
        body = body.rstrip() + "\n" + line + "\n"
    else:
        body = body.rstrip() + "\n\n## " + day + "\n\n" + line + "\n"
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return True


def auto_move(verbose=True):
    """把审计里的「改动类」记录搬进对应机器的日志。"""
    st = load_json(STATE, {})
    hosts = load_json(HOSTS, {})
    if not os.path.exists(AUDIT):
        return 0
    size = os.path.getsize(AUDIT)
    off = int(st.get("audit_offset") or 0)
    if off > size:
        off = 0
    moved = 0
    try:
        with open(AUDIT, encoding="utf-8") as f:
            f.seek(off)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                alias = rec.get("alias")
                verdict = (rec.get("verdict") or "").lower()
                decision = (rec.get("decision") or "").lower()
                cmd = (rec.get("cmd") or "").strip()
                if not alias or not cmd:
                    continue
                if alias not in hosts:          # 只认 hosts.json 里的自有机器（挡掉 "local" 这类旧测试记录）
                    continue
                if verdict and verdict != "read" and decision in ("approved", "auto"):
                    code = rec.get("exit_code")
                    tail = "" if code in (0, None) else "（退出码 %s）" % code
                    append(alias, cmd[:200] + tail, kind="自动")
                    moved += 1
            st["audit_offset"] = f.tell()
            save_json(STATE, st)
    except OSError:
        pass
    if verbose:
        print("搬了 %d 条改动" % moved)
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--add")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("-n", type=int, default=25)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--who", default="一号")
    a = ap.parse_args()

    if a.auto:
        auto_move()
        return 0
    if not a.host:
        ap.print_help()
        return 2
    if a.add:
        ok = append(a.host, a.add, who=a.who)
        print("已记：%s" % a.add if ok else "没记上（内容为空？）")
        return 0 if ok else 1
    if a.read:
        p = journal_path(a.host)
        if not os.path.exists(p):
            print("（%s 还没有日志）" % a.host)
            return 0
        lines = open(p, encoding="utf-8").read().splitlines()
        print("\n".join(lines[-(a.n + 10):]))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
