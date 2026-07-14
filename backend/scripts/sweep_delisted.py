"""Post-scrape delisting sweep — items that vanish from a retailer's feed stop
claiming to be in stock.

The scrape is upsert-only: a wine that disappears from the feed keeps its last
price and in_stock=True forever ("zombie rows" — the dossier/search/region
surfaces will happily show a bottle that left the shelf a month ago). After
each successful run, this flips in_stock=false on rows the run did NOT touch:
any row of a participating store whose last_scraped_at predates the run start.

Safety rules (both load-bearing):
- Only runs with status=success AND records_updated > 0 sweep. A failed or
  silent-zero run must never flip its retailer to out-of-stock.
- Only stores that PARTICIPATED in the run (>=1 row refreshed since run start)
  are swept — a subset run (some stores skipped) can't delist the others.

If the item reappears in a later feed, the ordinary upsert flips it back —
nothing is deleted, price_history stays intact.

Run from backend/ (../.env resolves):
    python3 -m scripts.sweep_delisted [--since-hours 24]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# scraper_runs names don't always match stores.retailer_name — the Kroger run
# covers two banners whose stores are named individually.
_RUN_RETAILER_ALIASES = {
    "Kroger (multi-banner)": ["Kroger", "Harris Teeter"],
}


def eligible_runs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Only successful runs that actually wrote records may sweep."""
    return [r for r in rows
            if r.get("status") == "success" and (r.get("records_updated") or 0) > 0]


def sweep_run(sb, run: Dict[str, Any]) -> int:
    """Sweep one run: mark rows the run didn't refresh as out of stock.
    Returns the number of stores swept."""
    started = run["started_at"]
    retailer_names = _RUN_RETAILER_ALIASES.get(
        run["retailer_name"], [run["retailer_name"]])
    stores = (
        sb.table("stores").select("id")
        .in_("retailer_name", retailer_names)
        .execute().data or []
    )
    participating = []
    for s in stores:
        probe = (
            sb.table("retail_inventory").select("id")
            .in_("store_ref", [s["id"]])
            .gte("last_scraped_at", started)
            .limit(1)
            .execute().data
        )
        if probe:
            participating.append(s["id"])
    if not participating:
        return 0
    (
        sb.table("retail_inventory")
        .update({"in_stock": False})
        .in_("store_ref", participating)
        .lt("last_scraped_at", started)
        .eq("in_stock", True)
        .execute()
    )
    return len(participating)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since-hours", type=float, default=24.0,
                        help="sweep for scraper runs started within this window")
    args = parser.parse_args()

    from db import get_service_client
    sb = get_service_client()

    since = (datetime.now(timezone.utc) - timedelta(hours=args.since_hours)).isoformat()
    runs = (
        sb.table("scraper_runs")
        .select("retailer_name,status,records_updated,started_at")
        .gte("started_at", since)
        .order("started_at")
        .execute().data or []
    )
    for run in eligible_runs(runs):
        n = sweep_run(sb, run)
        print(f"swept {run['retailer_name']}: {n} participating store(s), "
              f"rows older than {run['started_at'][:16]} marked out of stock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
