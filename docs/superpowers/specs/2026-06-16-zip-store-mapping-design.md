# Zip→Store Mapping Design

**Date:** 2026-06-16
**Status:** Approved

## Goal

Replace the hardcoded single-store filter in `/api/recommend` with a retailer-agnostic radius-based store lookup. Any scraper that seeds the `stores` table gets geographic search for free. MVP targets San Antonio, TX.

## Approach

Offline zip centroid lookup (`pgeocode`) + Python haversine distance filter. No external API, no PostGIS. Swappable to PostGIS later via a single function rewrite if store count exceeds ~10k.

## Components

### `backend/utils/geo.py` (new)

Three pure functions:

- `zip_to_centroid(zip_code: str) -> Optional[Tuple[float, float]]` — uses `pgeocode` offline US zip dataset to return `(lat, lon)`. Returns `None` for unrecognized zips.
- `haversine(lat1, lon1, lat2, lon2) -> float` — distance in miles between two lat/lon points.
- `find_nearby_store_ids(zip_code: str, db, radius_miles: float = 10.0) -> List[str]` — fetches all stores from DB, computes haversine to each, returns UUIDs of stores within `radius_miles`. Returns empty list if zip is unrecognized or no stores are nearby.

### `/api/recommend` endpoint

Replace:
```python
.eq("stores.zip_code", req.zip_code)
```
With:
```python
nearby_ids = find_nearby_store_ids(req.zip_code, db)
# early-exit checks, then:
.in_("store_id", nearby_ids)
```

Two distinct early-exit 400s:
- Zip not in pgeocode dataset → `"We don't recognize that zip code"`
- Zip valid but no stores within radius → `"No stores found near your zip code. We currently serve San Antonio, TX."`

### `BaseScraper._upsert_stores()` (update)

When writing a store row, call `zip_to_centroid(store_zip)` and populate `latitude` / `longitude`. All future scrapers get geocoding automatically.

### Backfill script (one-time)

Populate `latitude`/`longitude` for the 2 existing stores (HEB 567, Geraldine's) using `zip_to_centroid`. No migration needed — columns already exist.

## Data Flow

```
POST /api/recommend {zip_code, budget, style...}
  → find_nearby_store_ids(zip_code)
      → zip_to_centroid(zip_code)          # pgeocode offline lookup
      → fetch all stores from DB
      → haversine(store, centroid) for each
      → return store UUIDs within radius
  → if empty: 400
  → query retail_inventory WHERE store_id IN (nearby_ids)
  → score → Claude → session persist → response
```

## Testing

| Test | Assertion |
|---|---|
| `test_zip_to_centroid_known` | SA zip returns valid (lat, lon) |
| `test_zip_to_centroid_unknown` | garbage zip returns None |
| `test_haversine_known_distance` | two SA coords return expected mileage |
| `test_find_nearby_store_ids_sa` | SA zip + mocked DB returns both stores |
| `test_find_nearby_store_ids_distant` | Austin zip + mocked DB returns empty |
| `test_recommend_unknown_zip` | 400 with "don't recognize" message |
| `test_recommend_no_stores_nearby` | 400 with "no stores found" message |

## Future Expansion

- **More retailers:** each new scraper just seeds `stores` with address/zip — geocoding is automatic.
- **User-configurable radius:** `radius_miles` is already a parameter on `find_nearby_store_ids`; expose it in `RecommendRequest` when needed.
- **Beyond Texas:** `pgeocode` covers all US zips; no changes needed to expand markets.
- **PostGIS migration path:** swap `find_nearby_store_ids` internals only; all callers unchanged.

## Dependencies

- `pgeocode` (pip install) — offline zip centroid dataset, no API key
