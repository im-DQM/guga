#!/usr/bin/env bash
# 到期巡检（每 5 分钟跑一次，no_agent 任务）：有到点未完成的条目就输出提醒，否则什么都不输出。
# 顺带清理自己以前「静默运行」留下的空壳记录文件（只有头部、没有正文），免得每 5 分钟堆一个。

DIR="/home/ubuntu/.hermes/cron/output/1c6aae0c4875"
if [ -d "$DIR" ]; then
  now=$(date +%s)
  for f in "$DIR"/*.md; do
    [ -e "$f" ] || continue
    [ $(( now - $(stat -c %Y "$f") )) -gt 3600 ] || continue      # 只清一小时前的
    grep -q '^---' "$f" || rm -f "$f"                             # 没有正文分隔线＝空壳
  done
fi

exec python3 /home/ubuntu/.hermes/scripts/todo.py due-check
