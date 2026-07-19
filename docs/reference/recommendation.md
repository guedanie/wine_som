# Reference — Recommendation Engine

### Zip→Store Radius Lookup
- `/api/recommend` uses `find_nearby_store_ids(zip_code, db, radius_miles=10.0)` — not a hardcoded zip filter
- `backend/utils/geo.py`: `zip_to_centroid` (pgeocode offline dataset) + `haversine` + `find_nearby_store_ids`
- `BaseScraper._upsert_stores` auto-geocodes stores on seed — any new scraper gets it for free
- `retail_inventory` FK to `stores` is **`store_ref`** (UUID), NOT `store_id`
- Two distinct 400s: "don't recognize zip" vs "no stores near you (SA only)"
- Radius is a parameter — exposing it as a user setting is a future enhancement

### Recommendation engine v2.1
- **Tiered candidate pool** — no GrapeMinds hard-gate. Tier 1 = GrapeMinds-enriched
  (`grapeminds_enriched_at` set); Tier 2 = extractor-only (has `varietal` or `region`
  from the Haiku fact extractor). A wine with neither is dropped. Each candidate carries
  a `tier` flag (1 or 2).
- **Knowledge-based deterministic scorer** (`recommendation/scorer.py`, signature
  `score_candidates(intent: dict, candidates: list)`) — maps grape/region → flavor tags
  via `recommendation/flavor_profiles.py` so it can score even Tier-2 wines without
  GrapeMinds structure data. No LLM call in the scorer.
