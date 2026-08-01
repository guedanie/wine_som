"""Nearby stores for the aisle-mode store picker: 'Which one are you standing
in?' — branch name + address + miles, closest first."""
from fastapi import APIRouter, HTTPException, Query
from db import get_supabase_client
from utils.geo import zip_to_centroid, find_nearby_store_ids, haversine

router = APIRouter(prefix="/api", tags=["stores"])


@router.get("/stores/nearby")
def nearby_stores(zip: str = Query(..., description="User zip")):
    centroid = zip_to_centroid(zip)
    if centroid is None:
        raise HTTPException(status_code=400, detail="We don't recognize that zip code")
    supabase = get_supabase_client()
    ids = find_nearby_store_ids(zip, supabase, centroid=centroid)
    if not ids:
        raise HTTPException(status_code=400, detail="No stores found near your zip code.")
    rows = (supabase.table("stores")
            .select("id, retailer_name, name, address, latitude, longitude")
            .in_("id", ids).execute().data or [])
    out = []
    for s in rows:
        lat, lon = s.get("latitude"), s.get("longitude")
        dist = (round(haversine(centroid[0], centroid[1], float(lat), float(lon)), 1)
                if lat is not None and lon is not None else None)
        out.append({"id": s["id"], "retailer_name": s.get("retailer_name"),
                    "name": s.get("name"), "address": s.get("address"),
                    "distance_miles": dist})
    out.sort(key=lambda s: (s["distance_miles"] is None, s["distance_miles"] or 0))
    return {"zip": zip, "stores": out}
