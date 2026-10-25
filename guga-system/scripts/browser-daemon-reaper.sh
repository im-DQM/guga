#!/usr/bin/env bash
# cron 入口（cron 只认 ~/.hermes/scripts/ 下的真实文件，软链会被拦成 "resolves outside"）。
# 真身：~/.hermes/guga/guga8/scripts/browser-daemon-reaper.py（八号 · 保安咕嘎）
# 例行清理静默（只写日志），有异常才出声。
#
# 2026-10-20 主人拍板「巡检自动清理就行」：
#   · 空闲阈值 2h → 1h（判定仍是「无客户端连接 + CPU 不动」，在用的永不碰）
#   · 打开会话数量上限：超过 10 个就收最旧的（常驻档案/在用的不算）
#   清理不再问主人；只有失败或碰到常驻档案这类异常才出声。
export REAPER_TTL_SECONDS="${REAPER_TTL_SECONDS:-3600}"
export REAPER_BROWSER_TTL_SECONDS="${REAPER_BROWSER_TTL_SECONDS:-3600}"
exec /usr/bin/python3 "$HOME/.hermes/guga/guga8/scripts/browser-daemon-reaper.py" --quiet --max-sessions 10 "$@"
