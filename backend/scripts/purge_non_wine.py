"""Soft-delete non-wine catalog noise (CLAUDE.md item 32).

DRY-RUN by default — prints what WOULD be excluded (count, sample, reason). Pass
--apply to set wines.excluded_at = now() + exclusion_reason. Idempotent: only rows
where excluded_at IS NULL and should_exclude() is true.

Reverse: UPDATE public.wines SET excluded_at = NULL, exclusion_reason = NULL WHERE ...

Run from backend/:
    /usr/bin/python3 -m scripts.purge_non_wine            # dry-run
    /usr/bin/python3 -m scripts.purge_non_wine --apply
"""
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List

from db import get_service_client
from enrichment.non_wine import should_exclude, matched_marker

_COLS = "id,name,varietal,grapes,wine_type,excluded_at"


def rows_to_exclude(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pure: the subset of rows that should be soft-deleted, each annotated with the
    marker that fired (`reason`). Skips rows already excluded."""
    out = []
    for r in rows:
        if r.get("excluded_at"):
            continue
        if should_exclude(r):
            out.append({**r, "reason": matched_marker(r.get("name"))})
    return out


def _fetch_all(db) -> List[Dict[str, Any]]:
    rows, page, size = [], 0, 1000
    while True:
        chunk = (db.table("wines").select(_COLS)
                 .order("id").range(page * size, page * size + size - 1)
                 .execute().data or [])
        if not chunk:
            break
        rows.extend(chunk)
        page += 1
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write excluded_at (default: dry-run)")
    args = ap.parse_args()

    db = get_service_client()
    targets = rows_to_exclude(_fetch_all(db))
    print(f"non-wine to exclude: {len(targets)}")
    from collections import Counter
    by_reason = Counter(t["reason"] for t in targets)
    print(f"by reason: {dict(by_reason.most_common())}")
    for t in targets[:25]:
        print(f"  [{t['reason']}] {t['name'][:60]}")

    if not args.apply:
        print("\nDRY-RUN — nothing written. Re-run with --apply to soft-delete.")
        return

    now = datetime.now(timezone.utc).isoformat()
    for t in targets:
        db.table("wines").update(
            {"excluded_at": now, "exclusion_reason": t["reason"]}
        ).eq("id", t["id"]).execute()
    print(f"\nAPPLIED — soft-deleted {len(targets)} rows.")


if __name__ == "__main__":
    main()
