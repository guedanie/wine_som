# Somm — Wine Recommendation App

## What This Is
Full-stack wine recommendation app. Users enter zip code + budget + style preferences and get Claude-powered sommelier recommendations for wines available at local retailers near them. (Public overview: `README.md`. Frontend design system: `frontend/CLAUDE.md`.)

**LIVE (private beta since 2026-07-05):** frontend `wine-som-pkwz-chi.vercel.app` (Vercel) + backend `winesom-production.up.railway.app` (Railway) + Supabase. Installable PWA. Testers in San Antonio, Austin, Nashville, Charlotte + Winston-Salem NC; Dallas focus coming.

## Tech Stack
- **Database + Auth**: Supabase (cloud project `knpldhksfsetujbcfrsj`)
- **Backend**: Python 3.9, FastAPI, supabase-py
- **Frontend**: React 19 + Vite + Tailwind v3 (desktop + mobile/PWA)
- **AI**: Anthropic Claude (Haiku — recommendations + fact extraction)
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

- **Retail data** — 11 scrapers live (H-E-B, Central Market, Spec's, Kroger, Harris Teeter, Twin Liquors, Pogo's, Geraldine's, AOC, US Natural Wine, Antonelli's, Harvest) across TX/TN/NC. Weekly GitHub cron runs 10; **Twin Liquors + Vivino + local-LLM extraction run on the residential-IP Mac mini** (datacenter IPs are Cloudflare/Vivino-blocked). Details: `docs/reference/scrapers.md`, `docs/mac-mini-enrichment-server.md`.
- **Enrichment** — layered: retailer data → Vivino (ratings/facts/image) → local LLM (qwen2.5:7b, Haiku-parity) → deterministic grape+region structure table. Details: `docs/reference/enrichment.md`.
- **Recommendation** — deterministic knowledge-based scorer shortlists; Claude (Haiku) picks + narrates. Personalization (saved + cellar + 👍/👎 votes + taste-profile interview) re-ranks and is cited. Details: `docs/reference/recommendation.md`.
- **Frontend** — React SPA + installable PWA; anonymous-first with optional magic-link accounts (saved bottles, cellar, taste profile). Design system: `frontend/CLAUDE.md`.
- **Blocked retailers** — Total Wine (Imperva), Whole Foods (Amazon auth), Publix/Costco/Trader Joe's (Akamai), Food Lion (Cloudflare), Tom Thumb/Albertsons (Incapsula), Corkdorks/Frugal MacDoogal (City Hive auth — may be unblockable via the Twin Liquors bypass).

## Reference docs
These hold the deep detail moved out of this file — **consult the relevant one on demand when a task touches that system; don't read them preemptively.** The inline "Details: …" pointers above tell you which applies.

- `docs/reference/scrapers.md` — per-retailer API notes, UPC dedup, seeding commands
- `docs/reference/enrichment.md` — GrapeMinds, Vivino, local LLM, structure table
- `docs/reference/recommendation.md` — scorer, personalization, intent, zip→store
- `docs/reference/build-log.md` — full component status table + file map
- `docs/mac-mini-enrichment-server.md` — the residential-IP enrichment runbook
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

11. **Local LLM extraction cutover** — ⚙️ in flight: `EXTRACTOR_BACKEND=ollama` on the mini's weekly launchd; initial 5,516-wine backlog drain running (watcher chains `persist_structure.py`). REMAINING: once steady-state confirmed, drop Haiku from `weekly-scrape.yml` (capped 1500/run as fallback meanwhile).
12. **Blend structure/sweetness LLM pass** — table→LLM hybrid for the ~3% of blends the table can't anchor + LLM sweetness.
13. **Extraction pass on new Nashville/NC/Dallas wines** — `--null-only` to make them recommendable (also grows structure coverage).
14. ✅ **User accounts Phases 0–3** — magic-link auth, saved favorites, mobile account home, cellar (drinking windows + drank-rating), taste-profile interview. REMAINING: **Phase 4 price-alert watches** (`price_watches` + notifier). Roadmap: `docs/user-accounts-roadmap.md`.
15. ✅ **Feedback-as-scoring-signal** — votes carry `user_id` + RLS read; `buildTasteContext` folds 👍→liked / 👎→disliked; scorer boosts/penalizes. Niche remaining: merge anon session votes on sign-in (needs backend JWT verify).
16. **Price alerts + promo** — ⚙️ Phase 1 done (`price_history` + delta trigger). REMAINING: `price_watches` + notifier (depends on accounts).
17. ✅ **Ratings badge** in WineCard + mobile pick messages.
18. **Per-pick distance** — add store→zip distance to the Option C store pill.
19. **Analytics** — ⚙️ foundation shipped; PostHog live in Vercel.
20. **Kroger banner expansion** — Memphis/Houston/other NC-VA cities (config-only via `MARKETS`).
21. Local MCP server for Claude Desktop (parked — memory `mcp-desktop-parked`).
22. More Shopify wine shops (zero new code) · enumerate full ~90 Twin Liquors stores.
23. Blocked probes (headless-browser only): Total Wine, WFM, Publix, Food Lion, Tom Thumb/Albertsons.
24. ✅ **Twin Liquors scraper** — live on the mini (Sun 04:00 CT). GitHub IPs Cloudflare-blocked. **Reusable: the api_key + client_origin bypass likely unblocks Corkdorks / Frugal MacDoogal (Nashville).**
25. **Personalization follow-ons (parked)** — anon-vote merge; `similar_to` badge in pick UI; consumed-cellar as taste signal; profile avoids as mechanical scorer penalties; smarter top-10 for the "[Your wines]" block.
