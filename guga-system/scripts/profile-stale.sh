#!/usr/bin/env bash
# 月度复核：列出 90 天没再被确认的个人模型条目；没有则静默。
python3 "$HOME/.hermes/scripts/profile.py" stale --days 90 2>/dev/null
