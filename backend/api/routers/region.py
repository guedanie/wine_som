from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from api.schemas import RegionResponse, RegionRetailerGroup, RegionWineItem
from db import get_supabase_client
from utils.geo import zip_to_centroid, find_nearby_store_ids

router = APIRouter(prefix="/api", tags=["region"])

# DB stores sub-regions under the parent name for two DISCOVERY_REGIONS entries.
_REGION_ALIASES: Dict[str, str] = {
    "Rhône Valley": "Rhône",
    "Douro Valley": "Douro",
}

_REGION_INVENTORY_SELECT = (
    "price, wine_id,"
    "stores!inner(retailer_name, address),"
    "wines!inner(id, excluded_at, name, varietal, region, country, wine_type, grapes, image_url,"
    "wine_details(flavor_profile))"
)

_FETCH_LIMIT = 500   # rows per retailer from DB
_PER_RETAILER_LIMIT = 40  # wines returned per retailer (sorted by price)


def _db_region_name(region: str) -> str:
    return _REGION_ALIASES.get(region, region)


def _row_to_wine_item(row: Dict[str, Any], retailer: str, address: Optional[str]) -> Optional[RegionWineItem]:
    wine = row.get("wines") or {}
    if not wine:
        return None
    if wine.get("excluded_at"):
        return None
    details_raw = wine.get("wine_details") or {}
    details = details_raw[0] if isinstance(details_raw, list) else (details_raw if isinstance(details_raw, dict) else {})
    return RegionWineItem(
        wine_id=wine.get("id", ""),
        name=wine.get("name", ""),
        varietal=wine.get("varietal"),
        region=wine.get("region"),
        country=wine.get("country"),
        wine_type=wine.get("wine_type"),
        price=float(row.get("price") or 0),
        retailer=retailer,
        store_address=address,
        image_url=wine.get("image_url"),
        flavor_profile=details.get("flavor_profile") or [],
        grapes=wine.get("grapes") or [],
    )


@router.get("/region/{region_name}/subregions")
async def get_subregion_counts(
    region_name: str,
    zip: Optional[str] = Query(None, description="Scope counts to wines in stock near this zip"),
):
    """Wine counts grouped by sub_region for a region.

    With a `zip`, counts only wines that are in stock at stores near that zip —
    so the number a user sees matches what clicking it (a zip-scoped search)
    returns. Without a zip, catalog-wide (stable weights).
    """
    db = get_supabase_client()
    db_region = _db_region_name(region_name)
    rows = (
        db.table("wines")
        .select("id, sub_region")
        .eq("region", db_region)
        .not_.is_("sub_region", "null")
        .is_("excluded_at", "null")
        .limit(10000)
        .execute()
    ).data or []

    if zip:
        centroid = zip_to_centroid(zip)
        nearby = find_nearby_store_ids(zip, db, centroid=centroid) if centroid else []
        if not nearby:
            return {"region": region_name, "counts": {}}
        wine_ids = [r["id"] for r in rows]
        available: set = set()
        for i in range(0, len(wine_ids), 200):
            inv = (
                db.table("retail_inventory")
                .select("wine_id")
                .in_("wine_id", wine_ids[i:i + 200])
                .in_("store_ref", nearby)
                .eq("in_stock", True)
                .limit(5000)
                .execute()
            ).data or []
            available |= {r["wine_id"] for r in inv}
        rows = [r for r in rows if r["id"] in available]

    counts: Dict[str, int] = {}
    for row in rows:
        sub = row.get("sub_region")
        if sub:
            counts[sub] = counts.get(sub, 0) + 1
    return {"region": region_name, "counts": counts}


@router.get("/region/{region_name}", response_model=RegionResponse)
async def get_region_wines(
    region_name: str,
    zip: str = Query(..., description="User zip code for nearby store lookup"),
):
    db = get_supabase_client()

    centroid = zip_to_centroid(zip)
    if centroid is None:
        raise HTTPException(status_code=400, detail="We don't recognize that zip code")

    nearby_ids = find_nearby_store_ids(zip, db, centroid=centroid)
    if not nearby_ids:
        raise HTTPException(
            status_code=400,
            detail="No stores found near your zip code. We currently serve San Antonio, TX.",
        )

    db_region = _db_region_name(region_name)

    # Group nearby stores by retailer so we can cap per retailer
    stores_resp = (
        db.table("stores")
        .select("id, retailer_name")
        .in_("id", nearby_ids)
        .execute()
    )
    retailer_to_stores: Dict[str, List[str]] = {}
    for s in (stores_resp.data or []):
        sid, rname = s.get("id"), s.get("retailer_name")
        if sid and rname:
            retailer_to_stores.setdefault(rname, []).append(sid)

    by_retailer: Dict[str, List[Dict[str, Any]]] = {}

    for rname, store_ids in retailer_to_stores.items():
        rows = (
            db.table("retail_inventory")
            .select(_REGION_INVENTORY_SELECT)
            .in_("store_ref", store_ids)
            .eq("in_stock", True)
            .eq("wines.region", db_region)
            .gte("price", 0)
            .lte("price", 9999)
            .limit(_FETCH_LIMIT)
            .execute()
        )
        # Dedup by wine_id, keeping the lowest price across stores
        seen: Dict[str, Dict[str, Any]] = {}
        for row in (rows.data or []):
            wine = row.get("wines") or {}
            if not wine:
                continue
            wid = wine.get("id", "")
            price = float(row.get("price") or 0)
            if wid not in seen or price < seen[wid]["price"]:
                address = (row.get("stores") or {}).get("address")
                item = _row_to_wine_item(row, rname, address)
                if item:
                    seen[wid] = item.model_dump()
        by_retailer[rname] = list(seen.values()) if seen else []
        if not by_retailer[rname]:
            del by_retailer[rname]

    if not by_retailer:
        raise HTTPException(
            status_code=404,
            detail=f"No in-stock wines from {region_name} found near your zip code.",
        )

    retailers = []
    for rname in sorted(by_retailer.keys()):
        sorted_wines = sorted(by_retailer[rname], key=lambda w: w["price"])[:_PER_RETAILER_LIMIT]
        wines = [RegionWineItem(**w) for w in sorted_wines]
        retailers.append(RegionRetailerGroup(retailer=rname, wines=wines))

    return RegionResponse(region=region_name, retailers=retailers)
