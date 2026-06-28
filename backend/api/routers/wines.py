from typing import List
from fastapi import APIRouter, Query
from api.schemas import WineSearchResult
from db import get_supabase_client

router = APIRouter(prefix="/api/wines", tags=["wines"])


@router.get("/search", response_model=List[WineSearchResult])
async def search_wines(
    q: str = Query(..., min_length=1, description="Search term — matches wine name"),
    limit: int = Query(20, le=100),
):
    """Search wines by name. Returns up to `limit` results."""
    client = get_supabase_client()
    result = (
        client.table("wines")
        .select("id,name,brand,varietal,region,country,avg_price,wine_type")
        .ilike("name", f"%{q}%")
        .limit(limit)
        .execute()
    )
    return result.data


@router.get("/{wine_id}", response_model=dict)
async def get_wine(wine_id: str):
    """Get a single wine with enrichment detail and all in-stock store availability."""
    client = get_supabase_client()
    wine_result = (
        client.table("wines")
        .select(
            "id,name,brand,varietal,region,sub_region,country,vintage_year,"
            "bottle_size,wine_type,avg_price,"
            "wine_details(description,tasting_notes,flavor_profile,"
            "structure_profile,drinking_window_start,drinking_window_end,"
            "drinking_window_young,drinking_window_ripe,source,grapeminds_enriched_at)"
        )
        .eq("id", wine_id)
        .single()
        .execute()
    )
    data = wine_result.data or {}

    inv_result = (
        client.table("retail_inventory")
        .select("price, stores!inner(retailer_name, address)")
        .eq("wine_id", wine_id)
        .eq("in_stock", True)
        .gte("price", 0)
        .order("price")
        .execute()
    )
    seen = set()
    availability = []
    for row in (inv_result.data or []):
        store = row.get("stores") or {}
        retailer = store.get("retailer_name", "")
        address  = store.get("address", "")
        key = (retailer, address)
        if key in seen:
            continue
        seen.add(key)
        availability.append({
            "retailer": retailer,
            "address":  address,
            "price":    float(row.get("price") or 0),
        })
    data["availability"] = availability
    return data
