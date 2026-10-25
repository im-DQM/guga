#!/usr/bin/env bash
# 启动器：真身在 ~/.hermes/guga/guga1/scripts/guga-weekly.py（cron 不认软链，这里放真文件）
exec python3 "$HOME/.hermes/guga/guga1/scripts/guga-weekly.py" "$@"
