#!/usr/bin/env python3
"""cron 入口（cron 只认 ~/.hermes/scripts/ 下的真实文件，软链会被拦）。
真身：~/.hermes/guga/guga8/scripts/swap-patrol.py（八号 · 保安咕嘎）"""
import os
import sys

REAL = os.path.expanduser("~/.hermes/guga/guga8/scripts/swap-patrol.py")
if not os.path.exists(REAL):
    sys.exit("swap-patrol 真身不在：%s" % REAL)
os.execv(sys.executable, [sys.executable, REAL, *sys.argv[1:]])
