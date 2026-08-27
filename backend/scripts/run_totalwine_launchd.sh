#!/bin/bash
# Total Wine MONTHLY PROBE — invoked by launchd on the residential-IP mini.
#
# Total Wine sits behind PerimeterX and has IP-blocked this box since 2026-08-27
# (item 46). This job's PRIMARY purpose is DETECTION, not collection: it asks, once
# a month, "are we unblocked yet?" and only crawls if the answer is yes.
#
# Why monthly and why canary-first:
#   * PX scores a client's BEHAVIOUR over time and decays that score with quiet.
#     A blind retry loop would keep refreshing the score and hold the block open —
#     so the run makes ONE request, and stops immediately if it's refused.
#   * A blocked month is a NORMAL outcome, so it exits 0 and reports INFO, not FAIL.
#     Alerting monthly on an expected state is how real alerts get ignored.
#
# If a probe ever comes back open, that is the signal to consider a real cadence —
# note a monthly refresh alone can't beat the 10-day staleness bench, so Total Wine
# inventory would still be visible only part of the month until the schedule tightens.
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-totalwine.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | total wine monthly probe ===" >> "$LOG" 2>&1

# Canary: one request. Exit code 10 == still blocked (expected), 0 == open.
"$PY" -c "
import sys
from scrapers.total_wine import is_blocked
r = is_blocked()
print(('BLOCKED: ' + r) if r else 'OPEN')
sys.exit(10 if r else 0)
" >> "$LOG" 2>&1
CANARY=$?

if [ $CANARY -eq 10 ]; then
  REASON=$(grep -c 'BLOCKED' "$LOG" >/dev/null 2>&1 && tail -3 "$LOG" | grep -m1 'BLOCKED' || echo 'BLOCKED')
  echo "=== still blocked — not crawling (expected) ===" >> "$LOG" 2>&1
  notify_slack "Total Wine monthly probe" "INFO" "still blocked — ${REASON}. No crawl attempted; re-probing next month."
  exit 0                                    # expected state: NOT a failure
fi

if [ $CANARY -ne 0 ]; then
  notify_slack "Total Wine monthly probe" "FAIL" "canary itself errored (exit ${CANARY}) — check $LOG"
  exit $CANARY
fi

# Canary is open: seed a modest slice, gently. Not a full catalogue sweep — the
# point is to confirm a real crawl survives before scheduling one.
echo "=== canary OPEN — running seed ===" >> "$LOG" 2>&1
"$PY" -c "import asyncio; from scrapers.total_wine import TotalWineScraper; print(asyncio.run(TotalWineScraper().run_full(mode='seed')))" >> "$LOG" 2>&1
EXIT=$?
DURATION=$(( $(date +%s) - START ))
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | total wine probe end (exit $EXIT) ===" >> "$LOG" 2>&1

if [ $EXIT -eq 0 ]; then
  SUMMARY=$(tail -20 "$LOG" | grep -oE "\{[^}]*\}" | tail -1)
  notify_slack "Total Wine monthly probe" "OK" "UNBLOCKED — seed ran in ${DURATION}s: ${SUMMARY:-completed}. Consider a real cadence."
else
  notify_slack "Total Wine monthly probe" "FAIL" "canary was open but the seed failed (exit ${EXIT}) after ${DURATION}s" "$LOG"
fi
exit $EXIT
