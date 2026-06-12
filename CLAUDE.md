# Terroir — Wine Recommendation App

## What This Is
Full-stack wine recommendation app. Users enter zip code + budget + style preferences and get Claude-powered sommelier recommendations for wines available at local retailers near them.

## Current Build Status (as of 2026-06-11)

### Done
| Component | Location | Notes |
|---|---|---|
| Supabase schema | `supabase/migrations/` | 7 tables live in cloud DB |
| FastAPI app | `backend/api/` | `/health`, `/api/wines/search`, `/api/wines/:id` |
| Enrichment endpoints | `backend/api/routers/enrichment.py` | `/api/enrich/:id`, `/api/enrich/batch/pending` |
| GrapeMinds client | `backend/enrichment/grapeminds.py` | curl subprocess (Cloudflare bypass) |
| Enrichment pipeline | `backend/enrichment/pipeline.py` | Two-step warm-up, cache check, batch mode |
| Geraldine's scraper | `backend/scrapers/geraldines.py` | Shopify API, ~200 wines, no bot protection |
| HEB scraper | `backend/scrapers/heb.py` | Pure-curl GraphQL, store 567, ~1993 wines, dual (in-store/curbside) pricing |
| Recommend endpoint | `backend/api/routers/recommend.py` | `/api/recommend` — Claude Haiku tool-use, rule-based candidate scoring, session persistence |
| BaseScraper | `backend/scrapers/base.py` | Upsert to Supabase + scraper_runs logging |
| Wine type utils | `backend/utils.py` | `infer_wine_type()` used by all scrapers |
| Test suite | `backend/tests/` | 45 tests passing |

### In Progress / Blocked
| Item | Status |
|---|---|
| Total Wine scraper | Blocked — Imperva Enterprise, 403 on everything |
| Wine-Searcher API | Key requested 2026-06-02, pending approval |

### Not Started
- Frontend (intentionally last)

---

## Tech Stack
- **Database + Auth**: Supabase (cloud project: `knpldhksfsetujbcfrsj`)
- **Backend**: Python 3.9, FastAPI, supabase-py
- **Scraping**: urllib (Geraldine's), curl subprocess (GrapeMinds) — no Playwright needed yet
- **AI**: Anthropic Claude API (Haiku for recommendations) — key set in `.env`

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
- MVP hardcodes store 567 (San Antonio); zip→store lookup is a future enhancement
- `robots.txt` disallows `/graphql` (politeness only — it's open); scrape responsibly with the built-in retry/backoff

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
# Should show 26 tests passing
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
```

---

## Key Files

```
backend/
  api/
    main.py                    — FastAPI app, router registration
    routers/wines.py           — /api/wines/search + /api/wines/:id
    routers/enrichment.py      — /api/enrich/:id + /api/enrich/batch/pending
    routers/recommend.py       — /api/recommend (Claude Haiku tool-use)
    schemas.py                 — Pydantic request/response models
  enrichment/
    grapeminds.py              — GrapeMinds API client (curl subprocess)
    pipeline.py                — Enrichment orchestrator + two-step warm-up
  recommendation/
    scorer.py                  — rule-based candidate scoring
    claude_client.py           — Claude Haiku tool-use call
  scrapers/
    base.py                    — BaseScraper ABC + Supabase upsert logic
    geraldines.py              — Shopify scraper for shopgeraldines.com
    heb.py                     — HEB GraphQL scraper (pure curl, store 567)
  tests/                       — All unit tests (45 passing)
  config.py                    — Pydantic settings (reads from ../.env)
  db.py                        — Supabase anon + service role clients
  utils.py                     — infer_wine_type() shared utility

supabase/
  migrations/
    20260602000001_initial_schema.sql  — 7 tables + RLS + indexes
    20260602000002_grants.sql          — Role grants for service_role/anon
    20260611000001_heb_curbside_price.sql — adds retail_inventory.curbside_price

data/
  exploration/                 — API probe scripts + results (not production code)
    grapeminds_findings.md     — GrapeMinds API findings doc
    heb_probe.py / heb_api_probe.py / heb_graphql_probe.py
    totalwine_probe.py
    geraldines_probe.py

docs/
  superpowers/plans/
    2026-06-02-wine-app-supabase-foundation.md  — ACTIVE implementation plan
    api_info.md                                  — API key status + strategy
    2026-06-01-wine-app-data-foundation.md      — OLD plan (superseded)
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
| `WINE_SEARCHER_API_KEY` | 🕐 Requested, pending |
| `VINERADAR_API_KEY` | ⏳ API unreleased, on waitlist |
| `APIFY_API_TOKEN` | ⬜ Not set up |
| `INSTACART` | ❌ Not accepting new developers |

---

## What's Next (priority order)
1. Apply migration `20260611000001` to cloud DB, then run the HEB scraper to seed ~1993 wines
2. Add HEB zip→store lookup for multi-market coverage (MVP hardcodes store 567)
3. Await Wine-Searcher key → add as second retail data source for major chains
4. Add more Shopify local wine shops (same scraper pattern, zero new code)
5. Frontend (last)
