#!/usr/bin/env bash
# 把文件传到咕嘎五号（ASUS 笔记本）的 D:\咕嘎5号\ —— 主人 2026-10-25 定的落地点
# 用法：
#   push_guga5.sh 文件...            传到 D:\咕嘎5号\
#   push_guga5.sh -s 简历 文件...    传到 D:\咕嘎5号\简历\
#   push_guga5.sh -l [子目录]        只看那边有什么
set -euo pipefail

ROOT='D:\咕嘎5号'
TMP='C:\Users\ASUS\AppData\Local\Temp\guga5up'
HOST=win-asus
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)

if [ "${1:-}" = "-l" ]; then
  sub="${2:-}"
  target="$ROOT${sub:+\\$sub}"
  timeout 60 ssh "${SSH_OPTS[@]}" "$HOST" "chcp 65001 > \$null; [Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-ChildItem '$target' | Select-Object Name,@{n='KB';e={[math]::Round(\$_.Length/1KB,1)}},LastWriteTime | Format-Table -AutoSize"
  exit 0
fi

SUB=''
if [ "${1:-}" = "-s" ]; then
  SUB="$2"; shift 2
fi
[ "$#" -ge 1 ] || { echo "用法：$0 [-s 子目录] 文件... | -l [子目录]"; exit 2; }

target="$ROOT${SUB:+\\$SUB}"
timeout 300 scp "${SSH_OPTS[@]}" "$@" "$HOST:$TMP/"
timeout 120 ssh "${SSH_OPTS[@]}" "$HOST" "chcp 65001 > \$null; [Console]::OutputEncoding=[Text.Encoding]::UTF8; New-Item -ItemType Directory -Force -Path '$target' | Out-Null; Move-Item '$TMP\*' '$target' -Force; Get-ChildItem '$target' | Where-Object { \$_.LastWriteTime -gt (Get-Date).AddMinutes(-10) } | Select-Object Name,@{n='KB';e={[math]::Round(\$_.Length/1KB,1)}} | Format-Table -AutoSize"

echo "已发送到 $HOST 的 $target"
