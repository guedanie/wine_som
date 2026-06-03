# Terroir — Wine Recommendation App

## What This Is
Full-stack wine recommendation app. Users enter zip code + budget + style preferences and get Claude-powered sommelier recommendations for wines available at local retailers near them.

## Current Build Status (as of 2026-06-03)

### Done
| Component | Location | Notes |
|---|---|---|
| Supabase schema | `supabase/migrations/` | 7 tables live in cloud DB |
| FastAPI app | `backend/api/` | `/health`, `/api/wines/search`, `/api/wines/:id` |
| Enrichment endpoints | `backend/api/routers/enrichment.py` | `/api/enrich/:id`, `/api/enrich/batch/pending` |
| GrapeMinds client | `backend/enrichment/grapeminds.py` | curl subprocess (Cloudflare bypass) |
| Enrichment pipeline | `backend/enrichment/pipeline.py` | Two-step warm-up, cache check, batch mode |
| Geraldine's scraper | `backend/scrapers/geraldines.py` | Shopify API, ~200 wines, no bot protection |
| BaseScraper | `backend/scrapers/base.py` | Upsert to Supabase + scraper_runs logging |
| Wine type utils | `backend/utils.py` | `infer_wine_type()` used by all scrapers |
| Test suite | `backend/tests/` | 26 tests, all passing |

### In Progress / Blocked
| Item | Status |
|---|---|
| HEB scraper | Blocked — Cloudflare bot protection. HEB has GraphQL API (`POST /graphql`), `productSearch(shoppingContext: CURBSIDE_PICKUP)` confirmed working but needs phone proxy capture (Proxyman) to get full working query |
| Total Wine scraper | Blocked — Imperva Enterprise, 403 on everything |
| Wine-Searcher API | Key requested 2026-06-02, pending approval |

### Not Started
- Recommendation engine (Claude API integration)
- Frontend (intentionally last)

---

## Tech Stack
- **Database + Auth**: Supabase (cloud project: `knpldhksfsetujbcfrsj`)
- **Backend**: Python 3.9, FastAPI, supabase-py
- **Scraping**: urllib (Geraldine's), curl subprocess (GrapeMinds) — no Playwright needed yet
- **AI**: Anthropic Claude API (key not yet added to .env)

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
```

---

## Key Files

```
backend/
  api/
    main.py                    — FastAPI app, router registration
    routers/wines.py           — /api/wines/search + /api/wines/:id
    routers/enrichment.py      — /api/enrich/:id + /api/enrich/batch/pending
    schemas.py                 — Pydantic request/response models
  enrichment/
    grapeminds.py              — GrapeMinds API client (curl subprocess)
    pipeline.py                — Enrichment orchestrator + two-step warm-up
  scrapers/
    base.py                    — BaseScraper ABC + Supabase upsert logic
    geraldines.py              — Shopify scraper for shopgeraldines.com
  tests/                       — All unit tests (26 passing)
  config.py                    — Pydantic settings (reads from ../.env)
  db.py                        — Supabase anon + service role clients
  utils.py                     — infer_wine_type() shared utility

supabase/
  migrations/
    20260602000001_initial_schema.sql  — 7 tables + RLS + indexes
    20260602000002_grants.sql          — Role grants for service_role/anon

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
| `ANTHROPIC_API_KEY` | ⬜ Not yet added |
| `WINE_SEARCHER_API_KEY` | 🕐 Requested, pending |
| `VINERADAR_API_KEY` | ⏳ API unreleased, on waitlist |
| `APIFY_API_TOKEN` | ⬜ Not set up |
| `INSTACART` | ❌ Not accepting new developers |

---

## What's Next (priority order)
1. Add Anthropic API key to `.env` and build the recommendation engine
2. Wire up `/api/recommend` endpoint (candidate retrieval → Claude)
3. Await Wine-Searcher key → add as second retail data source
4. HEB GraphQL — capture live query via Proxyman phone proxy to crack the schema
5. Add more Shopify local wine shops (same scraper pattern, zero new code)
6. Frontend (last)
