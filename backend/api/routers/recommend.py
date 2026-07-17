import hashlib
import json
import re
import uuid
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from api.schemas import RecommendRequest
from db import get_supabase_client, get_service_client
from recommendation.scorer import score_candidates
from recommendation.claude_client import stream_recommendations
from recommendation.intent import parse_message, merge_intent, intent_from_request
from recommendation.candidate_filters import (apply_type_gate, detect_store,
                                              merge_candidates, requested_types_from)
from utils.geo import zip_to_centroid, find_nearby_store_ids, haversine
from api.ratelimit import RateLimiter, limit_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["recommend"])

# Each call costs a Sonnet invocation — cap per IP per hour.
_recommend_limiter = RateLimiter(limit=15, window_seconds=3600)

_MAX_CANDIDATES = 12
_FETCH_PER_RETAILER = 500
# Inventory not re-scraped within this window is benched from recommendations.
# Weekly scrape cadence + 3-day grace; the fetch fails open if nothing survives.
_STALE_INVENTORY_DAYS = 10
_RETAILER_CAP = 5    # max slots one retailer can take in the Claude candidate list
_VARIETAL_CAP = 4    # max slots one grape can take — spreads grocery-heavy markets


def _varietal_key(w: Dict[str, Any]) -> str:
    return (w.get("varietal") or (w.get("grapes") or [None])[0] or "?")


def _select_diverse_top(scored: List[Dict[str, Any]], max_candidates: int,
                        per_retailer_cap: int,
                        per_varietal_cap: int = None) -> List[Dict[str, Any]]:
    """Take the best-scored candidates with per-retailer and (optional)
    per-varietal caps.

    Retailer-correlated data (price clustering, Vivino coverage) lets one
    retailer fill the list; grocery-heavy markets over-index on Cabernet/
    Chardonnay. First pass respects both caps in score order; if fewer than
    max_candidates survive, backfill from the skipped wines (still in score
    order, caps ignored) so a narrow single-retailer/single-grape zip never
    starves.
    """
    r_counts: Dict[str, int] = {}
    v_counts: Dict[str, int] = {}
    top: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for w in scored:
        if len(top) >= max_candidates:
            break
        r = w.get("retailer") or "?"
        v = _varietal_key(w)
        r_ok = r_counts.get(r, 0) < per_retailer_cap
        v_ok = per_varietal_cap is None or v_counts.get(v, 0) < per_varietal_cap
        if r_ok and v_ok:
            r_counts[r] = r_counts.get(r, 0) + 1
            v_counts[v] = v_counts.get(v, 0) + 1
            top.append(w)
        else:
            skipped.append(w)
    for w in skipped:
        if len(top) >= max_candidates:
            break
        top.append(w)
    top.sort(key=lambda w: w.get("_score", 0), reverse=True)
    return top

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
    "stores!inner(id, retailer_name, name, zip_code, address, latitude, longitude),"
    "wines!inner(id, name, varietal, region, country, wine_type, grapes, abv, body,"
    "image_url, vivino_rating, vivino_ratings_count,"
    "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
)


def _apply_type_breadth_filter(q, requested_types: set):
    """Constrain a breadth inventory query to the requested wine types OR NULL
    (NULL kept so mis-typed reds survive; the type gate resolves them later)."""
    if not requested_types:
        return q
    ors = ",".join(f"wine_type.eq.{t}" for t in sorted(requested_types))
    return q.or_(f"{ors},wine_type.is.null", reference_table="wines")


_GENERIC_WINE_WORDS = {
    "cabernet", "sauvignon", "merlot", "pinot", "noir", "gris", "grigio", "chardonnay",
    "syrah", "shiraz", "zinfandel", "malbec", "tempranillo", "sangiovese", "nebbiolo",
    "grenache", "mourvedre", "carignan", "riesling", "blanc", "chenin", "viognier",
    "barbera", "tannat", "red", "white", "rose", "wine", "blend", "reserve", "reserva",
    "vineyard", "vineyards", "valley", "county", "napa", "sonoma", "paso", "robles",
    "california", "italian", "the", "and", "estate", "old", "vine", "vines", "cuvee",
}


