"""One-off grapes backfill for law-region rows (Bordeaux, Rhône, Champagne,
Douro, Tuscany, Penedès, Other Spain, Provence) the weekly extraction can't
reach (CLAUDE.md item 27).

Rows extracted before the appellation-law blend defaults shipped have
grapes=[] with region set, so --null-only extraction never revisits them and
the scorer's grape matching can't see them. Per row, in precedence order:

1. varietal names an actual grape           -> grapes=[varietal] (trusted)
2. appellation default (color-gated)        -> grapes=blend
3. region default (law regions, color-gated)  -> grapes=blend
4. else no-op — left for the Vivino queue.

varietal is set to the blend's lead grape only when NULL. Writes only changed
fields; whites in red appellations are never touched.

Run from backend/ (../.env resolves):
    python3 -m scripts.backfill_grapes [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrichment.extraction.reference import (canonical_grape,           # noqa: E402
                                             default_grapes_for,
                                             default_grapes_for_region,
                                             is_specific_grape)

TARGET_REGIONS = ("Bordeaux", "Rhône", "Champagne", "Douro", "Tuscany",
                  "Penedès", "Other Spain", "Provence")


def plan_change(row: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """Return (update payload, rule name) for one wine; ({}, None) when no-op."""
    if row.get("region") not in TARGET_REGIONS or (row.get("grapes") or []):
        return {}, None
    varietal = row.get("varietal")
    if is_specific_grape(varietal):
        grapes, rule = [canonical_grape(varietal)], "specific-varietal"
    else:
        grapes = default_grapes_for(row.get("sub_region"), row.get("wine_type"))
        rule = "appellation"
        if not grapes:
            grapes = default_grapes_for_region(row.get("region"), row.get("wine_type"))
            rule = "region"
        if not grapes:
            return {}, None
    changes = {"grapes": grapes}
    if not varietal:
        changes["varietal"] = grapes[0]
    return changes, rule


def fetch_target_wines(db, limit: int = 0) -> List[Dict[str, Any]]:
    """All law-region rows; plan_change skips the ones that have grapes
    (postgrest can't cleanly filter 'empty JSON array', so filter client-side
    — it's ~2,100 rows, 3 pages)."""
    wines, page, page_size = [], 0, 1000
    while True:
        rows = (db.table("wines")
                .select("id,name,region,sub_region,varietal,wine_type,grapes")
                .in_("region", list(TARGET_REGIONS))
                .order("id")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute().data)
        wines.extend(rows)
        page += 1
        if len(rows) < page_size or (limit and len(wines) >= limit):
            break
    if limit:
        wines = wines[:limit]
    return wines


def _notify_slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"slack notify failed: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from db import get_service_client
    db = get_service_client()

    wines = fetch_target_wines(db, limit=args.limit)
    empty = sum(1 for w in wines if not (w.get("grapes") or []))
    print(f"examining {len(wines)} law-region wines ({empty} grapes-empty)", flush=True)

    by_rule = {"specific-varietal": 0, "appellation": 0, "region": 0}
    changed = 0
    for w in wines:
        changes, rule = plan_change(w)
        if not changes:
            continue
        changed += 1
        by_rule[rule] += 1
        tag = "DRY " if args.dry_run else ""
        print(f'{tag}{w["id"][:8]} | {(w["name"] or "")[:55]} | {rule} | {changes}', flush=True)
        if not args.dry_run:
            db.table("wines").update(changes).eq("id", w["id"]).execute()

    summary = (f"Grapes backfill{' (dry run)' if args.dry_run else ''}: "
               f"{empty} empty of {len(wines)} law-region wines, {changed} filled "
               f"({by_rule['specific-varietal']} trusted varietal, "
               f"{by_rule['appellation']} appellation blends, "
               f"{by_rule['region']} region blends), "
               f"{empty - changed} left for Vivino")
    print(summary, flush=True)
    if not args.dry_run:
        _notify_slack(f":grapes: {summary}")


if __name__ == "__main__":
    main()
