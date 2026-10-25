#!/usr/bin/env bash
# 一行服务器资源摘要 —— 给早报（或手动）用：磁盘 / 内存 / Swap / 负载
set -uo pipefail
mem=$(free -m | awk 'NR==2{printf "%dMB 已用 / %dMB 总（可用 %dMB）", $3, $2, $7}')
swp=$(free -m | awk 'NR==3{printf "%dMB / %dMB", $3, $2}')
dsk=$(df -h / | awk 'NR==2{printf "%s 已用 / %s（%s）", $3, $2, $5}')
load=$(cut -d' ' -f1-3 /proc/loadavg)
printf '磁盘 %s；内存 %s；Swap %s；负载 %s\n' "$dsk" "$mem" "$swp" "$load"
