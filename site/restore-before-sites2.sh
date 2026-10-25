#!/bin/sh
# 一键还原：撤销「站点分两份（手机端 / Only PC）+ 手机端站点按钮」这次改动（备份时间 2026-10-13 15:17）
# 用法： sh /home/ubuntu/stack/hub/restore-before-sites2.sh
# 注意：还会把 remote-api.py 的 murl 字段与 sites.json 的手机版地址一起退回——脚本只还原页面文件。
set -e
cd /home/ubuntu/stack/hub
cp -p index.html.bak-20261013_151729-sites2 index.html
cp -p m.html.bak-20261013_151729-sites2 m.html
echo "已还原 index.html / m.html（回到 2026-10-13 15:17 的版本）"
echo "如也要退掉服务端字段： cp ~/stack/remote/remote-api.py.bak-sites2 ~/stack/remote/remote-api.py && sudo systemctl restart guga-remote-api.service"
