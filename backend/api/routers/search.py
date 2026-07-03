from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from db import get_supabase_client
from utils.geo import zip_to_centroid, find_nearby_store_ids, haversine

router = APIRouter(prefix="/api", tags=["search"])

_WINE_MATCH_LIMIT = 300      # catalog rows matched by name/brand/varietal/region
_INVENTORY_LIMIT = 1000


class SearchWineRow(BaseModel):
    wine_id: str
    name: str
    brand: Optional[str] = None
    vintage_year: Optional[int] = None
    varietal: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    wine_type: Optional[str] = None
    price: float
    retailer: str
    distance_miles: Optional[float] = None
    image_url: Optional[str] = None
    vivino_rating: Optional[float] = None
    vivino_ratings_count: Optional[int] = None


class SearchResponse(BaseModel):
    query: str
    wines: List[SearchWineRow]


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search term — matches name/brand/varietal/region"),
    zip: str = Query(..., description="User zip code for nearby availability + distance"),
    max_price: Optional[float] = Query(None, description="Price ceiling"),
    retailers: Optional[str] = Query(None, description="Comma-separated retailer names"),
    varietals: Optional[str] = Query(None, description="Comma-separated varietal names"),
):
    """Search the catalog, constrained to wines in stock at nearby stores.

    Returns one row per wine at its lowest nearby price, with retailer and
    straight-line distance from the zip centroid.
    """
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

    # Store metadata: retailer name + distance from the zip centroid
    stores_resp = (
        db.table("stores")
        .select("id, retailer_name, latitude, longitude")
        .in_("id", nearby_ids)
        .execute()
    )
    store_meta: Dict[str, Dict[str, Any]] = {}
    for s in (stores_resp.data or []):
        dist = None
        if s.get("latitude") is not None and s.get("longitude") is not None:
            dist = round(haversine(centroid[0], centroid[1],
                                   float(s["latitude"]), float(s["longitude"])), 1)
        store_meta[s["id"]] = {"retailer": s.get("retailer_name") or "", "distance": dist}

    # Catalog match on the query term
    term = q.strip().replace(",", " ")
    ilike = f"%{term}%"
    wines_q = (
        db.table("wines")
        .select("id,name,brand,vintage_year,varietal,region,country,wine_type,"
                "image_url,vivino_rating,vivino_ratings_count")
        .or_(f"name.ilike.{ilike},brand.ilike.{ilike},"
             f"varietal.ilike.{ilike},region.ilike.{ilike}")
        .limit(_WINE_MATCH_LIMIT)
    )
    wine_rows = wines_q.execute().data or []

    if varietals:
        wanted = {v.strip().lower() for v in varietals.split(",") if v.strip()}
        wine_rows = [w for w in wine_rows if (w.get("varietal") or "").lower() in wanted]

    if not wine_rows:
        return SearchResponse(query=q, wines=[])

    by_wine_id = {w["id"]: w for w in wine_rows}

    # Nearby in-stock inventory for the matched wines
    inv_q = (
        db.table("retail_inventory")
        .select("price, wine_id, store_ref")
        .in_("wine_id", list(by_wine_id.keys()))
        .in_("store_ref", nearby_ids)
        .eq("in_stock", True)
        .lte("price", max_price if max_price is not None else 99999)
        .limit(_INVENTORY_LIMIT)
    )
    inv_rows = inv_q.execute().data or []

    wanted_retailers = None
    if retailers:
        wanted_retailers = {r.strip() for r in retailers.split(",") if r.strip()}

    # Lowest price per wine
    best: Dict[str, Dict[str, Any]] = {}
    for row in inv_rows:
        wid = row.get("wine_id")
        meta = store_meta.get(row.get("store_ref"))
        if wid not in by_wine_id or meta is None:
            continue
        if wanted_retailers and meta["retailer"] not in wanted_retailers:
            continue
        price = float(row.get("price") or 0)
        if price <= 0:
            continue
        if wid not in best or price < best[wid]["price"]:
            best[wid] = {"price": price, "retailer": meta["retailer"],
                         "distance": meta["distance"]}

    term_lower = term.lower()
    results = []
    for wid, offer in best.items():
        w = by_wine_id[wid]
        results.append(SearchWineRow(
            wine_id=wid,
            name=w.get("name") or "",
            brand=w.get("brand"),
            vintage_year=w.get("vintage_year"),
            varietal=w.get("varietal"),
            region=w.get("region"),
            country=w.get("country"),
            wine_type=w.get("wine_type"),
            price=offer["price"],
            retailer=offer["retailer"],
            distance_miles=offer["distance"],
            image_url=w.get("image_url"),
            vivino_rating=w.get("vivino_rating"),
            vivino_ratings_count=w.get("vivino_ratings_count"),
        ))

    # Name hits first, then community standing, then price
    results.sort(key=lambda r: (
        0 if term_lower in (r.name or "").lower() else 1,
        -(r.vivino_ratings_count or 0),
        r.price,
    ))
    return SearchResponse(query=q, wines=results)
