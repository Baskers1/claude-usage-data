#!/bin/bash
# Hourly: export Claude Code usage, push it to GitHub, and copy it into issue #1
# (the dashboard reads the issue: the GitHub connector doesn't pass file contents through).
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
cd "$HOME/claude-usage-data" || exit 0
if /usr/bin/python3 export_usage.py; then s=ok; else s=FAILED; fi
echo "$(date -u +%FT%TZ) export $s" > status.txt
{
  echo "Auto-updated every hour by the iMac (com.baskers.claude-usage). Read by the Claude Code token burn rate dashboard. Don't edit."
  echo
  echo "### status"; echo '```'; cat status.txt; echo '```'
  echo "### fx.csv"; echo '```csv'; cat fx.csv; echo '```'
  echo "### usage.csv"; echo '```csv'; cat usage.csv; echo '```'
} > feed.md
[ "$(wc -c < feed.md)" -gt 64000 ] && echo "$(date -u +%FT%TZ) export ok, feed too big for issue" > status.txt  # shortcut: issue body max 65,536 chars; trim DAYS if this ever shows
git add usage.csv fx.csv status.txt export_usage.py run_hourly.sh
git commit -q -m "usage $(date -u +%FT%TZ)" || true
git push -q origin HEAD:main
if gh issue view 1 --repo Baskers1/claude-usage-data >/dev/null 2>&1; then
  gh issue edit 1 --repo Baskers1/claude-usage-data --body-file feed.md >/dev/null
else
  gh issue create --repo Baskers1/claude-usage-data --title "Usage feed (auto-updated hourly)" --body-file feed.md >/dev/null
fi
