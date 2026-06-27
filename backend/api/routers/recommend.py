import uuid
import logging
import random
from typing import Optional
from fastapi import APIRouter, HTTPException
from api.schemas import RecommendRequest, RecommendResponse, WinePick
from db import get_supabase_client, get_service_client
from recommendation.scorer import score_candidates
from recommendation.claude_client import get_recommendations
from recommendation.intent import parse_message, merge_intent, intent_from_request
from utils.geo import zip_to_centroid, find_nearby_store_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["recommend"])

_MAX_CANDIDATES = 12
_POOL_PER_RETAILER = 80   # wines kept per retailer after per-retailer fetch
_FETCH_PER_RETAILER = 500  # rows fetched per retailer (Supabase hard-caps at 1000/query)

# Maps common user phrasings to the retailer_name values stored in the DB.
_RETAILER_ALIASES = {
    "heb": "H-E-B",
    "h-e-b": "H-E-B",
    "h.e.b": "H-E-B",
    "specs": "Spec's",
    "spec's": "Spec's",
    "geraldines": "Geraldine's",
    "geraldine's": "Geraldine's",
    "geraldine": "Geraldine's",
}


def _detect_retailer(message: str) -> Optional[str]:
    """Return a DB retailer_name substring if the message names a specific shop, else None."""
    if not message:
        return None
    lower = message.lower()
    for alias, name in _RETAILER_ALIASES.items():
        if alias in lower:
            return name
    return None