def _pick_named_in_narrative(pick: Dict[str, Any], narr_lower: str) -> bool:
    """True when the narrative mentions a DISTINCTIVE token of the pick's name
    (producer/vineyard, not grape/type/region) — or the name has none, in which
    case we keep it (conservative)."""
    name = (pick.get("name") or "").lower()
    tokens = [t for t in re.findall(r"[a-z0-9é]{3,}", name) if t not in _GENERIC_WINE_WORDS]
    return not tokens or any(re.search(r"\b" + re.escape(t) + r"\b", narr_lower) for t in tokens)


def _reconcile_picks_to_narrative(picks: List[Dict[str, Any]], narrative: str) -> List[Dict[str, Any]]:
    """Claude sometimes returns more picks than it writes about — each extra pick
    renders a phantom card ("2 wines described, 3 cards shown"). Drop any pick the
    narrative never names, matched on a DISTINCTIVE token (producer/vineyard, not
    the grape/type/region). Conservative: keep a pick if it has no distinctive
    token or shares one with the narrative, and never drop to empty."""
    if not narrative or len(picks) <= 1:
        return picks
    narr = narrative.lower()
    kept, dropped = [], []
    for p in picks:
        if _pick_named_in_narrative(p, narr):
            kept.append(p)
        else:
            dropped.append(p)
    if dropped and kept:
        logger.info("PICKS RECONCILED | dropped %d pick(s) not named in narrative: %s",
                    len(dropped), [p.get("name") for p in dropped])
    return kept or picks


