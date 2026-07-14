"""GET /api/deals — the weekly editorial cut of price drops near a zip.

Recomputed per request from the delta-only price_history log (the cut changes
once a week — the Sunday scrape — so request-time cost is fine at beta scale;
precompute if it ever isn't). Empty result is a normal, designed state.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query

from db import get_supabase_client
from recommendation.deals import editorial_cut, rank_deals, week_of_label
from utils.geo import zip_to_centroid, find_nearby_store_ids
from utils.price_context import FRESH_DAYS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/deals", tags=["deals"])



@router.get("", response_model=dict)
async def get_deals(
    zip: str = Query(..., description="User zip — deals are anchored to nearby stores"),
    limit: int = Query(12, le=40),
):
    empty = {"week_of": week_of_label(), "count": 0, "deals": []}
    client = get_supabase_client()

    centroid = zip_to_centroid(zip)
    if centroid is None:
        return empty
    nearby = find_nearby_store_ids(zip, client, centroid=centroid)
    if not nearby:
        return empty

    # 1+2. Fresh drops per (wine × store) — one window-function pass in the DB
    # (fresh_price_drops, migration 20260713000003). Doing this client-side
    # fought postgrest's 1000-row page cap: initial-insert rows crowded the
    # real drops out of the scan.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=FRESH_DAYS)).isoformat()
    drop_rows = (
        client.rpc("fresh_price_drops", {"store_ids": nearby, "since": cutoff})
        .execute()
        .data
        or []
    )
    drops = {
        (r["wine_id"], r["store_ref"]): {
            "amount": float(r["amount"]),
            "from_price": float(r["from_price"]),
            "to_price": float(r["to_price"]),
        }
        for r in drop_rows
    }
    if not drops:
        return empty

    # 3. Confirm the pair is still in stock; inventory price is authoritative.
    drop_wine_ids = list({w for w, _ in drops})
    inv = []
    for i in range(0, len(drop_wine_ids), 200):
        inv.extend(
            client.table("retail_inventory")
            .select("wine_id,store_ref,price")
            .in_("wine_id", drop_wine_ids[i:i + 200])
            .in_("store_ref", nearby)
            .eq("in_stock", True)
            .execute()
            .data
            or []
        )
    in_stock = {(r["wine_id"], r["store_ref"]): float(r["price"]) for r in inv if r.get("price") is not None}

    # 4. Wine + store metadata for the cards.
    wines = {}
    for i in range(0, len(drop_wine_ids), 200):
        for w in (
            client.table("wines")
            .select("id,name,brand,vintage_year,varietal,region,wine_type,image_url,"
                    "vivino_rating,vivino_ratings_count,wine_details(tasting_notes,flavor_profile)")
            .in_("id", drop_wine_ids[i:i + 200])
            .execute()
            .data
            or []
        ):
            wines[w["id"]] = w
    stores = {
        s["id"]: s
        for s in (
            client.table("stores").select("id,retailer_name,address")
            .in_("id", list({s for _, s in drops}))
            .execute()
            .data
            or []
        )
    }

    items = []
    for (wine_id, store_ref), drop in drops.items():
        if (wine_id, store_ref) not in in_stock:
            continue
        wine = wines.get(wine_id) or {}
        details_raw = wine.get("wine_details") or {}
        details = details_raw[0] if isinstance(details_raw, list) else details_raw
        store = stores.get(store_ref) or {}
        items.append({
            "wine_id": wine_id,
            "name": wine.get("name"),
            "producer": wine.get("brand"),
            "vintage_year": wine.get("vintage_year"),
            "varietal": wine.get("varietal"),
            "region": wine.get("region"),
            "wine_type": wine.get("wine_type"),
            "image_url": wine.get("image_url"),
            "vivino_rating": wine.get("vivino_rating"),
            "vivino_ratings_count": wine.get("vivino_ratings_count"),
            "tasting_note": (details or {}).get("tasting_notes"),
            "flavor_profile": (details or {}).get("flavor_profile") or [],
            "price": in_stock[(wine_id, store_ref)],
            "was_price": drop["from_price"],
            "amount": drop["amount"],
            "retailer": store.get("retailer_name"),
            "store_address": store.get("address"),
        })

    # one card per wine — the best-scoring store wins
    ranked = rank_deals(editorial_cut(items))
    seen, deduped = set(), []
    for d in ranked:
        if d["wine_id"] in seen:
            continue
        seen.add(d["wine_id"])
        deduped.append(d)

    return {"week_of": week_of_label(), "count": len(deduped), "deals": deduped[:limit]}
