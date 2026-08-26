#!/bin/bash
# Local H-E-B scrape — invoked by a GUI LaunchAgent on the mini (item 45).
#
# HEB moved heb.com/graphql behind Imperva Incapsula (~2026-07-26). urllib/curl
# cannot solve its JS challenge and vanilla Playwright is fingerprint-blocked
# (errorCode 15) BOTH headless and headed; only patchright with a HEADED
# persistent context clears it. So this cannot run on GitHub Actions, and it
# cannot run as a launchd *daemon* either — a headed browser needs a real
# display, i.e. the logged-in Aqua session. Hence: GUI LaunchAgent on the mini.
#
# `caffeinate -i` keeps the mini awake for the duration; a sleep mid-scrape
# kills the browser session and the run with it.
#
# Idempotent (upserts by store x wine), safe to re-run.
#
# NOTE: Central Market shares this endpoint and this browser session, but every
# configured CM_STORES id currently returns total=0 (HEB renumbered/disabled
# them). CM is deliberately NOT run here — it would commit 0 rows and trip
# verify_scrape_runs.py's silent-zero alert every week. Re-add once the store
# ids are refreshed.
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-heb.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
# NOTE: do NOT wrap this in a `{ ... } >> LOG` group and read $? afterwards —
# that captures the group's LAST command (the trailing echo), so a failed scrape
# reports exit 0 and Slack is told "OK". That is exactly the silent-failure mode
# verify_scrape_runs.py exists to catch. Redirect per-command and capture the
# python's own status directly. (run_twin_liquors_launchd.sh still has the
# grouped form and mis-reports the same way — worth fixing there too.)
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | heb scrape start ===" >> "$LOG" 2>&1
caffeinate -i "$PY" -c "import asyncio; from scrapers.heb import HebScraper; print(asyncio.run(HebScraper().run_full()))" >> "$LOG" 2>&1
EXIT=$?
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | heb scrape end (exit $EXIT) ===" >> "$LOG" 2>&1
echo "" >> "$LOG" 2>&1
DURATION=$(( $(date +%s) - START ))

if [ $EXIT -eq 0 ]; then
  SUMMARY=$(tail -20 "$LOG" | grep -oE "\{[^}]*\}" | tail -1)
  notify_slack "H-E-B scrape" "OK" "duration ${DURATION}s — ${SUMMARY:-run completed}"
else
  notify_slack "H-E-B scrape" "FAIL" "exit ${EXIT} after ${DURATION}s" "$LOG"
fi
exit $EXIT
