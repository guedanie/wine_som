# Terroir — Wine Recommendation App

## What This Is
Full-stack wine recommendation app. Users enter zip code + budget + style preferences and get Claude-powered sommelier recommendations for wines available at local retailers near them.

**LIVE (private beta since 2026-07-05):** frontend `wine-som-pkwz-chi.vercel.app` (Vercel) + backend `winesom-production.up.railway.app` (Railway) + Supabase. Installable as a PWA. Testers in San Antonio, Nashville; second wave in Charlotte + Winston-Salem NC; Dallas focus coming.

## Current Build Status (as of 2026-07-05)

### Done
| Component | Location | Notes |
|---|---|---|
| Supabase schema | `supabase/migrations/` | 13 migrations live in cloud DB |
| Vivino enrichment | `backend/enrichment/vivino.py`, `backend/scripts/run_vivino_sample.py` | Async httpx; ratings + bottle image + canonical facts (grapes/region/abv/structure/pairing) from 2 HTML requests/wine; 429-safe (VivinoFetchError, no false stamps, pause-and-resume); `--missing-images` + `--backfill-facts` modes; ~1,027 matched |
| Daily Vivino workflow | `.github/workflows/daily-vivino.yml` | **PAUSED 2026-07-05** — GitHub runner datacenter IPs are IP-blocklisted by Vivino (~23 wines/day even on crawl profile). `workflow_dispatch` only |
| Local Vivino launchd job | `backend/scripts/run_vivino_launchd.sh` + `com.somm.vivino-enrich.plist` | Enricher for a **residential IP** (not blocklisted; verified 3/3 matched). Twice daily, `--limit 300`/run, logs to `~/Library/Logs/somm-vivino.log`; idempotent + abort-breaker safe. **BLOCKED on the laptop** by macOS TCC — `launchd` can't read the repo under `~/Documents` (`Operation not permitted`). Deferred to the Mac mini enhancement (repo at `~/dev/wine_app`, no TCC); manual runs still work. See `docs/mac-mini-enrichment-server.md` |
| Deployment | Vercel + Railway | Frontend Vercel (root `vercel.json` pins Vite build), backend Railway (`Procfile`, $PORT bind); env-driven CORS (`ALLOWED_ORIGINS`), per-IP rate limits, ADMIN_TOKEN gate on `/api/enrich/*` |
| Mobile / PWA | `frontend/src/components/MobileChrome.jsx`, `lib/useIsMobile.js` | Responsive ≤640px branch on every screen (shared logic, conditional layout); TopBar + BottomTabs chrome; chat cards in a bottom sheet; filter drawer; `manifest.json` + vine-mark icons; 16px inputs (no iOS zoom); session-restore on dossier back |
| FastAPI app | `backend/api/` | `/health`, `/api/wines/search`, `/api/wines/:id` |
| Enrichment endpoints | `backend/api/routers/enrichment.py` | `/api/enrich/:id`, `/api/enrich/batch/pending` |
| GrapeMinds client | `backend/enrichment/grapeminds.py` | curl subprocess (Cloudflare bypass) |
| Enrichment pipeline | `backend/enrichment/pipeline.py` | Two-step warm-up, cache check, batch mode |
| Geraldine's scraper | `backend/scrapers/geraldines.py` | Shopify API, ~200 wines, no bot protection |
| HEB scraper | `backend/scrapers/heb.py` | Pure-curl GraphQL, 25 active stores (6 SA + 12 Austin + 7 DFW: Frisco/Plano/McKinney/Allen/Melissa/Prosper — all ~2,200-2,300 wines), dual (in-store/curbside) pricing |
| Kroger scraper | `backend/scrapers/kroger.py` | **Official Developer API** (OAuth2, not a scrape) — per-location pricing + real UPCs. `MARKETS` registry covers all Kroger banners: Nashville (Kroger, 3,645 wines), Charlotte + Winston-Salem (Harris Teeter, 10,433 rows), Dallas (Kroger). 17-term search deduped by canonical UPC |
| Harvest Wine Market scraper | `backend/scrapers/harvest_wine.py` | Shopify API, Nashville TN (1,032 wines), first TN retailer; inconsistent product_type casing normalized |
| Central Market scraper | `backend/scrapers/central_market.py` | Same HEB GraphQL, `central-market` client header, 2 Austin stores (61, 420); SA store 191 not e-commerce-enabled |
| AOC Selections scraper | `backend/scrapers/aoc_selections.py` | Shopify API, SA-only (Location_SanAntonio tag filter), ~fine wine catalog, page-param pagination |
| US Natural Wine scraper | `backend/scrapers/us_natural_wine.py` | Shopify API, Austin (~560 natural wines), normalizes inconsistent product_types |
| Antonelli's scraper | `backend/scrapers/antonellis.py` | Shopify API, Austin (391 wines), product_type=Wine filter, slash-separated title format |
| Recommend endpoint v2 | `backend/api/routers/recommend.py` | `/api/recommend` — tiered candidate pool, knowledge-based scorer, optional NL intent parse, Claude Haiku pick+narrative, radius store lookup, session persistence |
| BaseScraper | `backend/scrapers/base.py` | Upsert to Supabase + auto-geocodes stores on seed |
| Wine type utils | `backend/utils/__init__.py` | `infer_wine_type()` — utils.py converted to package |
| Geo utils | `backend/utils/geo.py` | `zip_to_centroid` (pgeocode offline), `haversine`, `find_nearby_store_ids` |
| Haiku fact extractor | `backend/enrichment/extraction/extractor.py` | Extracts region/sub_region/varietal/grapes/abv/body from name+description; 97% varietal coverage, 78% region |
| Extraction reference | `backend/enrichment/extraction/reference.py` | Appellation→region cheat sheet, core grapes, few-shot examples |
| Extraction runner | `backend/enrichment/extraction/run_extraction.py` | `--null-only` flag for incremental runs; run on all 11,513 wines — 8,069 have region (70%) |
| Store coords backfill | `backend/scripts/backfill_store_coords.py` | One-time lat/lon backfill — already run, all stores geocoded |
| Spec's scraper | `backend/scrapers/specs.py` | Pure-curl REST API, 12 SA stores, wine-only filter, ~33k inventory records seeded |
| Wine images | `wines.image_url` (scrapers + Vivino) | All 5 Shopify/Spec's scrapers capture CDN URLs; HEB/CM gap filled by Vivino `bottle_medium` (`https:` + protocol-relative URL) on any match ≥0.6 |
| Cross-retailer dedup | `backend/utils/upc.py`, `scripts/merge_duplicate_wines.py` | canonical-UPC normalization; 910 dup wine rows merged (9321→8411), 0 inventory loss; full UNIQUE CONSTRAINT (migration 11) |
| Recommendation engine v2.1 | `backend/recommendation/` | Tiered pool (GrapeMinds + extractor), knowledge-based scorer (`flavor_profiles.py`), optional NL intent (`intent.py`); Vivino rating boost (max +1.5, ≥25 ratings), structure-profile body matching, ratings shown to Claude, full-pool scoring with seeded ±0.4 jitter (no pre-score truncation) |
| HEB store registry | `data/heb-stores.csv` | CSV-driven active flag; 25 active (SA + Austin + DFW); flip flag to add a store, no code change |
| Weekly scrape workflow | `.github/workflows/weekly-scrape.yml` | GitHub Actions cron Sunday 02:00 CT — all 9 scrapers (7 SA/Austin + Harvest + Kroger) + `--null-only` extraction; Slack notify per-scraper; each step `continue-on-error` |
| requirements.txt | `backend/requirements.txt` | 17 pinned deps for reproducible CI installs |
| Optional user accounts + favorites | `frontend/src/lib/{supabase,auth,favorites,pendingSave}.js(x)`, `components/{SignInModal,AuthNav,SaveBookmark,DossierSaveButton}.jsx`, `screens/Saved.jsx`, `supabase/migrations/20260707000002_user_accounts.sql` | **Anonymous-first, optional.** Supabase Auth email **magic link** (verified working; implicit flow). `AuthProvider`/`useAuth` centralizes session + saved bottles + a contextual sign-in prompt. Save bookmark on every WineCard + dossier Save button; anon tap → sign-in prompt → auto-saves via pending-save round-trip. `/saved` view (desktop avatar menu + mobile Saved tab). `profiles` + `favorites` tables, RLS-scoped `user_id=auth.uid()` (read/write direct via supabase-js, no backend). **Prod needs `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` in Vercel (set 2026-07-09) — sign-in UI hides entirely without them (build-time bake)** |
| Cellar (Phase 2) | `frontend/src/screens/Cellar.jsx`, `lib/{cellar,drinkingWindow}.js`, `components/AddBottleModal.jsx`, `supabase/migrations/20260708000001_cellar.sql` | Bottle tracking with computed drinking window (varietal+vintage heuristic, brass progress bar); catalog + off-catalog add paths; sort picker (**drink-soonest default** / added / vintage); "Drank it" → consumed + **quick 👍/👎 rating toast** (catalog bottles post feedback → personalization); mobile-scrollable |
| Personalization (behavioral) | `backend/recommendation/scorer.py`, `frontend/src/lib/taste.js`, `components/DossierRateButton.jsx`, `supabase/migrations/20260708000002_feedback_user_rls.sql` | **Saved + cellar + 👍/👎 → re-rank + cite.** `buildTasteContext` gathers liked (upvoted/saved/owned-cellar) + disliked (downvoted) via RLS → `RecommendRequest.taste` on every rec + follow-up. Scorer: similarity boost (`_W_SIMILAR` 2.5; shared grape > region > flavor) tags `_similar_to`/`_similar_source` → Claude cites accurately ("close to the X you saved"); dislike penalty (`_W_DISLIKE` 2.0). Votes carry `user_id`; RLS lets users read own feedback. Dossier thumbs. First rec gated on auth `ready` (race fix). Consumed cellar bottles drop out of taste |
| Taste profile interview (Phase 3) | `frontend/src/screens/TasteProfile.jsx`, `lib/{tasteInterview,profile}.js`, `/taste` route | Conversational Somm Q&A (6 scripted questions, chips + free text, chat-styled) → structured `profiles.taste_profile`. Entry: account-page row + desktop avatar menu. Feeds BOTH: scorer soft axes (loved-region +1.0 / body +1.0 / lean +0.75 — **only when the request doesn't specify that dimension; explicit request always wins**) AND Claude prompt (`_taste_profile_block` + "[Your wines]" list so the Somm can reference cellar/saved directly). `/api/somm` also accepts `taste` — the dossier overlay is personalized too |
| Phantom-card reconciler | `backend/api/routers/recommend.py` `_reconcile_picks_to_narrative` | Claude sometimes returns more picks than it narrates ("2 described, 3 cards" — prompt 1:1 rule alone insufficient). Deterministic backstop: narrative streams before picks, so drop any pick it never names (distinctive-token match: producer/vineyard, not grape/region; never to empty); logs `PICKS RECONCILED` |
| Search vintage grouping | `backend/api/routers/search.py` `_group_key` | Same wine, new UPC per vintage = separate rows → availability fragments (The Prisoner: Spec's-only row hid 16 HEB stores incl. Lincoln Heights). Search groups by vintage-stripped name, aggregates `retailers[]`, represents each group by its best-stocked row. Full fix (dossier/recs/counts too) = product-family key: `docs/product-family-key.md` |
| Zip-aware sub-region counts | `backend/api/routers/region.py` | `/region/{name}/subregions?zip=` counts only wines in stock near the zip — the "N nearby" badge now matches what the sub-region click (zip-scoped search) returns; no zip = catalog-wide |
| Twin Liquors scraper | `backend/scrapers/twin_liquors.py` | TX chain (Austin/SA), City Hive. Anonymous bypass = api_key + `client_origin` from storefront HTML → `products/search.json`. **Wine-only** via `additional_properties.type=="wine"` (spirits/beer/RTD/merch never enter; verified 0 leakage) — same block gives pre-enriched varietal/region/country/ABV persisted directly. Per-store = merchant_id (12 seeded of ~90); 30/term cap → 42-term sweep deduped by product id (~246 wines/store); synthetic `twinliquors-{id}` UPC. Cloudflare 1015 backoff (residential IP). Ref: `data/exploration/twinliquors_findings.md` |
| Analytics (PostHog) | `frontend/src/lib/analytics.js` | No-op-safe wrapper (silent without `VITE_POSTHOG_KEY`); SPA pageviews + funnel events (preferences_submitted, recommendation_shown, pick_opened, feedback_voted, region_opened, search_performed, subregion_deeplinked). LIVE — key set in Vercel + local. |
| Price history | `supabase/migrations/20260707000001_price_history.sql` | Append-only `price_history` table fed by a delta-only trigger on `retail_inventory` (`log_price_change`, SECURITY DEFINER) — logs initial price on insert + any price/curbside change. Scrapers untouched (full-refresh upsert). Baseline snapshot of 87,347 current prices captured. Phase 1 of price alerts (capture; alert UX awaits user accounts) |
| Feedback loop | `backend/api/routers/feedback.py`, `supabase/migrations/20260630000001_feedback_table.sql` | `POST /api/feedback` + `feedback` Supabase table; Pattern A (wine card thumbs) + Pattern B (sommelier message thumbs + follow-up bubble); session-scoped votes with toggle support |
| Somm overlay | `frontend/src/components/SommOverlay.jsx`, `backend/api/routers/somm.py` | FAB + 400px slide-in chat panel; wine-context Claude Haiku system prompt; suggestion chips (red vs white set); Pattern B feedback; chat history persists across close/reopen |
| StructureBars v2 | `frontend/src/components/StructureBars.jsx` | `variant="ruler"` (SVG editorial ruler, brass fill, bordeaux marker — default for dossier) + `variant="segmented"` (20-segment discrete track — for compact contexts) |
| Poster Option B | `frontend/src/components/Poster.jsx` | Above-frame header (country · rule · coord mono); below-frame footer (serif 32px name + compass rose SVG + subregion); `REGION_META` lookup added to `regions.js` |
| Ask Somm endpoint | `backend/api/routers/somm.py` | `POST /api/somm` — streaming SSE, Haiku, wine-context system prompt, history support; empty message → opening statement |
| Dossier bottle layout | `frontend/src/screens/RegionDossier.jsx` | Design handoff v2: bottle image primary (matted frame, stripe placeholder, Shopify `_1200x` hi-res rewrite), region poster demoted to 88px thumbnail; Vivino rating badge below price; BEST PRICE store badge |
| Search + Region Detail | `backend/api/routers/search.py`, `frontend/src/screens/{SearchScreen,RegionDetail}.jsx` | `/api/search` (name/brand/varietal/region/**sub_region** + nearby price + distance); Region Detail page (facts grid, sub-region counts, Leaflet map); **sub-region rows deep-link to `/search?q=` (mobile + desktop)**; nav search button |
| Grape+region structure table | `backend/recommendation/structure_profiles.py`, `scripts/persist_structure.py` | Deterministic `(grape, region) → {body, tannins, acidity, source:'table'}`, ~55 grapes + ~25 region modifiers (Napa Cab 9/9/5 vs Bordeaux 8/9/6). Validated vs Vivino (tannin 76% / acidity 49% within ±1, beats raw LLM). Wired into scorer body resolution below Vivino/GrapeMinds; **persisted catalog-wide** (structure coverage ~5%→52%, Vivino never overwritten, idempotent) |
| Local LLM extractor + benchmarks | `backend/enrichment/extraction/{ollama_extractor,benchmark,structure_benchmark}.py` | qwen2.5:7b via Ollama at Haiku parity for facts (80/85/97% varietal/region/country); benchmark harnesses vs Vivino ground truth. Backup/fill layer; **not yet wired into CI** (Haiku extraction capped at 1500/run meanwhile) |
| New "Pin" brand mark | `frontend/src/components/Stamp.jsx`, `frontend/public/{favicon,icons,assets}` | Map-pin mark with wine-glass negative space (grape-cluster retired); `reversed` = bordeaux-circle avatar for Somm identity; regenerated PWA icons |
| Conversational chat mode | `backend/recommendation/claude_client.py`, `frontend/src/lib/flags.js` | **Default ON** (`?natural=0` to opt out): follow-up questions answer conversationally (`picks:[]`) instead of spawning new cards, unless clearly re-asking. Backend `conversational` flag → follow-up directive; frontend `naturalChatMode()` sticky flag |
| Mobile chat Option C | `frontend/src/screens/ChatRecommend.jsx` (`PickMessage`) | **Mobile-only**: each wine is a conversational message (tasting note + tappable name-link/price/store-pill + thumbs), no card chrome. Replaced Option A inline cards / bottom sheet. **Desktop keeps split-panel WineCards** |
| Test suite | `backend/tests/` | 327 passing (+ 3 integration-schema vs live DB) |
| Frontend | `frontend/` | Vite + React 19 + Tailwind v3 — desktop + mobile/PWA, 143 tests passing; `npm run dev` at localhost:5173 |

### In Progress / Blocked
| Item | Status |
|---|---|
| Vivino local job | TODO — cron paused (GitHub IPs blocked); set up local `launchd` residential-IP run |
| Total Wine scraper | Blocked — Imperva Enterprise, 403 on everything |
| Wine-Searcher API | Blocked — denied, use case too similar to their product |
| Whole Foods scraper | Blocked — price hard-gated behind Amazon auth; see `data/exploration/wholefoodsmarket_probe2.md` |
| Publix | Blocked — Akamai Bot Manager; re-confirmed 2026-07-05 (now geo-relevant for TN but tech-blocked) |
| Food Lion | Blocked — Cloudflare 403 (Ahold Delhaize platform) |
| Tom Thumb / Albertsons | Blocked — Incapsula; store-resolver works w/ subscription key but product-search endpoint hangs; needs headless browser |
| Corkdorks / Frugal MacDoogal (Nashville) | Blocked — City Hive, product endpoints auth-gated |

### Not Started
- Spec's Austin stores (same scraper pattern, just add Austin store IDs)
- Feedback-as-scoring-signal (thumbs data collecting in `feedback` table, nothing reads it yet)

---

## Tech Stack
- **Database + Auth**: Supabase (cloud project: `knpldhksfsetujbcfrsj`)
- **Backend**: Python 3.9, FastAPI, supabase-py
- **Scraping**: urllib (Shopify shops), curl subprocess (GrapeMinds, Spec's, HEB GraphQL), OAuth REST (Kroger official API) — no Playwright needed yet
- **Hosting**: Vercel (frontend) + Railway (backend) + Supabase (DB) — live private beta
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
- **Antonelli's** (`antonellischeese.com`): filter via `?product_type=Wine` URL param; title format `WINE NAME / Producer / Region / Wine` (slash-separated)
- Synthetic UPCs (`shopify-aoc-{handle}`, `shopify-usnw-{handle}`, `shopify-antonellis-{handle}`) — no cross-retailer dedup possible (natural wines have no barcodes)

### Spec's (REST API — pure curl, no browser)
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

### Vivino Enrichment (HTML scrape — no API key)
- **Name search**: `GET https://www.vivino.com/search/wines?q={url-encoded name}` — true relevance-ranked HTML search (the JSON `/api/wines/search` endpoint 404s)
- **Match validation**: first `/w/{wine_id}` link in results carries a slug (`/en/{producer}-{wine}/w/{id}`) — slug-similarity score (overlap coefficient) against our wine name; varietal-only overlap is explicitly rejected (must have ≥1 distinctive shared token)
- **Two thresholds**: `MATCH_THRESHOLD=0.6` gates ratings + bottle image (cosmetic); `FACTS_THRESHOLD=0.7` gates canonical facts — a borderline match can get a rating badge but can't pollute facts columns
- **What one page fetch yields** (`/w/{id}` embeds full JSON): wine-level `ratings_count`/`ratings_average`, `bottle_medium` image URL (protocol-relative — prepend `https:`), plus canonical attributes: `grapes`, `foods` (pairings), `region`/`country`, `alcohol` (ABV), and the style's `baseline_structure` (1-5 scale)
- **Attribute parse anchoring**: all attributes live inside the wine object after `"id":{wine_id}`; parse window is capped at 40KB — this skips the localization strings earlier in the page (where `"grapes":"Grapes"` is a UI label) and stops short of the recommended-wines carousel
- **Write precedence**: `write_facts` fills NULLs only — scraped and Haiku-extracted data always win. `structure_to_profile` converts 1-5 → GrapeMinds 1-10 convention (intensity→body, fizziness dropped) with `source:"vivino"` marker inside the dict
- **Rate limiting — hard-won lessons**: 5 workers @ 0.3s (~10 req/s) trips a 429 that then reads as wall-to-wall NO_HIT (block pages have no wine links). Safe rate: 2 workers @ 1.0s delay (~2 req/s). Search (`/search/wines`) and wine pages (`/w/{id}`) have **separate rate buckets** — pages can work while search is still blocked
- **Failure semantics**: `_get` returns None on non-200; `search_wine`/`fetch_ratings` raise `VivinoFetchError` on fetch failure (distinct from a genuine no-result). The runner never stamps `vivino_enriched_at` on fetch failures, and aborts after 10 consecutive failures (`ABORT_AFTER`) — blocked runs exit clean and retry later
- **Runner modes** (from `backend/`): `python3 scripts/run_vivino_sample.py --limit N [--dry-run]` (incremental via `vivino_enriched_at IS NULL`); `--missing-images` targets `image_url IS NULL` (effectively HEB/CM — every other scraper captures images); `--backfill-facts` re-fetches pages for already-matched wines ≥0.7 using stored `vivino_wine_id` (no search request; `/w/{id}` redirects to canonical slug)
- **Junk filter**: runner skips sake/cocktail/margarita/RTD names — they never match and pollute NO_HIT stats
- **Automation**: `.github/workflows/daily-vivino.yml` — twice daily, 1,000 wines/run; Vivino step deliberately removed from weekly-scrape.yml so two enrichments never overlap
- **Columns**: `wines.vivino_wine_id`, `vivino_rating`, `vivino_ratings_count`, `vivino_match_score`, `vivino_enriched_at` (migration 13); facts land in `wines.grapes/abv/region/country` + `wine_details.structure_profile/pairing`

### Grape+Region Structure Table (deterministic, fills Vivino's gap)
- **Why not the LLM**: benchmarked qwen2.5:7b structure inference vs Vivino ground truth — sweetness 86% / body 65% but tannin 59% (under-scales) / acidity 22%; heavier calibration prompting made it WORSE. A small LLM can't quantify a 1-10 structure scale. But grape identity (LLM-extracted ~80%) *determines* most of it.
- **`recommendation/structure_profiles.py` `structure_for(varietal, grapes, region)`** → `{body, tannins, acidity, source:'table'}`. ~55 grapes with base profiles + ~25 region modifiers (warm New World +body/+tannin/−acid; cool climate +acid/−body; structured Old World +grip). A Napa Cabernet is 9/9/5 vs Bordeaux 8/9/6. Returns None if no known grape.
- **Validated vs Vivino** (100 wines, within ±1): table beats the raw LLM on tannin (76% vs 60%) and acidity (49% vs 20%). A table→LLM hybrid (LLM refines within ±2, anchored on the table baseline) is marginally best AND fills the ~3% of blends the table can't anchor — reserved for a future pass; sweetness stays LLM (its one strong axis, 87%).
- **Persist**: `scripts/persist_structure.py` writes table structure to `wine_details.structure_profile` via `structure_to_persist()`, which NEVER overwrites Vivino (`source:'vivino'`) or GrapeMinds (real data, no source) — fills empty profiles + refreshes prior table entries (idempotent), skips wines with no grape. One run took real-structure coverage ~5%→52% (8,352 table + 807 vivino of 17,619). Re-run after facts extraction fills more varietals to grow coverage.

### Local LLM Extraction (backup facts layer — not yet wired into CI)
- `enrichment/extraction/ollama_extractor.py` mirrors the Haiku `extractor.py` against Ollama `/api/chat` (`format:"json"`, temp 0). **qwen2.5:7b at Haiku parity** on facts (80/85/97% varietal/region/country vs 82/90/100); llama3.1:8b worse. ~9x slower but free — fits a nightly unattended batch.
- Deterministic normalization in `reference.py` (region aliases Toscana→Tuscany, grape synonyms Fume Blanc→Sauvignon Blanc, region→country inference) lifted both backends and pushed country 57%→~100%.
- Benchmarks: `benchmark.py` (facts) + `structure_benchmark.py` (table vs LLM vs hybrid), scored against Vivino. Migration plan: wire behind `EXTRACTOR_BACKEND=ollama`, drain the backlog locally, drop Haiku from CI. Weekly Haiku extraction CAPPED at 1500/run meanwhile.

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

### Recommendation engine v2.1
- **Tiered candidate pool** — no GrapeMinds hard-gate. Tier 1 = GrapeMinds-enriched
  (`grapeminds_enriched_at` set); Tier 2 = extractor-only (has `varietal` or `region`
  from the Haiku fact extractor). A wine with neither is dropped. Each candidate carries
  a `tier` flag (1 or 2).
- **Knowledge-based deterministic scorer** (`recommendation/scorer.py`, signature
  `score_candidates(intent: dict, candidates: list)`) — maps grape/region → flavor tags
  via `recommendation/flavor_profiles.py` so it can score even Tier-2 wines without
  GrapeMinds structure data. No LLM call in the scorer.
- **Vivino rating boost** — `_W_RATING=1.5` max, boost-only above a 3.5 baseline,
  ignored when `vivino_ratings_count < 25` (`_MIN_RATINGS`). Never penalizes unrated
  wines — obscure natural wines aren't punished for having no Vivino presence.
- **Body resolution order** — text `body` field → numeric `structure_profile.body`
  (≥7 full, 4–6.9 medium, <4 light; covers GrapeMinds + Vivino-backfilled wines) →
  **grape+region `structure_profiles.structure_for()`** (more precise than tags —
  covers medium-bodied grapes like Merlot) → `infer_body(tags)` from grape knowledge.
- **Relevance-first card count** — NO hard quota. The prompt says "recommend the
  wines that genuinely fit — up to 4, fewer is better; return just one if only one
  matches; never pad." Fixes padding a narrow request with an off-target second pick.
- **Store names exposed to Claude** — `_format_wine` shows `@ H-E-B — Lincoln Heights
  H-E-B` so the agent can honor "from Lincoln Heights" itself (soft, no hard filter).
- **Narrative↔picks 1:1** — the prompt forbids naming a wine in the narrative that
  isn't in `picks`; `_enrich_picks` logs a `PICK DROPPED` warning if a pick's wine_id
  isn't a known candidate (diagnoses "3 described, 2 carded" mismatches).
- **Full-pool scoring** — ALL fetched candidates are scored (no per-retailer
  shuffle-truncate; that randomly dropped best matches). Turn-to-turn variety comes
  from seeded ±0.4 jitter added to scores after scoring, below any axis weight.
- **Claude sees ratings** — `_format_wine` appends `4.3★ (57,491 ratings on Vivino)`
  to inventory listings so picks can cite community credibility in their `why`.
- **Picks carry media** — `_enrich_picks` passes `image_url` + `vivino_rating`/`count`
  through to the frontend (WineCard badge rendering is a pending frontend task).
- **Optional NL `message`** — `recommendation/intent.py.parse_message()` (Haiku tool-use)
  turns free text into structured intent, then `merge_intent()` merges it with the
  explicit request fields. Explicit fields win on scalar conflicts; lists (flavors/avoid)
  union; budget is always explicit. Fail-soft: parse errors return `None` and the request
  proceeds on explicit fields only. The router skips parsing the default placeholder
  message (`"Recommend wines based on my preferences"`).

---

## Running the Backend

```bash
# From project root
cd backend
python3 -m uvicorn api.main:app --reload
# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## Running the Frontend

```bash
cd frontend
npm run dev
# App at http://localhost:5173
```

## Running Tests

```bash
cd backend
python3 -m pytest tests/ -v
# 245 passing (242 unit + 3 integration vs live schema).
# Fast/secret-less run: pytest tests/ -m "not integration"  (242 passing, 3 deselected)
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

# Run Antonelli's scraper (Shopify, Austin, 391 wines)
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

---

## Key Files

```
backend/
  api/
    main.py                    — FastAPI app, router registration
    routers/wines.py           — /api/wines/search + /api/wines/:id
    routers/enrichment.py      — /api/enrich/:id + /api/enrich/batch/pending
    routers/recommend.py       — /api/recommend (tiered candidate pool + NL intent merge, Claude Haiku tool-use, radius store lookup)
    routers/feedback.py        — POST /api/feedback (upsert vote by session+entity+type; toggle support)
    routers/somm.py            — POST /api/somm (streaming SSE; wine-context Haiku; empty message → opener)
    schemas.py                 — Pydantic request/response models (incl. FeedbackRequest, SommWineContext, SommRequest)
  enrichment/
    grapeminds.py              — GrapeMinds API client (curl subprocess)
    pipeline.py                — Enrichment orchestrator + two-step warm-up
    vivino.py                  — Async Vivino client (httpx): search + ratings + image + attribute parse (grapes/region/abv/structure/foods); VivinoFetchError on 429/network; structure_to_profile 1-5→1-10
    extraction/
      extractor.py             — Haiku fact extractor (region/varietal/grapes/abv/body)
      ollama_extractor.py      — Local-LLM (qwen2.5:7b) facts extractor; Haiku-parity backup, not yet in CI
      reference.py             — Appellation→region cheat sheet + core grapes + few-shot + normalization (region/grape/country aliases)
      run_extraction.py        — One-shot script: extract all wines + write to DB (`--null-only`, `--limit N`)
      benchmark.py             — Facts benchmark (Haiku vs Ollama vs Vivino ground truth)
      structure_benchmark.py   — Structure benchmark: grape+region table vs LLM vs hybrid, scored on Vivino
  matching/
    eval/                      — GrapeMinds matching eval scripts + results
  recommendation/
    scorer.py                  — knowledge-based deterministic scoring (grape/region → flavor); body via structure table
    flavor_profiles.py         — curated grape/region → flavor-tag lookup
    structure_profiles.py      — deterministic (grape,region) → {body,tannins,acidity}; structure_for() + structure_to_persist()
    intent.py                  — NL message → structured intent + merge with explicit fields
    claude_client.py           — Claude tool-use call (pick + narrative); relevance-first count, conversational follow-up directive, store names in listings
  scrapers/
    base.py                    — BaseScraper ABC + Supabase upsert + auto-geocode stores
    geraldines.py              — Shopify scraper for shopgeraldines.com (SA, ~200 natural wines)
    heb.py                     — HEB GraphQL scraper (18 stores: 6 SA + 12 Austin; STORE_REGISTRY)
    central_market.py          — Central Market scraper (same GraphQL, CM client header, Austin stores 61+420)
    aoc_selections.py          — AOC Selections Shopify scraper (SA, Location_SanAntonio tag filter)
    us_natural_wine.py         — US Natural Wine Shopify scraper (Austin, ~560 natural wines)
    antonellis.py              — Antonelli's Cheese Shop Shopify scraper (Austin, 391 wines)
    harvest_wine.py            — Harvest Wine Market Shopify scraper (Nashville TN, 1,032 wines)
    kroger.py                  — Kroger official Developer API (OAuth) — MARKETS registry, all banners (Kroger + Harris Teeter), per-location pricing
    specs.py                   — Spec's REST scraper (pure curl, 12 SA stores, wine-only)
  scripts/
    backfill_store_coords.py   — One-time lat/lon backfill for existing stores
    merge_duplicate_wines.py   — One-time canonical-UPC dedup merge (idempotent, --dry-run)
    persist_structure.py       — Persist grape+region table structure to wine_details (Vivino-safe, idempotent; `--limit N`, `--dry-run`)
    run_vivino_sample.py       — Vivino runner: `--limit N [--dry-run] [--missing-images] [--backfill-facts]`; thresholds 0.6 (ratings/image) / 0.7 (facts); 2 workers @ 1.0s; abort breaker; never stamps on fetch failure
  tests/                       — 327 tests (324 unit + 3 integration vs live schema)
  conftest.py                  — registers the `integration` pytest marker
  config.py                    — Pydantic settings (reads from ../.env)
  db.py                        — Supabase anon + service role clients
  utils/
    __init__.py                — infer_wine_type() shared utility
    geo.py                     — zip_to_centroid, haversine, find_nearby_store_ids
    upc.py                     — canonical_upc() cross-retailer UPC normalization

supabase/
  migrations/
    20260602000001_initial_schema.sql       — 7 tables + RLS + indexes
    20260602000002_grants.sql               — Role grants for service_role/anon
    20260603000001_add_orange_wine_type.sql — orange wine type
    20260611000001_heb_curbside_price.sql   — adds retail_inventory.curbside_price
    20260614000001_grapeminds_matches.sql   — wine_grapeminds_matches table
    20260614000002_stores_table.sql         — stores registry + store_ref FK on retail_inventory
    20260615000001_wine_extracted_fields.sql — wines.grapes/abv/body columns
    20260620000001_wine_image_url.sql       — wines.image_url
    20260620000002_wine_upc_canonical.sql   — wines.upc_canonical column
    20260620000003_wines_upc_canonical_index.sql — partial UNIQUE index on upc_canonical
    20260630000001_feedback_table.sql           — feedback table (type/entity_id/vote/session_id/user_id/zip); RLS + service_role grant
    20260701000001_wine_vivino_fields.sql       — wines.vivino_wine_id/rating/ratings_count/match_score/enriched_at

frontend/
  src/
    lib/
      api.js                   — getWine, callRecommend, streamRecommend, postFeedback, streamSomm fetch wrappers
      flags.js                 — client feature flags; naturalChatMode() (default ON, sticky ?natural=0 opt-out)
      regions.js               — DISCOVERY_REGIONS (+ country/subregion), REGION_META, REGION_POSTERS, buildApiReq, deriveWineCardMeta
    components/
      Btn.jsx Eyebrow.jsx Tag.jsx  — shared design-system atoms
      StructureBars.jsx        — variant="ruler" (SVG editorial, default) | variant="segmented" (20-seg discrete); items=[label,desc,value] tuples
      Contours.jsx             — procedural SVG contour map (connective motif)
      Poster.jsx               — Option B: above-frame header (country·rule·coord) + compass rose footer; `REGION_META` drives metadata
      WineCard.jsx             — editorial wine card (ink frame, brass keyline, flavor tags, Pattern A thumbs)
      SommOverlay.jsx          — FAB + 400px slide-in chat panel; wine context strip; streaming chat; Pattern B thumbs; suggestion chips; history persists on close
    screens/
      PreferenceCapture.jsx    — zip + budget + style cards + occasion toggle → /recommend
      ChatRecommend.jsx        — desktop: sommelier chat left + WineCards right (split panel). MOBILE: Option C conversational PickMessages (name-link/price/store-pill, no cards). Pattern B message feedback; conversational follow-ups; sessionId + vote state persisted across dossier round-trip
      RegionDossier.jsx        — wine dossier: Poster (Option B), ruler StructureBars, store row, SommOverlay wired with wine context
      Discovery.jsx            — 18-region grid (10 Tier 1 + 8 Tier 2), click → /recommend
    App.jsx                    — NavBar + react-router-dom v7 routes
  design-system/               — design tokens, UI kit reference components, poster assets
  vite.config.js               — Vitest + React plugin config

data/
  heb-stores.csv               — Active HEB store registry (active flag); edit to add stores, no code change
  heb-store-list.csv           — Full HEB TX store list (source of truth for store IDs)
  exploration/                 — API probe scripts + results (not production code)
    grapeminds_findings.md     — GrapeMinds API findings doc
    heb_probe.py / heb_api_probe.py / heb_graphql_probe.py
    totalwine_probe.py
    geraldines_probe.py
    specs_probe.py             — Spec's API discovery (specsonline.com)
    specs_findings.md          — Spec's API reference (search endpoint, store numbers, field shapes)
    local_shopify_wine_shops.md — SA/Austin Shopify wine shop research (3 confirmed: AOC, USNW, Antonelli's)
    wholefoodsmarket_findings.md — WFM catalog API open, price blocked (requires Amazon auth)
    wholefoodsmarket_price_probe.md — WFM price probe: Amazon HTML works but bot-blocked; PA API is viable path
    wholefoodsmarket_probe2.md — WFM re-probe (2026-07-02): all blockers confirmed; varietal-search workaround covers 89% of catalog but price still auth-gated — verdict: don't build
    costco_findings.md         — Blocked (Akamai), no TX online wine
    traderjoes_findings.md     — Blocked (Akamai), no inventory API
    publix_findings.md         — Blocked (Akamai), wrong geography
    vivino_probe.py            — Vivino API probe script
    vivino_findings.md         — Vivino findings: JSON API 404s; HTML search (/search/wines?q=) is the only working name-lookup; wine page embeds full JSON stats

docs/
  superpowers/
    specs/
      2026-06-16-zip-store-mapping-design.md  — zip→store radius mapping design
      2026-06-18-specs-scraper-design.md     — Spec's scraper design
      2026-06-20-upc-canonical-dedup-design.md — cross-retailer UPC dedup design
      2026-06-22-recommendation-engine-v2-design.md — rec engine v2 design
    plans/
      2026-06-16-zip-store-mapping.md         — zip→store implementation plan
      2026-06-18-specs-scraper.md            — Spec's scraper implementation plan
      2026-06-20-upc-canonical-dedup.md       — UPC dedup implementation plan
      2026-06-22-recommendation-engine-v2.md  — rec engine v2 implementation plan
      2026-06-30-scheduled-scrape-heb-expansion.md — weekly scrape workflow + CSV store registry plan
      2026-07-01-somm-overlay-design-refresh.md — somm overlay + StructureBars v2 + Poster Option B implementation plan
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
| `ANTHROPIC_API_KEY` | ✅ Set (monthly spend cap set in console) |
| `KROGER_CLIENT_ID` / `KROGER_CLIENT_SECRET` | ✅ Set — official Developer API (covers Kroger + Harris Teeter banners) |
| `ADMIN_TOKEN` | ✅ Set — gates `/api/enrich/*` in prod |
| `SLACK_WEBHOOK_URL` | ✅ Set — scrape/enrich completion notifications |
| `ALLOWED_ORIGINS` | ✅ Set on Railway — prod CORS origin |
| `WINE_SEARCHER_API_KEY` | ❌ Denied — use case too similar to their offering |
| `VINERADAR_API_KEY` | ⏳ API unreleased, on waitlist |
| `APIFY_API_TOKEN` | ⬜ Not set up |
| `INSTACART` | ❌ Not accepting new developers |

---

## What's Next (priority order)
1. ~~Sommelier agent routing~~ ✅ Done
2. ~~Scheduled scrape + extraction pipeline~~ ✅ Done — GitHub Actions cron Sunday 02:00 CT; see `.github/workflows/weekly-scrape.yml`
3. ~~HEB store expansion (CSV-driven)~~ ✅ Done — 37 SA/suburb stores staged in `data/heb-stores.csv`; flip `active=true` to enable any
4. ~~Feedback loop~~ ✅ Done — Pattern A (wine card thumbs) + Pattern B (sommelier message thumbs + follow-up bubble); `POST /api/feedback` + `feedback` table live; session-scoped votes persist across dossier round-trip
5. ~~Somm overlay + design refresh~~ ✅ Done — `SommOverlay` FAB + slide-in chat panel on dossier; `POST /api/somm` streaming; StructureBars ruler/segmented variants; Poster Option B with compass rose
6. ~~Deploy~~ ✅ Done 2026-07-05 — Vercel + Railway; rate limits, ADMIN_TOKEN gate, ALLOWED_ORIGINS CORS; live private beta
7. ~~Mobile / PWA~~ ✅ Done — responsive ≤640px on all screens, installable PWA (mobile chat now Option C conversational messages, not cards)
8. ~~Grape+region structure table~~ ✅ Done — deterministic structure, validated vs Vivino, persisted catalog-wide (coverage ~5%→52%); see structure-table section
9. ~~Chat naturalness + mobile Option C~~ ✅ Done — conversational follow-ups (default ON), relevance-first card count, mobile conversational pick messages, new Pin mark, sub-region search deep-link
10. **Mac mini enrichment server** — dedicated always-on box for both enrichment jobs (residential-IP Vivino `launchd` + local qwen extraction). Clone repo to **`~/dev/wine_app`** (outside `~/Documents` → no macOS TCC / Full Disk Access hassle that blocked the laptop launchd job). 16 GB RAM fits qwen2.5:7b comfortably. Runbook: `docs/mac-mini-enrichment-server.md`. Vivino launchd + wrapper already built (`backend/scripts/`), just needs path edits. (Manual Vivino/extraction runs work on the laptop meanwhile)
11. **Local LLM extraction cutover** — qwen2.5:7b benchmarked at Haiku parity (`ollama_extractor.py`). Wire behind `EXTRACTOR_BACKEND=ollama`, drain backlog locally, drop Haiku from CI (capped at 1500/run now). Re-run `persist_structure.py` after to grow structure coverage past 52%
12. **Blend structure/sweetness LLM pass** — table→LLM hybrid for the ~3% of blends the table can't anchor + LLM sweetness (its one strong structure axis)
13. **Extraction pass on new Nashville/NC/Dallas wines** — Harvest + Kroger + Harris Teeter + DFW HEB wines need `--null-only` extraction to become recommendable (also unlocks more structure coverage on re-run of `persist_structure.py`)
14. ~~User accounts Phases 0–3~~ ✅ Done — magic-link auth, saved favorites, mobile account home + "You" tab, cellar (drinking windows, drank-rating), taste-profile interview. Remaining: **Phase 4 price-alert watches** (depends on `price_watches` table + notifier). Roadmap: `docs/user-accounts-roadmap.md`
15. ~~Feedback-as-scoring-signal~~ ✅ Done — votes carry `user_id`, RLS read policy, `buildTasteContext` folds 👍→liked / 👎→disliked, scorer boosts/penalizes resemblance. Remaining niche: merge anonymous session votes to user_id on sign-in (needs backend JWT verify)
16. **Price alerts + promo scraping** — ⚙️ Phase 1 DONE: `price_history` table + trigger capturing deltas now (can't backfill, so started early). REMAINING: `price_watches` (user × wine × target) + notifier — depends on user accounts. Promo data (Spec's `unitPricePromoDiscount`, Kroger promo, HEB ONLINE/CURBSIDE delta) flows into history too
17. ~~Ratings badge in WineCard + ChatRecommend~~ ✅ Done — desktop WineCards + mobile Option C pick messages show a compact `4.3★ · 57k` Vivino badge (gated on rating + count)
18. **Per-pick distance** — Option C store pill shows `◎ {retailer}` only; add store→zip distance per pick for the `· X.X mi` suffix
19. **Analytics** — ⚙️ Foundation shipped (`lib/analytics.js`, no-op without `VITE_POSTHOG_KEY`; funnel events + SPA pageviews). REMAINING: create a PostHog project (free tier) + set `VITE_POSTHOG_KEY` in Vercel to turn it on
20. Kroger banner expansion — Memphis/Houston (Kroger), other NC/VA cities (Harris Teeter); config-only via `MARKETS`
21. Local MCP server for Claude Desktop (parked) — see memory `mcp-desktop-parked`
22. Add more Shopify local wine shops (same scraper pattern, zero new code)
23. Blocked probes not worth revisiting without headless browser: Total Wine, WFM, Publix, Food Lion, Tom Thumb/Albertsons
24. ~~Twin Liquors scraper~~ ✅ **BUILT 2026-07-09** — `backend/scrapers/twin_liquors.py`. See Done-table row. Remaining: enumerate the full ~90-store merchant_id list (12 seeded) + run the full scrape on the mini (residential IP dodges the Cloudflare 1015 that datacenter/burst hits). **Reusable: the api_key + client_origin bypass likely unblocks the parked Nashville City Hive shops (Corkdorks, Frugal MacDoogal)**
25. **Personalization follow-ons (parked)** — anon-vote merge on sign-in; `similar_to` badge in pick UI (data already flows); consumed-cellar bottles as taste signal; profile avoids as mechanical scorer penalties (currently Claude-side); smarter top-10 selection for the "[Your wines]" block
