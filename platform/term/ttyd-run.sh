#!/usr/bin/env bash
# ttyd-run.sh <port> <base-path> <session-name> <command...>
# 统一给网页终端套深色主题；强调色可用环境变量覆盖：
#   TTYD_ACCENT（主色，不带 #，默认 7C8CFF 靛紫）
#   TTYD_GOLD  （点缀/黄，不带 #，默认 FF9F0A）
set -euo pipefail
port="$1"; base="$2"; session="$3"; shift 3
A="#${TTYD_ACCENT:-7C8CFF}"
G="#${TTYD_GOLD:-FF9F0A}"
THEME="{\"background\":\"#0A0A0A\",\"foreground\":\"#EDEDEF\",\"cursor\":\"$A\",\"cursorAccent\":\"#0A0A0A\",\"selectionBackground\":\"${A}55\",\"black\":\"#1E1E22\",\"red\":\"#FF453A\",\"green\":\"#30D158\",\"yellow\":\"$G\",\"blue\":\"$A\",\"magenta\":\"#BF8CFF\",\"cyan\":\"#5AC8FA\",\"white\":\"#EDEDEF\",\"brightBlack\":\"#6B6B72\",\"brightRed\":\"#FF6B60\",\"brightGreen\":\"#5BE07E\",\"brightYellow\":\"$G\",\"brightBlue\":\"$A\",\"brightMagenta\":\"#D0A6FF\",\"brightCyan\":\"#7FDBFF\",\"brightWhite\":\"#FFFFFF\"}"
exec /usr/bin/ttyd -p "$port" -b "$base" -W -i 0.0.0.0 \
  -t "theme=$THEME" \
  -t fontSize=14 \
  -t fontFamily="Consolas, 'Microsoft YaHei', monospace" \
  -t scrollback=5000 \
  /opt/term/term.sh "$session" "$@"
