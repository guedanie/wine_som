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
    """Get a single wine with its enrichment detail if available."""
    client = get_supabase_client()
    result = (
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
    return result.data
