#!/bin/bash
# Local Vivino enrichment run — invoked by launchd on a schedule from this
# machine's residential IP (GitHub datacenter IPs are blocklisted by Vivino).
#
# Drains the un-enriched backlog in bounded, polite batches. The Python runner
# is rate-limited (2 workers @ 1.0s) with an abort breaker (10 consecutive
# fetch failures → clean exit), so a blocked run stops itself and retries next
# schedule. Idempotent: targets vivino_enriched_at IS NULL, never re-stamps on
# fetch failure.
#
# Override the per-run cap with VIVINO_LIMIT (default 300).

set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LIMIT="${VIVINO_LIMIT:-300}"
LOG="$HOME/Library/Logs/somm-vivino.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | vivino run start (limit=$LIMIT) ==="
  "$PY" scripts/run_vivino_sample.py --limit "$LIMIT"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | vivino run end (exit $?) ==="
  echo ""
} >> "$LOG" 2>&1
EXIT=$?
DURATION=$(( $(date +%s) - START ))

if [ $EXIT -eq 0 ]; then
  # Parse the tail of this run's summary block for a Slack-friendly one-liner
  SUMMARY=$(grep -E "Matched \+ written|No search hit|Fetch failures" "$LOG" | tail -3 | tr '\n' ' ' | sed 's/  */ /g')
  notify_slack "Vivino enrichment" "OK" "duration ${DURATION}s (limit=${LIMIT}) — ${SUMMARY:-run completed}"
else
  notify_slack "Vivino enrichment" "FAIL" "exit ${EXIT} after ${DURATION}s (limit=${LIMIT})" "$LOG"
fi
exit $EXIT
