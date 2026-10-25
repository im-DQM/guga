#!/usr/bin/env bash
# 夜间值守自检（每晚 03:00 跑，no_agent 任务）：只读检查，不修改任何配置。
# 正常 → 输出一行「隔夜正常」+ 资源摘要；异常 → 列出问题与建议。
# 顺带清理 7 天前的旧备份 / 14 天前的旧日志，防止 40G 系统盘被撑满。
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/1000

# 巡检（安全兜底）不受「今晚先不做」影响：服务/容器/磁盘该看还是要看。
# 01:00 调研、02:00 小工程仍由 ~/.hermes/.nightly-pause 控制。

PROBLEMS=()
ADVICE=()
CLEANED=0

# 1) systemd 服务（系统级 + 用户级 gateway）
for u in hermes-todo-api code-server@ubuntu ttyd-hermes ttyd-claude; do
  systemctl is-active --quiet "$u" || { PROBLEMS+=("服务未运行：$u"); ADVICE+=("sudo systemctl restart $u"); }
done
systemctl --user is-active --quiet hermes-gateway 2>/dev/null || {
  PROBLEMS+=("服务未运行：hermes-gateway（用户级，聊天/定时全靠它）")
  ADVICE+=("用户级 gateway 需要重新拉起（先与主人确认再动）"); }

# 2) docker 容器
for c in caddy gitea; do
  st=$(sudo -n docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "inspect-failed")
  [ "$st" = "running" ] || { PROBLEMS+=("容器未运行：$c（$st）"); ADVICE+=("cd ~/stack && sudo docker compose up -d $c"); }
done

# 3) HTTP 探活（经本机回环，不走公网）
probe() { # url 名称 允许的状态码
  local code
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$1" 2>/dev/null || echo 000)
  case " $3 " in *" $code "*) ;; *) PROBLEMS+=("HTTP 异常：$2 返回 $code（$1）");; esac
}
probe "http://127.0.0.1:8080/"      "hub 入口(caddy)"    "200"
probe "http://127.0.0.1:8790/api/sysinfo" "后端 /api/sysinfo" "200"
probe "http://127.0.0.1:8081/"      "code-server"        "200 302"
probe "http://127.0.0.1:3000/"      "gitea"              "200 302 303"

# 4) 资源水位
dsk_used=$(df --output=pcent / | tail -1 | tr -dc '0-9'); dsk_used=${dsk_used:-0}
dsk_free=$(( 100 - dsk_used ))
avail_mb=$(free -m | awk 'NR==2{print $7}'); avail_mb=${avail_mb:-0}
sys_mb=$(free -m | awk 'NR==2{print $2}')
mem_used_pct=$(awk -v a="$avail_mb" -v t="$sys_mb" 'BEGIN{ if(t>0) printf "%d", (t-a)*100/t; else print 0 }')
read -r swp_tot swp_used <<<"$(free -m | awk 'NR==3{print $2, $3}')"
swp_pct=$(awk -v u="${swp_used:-0}" -v t="${swp_tot:-0}" 'BEGIN{ if(t>0) printf "%d", u*100/t; else print 0 }')

[ "$dsk_free" -le 15 ] && { PROBLEMS+=("磁盘剩余 ${dsk_free}%（已用 ${dsk_used}%）"); ADVICE+=("清 node_modules / 旧备份，或升套餐"); }
[ "$avail_mb" -lt 300 ] && { PROBLEMS+=("内存可用仅 ${avail_mb}MB（已用 ${mem_used_pct}%）"); ADVICE+=("查 code-server / claude 是否有僵进程：ps aux --sort=-%mem | head"); }
[ "$swp_pct" -ge 90 ] && { PROBLEMS+=("Swap 已用 ${swp_pct}%（${swp_used}MB/${swp_tot}MB）"); ADVICE+=("内存吃紧，同上先查僵进程"); }

# 5) 定时任务上次是否跑成功
while IFS=$'\t' read -r name status; do
  [ -n "$name" ] || continue
  [ "$status" = "ok" ] || PROBLEMS+=("定时任务上次未成功：$name（$status）")
done < <(python3 - <<'PY'
import json, os
p = os.path.expanduser('~/.hermes/cron/jobs.json')
try:
    d = json.load(open(p))
    js = d if isinstance(d, list) else d.get('jobs', d)
    if isinstance(js, dict): js = list(js.values())
    for j in js:
        if not j.get('enabled'): continue
        st = j.get('last_status')
        if st and st != 'ok':
            print(f"{j.get('name')}\t{st}")
except Exception as e:
    print(f"jobs.json 读取失败\t{e}")
PY
)

# 6) 关键文件完整性
for f in /home/ubuntu/.hermes/todos.md /home/ubuntu/.hermes/state.db /home/ubuntu/.hermes/cron/jobs.json /home/ubuntu/stack/hub/index.html; do
  [ -s "$f" ] || PROBLEMS+=("文件缺失或为空：$f")
done

# 7) 清理旧备份 / 旧日志（只删备份与日志，不碰数据与代码）
before=$(find /home/ubuntu/stack/backups /home/ubuntu/stack/hub /home/ubuntu/.hermes/logs -type f 2>/dev/null | wc -l)
find /home/ubuntu/stack/backups -type f -mtime +7 \( -name '*.bak*' -o -name '*-[0-9]*.html' -o -name 'Caddyfile-*' -o -name 'todo_api-*' \) -delete 2>/dev/null
find /home/ubuntu/stack/hub -maxdepth 1 -type f -mtime +7 -name '*.bak-*' -delete 2>/dev/null
find /home/ubuntu/.hermes/logs -type f -mtime +14 \( -name '*.log' -o -name '*.log.*' -o -name '*.jsonl' \) -delete 2>/dev/null
after=$(find /home/ubuntu/stack/backups /home/ubuntu/stack/hub /home/ubuntu/.hermes/logs -type f 2>/dev/null | wc -l)
CLEANED=$(( before - after ))

# 8) LightVela 登录态保活：浏览器 profile 落在 scratch 目录，定期 touch 避免被空闲清理
keep=$(find /home/ubuntu/.hermes/cache/scratch -maxdepth 1 -name 'agent-browser-chrome-*' -type d 2>/dev/null | wc -l)
if [ "$keep" -gt 0 ]; then
  find /home/ubuntu/.hermes/cache/scratch -maxdepth 1 -name 'agent-browser-chrome-*' -type d -exec touch {} + 2>/dev/null
fi

SUMMARY="磁盘剩余 ${dsk_free}% · 内存可用 ${avail_mb}MB（已用 ${mem_used_pct}%） · Swap ${swp_pct}%${CLEANED:+ · 清理旧文件 ${CLEANED} 个}"

if [ ${#PROBLEMS[@]} -eq 0 ]; then
  printf '🌙 隔夜自检：一切正常。%s\n' "$SUMMARY"
  exit 0
fi

printf '⚠️ 隔夜自检发现 %d 处问题：\n' "${#PROBLEMS[@]}"
for p in "${PROBLEMS[@]}"; do printf -- '- %s\n' "$p"; done
if [ ${#ADVICE[@]} -gt 0 ]; then
  printf '\n建议：\n'
  for a in "${ADVICE[@]}"; do printf -- '- %s\n' "$a"; done
fi
printf '\n资源：%s\n' "$SUMMARY"
