#!/usr/bin/env python3
"""咕嘎 · 远程执行公共引擎（只读判定 + 跑命令 + 超时/截断）。

两个服务共用，避免判定逻辑各写一份、日久漂移：
  · ~/stack/remote/remote-api.py  —— 自有机器（咕嘎五号那套，走 ~/.ssh/config 别名）
  · /opt/guga-join/join_api.py    —— 别人的机器（咕嘎六号，走临时密钥 + 指定端口）

本文件是从 remote-api.py **逐字搬移**出来的，不改判定行为。
"""
import posixpath
import shlex
import subprocess
import threading
import time

DEF_TIMEOUT = 30
MAX_TIMEOUT = 120
OUT_CAP = 256 * 1024          # 单路输出上限（超出截断）
SSH_CONCURRENCY = 4           # 同时最多几个 ssh（4 核 4G）

SSH_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

SSH_BASE = ["ssh",
            "-o", "ConnectTimeout=8",
            "-o", "BatchMode=yes",
            "-o", "NumberOfPasswordPrompts=0",
            "-o", "StrictHostKeyChecking=accept-new"]

_sem = threading.BoundedSemaphore(SSH_CONCURRENCY)


def env_for(home):
    """给子进程的环境（HOME 随调用方，PATH 固定）。"""
    return {"HOME": home, "PATH": SSH_PATH, "LANG": "C.UTF-8"}


# ────────────────────── 只读判定（确认门）──────────────────────

POSIX_META = set(";|&<>`$\n\r")
WIN_META = set("&|<>%\n\r")

POSIX_READ = {
    "ls", "cat", "head", "tail", "wc", "file", "stat", "du", "df", "find", "grep",
    "egrep", "fgrep", "rg", "tree", "pwd", "whoami", "id", "hostname", "uname",
    "uptime", "date", "free", "env", "printenv", "echo", "which", "type", "nproc",
    "lscpu", "lsblk", "lsusb", "lsof", "getent", "dig", "host", "nslookup", "ping",
    "traceroute", "ip", "ss", "netstat", "ps", "pgrep", "journalctl", "systemctl",
    "git", "docker", "podman", "top", "w", "last", "groups", "sort", "uniq", "cut",
    "awk", "tr", "column", "jq", "md5sum", "sha256sum",
}
POSIX_READ_SUBCMD = {
    "git": {"status", "log", "diff", "show", "branch", "remote", "describe",
            "rev-parse", "ls-files", "blame", "shortlog", "tag", "config"},
    "docker": {"ps", "images", "logs", "inspect", "version", "info", "port", "history"},
    "podman": {"ps", "images", "logs", "inspect", "version", "info", "port", "history"},
    "systemctl": {"status", "is-active", "is-enabled", "is-failed", "show",
                  "list-units", "list-unit-files", "cat", "list-timers"},
}
# 需要额外守卫的动词（含子命令/flag 才安全）
POSIX_NOFOLLOW = {"tail", "journalctl"}

WIN_READ = {
    "dir", "type", "hostname", "whoami", "ipconfig", "systeminfo", "tasklist", "ver",
    "date", "time", "ping", "tracert", "pathping", "netstat", "nslookup", "where",
    "findstr", "find", "echo", "set", "path", "cd", "chdir", "vol", "tree", "fc",
    "more", "getmac", "gpresult", "driverquery", "chkdsk", "wmic", "reg", "sc",
}
WIN_READ_SUBCMD = {"reg": {"query"}, "sc": {"query", "qc"}}

DANGER_POSIX = {"rm", "rmdir", "mkfs", "mke2fs", "dd", "shutdown", "reboot", "halt",
                "poweroff", "fdisk", "parted", "wipefs", "chmod", "chown", "chgrp",
                "mount", "umount", "kill", "killall", "pkill", "useradd", "userdel",
                "passwd", "visudo", "iptables", "ufw", "truncate", "shred"}
DANGER_WIN = {"format", "diskpart", "del", "erase", "rd", "rmdir", "shutdown",
              "taskkill", "bcdedit", "cipher", "takeown", "icacls", "attrib",
              "net", "netsh", "sfc", "runas"}


def base(tok):
    tok = tok.replace("\\", "/")
    b = posixpath.basename(tok).lower()
    if b.endswith(".exe"):
        b = b[:-4]
    return b


