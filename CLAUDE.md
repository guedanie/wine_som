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

- **Retail data** — 11 scrapers live (H-E-B, Central Market, Spec's, Kroger, Harris Teeter, Twin Liquors, Pogo's, Geraldine's, AOC, US Natural Wine, Antonelli's, Harvest) across TX/TN/NC. Weekly GitHub cron runs 9; **Spec's + Twin Liquors + Vivino + local-LLM extraction run on the residential-IP Mac mini** (datacenter IPs are Cloudflare/Vivino-blocked; Spec's silently blocked since 2026-07-01 — moved to the mini 2026-07-13). `scripts/verify_scrape_runs.py` runs after the weekly cron and flips silent-zero "successes" to failed + Slack-alerts. `scrapers/base.py` upserts retry on Postgres deadlock/serialization codes (`40P01`/`40001`, 4× backoff) — added after the mini Spec's run overlapped the GitHub scrape and deadlocked. Details: `docs/reference/scrapers.md`, `docs/mac-mini-enrichment-server.md`.
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
12. ✅→⚙️ **Blend structure/sweetness LLM pass** — code landed + pushed 2026-07-19; full drain running overnight. `scripts/backfill_structure_llm.py` (qwen2.5:7b on the mini) fills the two gaps the deterministic grape table can't: LLM-inferred `sweetness` MERGED onto the ~17.5k profiles that lack it (body/tannins/acidity untouched — table/Vivino/GrapeMinds stay authoritative; marked `sweetness_source:'llm'`), and full 4-axis profiles for the ~3,400 unanchored blends the table can't map (`source:'llm'`). Precedence `vivino/grapeminds > table > llm`: `structure_to_persist` refreshes an llm profile from the table once grapes arrive, keeping the llm sweetness. Non-wine guard (shared `_is_non_wine` with the wine_type backfill) keeps sake/food out; echo-id validation drops qwen's malformed-UUID rows (idempotent — re-fetched next pass). Weekly extraction LaunchAgent chain runs it incrementally (`--limit 500`). Spot-check quality excellent (Apothic Red/Tawny Port/Sweet Muscadine sweetness spot-on, dry reds/Champagne=1). REMAINING: the ~21k drain finishing (sweetness coverage 6%→~90% expected) + final-number docs; optional cleanup pass for the ~17% blend malformed-UUID drops.
13. ✅→⚙️ **Extraction pass on new Nashville/NC/Dallas wines** — mostly done by the weekly mini job (varietal-null 2026-07-13: Harvest 4%, Harris Teeter 10%, Kroger 12% — vs H-E-B baseline 2%). REMAINING: **Pogo's Dallas residue** — 36% varietal-null, ~15% missing BOTH varietal+region (invisible to the recommender). These are extraction *failures*, not backlog (obscure fine-wine labels with no grape/region in the name — the 07-10 drain already tried them); re-running `--null-only` won't help. Fix path: Vivino matching from the mini (knows producers by name) — prioritize both-null wines in its queue. Matters for the Dallas push. **Queue prioritization landed 2026-07-14** (item 27): `run_vivino_sample.py` now fills each run's `VIVINO_LIMIT` (300/run on the mini) in tiers — both-null first, then un-enriched Bordeaux/Rhône, then the rest — so Pogo's residue drains at the weekly cadence.
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
27. ✅ **Old-World scoring gap (Bordeaux/Rhône) + extraction hallucinations** — gazetteer + evidence gate + appellation-law blend defaults shipped 2026-07-13; the backfills + both residue sweeps landed 2026-07-14 from the mini (details: `docs/mini-agent-tasks.md` Task 3). Regions are now clean: Portuguese retype done, Rhône fragments normalized, `scripts/revalidate_regions.py` applied 2,195 positive fixes, Rhône residue 72→0 real errors (15 hand-fixed), Bordeaux residue 151→73 all-genuine (71 hand-fixed incl. a DRC La Tâche); gazetteer hardened (conflict guards, single-word château needles need a Chateau word, 'St.'→Saint folding, Bdx/CdR shorthand). **Bulk NULLING stays deferred** — the gate would null 3,804 mostly-correct producer-knowledge regions (Grgich Hills→Napa class). **Grapes backfill DONE 2026-07-14**: `default_grapes_for()` is now color-aware (gated by `wine_type`; dual-color appellations like Graves/Pessac-Léognan/Hermitage require an explicit type) with an expanded table (right-bank satellites, northern-Rhône crus, Condrieu Viognier, Tavel rosé) plus red-only region-level fallback (`default_grapes_for_region`); `scripts/backfill_grapes.py` filled 375 of 491 grapes-empty Bordeaux/Rhône rows (34 trusted varietals, 326 appellation blends, 15 region-level) — Bordeaux grapes-empty 33%→7.4%, Rhône 36%→9.7%; 116 left for Vivino (unknown-type Pessac-Léognan, legit rosés/whites in red appellations, long-tail appellations). Vivino queue now prioritizes both-null wines → un-enriched Bordeaux/Rhône → rest, and may replace a law-default blend with real Vivino grapes (multi-grape defaults only, never a single scraped/inferred grape). **Law-regions extension DONE 2026-07-15**: `_REGION_DEFAULT_RULES` extended color-aware to 6 regions (Champagne, Douro, Penedès, Provence rosé, on top of Bordeaux/Rhône red) plus new appellations (Sangiovese DOCGs, Carmignano, Cava, Bandol, Blanc de Blancs), governed by the standing conservative rule (hard law + explicitly-approved conventions only — Bolgheri/Madeira/Cassis/Tuscany-region deliberately excluded, White Port name-guarded off the red Douro trio). Production backfill filled 356 of 628 grapes-empty law-region rows; catalog-wide grapes-empty now 22.7% (was 24.5%). REMAINING: optional scorer region-fallback only.
28. ✅ **Progressive pick streaming** — fixed the "paragraph sits alone, cards arrive late" gap (measured 6.5s to first text + 4.4s narrative→cards). Three parts: `eager_input_streaming` on the tool (narrative truly streams, first text ~1s), per-pick SSE `pick` events as each object closes (first card ~1.5s after narrative), slim pick schema (model sends only `wine_id`+`why`; name/price/retailer re-attached from candidates). Details: `docs/reference/recommendation.md` (Streaming pipeline).
29. ✅ **Candidate-fetch fix — intent-aware targeted fetch + type gate** — fixed the unordered/intent-blind 500-row breadth fetch dropping matches before scoring (e.g. "Bordeaux blend at Lincoln Heights" wrongly read as no match). Targeted region/store fetch merges into the pool, resolved-type hard gate (`candidate_filters.py`) replaces the raw wine_type filter, fuzzy `detect_store` boosts named-store matches. Verified end-to-end for Bordeaux + Rhône. Details: `docs/reference/recommendation.md`.
30. ✅ **NULL-`wine_type` backfill** — landed 2026-07-18, same shape as the grapes backfill (item 27). `infer_wine_type` hardened (`utils/__init__.py`): NFKD accent-fold (`_fold`) resolves accented varietals (Mourvèdre, Grüner Veltliner); grape vocabulary synced to every `reference.CORE_GRAPES` entry with a drift-guard test; sparkling method terms added (Pet Nat, Col Fondo, Franciacorta, Lambrusco — fixes "Zinfandel Pet Nat" misreading red), over-broad "ancestral" token dropped; **Port/Sherry/Madeira now type `fortified` not `dessert`** (`FORTIFIED_TERMS` checked before `DESSERT_TERMS`, both `infer_wine_type` and `wine_type_for_appellation` agree — true dessert wines Sauternes/ice wine unaffected). New `wine_type_for_appellation(region, sub_region)` (`reference.py`): curated single-color/style appellation map (Chablis→white, Champagne→sparkling, Brunello→red, Sauternes→dessert, Port/Sherry→fortified); multi-color places (Burgundy villages, Bordeaux communes, bare regions) deliberately excluded. `scripts/backfill_wine_type.py`: fill-only precedence varietal→name→first-grape→appellation, plus a non-wine guard (`_is_non_wine`) skipping grocery/beverage catalog noise (sake, cocktails, cider, maple syrup) so it stays NULL instead of mistyped. **Live run**: 3,528 of 5,443 NULL-type wines filled (2,311 red, 996 white, 121 sparkling, 46 fortified, 26 rosé, 24 orange, 4 dessert) — catalog wine_type-NULL 27.5%→9.7%. Remainder (~1,915): signal-less producer-only listings → Vivino/LLM territory; non-wine catalog noise → item 32 purge. Fast suite 558→579 passing.
31. ✅ **Name-directed full-inventory fallback** — landed 2026-07-19. `wine_name` added to the Haiku `wine_intent` parse; `deep_fetch_reason` fires a deep fetch when a bottle is named OR when a concrete grape/region/type ask went unmet by the random-500 breadth sample. Named mode searches the full nearby inventory by `wines.name ilike` (budget IGNORED — a lookup shouldn't be hidden by the slider), ranks all-token matches first (`rank_name_matches`), and pins up to 3 to the front (`pin_named_matches`); weak-pool mode re-fetches by grape (jsonb `grapes.cs.[...]`) or region honoring budget. The deep fetch + Claude call moved INSIDE the SSE generator behind a themed `status` frame ("Looking deeper into the cellar…"), so the message only shows when we actually dig and the common request is untouched. Narrative confirms the found bottle or hedges when it's not stocked. Pure helpers in `candidate_filters.py` (tokenize/rank/reason/pin) unit-tested; acceptance `scripts/verify_name_fallback.py`.
32. **Purge irrelevant inventory** — grocery scrapers (H-E-B/CM) pull non-wine catalog noise into `wines`: fruit cocktail, pancake mix, sake, peach slices, cookies & cream, soda (surfaced during item 30's wine_type audit — ~462 of the untypeable NULL-`wine_type` rows are non-wine). A deterministic purge pass (name/category-based non-wine detection → soft-delete or exclude from `wines`/recommendation) would clean stats and stop junk reaching the recommender. Design the detection conservatively (never drop a real wine).
33. ✅ **Recommender country + fortified fixes** — landed 2026-07-19. A 78209 capability sweep (structural axes: type/region/country/grape/price/compound) found two gaps: (a) fortified wines unreachable via a typed request (enum has no `fortified`, only `dessert` — item 30 retyped Port/Sherry to fortified); (b) compound country+type queries surfaced on breadth-sample luck (fetch+scorer were country-blind; `white+Argentina`→0). Fixed: `requested_types_from` folds `fortified` into a `dessert` request (one-directional); the targeted fetch (`recommend.py`) and the scorer region boost (`scorer.py`) now match the intent place against region OR country (the parser stuffs a country into the `region` field). Verified end-to-end at 78209: white+Argentina 0→27 (top-ranked), dessert requests keep both Port and Sauternes, no type+region regression. **Second capability sweep DONE 2026-07-20** (soft axes flavor/avoid/body): `avoid` was the one broken hard-exclusion path — rework landed. `wine_excluded_by_avoid` (scorer.py) is now type-aware (conservative term→wine_type map: sparkling/bubbles/champagne→sparkling, port/sherry/madeira→fortified, red/white/rosé, dessert, orange-wine/skin-contact phrases) excluding by *resolved* wine_type, with word-boundary matching over structured fields (varietal/name/grapes/region/country/flavor-tags/real-tasting_notes) — no metadata, no raw substring. Measured fixes (8k sample): "no sparkling" leaked 57%→0, "nothing fortified" 93%→0, "no dessert" 59%→0, avoid "port"→Portugal 41 false-positives→0, avoid "red" 3,616 red-fruit over-matches→0 (correctly excludes 3,127/3,127 reds). Also dropped the 100%-metadata `flavor_profile` (tokens like `PWSMigration`/`Location_SanAntonio`/`review-92plus`; `tasting_notes` 100% empty) from the flavor kw-scoring path — was producing phantom flavor matches. Body axis healthy (88% resolvable) — untouched. DEFERRED to item 34: the flavor-axis coverage gap.

34. **Flavor-axis coverage gap** — surfaced by capability sweep #2 (item 33). Two compounding problems make flavor/style requests weaker than they look: (a) **28% of the catalog is flavor-invisible** — `flavor_tags_for` derives tags only from a curated grape+region map (`flavor_profiles.py`), so any wine whose grape/region isn't in the map gets ZERO tags (incl. 363 reds in a 6k sample); (b) the intent parser clamps `flavors` to a **15-word vocab** (`FLAVOR_VOCAB`), so common asks — buttery, oaky, smoky, jammy, mineral, floral, citrus, tropical, creamy — are silently dropped before scoring. The keyword-hit fallback can't rescue this because `tasting_notes` is 100% empty and `flavor_profile` is 100% metadata (item 33 dropped it from scoring). Fix is data/enrichment, not a scorer tweak: expand the grape/region tag map coverage AND/OR the parser vocab (with matching tags so a new vocab word can actually match something), and/or enrich real flavor descriptors into `tasting_notes` via the mini's LLM pass. Design conservatively per the standing rule — a flavor tag asserted about a wine must be defensible, not guessed.
