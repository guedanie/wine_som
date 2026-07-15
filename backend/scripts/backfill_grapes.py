"""One-off grapes backfill for Bordeaux/Rhône rows the weekly extraction can't
reach (CLAUDE.md item 27).

Rows extracted before the appellation-law blend defaults shipped have
grapes=[] with region set, so --null-only extraction never revisits them and
the scorer's grape matching can't see them. Per row, in precedence order:

1. varietal names an actual grape           -> grapes=[varietal] (trusted)
2. appellation default (color-gated)        -> grapes=blend
3. region default (Bordeaux/Rhône, red only)-> grapes=blend
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

TARGET_REGIONS = ("Bordeaux", "Rhône")


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
