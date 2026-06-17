import math
from typing import Optional, Tuple, List
import pgeocode

_nomi: Optional[pgeocode.Nominatim] = None


def _get_nomi() -> pgeocode.Nominatim:
    global _nomi
    if _nomi is None:
        _nomi = pgeocode.Nominatim("us")
    return _nomi


def zip_to_centroid(zip_code: str) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) centroid for a US zip code, or None if unrecognized."""
    if not zip_code:
        return None
    try:
        result = _get_nomi().query_postal_code(zip_code)
    except Exception:
        return None
    lat, lon = result.latitude, result.longitude
    if math.isnan(lat) or math.isnan(lon):
        return None
    return (float(lat), float(lon))


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby_store_ids(
    zip_code: str,
    db,
    radius_miles: float = 10.0,
    centroid: Optional[Tuple[float, float]] = None,
) -> List[str]:
    """Return store UUIDs within radius_miles of zip_code. Empty list if zip unknown or no stores nearby."""
    if centroid is None:
        centroid = zip_to_centroid(zip_code)
    if centroid is None:
        return []
    lat, lon = centroid
    stores = db.table("stores").select("id,latitude,longitude").execute()
    result = []
    for s in stores.data:
        slat, slon = s.get("latitude"), s.get("longitude")
        if slat is None or slon is None:
            continue
        if haversine(lat, lon, float(slat), float(slon)) <= radius_miles:
            result.append(s["id"])
    return result
