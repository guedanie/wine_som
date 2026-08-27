#!/bin/bash
# Total Wine 10-DAY PROBE — invoked by launchd on the residential-IP mini.
#
# Total Wine sits behind PerimeterX and has IP-blocked this box since 2026-08-27
# (item 46). This job's PRIMARY purpose is DETECTION, not collection: it asks, every
# 10 days, "are we unblocked yet?" and only crawls if the answer is yes.
#
# Why a canary, and why 10 days:
#   * PX scores a client's BEHAVIOUR over time and decays that score with quiet.
#     A blind retry loop would keep refreshing the score and hold the block open —
#     so the run makes ONE request, and stops immediately if it's refused.
#   * Cadence is 10 days, not monthly: a single GET with a normal UA is what any
#     browser does constantly, so it is unlikely to sustain a block that took
#     hundreds of rapid pageSize=200 fetches to earn. 3x the probes, ~3x the
#     information about when the block lifts, negligible added risk. NOTE this is
#     reasoning, not measurement — PX's decay curve is unknown, which is exactly
#     why every probe result is appended to the history file below.
#   * A blocked probe is a NORMAL outcome, so it exits 0 and reports INFO, not FAIL.
#     Alerting repeatedly on an expected state is how real alerts get ignored.
#
# THE RISK IS NOT THE CANARY, IT IS WHAT FOLLOWS. Charging into a full seed on the
# first green probe repeats the exact behaviour that earned the block, so the first
# success crawls only ONE page (TW_PROBE_PAGES) — enough to prove a crawl survives,
# small enough not to re-trigger. Widen it deliberately once a green probe holds.
#
# Freshness note: a 10-day cycle sits exactly ON the 10-day staleness bench, so even
# a working probe leaves Total Wine at the edge of being benched. ~7 days would be
# needed for continuous visibility — but that is moot until a crawl survives at all.
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-totalwine.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
HIST="$HOME/Library/Logs/somm-totalwine-probes.tsv"
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | total wine 10-day probe ===" >> "$LOG" 2>&1

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
  printf '%s\tBLOCKED\t%s\n' "$(date '+%Y-%m-%d %H:%M')" "${REASON}" >> "$HIST"
  notify_slack "Total Wine 10-day probe" "INFO" "still blocked — ${REASON}. No crawl attempted; re-probing in 10 days."
  exit 0                                    # expected state: NOT a failure
fi

if [ $CANARY -ne 0 ]; then
  notify_slack "Total Wine 10-day probe" "FAIL" "canary itself errored (exit ${CANARY}) — check $LOG"
  exit $CANARY
fi

# Canary is open: seed a modest slice, gently. Not a full catalogue sweep — the
# point is to confirm a real crawl survives before scheduling one.
echo "=== canary OPEN — running seed ===" >> "$LOG" 2>&1
TW_PROBE_PAGES=1 "$PY" -c "
import asyncio, os, scrapers.total_wine as tw
tw._SEED_PAGES = int(os.environ.get('TW_PROBE_PAGES', '1'))
print(asyncio.run(tw.TotalWineScraper().run_full(mode='seed')))
" >> "$LOG" 2>&1
EXIT=$?
DURATION=$(( $(date +%s) - START ))
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | total wine probe end (exit $EXIT) ===" >> "$LOG" 2>&1

if [ $EXIT -eq 0 ]; then
  SUMMARY=$(tail -20 "$LOG" | grep -oE "\{[^}]*\}" | tail -1)
  printf '%s\tOPEN\t%s\n' "$(date '+%Y-%m-%d %H:%M')" "${SUMMARY:-seed ok}" >> "$HIST"
  notify_slack "Total Wine 10-day probe" "OK" "UNBLOCKED — 1-page seed ran in ${DURATION}s: ${SUMMARY:-completed}. If this holds, widen TW_PROBE_PAGES and tighten cadence to ~7d."
else
  notify_slack "Total Wine 10-day probe" "FAIL" "canary was open but the seed failed (exit ${EXIT}) after ${DURATION}s" "$LOG"
fi
exit $EXIT
