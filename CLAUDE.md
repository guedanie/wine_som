# Somm — Wine Recommendation App

## What This Is
Full-stack wine recommendation app. Users enter zip code + budget + style preferences and get Claude-powered sommelier recommendations for wines available at local retailers near them. (Public overview: `README.md`. Frontend design system: `frontend/CLAUDE.md`.)

**LIVE (private beta since 2026-07-05):** frontend `wine-som-pkwz-chi.vercel.app` (Vercel) + backend `winesom-production.up.railway.app` (Railway) + Supabase. Installable PWA. Testers in San Antonio, Austin, Nashville, Charlotte + Winston-Salem NC; Dallas focus coming.

## Tech Stack
- **Database + Auth**: Supabase (cloud project `knpldhksfsetujbcfrsj`)
- **Backend**: Python 3.9, FastAPI, supabase-py
- **Frontend**: React 19 + Vite + Tailwind v3 (desktop + mobile/PWA)
- **AI**: Anthropic Claude — Sonnet 4.6 (recommendations, streamed) + Haiku 4.5 (Somm overlay chat, NL intent parse); fact extraction runs on the mini's local qwen
- **Scraping**: urllib (Shopify), curl subprocess (HEB/CM GraphQL, Spec's, City Hive), OAuth REST (Kroger) — no Playwright
- **Geo**: `pgeocode` (offline US zip centroids)
- **Hosting**: Vercel (web) + Railway (api) + Supabase (db)

---

## Critical gotchas (read before working)

- **Python 3.9.6** — use `Optional[str]` from `typing`, NOT `str | None` (that needs 3.10+).
- **Run backend commands from `backend/`** so `../.env` resolves. **Run frontend commands (vitest/vite) from `frontend/`** so config loads — a common failure is running from the repo root, which yields "test is not defined" / "cannot resolve index.html" (cwd drift).
- **Supabase**: anon key = public reads; service_role = backend only (bypasses RLS). Tables need explicit GRANTs (`supabase/migrations/20260602000002_grants.sql`). User tables (`profiles`, `favorites`, `cellar`, `feedback`) are RLS-scoped `user_id = auth.uid()` and read/written directly via supabase-js — no backend endpoint.
- **`retail_inventory` → `stores` FK is `store_ref`** (UUID), NOT `store_id`.
- **Wine identity = `wines.upc_canonical`** (full UNIQUE constraint). `canonical_upc()` normalizes real barcodes; any id with a letter (synthetic `shopify-…`, `twinliquors-…`) passes through unchanged. Scrapers upsert `on_conflict="upc_canonical"`; `retail_inventory.upc` stores the RAW barcode.
- **`.env` is not in git** — copy it manually to any new machine (e.g. the mini). Prod (Vercel) needs `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` baked at build time or the sign-in UI silently hides.
- **TDD** the logic-bearing code; when a scorer/parse test passes for the "wrong reason" (stable-sort ties), reorder inputs so only the change under test can pass.

## Running it

```bash
# Backend (from backend/)          Frontend (from frontend/)
cd backend                          cd frontend
python3 -m uvicorn api.main:app --reload    npm run dev        # localhost:5173
# localhost:8000  (docs: /docs)

# Tests
cd backend  && python3 -m pytest tests/ -m "not integration"   # fast, secret-less
cd frontend && npx vitest run
```

Seeding scrapers + the full per-retailer run commands: **`docs/reference/scrapers.md`**.

---

## Current status (summary)

Full component table + file map: **`docs/reference/build-log.md`**.

- **Retail data** — 11 scrapers live (H-E-B, Central Market, Spec's, Kroger, Harris Teeter, Twin Liquors, Pogo's, Geraldine's, AOC, US Natural Wine, Antonelli's, Harvest) across TX/TN/NC. Weekly GitHub cron runs 9; **Spec's + Twin Liquors + Vivino + local-LLM extraction run on the residential-IP Mac mini** (datacenter IPs are Cloudflare/Vivino-blocked; Spec's silently blocked since 2026-07-01 — moved to the mini 2026-07-13). `scripts/verify_scrape_runs.py` runs after the weekly cron and flips silent-zero "successes" to failed + Slack-alerts. Details: `docs/reference/scrapers.md`, `docs/mac-mini-enrichment-server.md`.
- **Enrichment** — layered: retailer data → Vivino (ratings/facts/image) → local LLM (qwen2.5:7b, Haiku-parity) → deterministic grape+region structure table. Details: `docs/reference/enrichment.md`.
- **Recommendation** — deterministic knowledge-based scorer shortlists; Claude (Sonnet 4.6) picks + narrates, streamed progressively (narrative word-by-word, then cards one at a time). Personalization (saved + cellar + 👍/👎 votes + taste-profile interview) re-ranks and is cited. Details: `docs/reference/recommendation.md`.
- **Frontend** — React SPA + installable PWA; anonymous-first with optional magic-link accounts (saved bottles, cellar, taste profile). Design system: `frontend/CLAUDE.md`.
- **Blocked retailers** — Total Wine (Imperva), Whole Foods (Amazon auth), Publix/Costco/Trader Joe's (Akamai), Food Lion (Cloudflare), Tom Thumb/Albertsons (Incapsula), Corkdorks/Frugal MacDoogal (City Hive auth — may be unblockable via the Twin Liquors bypass).