- **Staleness bench** — the inventory fetch excludes rows whose `last_scraped_at`
  is older than `_STALE_INVENTORY_DAYS` (10 — weekly cadence + grace), so a dead
  scraper (Spec's, silent 06-19→07-13) or zombie rows that dropped off a
  retailer's feed can't keep serving old prices. Fails open: if the filter
  empties the pool (e.g. a missed scrape week), it refetches unfiltered and logs
  a warning — stale bottles beat a blank app. Fresh scrapes re-include a
  retailer automatically.
- **Budget = hard window + soft pull toward 0.75×max** — the inventory fetch is a
  hard `[budget_min, budget_max]` filter (frontend sends a fixed $10 floor + the
  slider as ceiling). Inside the window the scorer adds up to `_W_BUDGET=1.0` for
  proximity to `max(budget_min, 0.75×budget_max)` — a $150 budget reads as appetite
  to spend (~$112 target), not "everything under $150 is equal" — while staying a
  tiebreaker (style/type/personalization weights are 2–3×), so a great-value bottle
  still beats a mediocre expensive one.
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
- **Grapes-aware matching (2026-07-14)** — candidate grape sets now union in `varietal`
  (`_norm(wine["varietal"])` folded into `grapes`), symmetric with the existing
  liked-wines path (`_norm_liked`); side effect: avoid-terms now also match against
  varietal text, not just `grapes`/tags. `_BLEND_WANTS = {"red blend": "red", "white
  blend": "white"}` + `_blend_match(want_grapes, wine_type, grapes_col)` boosts any
  same-color wine carrying a 2+ grape array when the intent asks for a "red blend" /
  "white blend" — type-gated so a white blend ask can't match a red wine. Verified
  end-to-end: a "Red Blend" intent over 135 real candidates ranks 5 Bordeaux in the
  top 10 (previously Bordeaux blends with no single dominant grape scored poorly on
  a strict grape-name match).
### Streaming pipeline (2026-07-12)
One forced tool-use call to **Sonnet 4.6**; everything arrives inside the tool's
input JSON in field order: `narrative` → `picks` → `followup_suggestions`.

- **`eager_input_streaming: True`** on `_TOOL` (GA fine-grained tool streaming, no
  beta header) — without it the API buffers `input_json_delta` into coarse chunks,
  so the narrative used to land in one burst after ~6.5s and all picks at once.
  With it: first narrative char ~1s, word-by-word streaming.
- **Per-pick events** — `_PicksScanner` (claude_client.py) incrementally parses the
  picks array and emits `("pick", dict)` the moment each object's closing brace
  arrives, then `("picks", list)` at array close. The router enriches each pick and
  emits an SSE `{"type":"pick","pick":{…}}` — but only if the (already complete)
  narrative names it (`_pick_named_in_narrative`); unnamed picks are held back. The
  final `picks` event stays authoritative: the frontend appends on `pick` (dedupe by
  wine_id) and replaces wholesale on `picks`.
- **Slim pick schema** — the model sends only `wine_id` + `why`; name/price/retailer
  are re-attached from the candidate pool by `_enrich_picks` (they were echoed before,
  ~40% of the picks JSON, pure latency). Consequence: reconcile-to-narrative now runs
  AFTER enrichment, since the name it matches on comes from the candidate.
- If the array never closes (degenerate stream), no `picks` event is emitted and
  `stream_recommendations` falls back to `get_final_message()`'s tool block.
- Measured (5-candidate prompt): first text 1.0s; narrative done 5.2s; cards at
  6.7/7.8/8.6s. Before: first text 6.5s (burst), all cards at 11.0s.

- **Optional NL `message`** — `recommendation/intent.py.parse_message()` (Haiku tool-use)
  turns free text into structured intent, then `merge_intent()` merges it with the
  explicit request fields. Explicit fields win on scalar conflicts; lists (flavors/avoid)
  union. A spoken price cap ("under $20") TIGHTENS the scoring window — `budget_max`
  drops to the stated max (and `budget_min` clamps below it if needed) so the scorer's
  budget pull re-centers on what was asked; it never widens the window since the
  inventory fetch already capped candidates at the slider max. Fail-soft: parse errors
  return `None` and the request proceeds on explicit fields only. The router skips
  parsing the default placeholder message (`"Recommend wines based on my preferences"`).

### Candidate-fetch fix — intent-aware targeted fetch + type gate (2026-07-17)
Live bug: the per-retailer 500-row breadth fetch is unordered/intent-blind, so a
specific ask ("red Bordeaux blend at Lincoln Heights") could get sampled away
before scoring ever saw it — the app wrongly said no match existed.

- **New pure module `recommendation/candidate_filters.py`** (unit-tested,
  `tests/test_candidate_filters.py`): `resolve_wine_type(wine)` infers a NULL
  `wine_type` from varietal → name → first-grape (`utils.infer_wine_type`);
  `apply_type_gate(candidates, requested_types)` resolves NULLs in place then
  hard-drops candidates whose resolved type is known-and-not-requested (keeps
  unresolvable None, fails open); `requested_types_from(chips, parsed)`;
  `detect_store(message, nearby_stores)` (typo-tolerant fuzzy store-name match,
  ignores generic geo/retailer words to dodge false positives); `merge_candidates`
  (dedup by `(wine_id, store_ref)`).
- **Targeted relevance fetch** (`api/routers/recommend.py`) — when the parsed
  intent carries a `region` and/or `detect_store` hits, a small `.limit(300)`
  query (region via `.ilike('wines.region', ...)`, store via `.eq('store_ref', ...)`)
  fetches those exact matches within the 10-mile radius and merges them into the
  pool, bypassing the unordered 500-row sample. Same staleness filter
  (`_STALE_INVENTORY_DAYS`, fail-open) as the breadth fetch.
- **Resolved-type hard gate** replaces the old raw `wine_type` filter — a
  requested type never surfaces a conflicting type, while mis-typed NULL reds
  (e.g. a "Bordeaux Red Wine" with `wine_type=NULL`) resolve to red and are kept.
- **Type-aware breadth fetch** — `INVENTORY_SELECT` switched to `wines!inner(...)`
  + `_apply_type_breadth_filter` constrains the 500-row query to
  requested-type-OR-NULL (chip types only, since parse runs after the fetch; the
  gate folds in the parsed type).
- **Fuzzy store detection + boost** — a named store (typo-tolerant) guarantees
  its matches into the pool and boosts them to the top; never hard-filters.
- **Somm absence-hedging** (`recommendation/claude_client.py`) — hedges absence
  to the surfaced set ("nothing matching turned up nearby") instead of claiming a
  wine/style is absent from a store's full inventory.
- **Verified end-to-end** (DB-level acceptance gate, zip 78209): `detect_store`
  resolves "lincon heights"→Lincoln Heights; targeted fetch + red gate surface 4
  red Bordeaux blends ≤$45 there (incl. a NULL-typed Château Saint-Sulpice) —
  all previously dropped by the 500-sample. Rhône likewise surfaces its
  qualifying red with rosés correctly gated out.

### Country-aware matching + fortified request path (2026-07-19)
- **Country queries** ("white wines from Argentina"): the intent parser has no `country` field, so it stuffs a country into `region`. Wines are stored region=Mendoza / country=Argentina, so a region-only match missed them. Both the targeted fetch (`recommend.py` `_targeted_rows` — `region.ilike OR country.ilike` via postgrest `or_`) and the scorer's region boost (`scorer.py` — the `_W_REGION` condition also credits `_norm(country)`) now match the intent place against region OR country. Fixes the compound country+type gap (previously surfaced only on breadth-sample luck; `white+Argentina`→0).
- **Fortified via dessert**: the intent enum has no `fortified` (only `dessert`), but item 30 retyped Port/Sherry/Madeira to `fortified`. `requested_types_from` (`candidate_filters.py`) folds `fortified` into any request containing `dessert` (one-directional — a `fortified` request stays strict), so Port/Sherry surface under a dessert/after-dinner ask through both the type gate and the type-aware breadth fetch. No intent-enum or frontend-chip change.