# PostgREST projection for the candidate query. Defined as a constant so the
# integration test (tests/test_integration_schema.py) can run the EXACT same
# projection against the real schema — every column named here must exist, or
# PostgREST raises 42703. Mocked unit tests can't catch a bad column name.
INVENTORY_SELECT = (
    "price, curbside_price, wine_id,"
    "stores!inner(retailer_name, zip_code),"
    "wines(id, name, varietal, region, country, wine_type, grapes, abv, body,"
    "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
)


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    supabase = get_supabase_client()

    centroid = zip_to_centroid(req.zip_code)
    if centroid is None:
        raise HTTPException(status_code=400, detail="We don't recognize that zip code")

    nearby_ids = find_nearby_store_ids(req.zip_code, supabase, centroid=centroid)
    if not nearby_ids:
        raise HTTPException(
            status_code=400,
            detail="No stores found near your zip code. We currently serve San Antonio, TX.",
        )

    # Supabase hard-caps responses at 1000 rows regardless of .limit(). With Spec's
    # holding 33k records across 12 stores, a single query always returns only Spec's.
    # Fix: look up which stores belong to which retailer, then query each retailer
    # separately so every shop is guaranteed representation in the candidate pool.
    stores_meta = (
        supabase.table("stores")
        .select("id, retailer_name")
        .in_("id", nearby_ids)
        .execute()
    )
    retailer_to_stores: dict = {}
    for s in (stores_meta.data or []):
        sid, rname = s.get("id"), s.get("retailer_name")
        if sid and rname:
            retailer_to_stores.setdefault(rname, []).append(sid)

    if retailer_to_stores:
        # Per-retailer fetch: each retailer gets its own 500-row window
        raw_rows: list = []
        for store_ids in retailer_to_stores.values():
            res = (
                supabase.table("retail_inventory")
                .select(INVENTORY_SELECT)
                .in_("store_ref", store_ids)
                .eq("in_stock", True)
                .gte("price", req.budget_min)
                .lte("price", req.budget_max)
                .limit(_FETCH_PER_RETAILER)
                .execute()
            )
            raw_rows.extend(res.data or [])
    else:
        # Fallback for tests/mocks where stores metadata returns mock data without id/retailer_name
        res = (
            supabase.table("retail_inventory")
            .select(INVENTORY_SELECT)
            .in_("store_ref", nearby_ids)
            .eq("in_stock", True)
            .gte("price", req.budget_min)
            .lte("price", req.budget_max)
            .limit(1000)
            .execute()
        )
        raw_rows = res.data or []

    by_retailer: dict = {}
    for row in raw_rows:
        wine = row.get("wines") or {}
        if not wine:
            continue
        details_raw = wine.get("wine_details") or {}
        details = details_raw[0] if isinstance(details_raw, list) else (details_raw if isinstance(details_raw, dict) else {})
        enriched = bool(details.get("grapeminds_enriched_at"))
        has_extract = bool(wine.get("varietal") or wine.get("region"))
        if not enriched and not has_extract:
            continue  # no basis to match
        retailer = (row.get("stores") or {}).get("retailer_name") or "unknown"
        by_retailer.setdefault(retailer, []).append({
            "wine_id": wine.get("id"),
            "name": wine.get("name"),
            "varietal": wine.get("varietal"),
            "region": wine.get("region"),
            "country": wine.get("country"),
            "wine_type": wine.get("wine_type"),
            "grapes": wine.get("grapes") or [],
            "body": wine.get("body"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"),
            "retailer": retailer,
            "tier": 1 if enriched else 2,
        })

    # Sample up to _POOL_PER_RETAILER from each retailer so every shop is represented.
    candidates = []
    for retailer, pool in by_retailer.items():
        random.shuffle(pool)
        candidates.extend(pool[:_POOL_PER_RETAILER])

    logger.info(
        "INVENTORY | fetched=%d retailers=%s pool=%d",
        sum(len(v) for v in by_retailer.values()),
        {r: len(v) for r, v in by_retailer.items()},
        len(candidates),
    )

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No enriched wines found matching your criteria. Try widening your budget or style preferences.",
        )

    explicit = intent_from_request(
        wine_type=req.wine_type,
        style_preferences=req.style_preferences,
        avoid=req.avoid,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
    )
    parsed = parse_message(req.message) if req.message and req.message != \
        "Recommend wines based on my preferences" else None
    resolved = merge_intent(parsed, explicit)
    resolved["message"] = req.message

    # If the user named a specific retailer, restrict the candidate pool to that shop.
    # Do this before scoring so Geraldine's GrapeMinds advantage doesn't crowd out HEB/Spec's.
    preferred_retailer = _detect_retailer(req.message)
    if preferred_retailer:
        retailer_pool = [c for c in candidates if preferred_retailer in (c.get("retailer") or "")]
        if retailer_pool:
            candidates = retailer_pool
            logger.info("RETAILER FILTER | %r → %d candidates", preferred_retailer, len(candidates))

    # Wine type filter (multi-select). wine_types takes precedence; fall back to legacy wine_type.
    effective_types = req.wine_types or ([req.wine_type] if req.wine_type else [])
    if effective_types:
        type_pool = [c for c in candidates if c.get("wine_type") in effective_types]
        if type_pool:
            candidates = type_pool
            logger.info("TYPE FILTER | %s → %d candidates", effective_types, len(candidates))

    top = score_candidates(resolved, candidates)[:_MAX_CANDIDATES]

    logger.info(
        "RECOMMEND | zip=%s budget=%.0f-%.0f message=%r candidates=%d history=%d",
        req.zip_code, req.budget_min, req.budget_max,
        req.message[:80], len(top), len(req.conversation_history or []),
    )

    try:
        narrative, picks_data = get_recommendations(
            candidates=top,
            intent=resolved,
            conversation_history=req.conversation_history,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")

    # Re-attach authoritative name/price/retailer from the candidate by wine_id —
    # never trust the model to transcribe structured fields it was shown only as text.
    by_id = {c["wine_id"]: c for c in top}
    enriched_picks = []
    for p in picks_data:
        cand = by_id.get(p.get("wine_id"))
        if not cand:
            continue
        enriched_picks.append({
            "wine_id": cand["wine_id"],
            "name": cand.get("name") or p.get("name"),
            "price": cand.get("price") if cand.get("price") is not None else p.get("price"),
            "retailer": cand.get("retailer") or p.get("retailer"),
            "why": p.get("why", ""),
        })
    picks_data = enriched_picks
    if not picks_data:
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")

    session_id = str(uuid.uuid4())
    try:
        service = get_service_client()
        service.table("recommendation_sessions").insert({
            "id": session_id,
            "conversation_history": [
                {"role": "user", "content": req.message},
                {"role": "assistant", "content": {"narrative": narrative, "picks": picks_data}},
            ],
            "recommendations": picks_data,
            "preference_snapshot": req.model_dump(),
        }).execute()
    except Exception:
        pass

    return RecommendResponse(
        narrative=narrative,
        picks=[WinePick(**p) for p in picks_data],
        session_id=session_id,
    )
