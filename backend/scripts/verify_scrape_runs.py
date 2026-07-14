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
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SILENT_ZERO_MSG = (
    "0 records updated — run completed without writing anything (possible IP "
    "block or API change); flipped from success by verify_scrape_runs"
)


def classify_runs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the runs that need eyes: success-with-zero-records ("silent
    zero"), failed, and partial. Running rows are in-flight, not issues."""
    issues = []
    for r in rows:
        status = r.get("status")
        updated = r.get("records_updated") or 0
        if status == "success" and updated == 0:
            issues.append({"kind": "silent_zero", "run": r})
        elif status in ("failed", "partial"):
            issues.append({"kind": status, "run": r})
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
    args = parser.parse_args()

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

    issues = classify_runs(rows)
    flip_silent_zeroes(sb, issues)
    _notify_slack(issues)

    print(f"checked {len(rows)} run(s) since {since[:16]}")
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
