"""LLM structure/sweetness pass (CLAUDE.md item 12).

Two eligibility classes, one qwen2.5:7b pass on the mini:
1. SWEETNESS FILL — a wine has a structure_profile with no `sweetness`. The LLM
   value is MERGED into the existing profile (body/tannins/acidity untouched).
2. UNANCHORED BLEND — a wine has grape data the table can't anchor
   (structure_for -> None) and no profile. The LLM writes the FULL profile.

Run from backend/ on the mini:
    python3 -m scripts.backfill_structure_llm [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recommendation.structure_profiles import structure_for               # noqa: E402
from enrichment.extraction.structure_benchmark import _SYSTEM, OLLAMA_URL  # noqa: E402

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def clamp_1_10(v) -> Optional[int]:
    """Integer 1-10 or None (out-of-range / unparseable -> drop, never coerce)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 10 else None


def needs_sweetness(profile: Optional[Dict[str, Any]]) -> bool:
    return bool(profile) and profile.get("sweetness") is None


def needs_full_profile(wine: Dict[str, Any], has_profile: bool) -> bool:
    if has_profile:
        return False
    if not (wine.get("grapes") or wine.get("varietal")):
        return False
    return structure_for(wine.get("varietal"), wine.get("grapes"),
                         wine.get("region")) is None


def merge_sweetness(profile: Dict[str, Any], sweetness: int) -> Dict[str, Any]:
    """Copy the profile with sweetness set; body/tannins/acidity untouched."""
    out = dict(profile)
    out["sweetness"] = sweetness
    if out.get("source") != "llm":
        out["sweetness_source"] = "llm"
    return out


def full_profile_from(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Full llm profile from a raw response row (maps 'tannin' -> 'tannins').
    None if ANY axis is out of range (don't write a partial profile)."""
    body = clamp_1_10(resp.get("body"))
    tannins = clamp_1_10(resp.get("tannin"))
    acidity = clamp_1_10(resp.get("acidity"))
    sweetness = clamp_1_10(resp.get("sweetness"))
    if None in (body, tannins, acidity, sweetness):
        return None
    return {"body": body, "tannins": tannins, "acidity": acidity,
            "sweetness": sweetness, "source": "llm"}


def validate_batch(resp: Dict[str, Any],
                   batch_ids: set) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
    """Return ({wine_id: raw_row}, bad_id_count, bad_value_count). Drops rows
    whose wine_id isn't in the input batch (qwen echo corruption) or whose
    sweetness doesn't clamp."""
    clean, bad_id, bad_val = {}, 0, 0
    for r in resp.get("wines", []):
        wid = str(r.get("wine_id") or "")
        if wid not in batch_ids:
            bad_id += 1
            continue
        if clamp_1_10(r.get("sweetness")) is None:
            bad_val += 1
            continue
        clean[wid] = r
    return clean, bad_id, bad_val
