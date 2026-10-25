#!/usr/bin/env bash
# 每 15 分钟：把解析出的「改动类」命令搬进对应自有机器的日志
# （主人 2026-10-13 定的分工：机器上的工作与改动，各归各家的咕嘎记 —— 五号记它那台笔记本）。
# 静默作业：没事就一个字都不输出；出错才说一句（cron 以 no_agent 方式跑，stdout 即消息）。
set -uo pipefail
out=$(python3 /home/ubuntu/.hermes/scripts/machine_journal.py --auto 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "机器日志的自动搬运失败了（退出码 $rc）：$out"
fi
exit 0
