import hashlib
import json
import uuid
import logging
import random
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from api.schemas import RecommendRequest
from db import get_supabase_client, get_service_client
from recommendation.scorer import score_candidates
from recommendation.claude_client import stream_recommendations
from recommendation.intent import parse_message, merge_intent, intent_from_request
from utils.geo import zip_to_centroid, find_nearby_store_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["recommend"])

_MAX_CANDIDATES = 12
_POOL_PER_RETAILER = 80
_FETCH_PER_RETAILER = 500

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
    if not message:
        return None
    lower = message.lower()
    for alias, name in _RETAILER_ALIASES.items():
        if alias in lower:
            return name
    return None


INVENTORY_SELECT = (
    "price, curbside_price, wine_id,"
    "stores!inner(retailer_name, zip_code, address),"
    "wines(id, name, varietal, region, country, wine_type, grapes, abv, body,"
    "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
)


def _enrich_picks(raw_picks: List[Dict[str, Any]], by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-attach authoritative name/price/retailer/address from candidates by wine_id."""
    enriched = []
    for p in raw_picks:
        cand = by_id.get(p.get("wine_id"))
        if not cand:
            continue
        enriched.append({
            "wine_id": cand["wine_id"],
            "name": cand.get("name") or p.get("name"),
            "price": cand.get("price") if cand.get("price") is not None else p.get("price"),
            "retailer": cand.get("retailer") or p.get("retailer"),
            "store_address": cand.get("store_address"),
            "why": p.get("why", ""),
        })
    return enriched


@router.post("/recommend")
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
            continue
        retailer = (row.get("stores") or {}).get("retailer_name") or "unknown"
        store_address = (row.get("stores") or {}).get("address") or None
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
            "store_address": store_address,
            "tier": 1 if enriched else 2,
        })

    turn = len(req.conversation_history or [])
    seed_str = f"{req.zip_code}:{req.budget_min:.0f}:{req.budget_max:.0f}:{turn}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2 ** 32)
    rng = random.Random(seed)

    candidates = []
    for retailer, pool in by_retailer.items():
        rng.shuffle(pool)
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
        grapes=req.grapes,
    )
    parsed = parse_message(req.message) if req.message and req.message != \
        "Recommend wines based on my preferences" else None
    resolved = merge_intent(parsed, explicit)
    resolved["message"] = req.message

    preferred_retailer = _detect_retailer(req.message)
    if preferred_retailer:
        retailer_pool = [c for c in candidates if preferred_retailer in (c.get("retailer") or "")]
        if retailer_pool:
            candidates = retailer_pool
            logger.info("RETAILER FILTER | %r → %d candidates", preferred_retailer, len(candidates))

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

    # Raises immediately (before StreamingResponse starts) if the client can't init.
    try:
        gen = stream_recommendations(top, resolved, req.conversation_history)
    except Exception:
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")

    by_id = {c["wine_id"]: c for c in top}
    session_id = str(uuid.uuid4())
    _result: dict = {"narrative": [], "picks": []}

    def event_gen():
        for event_type, data in gen:
            if event_type == "token":
                _result["narrative"].append(data)
                yield "data: " + json.dumps({"type": "token", "text": data}) + "\n\n"
            elif event_type == "picks":
                enriched_picks = _enrich_picks(data, by_id)
                if data and not enriched_picks:
                    # Claude returned picks but none matched known wine IDs — real error
                    yield "data: " + json.dumps({"type": "error", "message": "Recommendation service unavailable"}) + "\n\n"
                else:
                    _result["picks"] = enriched_picks
                    yield "data: " + json.dumps({"type": "picks", "picks": enriched_picks, "session_id": session_id}) + "\n\n"
            elif event_type == "suggestions":
                yield "data: " + json.dumps({"type": "suggestions", "suggestions": data}) + "\n\n"
            elif event_type == "error":
                yield "data: " + json.dumps({"type": "error", "message": data}) + "\n\n"
        yield "data: [DONE]\n\n"

        # Session persistence after stream completes
        try:
            narrative = "".join(_result["narrative"])
            service = get_service_client()
            service.table("recommendation_sessions").insert({
                "id": session_id,
                "conversation_history": [
                    {"role": "user", "content": req.message},
                    {"role": "assistant", "content": {"narrative": narrative, "picks": _result["picks"]}},
                ],
                "recommendations": _result["picks"],
                "preference_snapshot": req.model_dump(),
            }).execute()
        except Exception:
            pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
