#!/bin/bash
# Shared Slack notification helper for the enrichment launchd wrappers.
# Source this from a wrapper script:
#   source "$(dirname "$0")/lib_notify_slack.sh"
# then call:
#   notify_slack "Vivino" "OK"   "matched 297/300 in 5m12s"
#   notify_slack "Vivino" "FAIL" "exit 1 after 42s" "/path/to/log"
#
# Fails soft: no SLACK_WEBHOOK_URL → no-op, no error. Never blocks the job.
# Webhook URL is read from the environment first, else parsed from ../.env
# (relative to the wrapper's CWD after its own `cd`).

notify_slack() {
    local job="$1"
    local job_status="$2"    # "OK" or "FAIL"
    local msg="$3"
    local log_path="${4:-}"

    # Resolve webhook: env wins, else parse .env
    local webhook="${SLACK_WEBHOOK_URL:-}"
    if [ -z "$webhook" ] && [ -f ../.env ]; then
        webhook=$(grep -E "^SLACK_WEBHOOK_URL=" ../.env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
    fi
    [ -z "$webhook" ] && return 0

    local emoji=":white_check_mark:"
    [ "$job_status" != "OK" ] && emoji=":x:"

    local text="${emoji} *${job}* — ${job_status}\n${msg}"

    # On failure, append the last 15 log lines in a code block for triage
    if [ "$job_status" != "OK" ] && [ -n "$log_path" ] && [ -f "$log_path" ]; then
        local tail_block
        tail_block=$(tail -15 "$log_path" | python3 -c 'import sys,json; sys.stdout.write(json.dumps(sys.stdin.read())[1:-1])' 2>/dev/null)
        if [ -n "$tail_block" ]; then
            text="${text}\n\`\`\`${tail_block}\`\`\`"
        fi
    fi

    # Slack expects a JSON-encoded string. Build the payload with python to
    # bulletproof escaping (\n, quotes, backticks, unicode from Vivino names).
    local payload
    payload=$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1]}))" "$text" 2>/dev/null)
    [ -z "$payload" ] && return 0

    curl -s -X POST -H 'Content-type: application/json' \
         --max-time 10 \
         --data "$payload" \
         "$webhook" > /dev/null 2>&1
    return 0
}
