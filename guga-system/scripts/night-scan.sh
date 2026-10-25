#!/usr/bin/env bash
# 夜间调研启动器（每晚 01:00，no_agent）：
# 让一个后台的 hermes 一次性会话上网看看被广泛认可的 agent 小工具/小功能，
# 挑出适合本部署的 2–3 条候选，**追加**到想法文件 ~/.hermes/ideas.md 的「## 可做的小工程（候选池）」节（只写候选，不执行）。
# 本脚本自己不输出任何东西 —— 收件箱保持干净，候选由晚报呈现。
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/1000

# 候选只活一晚：主人没批准的、过夜了就删（归档到 knowledge/idea-history.md 供去重）。
# 放在「今晚先不做」判断之前 —— 那一晚不做，也不该把旧候选留着。
python3 /home/ubuntu/.hermes/scripts/idea_pool.py prune >/dev/null 2>&1 || true

# 「今晚先不做」开关：文件里出现今天的日期就整夜跳过（日期过了自动恢复）
PAUSE_FILE="/home/ubuntu/.hermes/.nightly-pause"
if [ -f "$PAUSE_FILE" ] && grep -qx "${NIGHT_TODAY:-$(date +%F)}" "$PAUSE_FILE"; then exit 0; fi

PROMPT_FILE="/home/ubuntu/.hermes/scripts/night-scan-prompt.txt"
LOG_DIR="/home/ubuntu/.hermes/logs"
LOCK="/home/ubuntu/.hermes/.night-scan.pid"
LOG="$LOG_DIR/night-scan-$(date +%F).log"

mkdir -p "$LOG_DIR"
[ -f "$PROMPT_FILE" ] || exit 0

# 已有一次在跑 → 不重复起
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then exit 0; fi

# 资源兜底：内存可用低于 250MB 就别再起任务
avail=$(free -m | awk 'NR==2{print $7}')
[ "${avail:-0}" -lt 250 ] && exit 0

cd /home/ubuntu || exit 0
setsid nohup hermes chat -q "$(cat "$PROMPT_FILE")" >>"$LOG" 2>&1 &
echo $! > "$LOCK"
exit 0
