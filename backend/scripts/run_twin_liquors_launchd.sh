#!/bin/bash
# Local Twin Liquors scrape — invoked by launchd/cron on a RESIDENTIAL IP.
#
# GitHub datacenter IPs are Cloudflare-1015-blocked by City Hive (confirmed
# 2026-07-10: a workflow_dispatch test committed 0/12 stores), same failure
# mode as Vivino — so this scraper lives on the mini, not GitHub Actions.
#
# The scraper is self-pacing (~1 req/s) with Cloudflare-1015 backoff and
# per-store isolation, so a partial block degrades gracefully. Idempotent
# (upserts by store × wine), safe to re-run. Weekly cadence is plenty.
set -u
cd "$(dirname "$0")/.." || exit 1          # -> backend/ (so ../.env resolves)

LOG="$HOME/Library/Logs/somm-twin-liquors.log"
PY="$(command -v python3)"

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | twin liquors scrape start ==="
  "$PY" -c "import asyncio; from scrapers.twin_liquors import TwinLiquorsScraper; print(asyncio.run(TwinLiquorsScraper().run_full()))"
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') | twin liquors scrape end (exit $?) ==="
  echo ""
} >> "$LOG" 2>&1
