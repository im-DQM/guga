#!/bin/sh
# 一键还原：撤销「站点一键复制网址」（桌面 index.html + 手机版 m.html）
# 备份时间：index.html 2026-10-13 15:25 / m.html 2026-10-13 15:26
# 用法： sh /home/ubuntu/stack/hub/restore-before-copyurl.sh
set -e
cd /home/ubuntu/stack/hub
cp -p index.html.bak-20261013_152538-copyurl index.html
cp -p m.html.bak-20261013_152641-copym m.html
echo "已还原 index.html / m.html（回到 2026-10-13 15:25 的版本）"
