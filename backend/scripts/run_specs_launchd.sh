#!/bin/bash
# Local Spec's scrape — invoked by launchd on a RESIDENTIAL IP.
#
# GitHub datacenter IPs are silently blocked by specsonline.com (confirmed
# 2026-07-13: every weekly-scrape run since 2026-07-01 completed "successfully"
# with 0 records; last real run was 2026-06-19 from a different IP, 33,456
# records). Same failure mode as Twin Liquors/Vivino — so this scraper lives
# on the mini, not GitHub Actions.
#
# The scraper is self-pacing (~1 req/s) with bounded retry/backoff on
# non-JSON responses (SpecsRateLimited) and per-page isolation — a rate
# limit skips the store rather than surfacing as a silent zero. Idempotent
# (upserts by canonical UPC × store), safe to re-run. Weekly cadence covers
# SA + Austin + Dallas stores (~30 min end-to-end).
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-specs.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
SCRAPE_EXIT=0
SWEEP_EXIT=0
VERIFY_EXIT=0

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | specs scrape start ==="
  "$PY" -c "import asyncio; from scrapers.specs import SpecsScraper, SA_STORE_NUMBERS, AUSTIN_STORE_NUMBERS, DALLAS_STORE_NUMBERS; print(asyncio.run(SpecsScraper().run_full(SA_STORE_NUMBERS + AUSTIN_STORE_NUMBERS + DALLAS_STORE_NUMBERS)))"
  SCRAPE_EXIT=$?
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | specs scrape end (exit $SCRAPE_EXIT) ==="

  # Self-run sweep + verify. The GH weekly-scrape workflow runs these too, but
  # only over runs finished when it fires (~10:30 UTC). Spec's on the mini
  # fires at 05:00 CT = 10:00 UTC — it races that window and would otherwise
  # skip its own sweep/verify entirely. Both scripts are idempotent, so double
  # coverage is harmless. Window shorter than the scrape itself is fine — the
  # scripts filter to this run's own scraper_runs row.
  echo "--- chaining sweep_delisted (--since-hours 6) ---"
  "$PY" -m scripts.sweep_delisted --since-hours 6
  SWEEP_EXIT=$?
  echo "--- chaining verify_scrape_runs (--since-hours 6) ---"
  "$PY" -m scripts.verify_scrape_runs --since-hours 6
  VERIFY_EXIT=$?
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | wrapper end (scrape=$SCRAPE_EXIT sweep=$SWEEP_EXIT verify=$VERIFY_EXIT) ==="
  echo ""
} >> "$LOG" 2>&1
DURATION=$(( $(date +%s) - START ))

if [ $SCRAPE_EXIT -eq 0 ] && [ $SWEEP_EXIT -eq 0 ] && [ $VERIFY_EXIT -eq 0 ]; then
  SUMMARY=$(tail -30 "$LOG" | grep -oE "\{[^}]*\}" | tail -1)
  notify_slack "Spec's scrape" "OK" "duration ${DURATION}s — ${SUMMARY:-run completed}"
else
  notify_slack "Spec's scrape" "FAIL" "scrape=${SCRAPE_EXIT} sweep=${SWEEP_EXIT} verify=${VERIFY_EXIT} after ${DURATION}s" "$LOG"
fi
[ $SCRAPE_EXIT -ne 0 ] && exit $SCRAPE_EXIT
[ $SWEEP_EXIT -ne 0 ] && exit $SWEEP_EXIT
exit $VERIFY_EXIT
