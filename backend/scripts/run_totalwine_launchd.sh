#!/bin/bash
# Total Wine WEEKLY PROBE — invoked by launchd on the residential-IP mini.
#
# Total Wine sits behind PerimeterX and has IP-blocked this box since 2026-08-27
# (item 46). This job's PRIMARY purpose is DETECTION, not collection: it asks, every
# week, "are we unblocked yet?" and only crawls if the answer is yes.
#
# Why a canary, and why weekly:
#   * PX scores a client's BEHAVIOUR over time and decays that score with quiet.
#     A blind retry loop would keep refreshing the score and hold the block open —
#     so the run makes ONE request, and stops immediately if it's refused.
#   * Cadence is WEEKLY (was every 10 days). Two reasons it changed on 2026-09-06:
#     the staleness bench is 10 days, so a 10-day probe sat exactly ON it and even
#     a working probe left Total Wine at the edge of invisible; and 10 days of
#     near-total quiet demonstrably did NOT clear the block (probed 2026-09-06,
#     still HTTP 403 PerimeterX, after the canary had never once fired). That
#     weakens the "PX decays with quiet" reasoning the old cadence rested on, so
#     spacing probes further apart buys nothing. A blocked week still costs
#     exactly ONE request — nothing like the hundreds of rapid pageSize=200
#     fetches that earned the block. Every result is appended to the history file
#     below so the decay curve is measured rather than assumed.
#   * A blocked probe is a NORMAL outcome, so it exits 0 and reports INFO, not FAIL.
#     Alerting repeatedly on an expected state is how real alerts get ignored.
#
# THE RISK IS NOT THE CANARY, IT IS WHAT FOLLOWS. Charging into a full seed on the
# first green probe repeats the exact behaviour that earned the block, so the first
# success crawls only ONE page (TW_PROBE_PAGES) — enough to prove a crawl survives,
# small enough not to re-trigger. Widen it deliberately once a green probe holds.
#
# Freshness note: weekly (7d) now sits inside the 10-day staleness bench, so a
# surviving crawl would keep Total Wine continuously visible rather than blinking
# out. Still moot until a crawl survives at all — as of 2026-09-06 it does not.
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-totalwine.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
HIST="$HOME/Library/Logs/somm-totalwine-probes.tsv"
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | total wine weekly probe ===" >> "$LOG" 2>&1

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
  notify_slack "Total Wine weekly probe" "INFO" "still blocked — ${REASON}. No crawl attempted; re-probing next Sunday."
  exit 0                                    # expected state: NOT a failure
fi

if [ $CANARY -ne 0 ]; then
  notify_slack "Total Wine weekly probe" "FAIL" "canary itself errored (exit ${CANARY}) — check $LOG"
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
  notify_slack "Total Wine weekly probe" "OK" "UNBLOCKED — 1-page seed ran in ${DURATION}s: ${SUMMARY:-completed}. If this holds, widen TW_PROBE_PAGES and tighten cadence to ~7d."
else
  notify_slack "Total Wine weekly probe" "FAIL" "canary was open but the seed failed (exit ${EXIT}) after ${DURATION}s" "$LOG"
fi
exit $EXIT
