# Reference — Scrapers

Per-retailer API notes for the 11 scrapers. See also `data/exploration/*_findings.md` for the raw reverse-engineering, and `backend/scrapers/` for the code. Twin Liquors + Pogo's have dedicated findings docs (`data/exploration/twinliquors_findings.md`; Pogo's mirrors Harvest).

## Critical Technical Notes — scrapers
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
- 18 stores active in `STORE_REGISTRY`: 6 SA (567, 372, 585, 385, 568, 556) + 12 Austin within 10mi of 78749
- **Store registry is CSV-driven** — `data/heb-stores.csv` has `active` flag; flip `false→true` to add a store, no code change; 37 additional SA/suburb stores already staged
- `SA_STORES` dict kept for backward compat; `run_full(city='Austin')` or `run_full(store_ids=[...])` to filter
- Store list source: `data/heb-store-list.csv` (full HEB TX list); active stores managed in `data/heb-stores.csv`
- `robots.txt` disallows `/graphql` (politeness only — it's open); scrape responsibly with the built-in retry/backoff

### Central Market (GraphQL — same as HEB)
- Same endpoint as HEB (`heb.com/graphql`) with `Apollographql-Client-Name: central-market`
- 10 CM store IDs total: 55 (Southlake), 61 (Austin NL), 191 (SA Broadway), 420 (Austin Westgate), 491, 545, 546, 552, 653, 747
- **SA Broadway (store 191) is in centralmarket.com's store list but returns 0 from GraphQL** — not e-commerce-enabled for online ordering; confirmed via RSC product page showing store_id arrays
- Austin stores 61 and 420 are fully e-commerce-enabled; all others untested
- `CentralMarketScraper` inherits `HebScraper`, uses `CM_STORES` dict with stores 61+420

### AOC Selections / US Natural Wine / Antonelli's (Shopify)
- All three use same pattern as Geraldine's: `GET /products.json?limit=250&page=N`
- **AOC** (`aocselections.com`): wine-only store, NO product_type filter; use `Location_SanAntonio` tag to filter SA inventory (store also has Houston location); wine type inferred from colour tags (`White`, `Red`, `Sparkling`, etc.)
- **US Natural Wine** (`usnaturalwine.com`): scrape all (wine-only); normalize inconsistent `product_type` values (`Red` → `Red Wine`, etc.); `_SKIP_TYPES` excludes Non-Alcoholic and Cider
- **Antonelli's** (`antonellischeese.com`): the `?product_type=Wine` URL param is IGNORED by Shopify (returns all 391 products), so wine is filtered client-side (`product_type=="wine"` → 65 wines); title format `WINE NAME / Producer / Region / Wine` (slash-separated)
- Synthetic UPCs (`shopify-aoc-{handle}`, `shopify-usnw-{handle}`, `shopify-antonellis-{handle}`) — no cross-retailer dedup possible (natural wines have no barcodes)

### Spec's (REST API — pure curl, no browser; runs on the mini)
> ⚠️ **Datacenter-IP blocked.** GitHub-cron runs 2026-07-01→07-13 all returned
> success/0 records (silent). Moved to the mini's `com.somm.specs` LaunchAgent
> (Sun 05:00 CT) on 2026-07-13. Do NOT re-add the step to `.github/workflows/weekly-scrape.yml`.

- **Domain**: `specsonline.com` (NOT `specs.com` — that's a glasses company)
- **Endpoint**: `POST https://specsonline.com/api/search/` — trailing slash required (without → 308)
- No auth, no cookies, no session needed — just `Content-Type: application/json` + `Referer`
- Wine filter: `facets.category.keyword = "[\"Wine\"]"` — excludes beer/spirits/sake at API level
- Pricing in **cents**: `unitPrice / 100` = shelf price; `unitPricePromoDiscount / 100` = sale price (use if non-null)
- `stock.inStock` boolean per store — must query each store separately
- UPCs are real barcodes → cross-retailer dedup with HEB works via `upc_canonical` (see below)
- SA stores hardcoded: `SA_STORE_NUMBERS = [69, 72, 98, 100, 110, 113, 114, 117, 169, 171, 194, 197]`
- ~77% of wines have descriptions; 23% fall back to Haiku extraction from name + categoryGroup
- See `data/exploration/specs_findings.md` for full API reference

### Kroger (official Developer API — NOT a scrape)
- **Sanctioned free API** with per-location pricing + real UPCs — the pricing Wine-Searcher/WFM denied us. Register a free app at developer.kroger.com → `KROGER_CLIENT_ID` / `KROGER_CLIENT_SECRET`
- **Auth**: OAuth2 client_credentials, **`scope=product.compact` is REQUIRED** for the products endpoint (scopeless token → 403). Token TTL 30 min, cached + lazy-refreshed on 401
- **Endpoints**: `POST /v1/connect/oauth2/token`; `GET /v1/locations?filter.zipCode.near={zip}&filter.chain={code}`; `GET /v1/products?filter.term={t}&filter.locationId={id}&filter.limit=50&filter.start={n}`
- **Covers ALL Kroger banners** (one API): Kroger, **Harris Teeter=`HART`**, Ralphs, Fred Meyer=`FRED`, King Soopers=`KINGSOOPERS`, Fry's, Smith's, QFC, Mariano's, Dillons, Food4Less, City Market, Pick n Save, Baker's. `filter.chain` codes differ from display names — query without the filter to read the real `chain` value
- **Config-driven `MARKETS` registry** in `kroger.py` (city → {city, state, retailer, stores}). `retailer` is the display banner (so NC shows "Harris Teeter"). Expansion is config-only: add store IDs from the Locations API. `run_full(markets=[...])` scopes to cities
- **Pagination caps ~250 offset** — one "wine" term can't cover a store, so search 17 wine terms + varietals and **dedup by CANONICAL upc** (two raw UPCs can normalize to one core → upsert constraint violation if deduped by raw UPC only)
- **Resilience**: retries 429 + 5xx + `socket.timeout`/URLError with backoff; per-store failure isolation (one store's blip → run status "partial", others still commit)
- **Kroger geography**: NOT in San Antonio/Austin (HEB territory). Present: Nashville, Memphis, Dallas, Houston. Harris Teeter: NC/VA/DC/SE. Rate limit 10k calls/day (public tier)

### Harvest Wine Market (Nashville — Shopify)
- Same public `/products.json` pattern as Geraldine's/AOC/USNW; 6043 TN-100 Belle Meade (37205); ~1,032 wines
- Inconsistent product_type casing (`Rosé`/`Rose wine`/`rose`) normalized via `_normalize_type()`; non-wine types (Bourbon/Gin/Event) dropped; synthetic UPCs (`shopify-harvest-{handle}`)

### Cross-Retailer UPC Dedup (canonical UPC)
- The same wine is encoded differently per retailer: **HEB** stores full 12-digit UPC-A (11-digit core + check digit); **Spec's** stores the 11-digit core with a leading zero. Both normalize to the same 11-digit core.
- `backend/utils/upc.py` `canonical_upc(raw)` does the normalization (UPC-A check-digit validation decides HEB-style `[:11]` vs Spec's-style `[1:]`). Synthetic `shopify-…` IDs pass through unchanged (Geraldine's natural wines have no barcode — never dedup).
- `wines.upc_canonical` column + **full UNIQUE CONSTRAINT** (`wines_upc_canonical_unique`) is the dedup identity (migration 11 replaced the partial index — PostgREST ON CONFLICT requires a full constraint). `BaseScraper._upsert_wines` upserts `on_conflict="upc_canonical"`; it still returns a `{raw_upc → wine_id}` map because `retail_inventory.upc` stores the **raw** barcode.
- Prices are NOT deduplicated — they live in `retail_inventory` per (wine × store). Merging wines re-points all inventory rows, preserving every retailer's price.
- One-time merge already run (2026-06-21): `backend/scripts/merge_duplicate_wines.py` collapsed 910 duplicate wine rows (9321 → 8411), 0 inventory loss. Script is idempotent + has `--dry-run`. Re-run it after adding a new barcode retailer if needed.
- Geraldine's (and other natural-wine shops) can't UPC-dedup — that's a future fuzzy name/producer/vintage matching problem (GrapeMinds matching subsystem).

## Seeding commands
## Seeding Data

```bash
# Run Geraldine's scraper (live Shopify API, seeds wines + inventory + wine_details)
cd backend
python3 -c "
import asyncio
from scrapers.geraldines import GeraldinesScraper
asyncio.run(GeraldinesScraper().run_full())
"

# Run HEB scraper (live GraphQL, STORE_REGISTRY — all 18 stores SA+Austin, or filter by city)
cd backend
python3 -c "
import asyncio
from scrapers.heb import HebScraper
asyncio.run(HebScraper().run_full())                   # all 18 stores
# asyncio.run(HebScraper().run_full(city='Austin'))    # Austin only
"

# Run Central Market scraper (2 Austin stores: 61 + 420; SA store 191 not e-commerce-enabled)
cd backend
python3 -c "
import asyncio
from scrapers.central_market import CentralMarketScraper
asyncio.run(CentralMarketScraper().run_full())
"

# Run AOC Selections scraper (Shopify, SA only — Location_SanAntonio tag filter, ~fine wine catalog)
cd backend
python3 -c "
import asyncio
from scrapers.aoc_selections import AOCSelectionsScraper
asyncio.run(AOCSelectionsScraper().run_full())
"

# Run US Natural Wine scraper (Shopify, Austin, ~560 natural wines)
cd backend
python3 -c "
import asyncio
from scrapers.us_natural_wine import USNaturalWineScraper
asyncio.run(USNaturalWineScraper().run_full())
"

# Run Antonelli's scraper (Shopify, Austin, 65 wines)
cd backend
python3 -c "
import asyncio
from scrapers.antonellis import AntonellisScraper
asyncio.run(AntonellisScraper().run_full())
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
