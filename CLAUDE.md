# Terroir — Wine Recommendation App

## What This Is
Full-stack wine recommendation app. Users enter zip code + budget + style preferences and get Claude-powered sommelier recommendations for wines available at local retailers near them.

## Current Build Status (as of 2026-06-19)

### Done
| Component | Location | Notes |
|---|---|---|
| Supabase schema | `supabase/migrations/` | 9 migrations live in cloud DB |
| FastAPI app | `backend/api/` | `/health`, `/api/wines/search`, `/api/wines/:id` |
| Enrichment endpoints | `backend/api/routers/enrichment.py` | `/api/enrich/:id`, `/api/enrich/batch/pending` |
| GrapeMinds client | `backend/enrichment/grapeminds.py` | curl subprocess (Cloudflare bypass) |
| Enrichment pipeline | `backend/enrichment/pipeline.py` | Two-step warm-up, cache check, batch mode |
| Geraldine's scraper | `backend/scrapers/geraldines.py` | Shopify API, ~200 wines, no bot protection |
| HEB scraper | `backend/scrapers/heb.py` | Pure-curl GraphQL, 6 SA stores, ~5,983 inventory records, dual (in-store/curbside) pricing |
| Recommend endpoint | `backend/api/routers/recommend.py` | `/api/recommend` — Claude Haiku tool-use, radius-based store lookup, session persistence |
| BaseScraper | `backend/scrapers/base.py` | Upsert to Supabase + auto-geocodes stores on seed |
| Wine type utils | `backend/utils/__init__.py` | `infer_wine_type()` — utils.py converted to package |
| Geo utils | `backend/utils/geo.py` | `zip_to_centroid` (pgeocode offline), `haversine`, `find_nearby_store_ids` |
| Haiku fact extractor | `backend/enrichment/extraction/extractor.py` | Extracts region/sub_region/varietal/grapes/abv/body from name+description; 97% varietal coverage, 78% region |
| Extraction reference | `backend/enrichment/extraction/reference.py` | Appellation→region cheat sheet, core grapes, few-shot examples |
| Extraction runner | `backend/enrichment/extraction/run_extraction.py` | One-shot: runs extractor on all wines, writes to DB — already run on all 2213 wines |
| Store coords backfill | `backend/scripts/backfill_store_coords.py` | One-time lat/lon backfill — already run, all stores geocoded |
| Spec's scraper | `backend/scrapers/specs.py` | Pure-curl REST API, 12 SA stores, wine-only filter, ~33k inventory records seeded |
| Test suite | `backend/tests/` | 110 tests passing |

### In Progress / Blocked
| Item | Status |
|---|---|
| Total Wine scraper | Blocked — Imperva Enterprise, 403 on everything |
| Wine-Searcher API | Blocked — denied, use case too similar to their product |

### Not Started
- Frontend (intentionally last)

---

## Tech Stack
- **Database + Auth**: Supabase (cloud project: `knpldhksfsetujbcfrsj`)
- **Backend**: Python 3.9, FastAPI, supabase-py
- **Scraping**: urllib (Geraldine's), curl subprocess (GrapeMinds, Spec's, HEB) — no Playwright needed yet
- **AI**: Anthropic Claude API (Haiku for recommendations + fact extraction) — key set in `.env`
- **Geo**: `pgeocode` (offline US zip centroid dataset, no API key)

## Critical Technical Notes

### Python version
System Python is **3.9.6**. Use `Optional[str]` from `typing`, NOT `str | None` syntax. The `str | None` union shorthand requires Python 3.10+.

### GrapeMinds API
- Auth: `Authorization: Bearer <key>` — `X-API-Key` does NOT work
- Cloudflare blocks Python urllib/requests — must call via `subprocess curl`
- First request for a wine triggers async content generation (returns nulls)
- Re-fetch after ~60s for populated tasting notes, structure profile
- Monthly budget: 250 calls — always check `grapeminds_enriched_at` before calling
- `structure_profile` is 1-10 scale: `sweetness, acidity, tannins, alcohol, body, finish`

### Geraldine's (Shopify)
- Public Shopify API: `GET /products.json?limit=250`
- No auth, no bot protection, full JSON including tasting notes
- Pagination via `since_id`, NOT `page` param (deprecated)
- Filter by `product_type` to exclude events/merchandise
- One physical location: 7700 Broadway St, San Antonio TX 78209

