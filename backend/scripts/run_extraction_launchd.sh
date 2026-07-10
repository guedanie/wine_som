#!/bin/bash
# Local qwen2.5:7b fact extraction — invoked by launchd on a weekly cadence to
# keep newly scraped wines' varietal/region/grapes/etc populated using the local
# LLM backend (no Haiku spend, no CI dependency).
#
# --null-only makes this idempotent + resumable: only touches wines still
# missing a varietal. Safe to run alongside the initial backlog drain (they'll
# converge on the shrinking set).
#
# Requires: Ollama running (brew services start ollama) with qwen2.5:7b pulled.
# Skips itself if another --null-only run is already in flight (avoids
# double-hitting Ollama during backlog drains).

set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-extraction.log"
PY="/usr/bin/python3"

source "$(dirname "$0")/lib_notify_slack.sh"

START=$(date +%s)
SKIPPED=0
EXTRACT_EXIT=0
PERSIST_EXIT=0

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | extraction run start ==="
  if pgrep -f "enrichment.extraction.run_extraction.*--null-only" >/dev/null 2>&1; then
    echo "another --null-only extraction is already running; skipping"
    SKIPPED=1
  else
    EXTRACTOR_BACKEND=ollama "$PY" -m enrichment.extraction.run_extraction --null-only
    EXTRACT_EXIT=$?
    echo "--- chaining persist_structure.py ---"
    "$PY" scripts/persist_structure.py
    PERSIST_EXIT=$?
  fi
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | extraction run end (extract=$EXTRACT_EXIT persist=$PERSIST_EXIT skipped=$SKIPPED) ==="
  echo ""
} >> "$LOG" 2>&1
DURATION=$(( $(date +%s) - START ))
DUR_HUMAN=$(printf '%dh%02dm' $((DURATION/3600)) $(((DURATION%3600)/60)))

if [ $SKIPPED -eq 1 ]; then
  notify_slack "Extraction + persist_structure" "OK" "skipped — another --null-only run already in flight"
elif [ $EXTRACT_EXIT -eq 0 ] && [ $PERSIST_EXIT -eq 0 ]; then
  notify_slack "Extraction + persist_structure" "OK" "duration ${DUR_HUMAN} — both stages clean"
else
  notify_slack "Extraction + persist_structure" "FAIL" "extract=${EXTRACT_EXIT} persist=${PERSIST_EXIT} after ${DUR_HUMAN}" "$LOG"
fi
[ $EXTRACT_EXIT -ne 0 ] && exit $EXTRACT_EXIT
exit $PERSIST_EXIT
