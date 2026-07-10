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