### HEB (GraphQL — pure curl, no browser)
- Endpoint: `POST https://www.heb.com/graphql` — no auth, cookies, or browser needed
- Imperva protects HEB's HTML/REST routes but NOT `/graphql` (WAF is path-based; the `/_next/static/` prefix also bypasses it — that's how we pulled the JS chunks during discovery)
- Introspection AND Apollo "did you mean" suggestions are disabled, but **validation errors leak the schema** (field names, types, required args) — that's how the query was reconstructed
- HEB accepts ad-hoc full queries — no persisted-query hash required
- Required headers: `Apollographql-Client-Name: heb-com`, `Origin: https://www.heb.com`, `Referer: https://www.heb.com/`, any real `User-Agent`
- Query: `productSearch(shoppingContext: CURBSIDE_PICKUP, query: "wine", storeId: N, limit, offset)` → paginate via `offset` (store 567 has ~1993 "wine" results)
- Price lives at `records.SKUs[].contextPrices[]`: **ONLINE = in-store/shelf price (lower, canonical)**, **CURBSIDE = pickup+delivery price (~4% higher)** — stored in `retail_inventory.curbside_price`
- UPC at `SKUs[].twelveDigitUPC`; `productDescription` embeds Type/Blend/Tasting Notes/ABV as light HTML
- 6 SA stores hardcoded in `SA_STORES` dict: 567, 372, 585, 385, 568, 556 (all verified to carry wine)
- Store list source: `data/heb-store-list.csv`
- `robots.txt` disallows `/graphql` (politeness only — it's open); scrape responsibly with the built-in retry/backoff

### Spec's (REST API — pure curl, no browser)
- **Domain**: `specsonline.com` (NOT `specs.com` — that's a glasses company)
- **Endpoint**: `POST https://specsonline.com/api/search/` — trailing slash required (without → 308)
- No auth, no cookies, no session needed — just `Content-Type: application/json` + `Referer`
- Wine filter: `facets.category.keyword = "[\"Wine\"]"` — excludes beer/spirits/sake at API level
- Pricing in **cents**: `unitPrice / 100` = shelf price; `unitPricePromoDiscount / 100` = sale price (use if non-null)
- `stock.inStock` boolean per store — must query each store separately
- UPCs are real barcodes → cross-retailer deduplication with HEB works automatically
- SA stores hardcoded: `SA_STORE_NUMBERS = [69, 72, 98, 100, 110, 113, 114, 117, 169, 171, 194, 197]`
- ~77% of wines have descriptions; 23% fall back to Haiku extraction from name + categoryGroup
- See `data/exploration/specs_findings.md` for full API reference

### Zip→Store Radius Lookup
- `/api/recommend` uses `find_nearby_store_ids(zip_code, db, radius_miles=10.0)` — not a hardcoded zip filter
- `backend/utils/geo.py`: `zip_to_centroid` (pgeocode offline dataset) + `haversine` + `find_nearby_store_ids`
- `BaseScraper._upsert_stores` auto-geocodes stores on seed — any new scraper gets it for free
- `retail_inventory` FK to `stores` is **`store_ref`** (UUID), NOT `store_id`
- Two distinct 400s: "don't recognize zip" vs "no stores near you (SA only)"
- Radius is a parameter — exposing it as a user setting is a future enhancement

### Supabase
- Anon key for public reads; service_role key bypasses RLS (backend only)
- Run from `backend/` directory so `.env` path resolves correctly
- Tables need explicit GRANTs — see migration `20260602000002_grants.sql`

---

## Running the Backend

```bash
# From project root
cd backend
python3 -m uvicorn api.main:app --reload
# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## Running Tests

```bash
cd backend
python3 -m pytest tests/ -v
# Should show 98 tests passing
```

## Seeding Data

```bash
# Run Geraldine's scraper (live Shopify API, seeds wines + inventory + wine_details)
cd backend
python3 -c "
import asyncio
from scrapers.geraldines import GeraldinesScraper
asyncio.run(GeraldinesScraper().run_full())
"

# Run HEB scraper (live GraphQL, store 567, ~1993 wines, dual pricing)
# NOTE: apply migration 20260611000001 first (adds retail_inventory.curbside_price)
cd backend
python3 -c "
import asyncio
from scrapers.heb import HebScraper
asyncio.run(HebScraper().run_full())
"

# Run Spec's scraper (REST API, 12 SA stores, wine-only, ~4,983 wines per store)
# Takes ~25-30 min for all 12 stores. Safe to re-run (idempotent upserts).
cd backend
python3 -c "
import asyncio
from scrapers.specs import SpecsScraper
asyncio.run(SpecsScraper().run_full())
"
```

---

## Key Files

```
backend/
  api/
    main.py                    — FastAPI app, router registration
    routers/wines.py           — /api/wines/search + /api/wines/:id
    routers/enrichment.py      — /api/enrich/:id + /api/enrich/batch/pending
    routers/recommend.py       — /api/recommend (Claude Haiku tool-use, radius store lookup)
    schemas.py                 — Pydantic request/response models
  enrichment/
    grapeminds.py              — GrapeMinds API client (curl subprocess)
    pipeline.py                — Enrichment orchestrator + two-step warm-up
    extraction/
      extractor.py             — Haiku fact extractor (region/varietal/grapes/abv/body)
      reference.py             — Appellation→region cheat sheet + core grapes + few-shot
      run_extraction.py        — One-shot script: extract all wines + write to DB
  matching/
    eval/                      — GrapeMinds matching eval scripts + results
  recommendation/
    scorer.py                  — rule-based candidate scoring
    claude_client.py           — Claude Haiku tool-use call
  scrapers/
    base.py                    — BaseScraper ABC + Supabase upsert + auto-geocode stores
    geraldines.py              — Shopify scraper for shopgeraldines.com
    heb.py                     — HEB GraphQL scraper (pure curl, store 567)
    specs.py                   — Spec's REST scraper (pure curl, 12 SA stores, wine-only)
  scripts/
    backfill_store_coords.py   — One-time lat/lon backfill for existing stores
  tests/                       — All unit tests (110 passing)
  config.py                    — Pydantic settings (reads from ../.env)
  db.py                        — Supabase anon + service role clients
  utils/
    __init__.py                — infer_wine_type() shared utility
    geo.py                     — zip_to_centroid, haversine, find_nearby_store_ids

supabase/
  migrations/
    20260602000001_initial_schema.sql       — 7 tables + RLS + indexes
    20260602000002_grants.sql               — Role grants for service_role/anon
    20260603000001_add_orange_wine_type.sql — orange wine type
    20260611000001_heb_curbside_price.sql   — adds retail_inventory.curbside_price
    20260614000001_grapeminds_matches.sql   — wine_grapeminds_matches table
    20260614000002_stores_table.sql         — stores registry + store_ref FK on retail_inventory
    20260615000001_wine_extracted_fields.sql — wines.grapes/abv/body columns

data/
  exploration/                 — API probe scripts + results (not production code)
    grapeminds_findings.md     — GrapeMinds API findings doc
    heb_probe.py / heb_api_probe.py / heb_graphql_probe.py
    totalwine_probe.py
    geraldines_probe.py
    specs_probe.py             — Spec's API discovery (specsonline.com)
    specs_findings.md          — Spec's API reference (search endpoint, store numbers, field shapes)

docs/
  superpowers/
    specs/
      2026-06-16-zip-store-mapping-design.md  — zip→store radius mapping design
      2026-06-18-specs-scraper-design.md     — Spec's scraper design
    plans/
      2026-06-16-zip-store-mapping.md         — zip→store implementation plan
      2026-06-18-specs-scraper.md            — Spec's scraper implementation plan
      api_info.md                             — API key status + strategy
```

---

## API Keys (.env)

| Key | Status |
|---|---|
| `SUPABASE_URL` | ✅ Set |
| `SUPABASE_ANON_KEY` | ✅ Set |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ Set |
| `GRAPEMINDS_API_KEY` | ✅ Set (~17/250 calls used) |
| `ANTHROPIC_API_KEY` | ✅ Set |
| `WINE_SEARCHER_API_KEY` | ❌ Denied — use case too similar to their offering |
| `VINERADAR_API_KEY` | ⏳ API unreleased, on waitlist |
| `APIFY_API_TOKEN` | ⬜ Not set up |
| `INSTACART` | ❌ Not accepting new developers |

---

## What's Next (priority order)
1. Add more Shopify local wine shops (same scraper pattern as Geraldine's, zero new code)
2. Add more HEB stores across San Antonio (6 live, `data/heb-store-list.csv` has full list)
3. Target scraper — Playwright probe needed first
4. Frontend (last)
