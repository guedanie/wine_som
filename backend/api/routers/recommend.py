import uuid
from fastapi import APIRouter, HTTPException
from api.schemas import RecommendRequest, RecommendResponse, WinePick
from db import get_supabase_client, get_service_client
from recommendation.scorer import score_candidates
from recommendation.claude_client import get_recommendations

router = APIRouter(prefix="/api", tags=["recommend"])

_MAX_CANDIDATES = 12


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    supabase = get_supabase_client()

    result = (
        supabase.table("retail_inventory")
        .select(
            "price, retailer_name, wine_id,"
            "wines(id, name, varietal, region, country, wine_type,"
            "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
        )
        .eq("zip_code", req.zip_code)
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
        if not details.get("grapeminds_enriched_at"):
            continue
        candidates.append({
            "wine_id": wine.get("id"),
            "name": wine.get("name"),
            "varietal": wine.get("varietal"),
            "region": wine.get("region"),
            "country": wine.get("country"),
            "wine_type": wine.get("wine_type"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"),
            "retailer": row.get("retailer_name"),
        })

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No enriched wines found matching your criteria. Try widening your budget or style preferences.",
        )

    top = score_candidates(
        candidates=candidates,
        wine_type=req.wine_type,
        style_preferences=req.style_preferences,
        avoid=req.avoid,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
    )[:_MAX_CANDIDATES]

    try:
        narrative, picks_data = get_recommendations(
            candidates=top,
            budget_min=req.budget_min,
            budget_max=req.budget_max,
            style_preferences=req.style_preferences,
            avoid=req.avoid,
            wine_type=req.wine_type,
        )
    except Exception:
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
