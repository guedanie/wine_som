import uuid
from fastapi import APIRouter, HTTPException
from api.schemas import RecommendRequest, RecommendResponse, WinePick
from db import get_supabase_client, get_service_client
from recommendation.scorer import score_candidates
from recommendation.claude_client import get_recommendations
from recommendation.intent import parse_message, merge_intent, intent_from_request
from utils.geo import zip_to_centroid, find_nearby_store_ids

router = APIRouter(prefix="/api", tags=["recommend"])

_MAX_CANDIDATES = 12

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

    result = (
        supabase.table("retail_inventory")
        .select(INVENTORY_SELECT)
        .in_("store_ref", nearby_ids)
        .eq("in_stock", True)
        .gte("price", req.budget_min)
        .lte("price", req.budget_max)
        .execute()
    )

    candidates = []
    for row in (result.data or []):
        wine = row.get("wines") or {}
        if not wine:
            continue
        details_list = wine.get("wine_details") or []
        details = details_list[0] if isinstance(details_list, list) and details_list else {}
        enriched = bool(details.get("grapeminds_enriched_at"))
        has_extract = bool(wine.get("varietal") or wine.get("region"))
        if not enriched and not has_extract:
            continue  # no basis to match
        candidates.append({
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
            "retailer": (row.get("stores") or {}).get("retailer_name"),
            "tier": 1 if enriched else 2,
        })

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

    top = score_candidates(resolved, candidates)[:_MAX_CANDIDATES]

    try:
        narrative, picks_data = get_recommendations(candidates=top, intent=resolved)
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
