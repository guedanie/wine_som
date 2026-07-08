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
PY="$(command -v python3)"

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | vivino run start (limit=$LIMIT) ==="
  "$PY" scripts/run_vivino_sample.py --limit "$LIMIT"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | vivino run end (exit $?) ==="
  echo ""
} >> "$LOG" 2>&1
