#!/bin/bash
# Hourly: export Claude Code usage and push it to GitHub (launchd: com.baskers.claude-usage)
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
cd "$HOME/claude-usage-data" || exit 0
/usr/bin/python3 export_usage.py || { echo "$(date -u +%FT%TZ) export failed" > status.txt; }
[ -f status.txt ] && grep -q failed status.txt || echo "$(date -u +%FT%TZ) ok" > status.txt
git add usage.csv fx.csv status.txt export_usage.py run_hourly.sh
git commit -q -m "usage $(date -u +%FT%TZ)" || true
git pull -q --rebase origin main && git push -q origin HEAD:main