## Reference docs
These hold the deep detail moved out of this file — **consult the relevant one on demand when a task touches that system; don't read them preemptively.** The inline "Details: …" pointers above tell you which applies.

- `docs/reference/scrapers.md` — per-retailer API notes, UPC dedup, seeding commands
- `docs/reference/enrichment.md` — GrapeMinds, Vivino, local LLM, structure table
- `docs/reference/recommendation.md` — scorer, personalization, intent, zip→store
- `docs/reference/build-log.md` — full component status table + file map
- `docs/mac-mini-enrichment-server.md` — the residential-IP enrichment runbook
- `docs/mini-agent-tasks.md` — queued mini work: Spec's migration (+ its two known landmines) and extraction run-logging
- `docs/product-family-key.md` — vintage-agnostic wine identity (future)
- `data/exploration/*_findings.md` — how each retailer API was reverse-engineered
- `frontend/CLAUDE.md` — design system (type, color, components, voice)

---

## API Keys (.env)

| Key | Status |
|---|---|
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | ✅ Set |
| `ANTHROPIC_API_KEY` | ✅ Set (monthly spend cap in console) |
| `GRAPEMINDS_API_KEY` | ✅ Set (~17/250 calls used) |
| `KROGER_CLIENT_ID` / `KROGER_CLIENT_SECRET` | ✅ Set — official Developer API (Kroger + Harris Teeter) |
| `ADMIN_TOKEN` | ✅ Set — gates `/api/enrich/*` in prod |
| `SLACK_WEBHOOK_URL` | ✅ Set — scrape/enrich notifications |
| `ALLOWED_ORIGINS` | ✅ Set on Railway — prod CORS |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` / `VITE_POSTHOG_KEY` | ✅ Set in Vercel (build-time) |
| `WINE_SEARCHER_API_KEY` | ❌ Denied | · `VINERADAR_API_KEY` ⏳ waitlist · `APIFY_API_TOKEN` ⬜ · `INSTACART` ❌ |

---

## What's Next (priority order)

Done unless noted. Detailed history: `docs/reference/build-log.md`.

1–10. ✅ Sommelier routing · scheduled scrape · HEB CSV expansion · feedback loop · Somm overlay · deploy · mobile/PWA · structure table · chat naturalness · **Mac mini enrichment server** (Vivino + weekly extraction + Twin Liquors launchd, all live).

11. ✅ **Local LLM extraction cutover** — done 2026-07-10: initial 6,298-wine drain wrote 5,974 (~5% loss to malformed-UUID echoes, non-corrupting); persist_structure landed 11,899 new structure rows. Haiku extraction step removed from `weekly-scrape.yml` 2026-07-11. Mini's weekly `com.somm.extraction-enrich` LaunchAgent (Sun 03:00 CT) is now the only extraction path. Steady-state NULL: 16.9% varietal / 19.1% region / 10.9% both (of 19,254 wines).
12. **Blend structure/sweetness LLM pass** — table→LLM hybrid for the ~3% of blends the table can't anchor + LLM sweetness.
13. ✅→⚙️ **Extraction pass on new Nashville/NC/Dallas wines** — mostly done by the weekly mini job (varietal-null 2026-07-13: Harvest 4%, Harris Teeter 10%, Kroger 12% — vs H-E-B baseline 2%). REMAINING: **Pogo's Dallas residue** — 36% varietal-null, ~15% missing BOTH varietal+region (invisible to the recommender). These are extraction *failures*, not backlog (obscure fine-wine labels with no grape/region in the name — the 07-10 drain already tried them); re-running `--null-only` won't help. Fix path: Vivino matching from the mini (knows producers by name) — prioritize both-null wines in its queue. Matters for the Dallas push.
14. ✅ **User accounts Phases 0–4** — magic-link auth, saved favorites, mobile account home, cellar (drinking windows + drank-rating), taste-profile interview, price watches (2026-07-13, see item 16). REMAINING: the watch notifier. Roadmap: `docs/user-accounts-roadmap.md`.
15. ✅ **Feedback-as-scoring-signal** — votes carry `user_id` + RLS read; `buildTasteContext` folds 👍→liked / 👎→disliked; scorer boosts/penalizes. Niche remaining: merge anon session votes on sign-in (needs backend JWT verify).
16. **Price intelligence** — ⚙️ design handoff: `frontend/design-system/handoffs/price-intelligence/`. Phase 1 done (`price_history` + delta trigger). **Phase A done 2026-07-13**: `PriceMarker` chip (4 variants) + dossier price-context module (drop/steady states, week-strip glyph, cheapest-row flag + struck was-price) fed by `utils/price_context.py` via `/api/wines/{id}`. **Phase B done 2026-07-13**: shortlist annotated with fresh drops (`fresh_drops_for`, one history fetch for the top-12), `price_drop` rides pick payloads, chip leads WineCard chip rows + mobile pick pill line, somm voices drops week-anchored ("dropped $5 at H-E-B this week"). **Phase C done 2026-07-13**: `GET /api/deals` (fresh drops via `fresh_price_drops` SQL window fn — postgrest's 1000-row pages made client-side scanning lossy — ranked quality×movement with an editorial floor: ≥$7, rated wines ≥3.7★, unrated pass) + Discover rail ("Worth grabbing · Week of X", hidden on empty weeks) + `/deals` screen. NOTE: `price_history` needed a read GRANT + RLS policy (migrations 20260713000001-3, applied) — anon silently saw 0 rows, so Phase A was steady-only in prod until then. **Phase D done 2026-07-13**: `price_watches` table (RLS like favorites, migration 20260713000004 applied) + Watch price ghost→Watching button in the dossier price module (both layouts) + anonymous tap → contextual sign-in nudge ("I'll tell you when X drops") with pending-watch intent through the magic-link round-trip. REMAINING: the notifier (weekly job joining `price_watches` × `fresh_price_drops` → PWA push/email — copy is in the design handoff). NOTE: restock variant needs a trigger extension (in_stock-only flips write no history row).
17. ✅ **Ratings badge** in WineCard + mobile pick messages.
18. ✅ **Per-pick distance** — `distance_miles` (user-zip centroid → store, haversine) flows recommend endpoint → pick → mobile store pill + desktop WineCard retailer line. Also fixed: Spec's + Twin Liquors scrapers now write `stores.address` (street was parsed then dropped; every other retailer already had it).
19. **Analytics** — ⚙️ foundation shipped; PostHog live in Vercel.
20. **Kroger banner expansion** — Memphis/Houston/other NC-VA cities (config-only via `MARKETS`).
21. Local MCP server for Claude Desktop (parked — memory `mcp-desktop-parked`).
22. More Shopify wine shops (zero new code) · enumerate full ~90 Twin Liquors stores.
23. Blocked probes (headless-browser only): Total Wine, WFM, Publix, Food Lion, Tom Thumb/Albertsons.
24. ✅ **Twin Liquors scraper** — live on the mini (Sun 04:00 CT). GitHub IPs Cloudflare-blocked. **Reusable: the api_key + client_origin bypass likely unblocks Corkdorks / Frugal MacDoogal (Nashville).**
25. **Personalization follow-ons (parked)** — anon-vote merge; `similar_to` badge in pick UI; consumed-cellar as taste signal; profile avoids as mechanical scorer penalties; smarter top-10 for the "[Your wines]" block.
26. **Bottle photo identification (future)** — user snaps a photo of a bottle label; app identifies the wine, then either (a) shows where to buy it locally (match against `retail_inventory`) or (b) one-tap adds it to saved/cellar. Likely Claude vision on the label image → match to `wines` (name/producer/vintage fuzzy match, or barcode scan as a cheaper first pass). UI needs design collaboration before any build.
27. ⚙️ **Old-World scoring gap (Bordeaux/Rhône) + extraction hallucinations** — measured 2026-07-13: Bordeaux 1,000 wines / 5% Vivino-rated / 27% grapes-empty; Rhône 363 / 2% rated / 35% grapes-empty (+ real hallucinations: a Savoie white and a Prosecco filed under Rhône; Viña Requingua Merlot filed under Bordeaux, fixed). SHIPPED: château+producer gazetteer (deterministic, overrides the model), evidence gate (unevidenced region/sub_region/country → NULL — grape names never determine region), appellation-law blend defaults (left/right bank, GSM, Sauternes), counter few-shots, word-boundary `infer_wine_type` ('Portuguese'≠Port — 28 prod wines still dessert-typed, backfill pending), 'Rhone' alias. REMAINING: re-extraction/validation pass over existing rows (mini — pairs with `docs/mini-agent-tasks.md`), Vivino queue prioritizing unrated Bordeaux/Rhône, optional scorer region-fallback.
28. ✅ **Progressive pick streaming** — fixed the "paragraph sits alone, cards arrive late" gap (measured 6.5s to first text + 4.4s narrative→cards). Three parts: `eager_input_streaming` on the tool (narrative truly streams, first text ~1s), per-pick SSE `pick` events as each object closes (first card ~1.5s after narrative), slim pick schema (model sends only `wine_id`+`why`; name/price/retailer re-attached from candidates). Details: `docs/reference/recommendation.md` (Streaming pipeline).
