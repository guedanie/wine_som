"""One-off wine_type backfill for NULL-wine_type wines (CLAUDE.md item 30).

27.5% of wines have wine_type NULL, invisible to DB-level type surfaces (search
filter, /deals, /discover, stats). Per row (fill-only, never overwrites), resolve
type deterministically in precedence order:

1. infer_wine_type(varietal)
2. infer_wine_type(name)
3. infer_wine_type(first grape)
4. wine_type_for_appellation(region, sub_region)   # single-color appellations

None resolves -> no-op (non-wine junk + signal-less producers stay NULL for
Vivino/LLM). wine_type is fill-only and Vivino can't overwrite it, so writes are
permanent — the resolvers are deterministic/law-backed only.

Run from backend/ (../.env resolves):
    python3 -m scripts.backfill_wine_type [--dry-run] [--limit N]
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import infer_wine_type                                       # noqa: E402
from enrichment.extraction.reference import (                           # noqa: E402
    wine_type_for_appellation, APPELLATION_WINE_TYPE, _norm as _region_norm,
)


# Appellation keys too ambiguous to word-match inside a free-text NAME (common
# words / surnames). They still resolve via the authoritative region/sub_region
# path in wine_type_for_appellation — just not from a name scan.
_NAME_SCAN_SKIP = {"fino", "marsala", "jerez", "gavi"}


def _appellation_in_text(text: Optional[str]) -> Optional[str]:
    """Scan free text (e.g. a wine name) for a definitionally single-color
    appellation ('Domaine X Chablis 2022' -> white) using the same map
    wine_type_for_appellation checks against explicit region/sub_region
    fields. Multi-color places (Burgundy villages, Bordeaux communes, ...)
    aren't in the map, so they correctly don't match here either."""
    if not text:
        return None
    hay = f" {_region_norm(text)} "
    for app_norm, t in APPELLATION_WINE_TYPE.items():
        if app_norm in _NAME_SCAN_SKIP:
            continue
        if f" {app_norm} " in hay:
            return t
    return None


# Non-grape-wine catalog noise (grocery scrapers pull these into `wines`): sake,
# cocktails, non-alcoholic drinks, cider/mead, and food. The backfill leaves them
# NULL rather than stamp a spurious wine_type from a color/style word in the name.
# Distinctive tokens only, word-boundary matched, to avoid skipping real wines
# (a 'Maple Creek' winery, 'Sakonnet Vineyards', a 'Muscadine' grape wine).
_NON_WINE_MARKERS = (
    "sake", "junmai", "daiginjo", "ginjo", "nigori",
    "non-alcoholic", "non alcoholic", "nonalcoholic", "alcohol removed",
    "alcohol-removed", "zero proof", "kombucha", "seltzer", "hard cider",
    "cider", "mead", "cocktail", "cocktails", "lemonade", "limeade", "iced tea",
    "sweet tea", "sparkling water", "tonic water", "energy drink",
    "maple syrup", "pancake", "waffle", "grapefruit", "fruit cup",
    "oatmeal", "grits", "fruit wine", "apple wine", "peach wine", "plum wine",
    "syrup",
)


def _is_non_wine(name: Optional[str]) -> bool:
    """True when the name marks a non-grape-wine product that must not be typed."""
    if not name:
        return False
    low = name.lower()
    return any(re.search(rf"\b{re.escape(m)}\b", low) for m in _NON_WINE_MARKERS)


def plan_change(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return {"wine_type": <resolved>} to write, or {} for a no-op."""
    if row.get("wine_type"):
        return {}
    if _is_non_wine(row.get("name")):
        return {}
    varietal, name = row.get("varietal"), row.get("name")
    grape = (row.get("grapes") or [None])[0]

    if varietal:
        t = infer_wine_type(varietal)
        if t:
            return {"wine_type": t}
    if name:
        t = infer_wine_type(name) or _appellation_in_text(name)
        if t:
            return {"wine_type": t}
    if grape:
        t = infer_wine_type(grape)
        if t:
            return {"wine_type": t}
    t = wine_type_for_appellation(row.get("region"), row.get("sub_region"))
    return {"wine_type": t} if t else {}


def fetch_null_type_wines(db, limit: int = 0) -> List[Dict[str, Any]]:
    """All wines with wine_type NULL (paged)."""
    wines, page, page_size = [], 0, 1000
    while True:
        rows = (db.table("wines")
                .select("id,name,varietal,grapes,region,sub_region,wine_type")
                .is_("wine_type", "null")
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

    wines = fetch_null_type_wines(db, limit=args.limit)
    print(f"examining {len(wines)} NULL-wine_type wines", flush=True)

    by_type: Dict[str, int] = {}
    changed = 0
    for w in wines:
        changes = plan_change(w)
        if not changes:
            continue
        changed += 1
        t = changes["wine_type"]
        by_type[t] = by_type.get(t, 0) + 1
        tag = "DRY " if args.dry_run else ""
        print(f'{tag}{w["id"][:8]} | {(w["name"] or "")[:55]} | {t}', flush=True)
        if not args.dry_run:
            db.table("wines").update(changes).eq("id", w["id"]).execute()

    dist = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items(), key=lambda x: -x[1]))
    summary = (f"wine_type backfill{' (dry run)' if args.dry_run else ''}: "
               f"{changed} of {len(wines)} NULL-type wines filled ({dist}), "
               f"{len(wines) - changed} left NULL")
    print(summary, flush=True)
    if not args.dry_run:
        _notify_slack(f":wine_glass: {summary}")


if __name__ == "__main__":
    main()
