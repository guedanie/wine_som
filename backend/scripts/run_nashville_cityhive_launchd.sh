#!/bin/bash
# Nashville independents (Frugal MacDoogal + Corkdorks ×2) — City Hive term sweep,
# invoked by launchd on a RESIDENTIAL IP.
#
# City Hive Cloudflare-1015s datacenter IPs on sustained sweeps (same wall as Twin
# Liquors and Vivino), so this lives on the mini rather than GitHub Actions. The
# scraper self-paces (~1.2s/term) and banks-then-skips a store that starts 1015ing,
# so a partial block degrades gracefully. Idempotent (upserts by store × wine).
#
# WHY these stores: Nashville had volume but no depth — 35 Kroger stores gave only
# 8.8% of in-stock rows at $30+. These three specialists run 31.6% premium and
# lifted Nashville's $100+ inventory 347 -> 476 on their first run.
#
# NOTE: no browser needed (plain curl), so unlike com.somm.heb this does NOT
# require a GUI session — a background LaunchAgent is fine.
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-nashville-cityhive.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
# `EXIT=$?` after a `{ ... } >> LOG` group captures the group's LAST command (the
# trailing echo), NOT the python — so every run reported exit 0 and Slack was told
# "OK" even when the run failed. Redirect per-command and capture directly.
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | nashville cityhive scrape start ===" >> "$LOG" 2>&1
"$PY" -c "import asyncio; from scrapers.nashville_cityhive import NashvilleCityHiveScraper; print(asyncio.run(NashvilleCityHiveScraper().run_full()))" >> "$LOG" 2>&1
EXIT=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | nashville cityhive scrape end (exit $EXIT) ===" >> "$LOG" 2>&1
echo "" >> "$LOG" 2>&1
DURATION=$(( $(date +%s) - START ))

if [ $EXIT -eq 0 ]; then
  SUMMARY=$(tail -20 "$LOG" | grep -oE "\{[^}]*\}" | tail -1)
  notify_slack "Nashville City Hive scrape" "OK" "duration ${DURATION}s — ${SUMMARY:-run completed}"
else
  notify_slack "Nashville City Hive scrape" "FAIL" "exit ${EXIT} after ${DURATION}s" "$LOG"
fi
exit $EXIT
