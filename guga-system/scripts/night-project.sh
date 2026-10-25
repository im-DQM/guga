#!/usr/bin/env bash
# 夜间小工程启动器（每晚 02:00，no_agent）：
# 把「主人已批准的一件小改进」交给一个后台的 hermes 一次性会话去做，产出**预览**（不上线），
# 结果由那个后台会话自己写成【夜间预览】报告落进收件箱。
# 本脚本自己不输出任何东西 —— 保持收件箱里只有真正的成果。
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/1000

# 「今晚先不做」开关：文件里出现今天的日期就整夜跳过（日期过了自动恢复）
PAUSE_FILE="/home/ubuntu/.hermes/.nightly-pause"
if [ -f "$PAUSE_FILE" ] && grep -qx "${NIGHT_TODAY:-$(date +%F)}" "$PAUSE_FILE"; then exit 0; fi

APPROVED="/home/ubuntu/.hermes/night-approved.md"
PROMPT_FILE="/home/ubuntu/.hermes/scripts/night-project-prompt.txt"
LOG_DIR="/home/ubuntu/.hermes/logs"
LOCK="/home/ubuntu/.hermes/.night-project.pid"
LOG="$LOG_DIR/night-project-$(date +%F).log"

mkdir -p "$LOG_DIR" /home/ubuntu/.hermes/previews

# 批准清单里没有未完成项 → 静默跳过（绝不自己挑活）
[ -f "$APPROVED" ] || exit 0
grep -q '^- \[ \]' "$APPROVED" || exit 0

# 已有一次在跑 → 不重复起
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then exit 0; fi

# 资源兜底：内存可用低于 250MB 就别再起任务
avail=$(free -m | awk 'NR==2{print $7}')
[ "${avail:-0}" -lt 250 ] && exit 0

cd /home/ubuntu || exit 0
setsid nohup hermes chat -q "$(cat "$PROMPT_FILE")" >>"$LOG" 2>&1 &
echo $! > "$LOCK"
exit 0
