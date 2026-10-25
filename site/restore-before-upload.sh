#!/bin/sh
# 一键还原：撤销「附件投递（回形针）」——桌面 index.html + 手机 m.html + m6.html + 后端 todo_api.py
# 备份时间：2026-10-13 17:40（上传功能上线前）
# 用法： sh /home/ubuntu/stack/hub/restore-before-upload.sh
set -e
cd /home/ubuntu/stack/hub
cp -p index.html.bak-20261013_174001-upload index.html
cp -p m.html.bak-20261013_174001-upload m.html
cp -p m6.html.bak-20261013_174001-upload m6.html
cp -p make-m6.py.bak-*-upload make-m6.py 2>/dev/null || true
cp -p /home/ubuntu/stack/todo_service/todo_api.py.bak-20261013_174001-upload /home/ubuntu/stack/todo_service/todo_api.py
sudo systemctl restart hermes-todo-api.service
echo "已还原三个页面 + todo_api.py（回到 2026-10-13 17:40 的版本），后端已重启"
echo "（上传目录 ~/stack/hub/uploads/ 保留未删；不需要可自行 rm -rf）"
