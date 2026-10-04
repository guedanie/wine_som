"""Bottle-photo identification: label photo -> vision read -> catalog match.

Wires together two already-built, already-tested pieces with no changes to
either: enrichment.label_scan (Claude vision reads the label) and
recommendation.label_match (pure catalog-matching logic, the five-state
scanResult classifier). This router owns all the I/O -- reading the upload,
the DB candidate fetch, the vision call -- the same split recommend.py uses
between router-level I/O and pure recommendation/* logic.

Catalog-wide matching, no zip scoping, Haiku only -- see the design doc
(docs/superpowers/specs/2026-10-03-bottle-identify-endpoint-design.md) for
why: this endpoint exists for manual validation against real photos, not
as a finished public feature yet.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from db import get_supabase_client
from enrichment.label_scan import HAIKU, read_label
from recommendation.candidate_filters import significant_name_tokens
from recommendation.label_match import classify_scan
from api.ratelimit import RateLimiter, limit_dependency

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["identify"])

# A vision call per request -- cap per IP per hour. Generous: this endpoint
# exists for manual validation with real photos, not production traffic yet.
_identify_limiter = RateLimiter(limit=30, window_seconds=3600)

_CANDIDATE_LIMIT = 120
_MAX_TOKENS_FOR_SEARCH = 6


def _fetch_candidates(supabase, read: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Catalog-wide token search over name/brand -- mirrors
    scripts/spike_vision_match.py's fetch_candidates. Not shared with that
    script: production routers shouldn't import from scripts/, and both
    sides are small enough that the duplication is cheaper than a shared
    module for two call sites."""
    text = " ".join(filter(None, [read.get("producer"), read.get("wine_name")]))
    tokens = significant_name_tokens(text)
    if not tokens:
        return []
    conds = []
    for t in tokens[:_MAX_TOKENS_FOR_SEARCH]:
        conds.append(f"name.ilike.%{t}%")
        conds.append(f"brand.ilike.%{t}%")
    return (supabase.table("wines")
            .select("id, name, brand, vintage_year, region, varietal")
            .is_("excluded_at", "null")
            .or_(",".join(conds))
            .limit(_CANDIDATE_LIMIT)
            .execute().data or [])


@router.post("/identify", dependencies=[Depends(limit_dependency(_identify_limiter, "identify"))])
async def identify_bottle(photo: UploadFile = File(...)):
    content_type = photo.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400,
                            detail="Upload an image file (jpeg/png/heic).")

    image_bytes = await photo.read()

    try:
        read, meta = read_label(image_bytes, content_type, model=HAIKU)
    except Exception as e:
        logger.exception("IDENTIFY | vision call failed: %s", e)
        raise HTTPException(status_code=502,
                            detail="Couldn't reach the vision service — try again.")

    supabase = get_supabase_client()
    candidates = _fetch_candidates(supabase, read) if read else []
    result = classify_scan(read, candidates)
    result["_debug"] = {
        "read": read,
        "latency_s": meta.get("latency_s"),
        "model": meta.get("model"),
        "input_tokens": meta.get("input_tokens"),
        "output_tokens": meta.get("output_tokens"),
    }
    return result
