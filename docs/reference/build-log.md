# Build Log — component status + file map

Detailed per-component status and the full file tree, moved out of CLAUDE.md to keep it lean. This is the exhaustive record; CLAUDE.md carries the condensed status + roadmap.

## Current Build Status (as of 2026-07-05)

### Done
| Component | Location | Notes |
|---|---|---|
| Supabase schema | `supabase/migrations/` | 13 migrations live in cloud DB |
| Vivino enrichment | `backend/enrichment/vivino.py`, `backend/scripts/run_vivino_sample.py` | Async httpx; ratings + bottle image + canonical facts (grapes/region/abv/structure/pairing) from 2 HTML requests/wine; 429-safe (VivinoFetchError, no false stamps, pause-and-resume); `--missing-images` + `--backfill-facts` modes; ~1,027 matched |
| Daily Vivino workflow | `.github/workflows/daily-vivino.yml` | **RETIRED 2026-07-09** — GitHub runner datacenter IPs are IP-blocklisted by Vivino (~23 wines/day even on crawl profile). Superseded by the Mac mini local launchd job (residential IP). `workflow_dispatch` only |
| Local Vivino launchd job | `backend/scripts/run_vivino_launchd.sh` + `com.somm.vivino-enrich.plist` | **LIVE on M4 Mac mini as of 2026-07-09** — residential IP, repo at `~/dev/wine_app` (outside `~/Documents` → no TCC). Twice daily 10:00 & 16:00 local, `--limit 300`/run, logs to `~/Library/Logs/somm-vivino.log`; idempotent + abort-breaker safe. Wrapper pins `/usr/bin/python3` explicitly (matches CLAUDE.md 3.9 target; launchd's minimal PATH resolves there too) and sources `lib_notify_slack.sh` to ping Slack on success/failure. See `docs/mac-mini-enrichment-server.md` |
| Weekly extraction LaunchAgent | `backend/scripts/run_extraction_launchd.sh` + `com.somm.extraction-enrich.plist` | **LIVE on mini as of 2026-07-09** — weekly Sun 03:00 CT (fires after the GitHub weekly-scrape). Runs `EXTRACTOR_BACKEND=ollama python3 -m enrichment.extraction.run_extraction --null-only` then chains `python3 scripts/persist_structure.py`. Self-mutex via `pgrep` (skips if another `--null-only` run is in flight). Logs to `~/Library/Logs/somm-extraction.log`, Slack-notifies with separate extract/persist exit codes so a partial failure is diagnosable from the message alone |
| Enrichment Slack notifier | `backend/scripts/lib_notify_slack.sh` | Shared bash helper both mini wrappers source. Reads `SLACK_WEBHOOK_URL` from env or parses `../.env`; fails soft (no webhook → no-op). Success posts `:white_check_mark: *Job* — OK` with a one-line summary; failure posts `:x:` with the last 15 log lines in a code block for triage. Escapes payload via `python3 -c "import json; ..."` to bulletproof unicode/quotes/newlines from Vivino names |
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
| Pogo's Wine & Spirits scraper | `backend/scrapers/pogos.py` | Shopify API, Dallas (Inwood Village fine/natural wine shop) — ~770 wines inside a 1,500-product beer/spirits catalog; same `/products.json` pattern as Harvest, capitalized single-word product_type normalized + non-wine dropped; `vendor` is a distributor so brand left null; synthetic `shopify-pogos-{handle}` UPCs. **In weekly workflow as of 2026-07-10** (was manual-only before) |
| Central Market scraper | `backend/scrapers/central_market.py` | Same HEB GraphQL, `central-market` client header, 2 Austin stores (61, 420); SA store 191 not e-commerce-enabled |
| AOC Selections scraper | `backend/scrapers/aoc_selections.py` | Shopify API, SA-only (Location_SanAntonio tag filter), ~fine wine catalog, page-param pagination |
| US Natural Wine scraper | `backend/scrapers/us_natural_wine.py` | Shopify API, Austin (~560 natural wines), normalizes inconsistent product_types |
| Antonelli's scraper | `backend/scrapers/antonellis.py` | Shopify API, Austin (**65 wines** of 391 total products — cheese shop, mostly non-wine), product_type=Wine filter (client-side; the `?product_type=` URL param is ignored by Shopify so we fetch all + filter), slash-separated title format |
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
| Weekly scrape workflow | `.github/workflows/weekly-scrape.yml` | GitHub Actions cron Sunday 02:00 CT — 10 scrapers (7 SA/Austin + Harvest + Pogo's + Kroger) + `--null-only` extraction; Slack notify per-scraper; each step `continue-on-error`. **Twin Liquors is NOT here — Cloudflare-1015-blocks GitHub datacenter IPs (confirmed 2026-07-10, 0/12 stores); runs on the mini instead (like Vivino).** |
| requirements.txt | `backend/requirements.txt` | 17 pinned deps for reproducible CI installs |
| Optional user accounts + favorites | `frontend/src/lib/{supabase,auth,favorites,pendingSave}.js(x)`, `components/{SignInModal,AuthNav,SaveBookmark,DossierSaveButton}.jsx`, `screens/Saved.jsx`, `supabase/migrations/20260707000002_user_accounts.sql` | **Anonymous-first, optional.** Supabase Auth email **magic link** (verified working; implicit flow). `AuthProvider`/`useAuth` centralizes session + saved bottles + a contextual sign-in prompt. Save bookmark on every WineCard + dossier Save button; anon tap → sign-in prompt → auto-saves via pending-save round-trip. `/saved` view (desktop avatar menu + mobile Saved tab). `profiles` + `favorites` tables, RLS-scoped `user_id=auth.uid()` (read/write direct via supabase-js, no backend). **Prod needs `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` in Vercel (set 2026-07-09) — sign-in UI hides entirely without them (build-time bake)** |
| Cellar (Phase 2) | `frontend/src/screens/Cellar.jsx`, `lib/{cellar,drinkingWindow}.js`, `components/AddBottleModal.jsx`, `supabase/migrations/20260708000001_cellar.sql` | Bottle tracking with computed drinking window (varietal+vintage heuristic, brass progress bar); catalog + off-catalog add paths; sort picker (**drink-soonest default** / added / vintage); "Drank it" → consumed + **quick 👍/👎 rating toast** (catalog bottles post feedback → personalization); mobile-scrollable |
| Personalization (behavioral) | `backend/recommendation/scorer.py`, `frontend/src/lib/taste.js`, `components/DossierRateButton.jsx`, `supabase/migrations/20260708000002_feedback_user_rls.sql` | **Saved + cellar + 👍/👎 → re-rank + cite.** `buildTasteContext` gathers liked (upvoted/saved/owned-cellar) + disliked (downvoted) via RLS → `RecommendRequest.taste` on every rec + follow-up. Scorer: similarity boost (`_W_SIMILAR` 2.5; shared grape > region > flavor) tags `_similar_to`/`_similar_source` → Claude cites accurately ("close to the X you saved"); dislike penalty (`_W_DISLIKE` 2.0). Votes carry `user_id`; RLS lets users read own feedback. Dossier thumbs. First rec gated on auth `ready` (race fix). Consumed cellar bottles drop out of taste |
| Taste profile interview (Phase 3) | `frontend/src/screens/TasteProfile.jsx`, `lib/{tasteInterview,profile}.js`, `/taste` route | Conversational Somm Q&A (6 scripted questions, chips + free text, chat-styled) → structured `profiles.taste_profile`. Entry: account-page row + desktop avatar menu. Feeds BOTH: scorer soft axes (loved-region +1.0 / body +1.0 / lean +0.75 — **only when the request doesn't specify that dimension; explicit request always wins**) AND Claude prompt (`_taste_profile_block` + "[Your wines]" list so the Somm can reference cellar/saved directly). `/api/somm` also accepts `taste` — the dossier overlay is personalized too |
| Phantom-card reconciler | `backend/api/routers/recommend.py` `_reconcile_picks_to_narrative` | Claude sometimes returns more picks than it narrates ("2 described, 3 cards" — prompt 1:1 rule alone insufficient). Deterministic backstop: narrative streams before picks, so drop any pick it never names (distinctive-token match: producer/vineyard, not grape/region; never to empty); logs `PICKS RECONCILED` |
| Search vintage grouping | `backend/api/routers/search.py` `_group_key` | Same wine, new UPC per vintage = separate rows → availability fragments (The Prisoner: Spec's-only row hid 16 HEB stores incl. Lincoln Heights). Search groups by vintage-stripped name, aggregates `retailers[]`, represents each group by its best-stocked row. Full fix (dossier/recs/counts too) = product-family key: `docs/product-family-key.md` |
| Zip-aware sub-region counts | `backend/api/routers/region.py` | `/region/{name}/subregions?zip=` counts only wines in stock near the zip — the "N nearby" badge now matches what the sub-region click (zip-scoped search) returns; no zip = catalog-wide |
| Twin Liquors scraper | `backend/scrapers/twin_liquors.py` | TX chain (Austin/SA), City Hive. Anonymous bypass = api_key + `client_origin` from storefront HTML → `products/search.json`. **Wine-only** via `additional_properties.type=="wine"` (spirits/beer/RTD/merch never enter; verified 0 leakage) — same block gives pre-enriched varietal/region/country/ABV persisted directly. Per-store = merchant_id (12 seeded of ~90); 30/term cap → 42-term sweep deduped by product id (~246 wines/store); synthetic `twinliquors-{id}` UPC. **Runs on the residential-IP mini only** — GitHub datacenter IPs are Cloudflare-1015-blocked (confirmed 2026-07-10, 0/12 stores committed), like Vivino. Wrapper `backend/scripts/run_twin_liquors_launchd.sh`; runbook `docs/mac-mini-enrichment-server.md`. Ref: `data/exploration/twinliquors_findings.md` |
| Twin Liquors LaunchAgent | `backend/scripts/run_twin_liquors_launchd.sh` + `com.somm.twin-liquors.plist` | **LIVE on mini as of 2026-07-09** — weekly Sun 04:00 CT (fires after the 02:00 GitHub weekly-scrape and 03:00 extraction LaunchAgent so nothing overlaps). Wrapper mirrors Vivino: pins `/usr/bin/python3`, sources `lib_notify_slack.sh`, Slack-notifies OK (duration + last summary line) / FAIL (exit code + last 15 log lines). Logs `~/Library/Logs/somm-twin-liquors.log`. Smoke-tested 2026-07-09 via `launchctl start`. Runs the 12 seeded merchant_ids until the full ~90-store list is enumerated |
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
| Local LLM extractor + benchmarks | `backend/enrichment/extraction/{ollama_extractor,benchmark,structure_benchmark}.py` | qwen2.5:7b via Ollama at Haiku parity for facts (80/85/97% varietal/region/country); benchmark harnesses vs Vivino ground truth. **Wired on Mac mini** via `EXTRACTOR_BACKEND=ollama` in the weekly extraction LaunchAgent (Sun 03:00 CT, chains `persist_structure.py`). Initial 5,516-wine backlog drain kicked off 2026-07-09 with a watcher that Slack-notifies drain completion + persist result. Haiku still active in `weekly-scrape.yml` as a fallback (capped 1500/run) until local drains catch up |
| New "Pin" brand mark | `frontend/src/components/Stamp.jsx`, `frontend/public/{favicon,icons,assets}` | Map-pin mark with wine-glass negative space (grape-cluster retired); `reversed` = bordeaux-circle avatar for Somm identity; regenerated PWA icons |
| Conversational chat mode | `backend/recommendation/claude_client.py`, `frontend/src/lib/flags.js` | **Default ON** (`?natural=0` to opt out): follow-up questions answer conversationally (`picks:[]`) instead of spawning new cards, unless clearly re-asking. Backend `conversational` flag → follow-up directive; frontend `naturalChatMode()` sticky flag |
| Mobile chat Option C | `frontend/src/screens/ChatRecommend.jsx` (`PickMessage`) | **Mobile-only**: each wine is a conversational message (tasting note + tappable name-link/price/store-pill + thumbs), no card chrome. Replaced Option A inline cards / bottom sheet. **Desktop keeps split-panel WineCards** |
| Test suite | `backend/tests/` | 327 passing (+ 3 integration-schema vs live DB) |
| Frontend | `frontend/` | Vite + React 19 + Tailwind v3 — desktop + mobile/PWA, 143 tests passing; `npm run dev` at localhost:5173 |

### In Progress / Blocked
| Item | Status |
|---|---|
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
    antonellis.py              — Antonelli's Cheese Shop Shopify scraper (Austin, 65 wines)
    harvest_wine.py            — Harvest Wine Market Shopify scraper (Nashville TN, 1,032 wines)
    pogos.py                   — Pogo's Wine & Spirits Shopify scraper (Dallas, ~770 wines)
    kroger.py                  — Kroger official Developer API (OAuth) — MARKETS registry, all banners (Kroger + Harris Teeter), per-location pricing
    specs.py                   — Spec's REST scraper (pure curl, 12 SA stores, wine-only)
  scripts/
    backfill_store_coords.py   — One-time lat/lon backfill for existing stores
    merge_duplicate_wines.py   — One-time canonical-UPC dedup merge (idempotent, --dry-run)
    persist_structure.py       — Persist grape+region table structure to wine_details (Vivino-safe, idempotent; `--limit N`, `--dry-run`)
    run_vivino_sample.py       — Vivino runner: `--limit N [--dry-run] [--missing-images] [--backfill-facts]`; thresholds 0.6 (ratings/image) / 0.7 (facts); 2 workers @ 1.0s; abort breaker; never stamps on fetch failure
    run_vivino_launchd.sh      — Mac mini Vivino wrapper (residential-IP launchd job, twice daily, Slack notify)
    run_extraction_launchd.sh  — Mac mini weekly qwen extraction wrapper (Sun 03:00 CT; chains persist_structure; Slack notify)
    lib_notify_slack.sh        — Shared Slack notify helper sourced by both mini wrappers; fails soft if webhook unset
    _watch_current_drain.sh    — One-shot watcher for the initial 2026-07-09 backlog drain; polls extraction PID, then runs persist_structure and Slack-notifies both stages
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
