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
import sys
import urllib.request
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import infer_wine_type                                       # noqa: E402
from enrichment.extraction.reference import (                           # noqa: E402
    wine_type_for_appellation, APPELLATION_WINE_TYPE, _norm as _region_norm,
)


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
        if f" {app_norm} " in hay:
            return t
    return None


def plan_change(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return {"wine_type": <resolved>} to write, or {} for a no-op."""
    if row.get("wine_type"):
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
