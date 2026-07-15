"""Revalidate place fields on existing wines with the gazetteer + evidence gate.

Runs _post_process(rec, source_text=name+description) over every wine that has
a region set and writes back only changed place fields (region/sub_region/
country). Nulls hallucinated regions (grape→region free-association) and fixes
producer misattributions in bulk — CLAUDE.md item 27's re-extraction pass.

Safe-subset policy: only POSITIVE changes are applied (gazetteer fixes,
canonicalization renames, country fills for evidenced regions). Null-
assignments from the evidence gate are DEFERRED and reported, not written —
the gate's appellation coverage is too thin to bulk-null at rest (a 2026-07-13
dry run planned 3,804 nulls, mostly correct producer-knowledge regions like
Grgich Hills → Napa). Revisit once appellation coverage improves.

Run from backend/ (../.env resolves):
    python3 -m scripts.revalidate_regions [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrichment.extraction.extractor import _post_process  # noqa: E402

PLACE_FIELDS = ("region", "sub_region", "country")


def plan_change(row: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (changes, deferred): the positive place-field update payload for
    this wine, and the evidence-gate null-assignments deferred for reporting."""
    # Name only — descriptions compare wines to famous estates ("in the style
    # of Pétrus") and those mentions false-fire the gazetteer.
    source_text = row.get("name") or ""
    rec = {f: row.get(f) for f in PLACE_FIELDS}
    out = _post_process(rec, source_text=source_text)

    changes, deferred = {}, {}
    for f in PLACE_FIELDS:
        if out.get(f) == row.get(f):
            continue
        if out.get(f) is None:
            deferred[f] = None
        else:
            changes[f] = out.get(f)
    return changes, deferred


def fetch_region_set_wines(db, limit: int = 0) -> List[Dict[str, Any]]:
    wines, page, page_size = [], 0, 1000
    while True:
        rows = (db.table("wines")
                .select("id,name,region,sub_region,country")
                .not_.is_("region", "null")
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

    wines = fetch_region_set_wines(db, limit=args.limit)
    print(f"examining {len(wines)} region-set wines", flush=True)

    changed = fixed_region = deferred_nulls = 0
    for w in wines:
        changes, deferred = plan_change(w)
        if deferred:
            deferred_nulls += 1
        if not changes:
            continue
        changed += 1
        if "region" in changes:
            fixed_region += 1
        tag = "DRY " if args.dry_run else ""
        print(f'{tag}{w["id"][:8]} | {w["name"][:60]} | {changes}', flush=True)
        if not args.dry_run:
            db.table("wines").update(changes).eq("id", w["id"]).execute()

    summary = (f"Region revalidation{' (dry run)' if args.dry_run else ''}: "
               f"{len(wines)} examined, {changed} changed "
               f"({fixed_region} regions corrected), "
               f"{deferred_nulls} unevidenced rows deferred (not nulled)")
    print(summary, flush=True)
    if not args.dry_run:
        _notify_slack(f":wine_glass: {summary}")


if __name__ == "__main__":
    main()
