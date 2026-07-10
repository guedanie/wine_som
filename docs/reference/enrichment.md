# Reference — Enrichment

Layered enrichment: retailer data → Vivino → local LLM → deterministic structure table. Mac mini runbook: `docs/mac-mini-enrichment-server.md`.

## GrapeMinds API
- Auth: `Authorization: Bearer <key>` — `X-API-Key` does NOT work
- Cloudflare blocks Python urllib/requests — must call via `subprocess curl`
- First request for a wine triggers async content generation (returns nulls)
- Re-fetch after ~60s for populated tasting notes, structure profile
- Monthly budget: 250 calls — always check `grapeminds_enriched_at` before calling
- `structure_profile` is 1-10 scale: `sweetness, acidity, tannins, alcohol, body, finish`

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
- **⚠️ Known observability issue — malformed UUIDs from qwen2.5:7b** (spotted during initial 2026-07-09 drain, ~1 in 15 batches). The runner asks the model to echo `wine_id` alongside extracted facts (`ollama_extractor.py:75`) and then trusts that id for the UPDATE (`run_extraction.py:70`). Qwen sometimes corrupts a character (`e86g` — `g` is not hex, embedded space, extra digit). **Not corrupting source of truth today**: Postgres rejects the malformed UUID with `22P02` and no write occurs → the wine stays NULL and gets picked up on the next `--null-only` run. **But the design is fragile** — if qwen ever returns a *valid-but-swapped* UUID (a real id belonging to a different wine in the batch), we'd silently write A's facts onto B with zero error. Fix path: match by batch position instead of trusting the model's echo, or validate the echoed id is in the input batch before UPDATE. Monitor via `grep "write failed for" /tmp/extraction.log` (drain) or `~/Library/Logs/somm-extraction.log` (weekly).
