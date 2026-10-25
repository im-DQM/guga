#!/bin/sh
# 一键还原：撤销「删除失败不再静默」这次改动（备份时间 2026-10-13 14:52）
# 用法： sh /home/ubuntu/stack/hub/restore-before-delfail.sh
set -e
cd /home/ubuntu/stack/hub
cp -p index.html.bak-20261013_145250-delfail index.html
cp -p m.html.bak-20261013_145250-delfail m.html
echo "已还原 index.html / m.html（回到 2026-10-13 14:52 的版本）"
