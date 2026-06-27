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
    "wines!inner(id, name, varietal, region, country, wine_type, grapes, image_url,"
    "wine_details(flavor_profile))"
)

_FETCH_LIMIT = 500   # rows per retailer before partitioning


def _db_region_name(region: str) -> str:
    return _REGION_ALIASES.get(region, region)


def _price_partition(wines: List[Dict[str, Any]], n_per_tier: int = 5) -> List[Dict[str, Any]]:
    """Return up to n_per_tier wines from each of 3 price tiers (low/mid/high)."""
    if not wines:
        return []
    prices = [w["price"] for w in wines]
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return wines[:n_per_tier * 3]
    span = (hi - lo) / 3
    tiers: List[List[Dict[str, Any]]] = [[], [], []]
    for w in wines:
        idx = min(int((w["price"] - lo) / span), 2)
        tiers[idx].append(w)
    result: List[Dict[str, Any]] = []
    for tier in tiers:
        result.extend(tier[:n_per_tier])
    return result


def _row_to_wine_item(row: Dict[str, Any], retailer: str, address: Optional[str]) -> Optional[RegionWineItem]:
    wine = row.get("wines") or {}
    if not wine:
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
            .gte("price", 0)
            .lte("price", 9999)
            .limit(_FETCH_LIMIT)
            .execute()
        )
        for row in (rows.data or []):
            wine = row.get("wines") or {}
            if wine.get("region") != db_region:
                continue
            address = (row.get("stores") or {}).get("address")
            item = _row_to_wine_item(row, rname, address)
            if item:
                by_retailer.setdefault(rname, []).append(item.model_dump())

    if not by_retailer:
        raise HTTPException(
            status_code=404,
            detail=f"No in-stock wines from {region_name} found near your zip code.",
        )

    retailers = []
    for rname in sorted(by_retailer.keys()):
        partitioned = _price_partition(by_retailer[rname], n_per_tier=5)
        wines = [RegionWineItem(**w) for w in partitioned]
        retailers.append(RegionRetailerGroup(retailer=rname, wines=wines))

    return RegionResponse(region=region_name, retailers=retailers)