def _enrich_picks(raw_picks: List[Dict[str, Any]], by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-attach authoritative name/price/retailer/address from candidates by wine_id."""
    enriched = []
    for p in raw_picks:
        cand = by_id.get(p.get("wine_id"))
        if not cand:
            # Claude named a wine in the narrative but its wine_id isn't a known
            # candidate — it gets no card. Log it so narrative/card mismatches
            # (e.g. "3 wines described, 2 cards shown") are diagnosable.
            logger.warning(
                "PICK DROPPED | wine_id=%r name=%r not in candidate pool — no card rendered",
                p.get("wine_id"), p.get("name"),
            )
            continue
        enriched.append({
            "wine_id": cand["wine_id"],
            "name": cand.get("name") or p.get("name"),
            "price": cand.get("price") if cand.get("price") is not None else p.get("price"),
            "retailer": cand.get("retailer") or p.get("retailer"),
            "store_address": cand.get("store_address"),
            "distance_miles": cand.get("distance_miles"),
            "price_drop": cand.get("price_drop"),
            "why": p.get("why", ""),
            "image_url": cand.get("image_url"),
            "vivino_rating": cand.get("vivino_rating"),
            "vivino_ratings_count": cand.get("vivino_ratings_count"),
            "similar_to": cand.get("_similar_to"),          # personalization: liked wine this echoes
            "similar_source": cand.get("_similar_source"),
        })
    return enriched


def _annotate_price_drops(supabase, candidates: List[Dict[str, Any]]) -> None:
    """Attach price_drop {amount, from_price, to_price} to shortlist candidates
    whose (wine, store) price dropped this week — one price_history fetch for
    the whole shortlist. The somm cites it; the card renders the chip."""
    from utils.price_context import fresh_drops_for
    wine_ids = [c["wine_id"] for c in candidates if c.get("wine_id") and c.get("store_ref")]
    if not wine_ids:
        return
    try:
        history = (
            supabase.table("price_history")
            .select("wine_id,store_ref,price,recorded_at")
            .in_("wine_id", wine_ids)
            .order("recorded_at")
            .execute()
            .data
            or []
        )
    except Exception:
        logger.warning("PRICE DROPS | history fetch failed — skipping annotation", exc_info=True)
        return
    drops = fresh_drops_for(history)
    for c in candidates:
        drop = drops.get((c.get("wine_id"), c.get("store_ref")))
        if drop:
            c["price_drop"] = drop


@router.post("/recommend", dependencies=[Depends(limit_dependency(_recommend_limiter, "recommend"))])
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
        .select("id, retailer_name, name")
        .in_("id", nearby_ids)
        .execute()
    )
    retailer_to_stores: dict = {}
    for s in (stores_meta.data or []):
        sid, rname = s.get("id"), s.get("retailer_name")
        if sid and rname:
            retailer_to_stores.setdefault(rname, []).append(sid)

    # chip types only — resolved/parsed intent isn't available until after the fetch; the post-fetch type gate folds in the parsed type for the hard guarantee
    breadth_types = set(t for t in (req.wine_types or ([req.wine_type] if req.wine_type else [])) if t)

    def _fetch_rows(since: Optional[str]) -> list:
        def _query(store_ids: list, limit: int):
            q = (
                supabase.table("retail_inventory")
                .select(INVENTORY_SELECT)
                .in_("store_ref", store_ids)
                .eq("in_stock", True)
                .gte("price", req.budget_min)
                .lte("price", req.budget_max)
            )
            q = _apply_type_breadth_filter(q, breadth_types)
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(limit).execute().data or []

        if retailer_to_stores:
            rows: list = []
            for store_ids in retailer_to_stores.values():
                rows.extend(_query(store_ids, _FETCH_PER_RETAILER))
            return rows
        return _query(nearby_ids, 1000)

    # Bench inventory a dead scraper stopped refreshing (Spec's went silent for
    # 3.5 weeks serving 06-19 prices) — plus zombie rows that dropped off a
    # retailer's feed and never re-upsert. Fail open if the filter empties the
    # pool (e.g. a missed scrape week): stale bottles beat a blank app.
    stale_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=_STALE_INVENTORY_DAYS)
    ).isoformat()
    raw_rows = _fetch_rows(stale_cutoff)
    if not raw_rows:
        logger.warning(
            "INVENTORY | staleness filter emptied the pool (nothing newer than %s) — failing open",
            stale_cutoff[:10],
        )
        raw_rows = _fetch_rows(None)

    def _row_to_candidate(row: dict) -> Optional[dict]:
        wine = row.get("wines") or {}
        if not wine:
            return None
        details_raw = wine.get("wine_details") or {}
        details = details_raw[0] if isinstance(details_raw, list) else (details_raw if isinstance(details_raw, dict) else {})
        enriched = bool(details.get("grapeminds_enriched_at"))
        has_extract = bool(wine.get("varietal") or wine.get("region"))
        if not enriched and not has_extract:
            return None
        store = row.get("stores") or {}
        slat, slon = store.get("latitude"), store.get("longitude")
        distance_miles = (
            round(haversine(centroid[0], centroid[1], float(slat), float(slon)), 1)
            if slat is not None and slon is not None else None
        )
        return {
            "wine_id": wine.get("id"), "name": wine.get("name"),
            "varietal": wine.get("varietal"), "region": wine.get("region"),
            "country": wine.get("country"), "wine_type": wine.get("wine_type"),
            "grapes": wine.get("grapes") or [], "body": wine.get("body"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"), "retailer": store.get("retailer_name") or "unknown",
            "store_address": store.get("address") or None,
            "store_name": store.get("name") or None, "store_ref": store.get("id"),
            "distance_miles": distance_miles, "image_url": wine.get("image_url"),
            "vivino_rating": wine.get("vivino_rating"),
            "vivino_ratings_count": wine.get("vivino_ratings_count"),
            "tier": 1 if enriched else 2,
        }

    by_retailer: dict = {}
    for row in raw_rows:
        cand = _row_to_candidate(row)
        if cand is None:
            continue
        by_retailer.setdefault(cand["retailer"], []).append(cand)

    turn = len(req.conversation_history or [])
    seed_str = f"{req.zip_code}:{req.budget_min:.0f}:{req.budget_max:.0f}:{turn}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2 ** 32)
    rng = random.Random(seed)

    # Score EVERYTHING fetched — truncating per retailer before scoring randomly
    # dropped the best matches. Turn-to-turn variety comes from seeded score
    # jitter applied in the scorer output below, not from discarding candidates.
    candidates = [w for pool in by_retailer.values() for w in pool]

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
    resolved["liked_wines"] = (req.taste or {}).get("liked_wines") or []
    resolved["disliked_wines"] = (req.taste or {}).get("disliked_wines") or []
    resolved["profile"] = (req.taste or {}).get("profile") or None

    detected_store = detect_store(req.message, stores_meta.data or [])

    def _targeted_rows() -> list:
        region = resolved.get("region")
        if not region and not detected_store:
            return []

        def _q(since: Optional[str]) -> list:
            q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
                 .in_("store_ref", nearby_ids).eq("in_stock", True)
                 .gte("price", req.budget_min).lte("price", req.budget_max))
            if region:
                q = q.ilike("wines.region", f"%{region}%")
            if detected_store:
                q = q.eq("store_ref", detected_store["id"])
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(300).execute().data or []

        # Same staleness policy as the breadth fetch: bench dead-scraper rows,
        # but fail open (stale bottles beat a blank targeted result).
        return _q(stale_cutoff) or _q(None)

    targeted = [c for c in (_row_to_candidate(r) for r in _targeted_rows()) if c]
    if targeted:
        candidates = merge_candidates(candidates, targeted)
        logger.info("TARGETED FETCH | region=%r store=%r → +%d rows",
                    resolved.get("region"), detected_store and detected_store["name"], len(targeted))

    preferred_retailer = _detect_retailer(req.message)
    if preferred_retailer:
        retailer_pool = [c for c in candidates if preferred_retailer in (c.get("retailer") or "")]
        if retailer_pool:
            candidates = retailer_pool
            logger.info("RETAILER FILTER | %r → %d candidates", preferred_retailer, len(candidates))

    chip_types = req.wine_types or ([req.wine_type] if req.wine_type else [])
    req_types = requested_types_from(chip_types, resolved.get("wine_type"))
    before = len(candidates)
    candidates = apply_type_gate(candidates, req_types)
    if req_types:
        logger.info("TYPE GATE | %s → %d/%d candidates", sorted(req_types), len(candidates), before)

    # Seeded jitter (±0.4, well under any single axis weight) varies the
    # candidate mix between turns without ever dropping strong matches.
    scored = score_candidates(resolved, candidates)
    for w in scored:
        w["_score"] += rng.uniform(-0.4, 0.4)
    scored.sort(key=lambda w: w["_score"], reverse=True)
    top = _select_diverse_top(scored, _MAX_CANDIDATES, _RETAILER_CAP, _VARIETAL_CAP)
    if detected_store:
        top.sort(key=lambda w: (w.get("store_ref") == detected_store["id"],
                                w.get("_score", 0)), reverse=True)
    _annotate_price_drops(supabase, top)

    logger.info(
        "RECOMMEND | zip=%s budget=%.0f-%.0f message=%r candidates=%d history=%d",
        req.zip_code, req.budget_min, req.budget_max,
        req.message[:80], len(top), len(req.conversation_history or []),
    )

    # Raises immediately (before StreamingResponse starts) if the client can't init.
    try:
        gen = stream_recommendations(top, resolved, req.conversation_history, req.conversational)
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
            elif event_type == "pick":
                # Progressive card: the narrative is fully streamed before any
                # pick arrives (JSON field order), so we can vet it now. Picks
                # the narrative never named are held back — the final "picks"
                # event stays the authority on what ultimately shows.
                enriched_one = _enrich_picks([data], by_id)
                if enriched_one and _pick_named_in_narrative(
                        enriched_one[0], "".join(_result["narrative"]).lower()):
                    yield "data: " + json.dumps({"type": "pick", "pick": enriched_one[0]}) + "\n\n"
            elif event_type == "picks":
                # Enrich BEFORE reconciling: slim model picks carry only
                # wine_id + why, so the name reconcile matches on comes from
                # the candidate.
                enriched_all = _enrich_picks(data, by_id)
                if data and not enriched_all:
                    # Claude returned picks but none matched known wine IDs — real error
                    yield "data: " + json.dumps({"type": "error", "message": "Recommendation service unavailable"}) + "\n\n"
                else:
                    enriched_picks = _reconcile_picks_to_narrative(enriched_all, "".join(_result["narrative"]))
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
