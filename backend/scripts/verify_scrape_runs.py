"""Post-scrape verifier — catches runs that "succeed" while writing nothing.

A scraper whose fetches all error (IP block, API change) can finish cleanly
with records_updated=0 and a green status; Spec's hid a 3.5-week outage that
way (last real run 2026-06-19, every run after: success/0). This script reads
the actual scraper_runs rows for the window, flips silent-zero successes to
failed, posts a Slack alert when anything needs eyes, and exits nonzero so the
calling workflow goes red.

Run from backend/ (../.env resolves):
    python3 -m scripts.verify_scrape_runs [--since-hours 24]
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SILENT_ZERO_MSG = (
    "0 records updated — run completed without writing anything (possible IP "
    "block or API change); flipped from success by verify_scrape_runs"
)


# A run still `running` past this never closed. Above the longest same-cycle
# scrape (Spec's ~30 min, H-E-B ~50 min) and below a full day.
#
# Honest about its reach: this does NOT catch a row that fails to close at the
# very end of the cycle that created it — Kroger's was ~10 minutes old when the
# workflow's own verify ran. It catches a genuine hang, and a straggler from a
# prior invocation inside the lookback window. The Kroger recurrence is
# prevented at source in scrapers/kroger.py; this is the net for the class.
#
# The local-LLM extraction chain legitimately runs ~13h, so exclude it from the
# caller that does not own it rather than raising this above a full day.
STUCK_AFTER_HOURS = 6.0


def classify_runs(rows: List[Dict[str, Any]],
                  now: Optional[datetime] = None,
                  exclude: Optional[Set[str]] = None,
                  stuck_after_hours: float = STUCK_AFTER_HOURS) -> List[Dict[str, Any]]:
    """Return the runs that need eyes.

    Four kinds: success-with-zero-records ("silent zero"), failed, partial, and
    **stuck** — a row still `running` long after any plausible duration.

    The stuck check exists because `running` was a blind spot. Kroger wrote an
    invalid status ("partial", which the scraper_runs CHECK enum rejects), the
    terminal update raised, the workflow's continue-on-error swallowed it, and
    the row sat at `running`/0 for two weeks. Nothing was failing, so nothing
    complained — while sweep_delisted skipped the retailer the whole time.

    `exclude` scopes the check to runs the CALLER owns. GitHub and the mini both
    verify by time window and therefore see each other's runs, so GitHub was
    going red for an H-E-B failure it neither ran nor could fix. Excluding is
    deliberately opt-OUT rather than opt-in: a newly added scraper is verified by
    default, and forgetting to exclude a moved one fails loudly instead of
    silently skipping it.
    """
    now = now or datetime.now(timezone.utc)
    exclude = exclude or set()
    issues = []
    for r in rows:
        if r.get("retailer_name") in exclude:
            continue
        status = r.get("status")
        updated = r.get("records_updated") or 0
        if status == "success" and updated == 0:
            issues.append({"kind": "silent_zero", "run": r})
        elif status in ("failed", "partial"):
            issues.append({"kind": status, "run": r})
        elif status == "running":
            started = r.get("started_at")
            if not started:
                continue
            try:
                began = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            except ValueError:
                continue
            if (now - began).total_seconds() > stuck_after_hours * 3600:
                issues.append({"kind": "stuck", "run": r})
    return issues


def flip_silent_zeroes(sb, issues: List[Dict[str, Any]]) -> None:
    """Rewrite silent-zero rows as failed so history stops lying."""
    for issue in issues:
        if issue["kind"] != "silent_zero":
            continue
        sb.table("scraper_runs").update({
            "status": "failed",
            "error_message": SILENT_ZERO_MSG,
        }).eq("id", issue["run"]["id"]).execute()


def _notify_slack(issues: List[Dict[str, Any]]) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook or not issues:
        return
    lines = [
        f"• {i['run']['retailer_name']}: {i['kind'].replace('_', ' ')} "
        f"(records={i['run'].get('records_updated')})"
        for i in issues
    ]
    text = ":rotating_light: Scrape verification — runs needing eyes:\n" + "\n".join(lines)
    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:                       # alerting must never mask the exit code
        print(f"slack notify failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since-hours", type=float, default=24.0,
                        help="how far back to check scraper_runs (default 24)")
    parser.add_argument("--exclude", default="",
                        help="comma-separated retailer_names this caller does not "
                             "own (GitHub and the mini both see each other's runs)")
    args = parser.parse_args()
    exclude = {n.strip() for n in args.exclude.split(",") if n.strip()}

    from db import get_service_client
    sb = get_service_client()

    since = (datetime.now(timezone.utc) - timedelta(hours=args.since_hours)).isoformat()
    rows = (
        sb.table("scraper_runs")
        .select("id,retailer_name,status,records_updated,started_at,error_message")
        .gte("started_at", since)
        .order("started_at")
        .execute()
        .data
    )

    issues = classify_runs(rows, exclude=exclude)
    flip_silent_zeroes(sb, issues)
    _notify_slack(issues)

    skipped = sum(1 for r in rows if r.get("retailer_name") in exclude)
    print(f"checked {len(rows) - skipped} run(s) since {since[:16]}"
          + (f" ({skipped} excluded: {sorted(exclude)})" if skipped else ""))
    for r in rows:
        print(f"  {r['started_at'][:16]}  {r['retailer_name']:28s} "
              f"{r['status']:9s} records={r.get('records_updated')}")
    if issues:
        print(f"\n{len(issues)} issue(s):")
        for i in issues:
            print(f"  {i['run']['retailer_name']}: {i['kind']} "
                  f"(records={i['run'].get('records_updated')})")
        return 1
    print("all runs healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