def classify(cmd, os_):
    """返回 (verdict, reason)。verdict ∈ read|write|danger。default-deny。"""
    s = cmd.strip()
    if not s:
        return ("write", "空命令")

    meta = WIN_META if os_ == "windows" else POSIX_META
    if set(s) & meta:
        return ("danger", "含 shell 元字符（组合/重定向），必须确认")

    try:
        toks = s.split() if os_ == "windows" else shlex.split(s)
    except ValueError:
        return ("danger", "命令无法解析（引号不闭合）")
    if not toks:
        return ("write", "空命令")

    first = base(toks[0])
    low = [t.lower() for t in toks[1:]]

    # PowerShell 直发 cmdlet：Get-* 视为只读
    if first.startswith("get-"):
        return ("read", "PowerShell Get-* 只读")
    if first in ("powershell", "pwsh", "cmd"):
        return ("danger", "显式调用 shell，必须确认")

    if os_ == "windows":
        if first in WIN_READ_SUBCMD:
            subs = WIN_READ_SUBCMD[first]
            if any(t in subs for t in low[:2]):
                return ("read", f"{first} 查询类子命令")
            return ("write", f"{first} 非查询子命令")
        if first == "wmic":
            return ("read", "wmic get") if "get" in low else ("write", "wmic 非 get 子句")
        if first == "chkdsk" and any(f in low for f in ("/f", "/r", "/b", "/x")):
            return ("write", "chkdsk 带修复参数")
        if first in WIN_READ:
            return ("read", "Windows 只读白名单")
        if first in DANGER_WIN:
            return ("danger", f"危险命令：{first}")
        return ("write", "不在只读白名单")

    # POSIX
    if first in POSIX_READ_SUBCMD:
        subs = POSIX_READ_SUBCMD[first]
        if first == "git" and low and low[0] == "config":
            return ("read", "git config 需 --get") if "--get" in low else ("write", "git config 可能写入")
        if low and low[0] in subs:
            if first in ("docker", "podman") and low[0] == "logs" and any(
                    f in low[1:] for f in ("-f", "--follow")):
                return ("write", "logs -f 会一直挂住")
            return ("read", f"{first} 只读子命令")
        return ("write", f"{first} 非只读子命令")
    if first in POSIX_NOFOLLOW and any(f in low for f in ("-f", "--follow")):
        return ("write", f"{first} -f 会一直挂住")
    if first == "find" and any(a in low for a in
                               ("-delete", "-exec", "-execdir", "-ok", "-okdir",
                                "-fprint", "-fprintf", "-fls")):
        return ("write", "find 带写操作")
    if first == "top" and "-b" not in low:
        return ("write", "top 非批处理模式会挂住")
    if first == "sort" and "-o" in low:
        return ("write", "sort -o 会写文件")
    if first in POSIX_READ:
        return ("read", "POSIX 只读白名单")
    if first in DANGER_POSIX:
        return ("danger", f"危险命令：{first}")
    return ("write", "不在只读白名单")


# ────────────────────────── 执行 ──────────────────────────

def collect(p, t0, timeout):
    try:
        out, err = p.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        timed_out = True
    ms = int((time.monotonic() - t0) * 1000)
    trunc = len(out) > OUT_CAP or len(err) > OUT_CAP
    return {"exit_code": p.returncode, "stdout": out[:OUT_CAP], "stderr": err[:OUT_CAP],
            "duration_ms": ms, "truncated": trunc, "timed_out": timed_out}


def run(argv, timeout=DEF_TIMEOUT, env=None):
    """跑一条命令（argv 列表，不经本地 shell）。带并发闸 + 超时 + 截断。"""
    t0 = time.monotonic()
    try:
        timeout = max(1, min(MAX_TIMEOUT, int(timeout)))
    except (TypeError, ValueError):
        timeout = DEF_TIMEOUT
    try:
        with _sem:
            p = subprocess.Popen(argv,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, errors="replace", env=env or env_for("/tmp"),
                                 stdin=subprocess.DEVNULL)
            return collect(p, t0, timeout)
    except Exception as e:
        return {"exit_code": None, "stdout": "", "stderr": f"{type(e).__name__}: {e}",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "truncated": False, "timed_out": False}


def run_ssh_alias(alias, cmd, timeout=DEF_TIMEOUT, env=None):
    """经 ~/.ssh/config 里的别名跑一条命令。"""
    return run(SSH_BASE + [alias, cmd], timeout, env)
