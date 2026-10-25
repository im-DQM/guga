#!/usr/bin/env bash
# 把「整站源码 + 咕嘎系统」同步到 GitHub 的 im-DQM/guga，临时目录用完即删，服务器上不留副本。
# 用法：guga_repo_push.sh ["提交说明"]
set -euo pipefail

REPO="git@github.com:im-DQM/guga.git"
KEY="$HOME/.ssh/guga_github"
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes"
WORK=$(mktemp -d "$HOME/.hermes/cache/scratch/guga-repo.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

git clone -q "$REPO" "$WORK"
cd "$WORK"

EX="--exclude=*.bak* --exclude=__pycache__ --exclude=*.pyc --exclude=*.log --exclude=uploads/ --exclude=gitea-data/ --exclude=backups/ --exclude=OpenSSH-Win64.zip --exclude=.git/"

rsync -a --delete $EX ~/stack/hub/ site/
rsync -a --delete $EX --exclude=sessions.json --exclude=sites.json --exclude=group.json \
      --exclude=memories/ --exclude=state/ --exclude=audit.log --exclude=journal/ \
      ~/stack/remote/ platform/remote/
rsync -a --delete $EX --exclude=data.json --exclude=data.json.bak --exclude=seen.json \
      ~/stack/todo_service/ platform/todo_service/
rsync -a --delete $EX ~/stack/jiaxin_service/ platform/jiaxin_service/
rsync -a --delete $EX ~/stack/term/ platform/term/
cp ~/stack/Caddyfile ~/stack/docker-compose.yml platform/
cp ~/workspace/CLAUDE.md guga-system/CLAUDE.md   # 0号的编码规则书也进仓库
rsync -a --delete $EX --exclude=state/ ~/.hermes/guga/ guga-system/guga/
rsync -a --delete $EX ~/.hermes/scripts/ guga-system/scripts/
rsync -a --delete $EX ~/.hermes/knowledge/ guga-system/knowledge/
rsync -a --delete $EX ~/stack/docs/ docs/

git add -A
if git diff --cached --quiet; then
  echo "没有变化，仓库已是最新。"
  exit 0
fi
MSG="${1:-sync: 同步服务器上的网站与咕嘎系统 $(date '+%F %H:%M')}"
git -c user.name="im-DQM" -c user.email="im-DQM@users.noreply.github.com" commit -q -m "$MSG"
git push -q origin HEAD:main
echo "已推送：$(git log --oneline -1)（$(git diff --cached --stat HEAD^ 2>/dev/null | tail -1 || true)）"
