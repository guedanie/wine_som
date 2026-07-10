#!/bin/bash
# One-shot watcher for the initial extraction backlog drain (the manual nohup
# process kicked off during Mac mini setup). Polls the extraction PID; when it
# exits, runs persist_structure.py and posts Slack notifications for both stages.
#
# This is NOT a launchd job — it's a self-detached script that runs in the
# background of a single "drain the backlog once" migration. The recurring
# weekly cadence lives in run_extraction_launchd.sh instead.
#
# Usage: EXTRACT_PID=<pid> LOG=<path> nohup bash _watch_current_drain.sh &

set -u
EXTRACT_PID="${EXTRACT_PID:?EXTRACT_PID required}"
LOG="${LOG:-/tmp/extraction.log}"
PERSIST_LOG="/tmp/persist_structure.log"

cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env + source path resolve)
source "$(dirname "$0")/scripts/lib_notify_slack.sh" 2>/dev/null || source "scripts/lib_notify_slack.sh"

START=$(date +%s)

# Wait for extraction to exit
while kill -0 "$EXTRACT_PID" 2>/dev/null; do sleep 120; done

DRAIN_DUR=$(( $(date +%s) - START ))
DRAIN_HUMAN=$(printf '%dh%02dm' $((DRAIN_DUR/3600)) $(((DRAIN_DUR%3600)/60)))

# Parse the log for a final progress line — best-effort, extraction runner writes
# lines like "  6298/6298 (100%) — 6180 written"
STATS=$(grep -E "^\s+[0-9]+/[0-9]+ \([0-9]+%\) — [0-9]+ written" "$LOG" 2>/dev/null | tail -1 | sed 's/^\s*//')
[ -z "$STATS" ] && STATS="see $LOG for details"

notify_slack "Initial extraction drain" "OK" "PID ${EXTRACT_PID} exited after ${DRAIN_HUMAN} — ${STATS}"

# Now run persist_structure
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | extraction PID $EXTRACT_PID exited; running persist_structure ==="
} >> "$PERSIST_LOG"

PSTART=$(date +%s)
/usr/bin/python3 scripts/persist_structure.py >> "$PERSIST_LOG" 2>&1
PEXIT=$?
PDUR=$(( $(date +%s) - PSTART ))
PDUR_HUMAN=$(printf '%dh%02dm' $((PDUR/3600)) $(((PDUR%3600)/60)))

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | persist_structure done (exit $PEXIT) ==="
} >> "$PERSIST_LOG"

if [ $PEXIT -eq 0 ]; then
  PSTATS=$(grep -iE "wines updated|structure written|coverage|persisted" "$PERSIST_LOG" 2>/dev/null | tail -2 | tr '\n' ' ' | sed 's/^\s*//;s/  */ /g')
  notify_slack "persist_structure" "OK" "duration ${PDUR_HUMAN} — ${PSTATS:-completed}"
else
  notify_slack "persist_structure" "FAIL" "exit ${PEXIT} after ${PDUR_HUMAN}" "$PERSIST_LOG"
fi
