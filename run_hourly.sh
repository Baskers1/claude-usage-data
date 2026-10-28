#!/bin/bash
# Hourly: export Claude Code usage and push it to GitHub (launchd: com.baskers.claude-usage)
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
cd "$HOME/claude-usage-data" || exit 0
if /usr/bin/python3 export_usage.py; then s=ok; else s=FAILED; fi
echo "$(date -u +%FT%TZ) export $s" > status.txt
git add usage.csv fx.csv status.txt export_usage.py run_hourly.sh
git commit -q -m "usage $(date -u +%FT%TZ)" || true
git push -q origin HEAD:main
