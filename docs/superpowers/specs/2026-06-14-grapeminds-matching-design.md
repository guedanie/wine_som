# GrapeMinds Matching + Enrichment Core — Design

**Date:** 2026-06-14
**Status:** Approved (design)
**Scope:** Confidence-scored, one-to-many GrapeMinds candidate matching + primary enrichment. Retailer-agnostic.

---

## 1. Overview

Upgrade the enrichment pipeline from blind first-hit matching to **confidence-scored, one-to-many** matching. For each wine we:

1. Search GrapeMinds once with the wine's `name` (1 API call) → up to 5 hits. (Discovery testing confirmed GrapeMinds search tolerates noisy retail names like "Decoy Cabernet Sauvignon California Red Wine".)
2. Score and rank each hit with a deterministic rule-based scorer (no API cost).
3. Persist the **top 3** candidates to a new `wine_grapeminds_matches` table (free — the data comes from the one search response).
4. Fetch full detail for the **primary** (rank 1) only, into the existing `wine_details` table, recording its `match_confidence`.

This gives the sommelier agent ranked alternates to reason about, keeps full enrichment to one detail fetch (budget-driven), and exposes a confidence signal so the recommender can hedge on weak matches.

The work operates entirely on the `wines` table, so it is **retailer-agnostic** — it works identically for H-E-B and Geraldine's wines.

---

## 2. Scope

**In scope (A — the matching/enrichment core):**
- New one-to-many candidate table + `wine_details.match_confidence` column.
- Rule-based confidence scorer (pure, testable, retailer-agnostic).
- Pipeline integration (replace `hits[0]` with score → store candidates → enrich primary).
- Effectiveness evaluation harness with CSV-based labeling.

**Out of scope (follow-on specs, schema designed to support them):**
- **(B) Bulk warm-up job** — paid-tier burst prioritizing wines found across multiple retailers.
- **(C) Age-based refresh** — free-tier scheduler re-pulling entries older than ~6 months.
- **LLM-judge** — a future enhancement to re-judge low-confidence matches with Claude.

---

## 3. Data Model

### New table: `wine_grapeminds_matches`

```sql
CREATE TABLE wine_grapeminds_matches (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id       UUID NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
  grapeminds_id TEXT NOT NULL,
  display_name  TEXT,            -- from search hit
  producer_name TEXT,            -- from search hit
  color         TEXT,            -- from search hit
  confidence    NUMERIC(4,3),    -- 0.000–1.000
  rank          INTEGER,         -- 1 = best
  is_primary    BOOLEAN DEFAULT FALSE,
  matched_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (wine_id, grapeminds_id)
);

CREATE INDEX idx_gm_matches_wine    ON wine_grapeminds_matches(wine_id);
CREATE INDEX idx_gm_matches_primary ON wine_grapeminds_matches(wine_id) WHERE is_primary;

ALTER TABLE wine_grapeminds_matches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read gm matches" ON wine_grapeminds_matches FOR SELECT USING (TRUE);
GRANT SELECT ON wine_grapeminds_matches TO anon, authenticated;
GRANT ALL    ON wine_grapeminds_matches TO service_role;
```

`is_primary` is a real BOOLEAN flag (not an emoji — that was display shorthand in design mocks).

### Modify `wine_details`

```sql
ALTER TABLE wine_details ADD COLUMN match_confidence NUMERIC(4,3);
```

### Relationships

- `wines` (1) → `wine_grapeminds_matches` (≤3): ranked candidate summaries.
- `wines` (1) → `wine_details` (1): full enrichment of the **primary** candidate, linked by shared `grapeminds_id`; carries `match_confidence`.
- Only the candidate table stores `display_name`/`producer_name`/`color` for *alternates*. Full tasting/structure/drinking data lives in `wine_details` for the primary only. `region`/`grapes` are **not** stored on candidates because the search response does not include them.
- On a future refresh, if a better primary emerges, flip `is_primary` and re-enrich `wine_details`. The schema already supports this.

---

## 4. Confidence Scoring

The scorer runs on each GrapeMinds **search hit**, where only `display_name`, `producer_name`, and `color` are available (no `grapes`/`region` until the detail fetch). It returns `confidence ∈ [0, 1]`:

```
confidence = producer_score * 0.45
           + color_score    * 0.25
           + name_score      * 0.30
```

Weights and the stopword list (below) are the knobs the effectiveness harness tunes.

### Normalization helper
`normalize(s)` → lowercase, strip punctuation, collapse internal whitespace, trim. Operates on Unicode (preserves accented chars, e.g. "rosé").

### `producer_score` ∈ [0, 1] — GrapeMinds `producer_name` vs `wines.brand`
- `brand` is None → **0.0** (signal unavailable)
- `normalize(brand) == normalize(producer_name)` → **1.0**
- one normalized string contains the other → **0.6**
- otherwise → **Jaccard** of the two token sets

### `color_score` ∈ {0.0, 0.5, 1.0} — GrapeMinds `color` vs `wines.wine_type`
- either side None, or GrapeMinds `color` not in the mapping below → **0.5** (neutral; don't punish missing data)
- mapped color == `wine_type` → **1.0**, else **0.0**
- color mapping: `red→red`, `white→white`, `rosé/rose→rosé`. (Sparkling/dessert/orange/fortified are GrapeMinds `type`/`sub_type`, not `color`, so they fall through to neutral 0.5 — acceptable, the name signal carries them.)

### `name_score` ∈ [0, 1] — token-set similarity (the retailer-agnostic core)
1. Tokenize `normalize(wines.name)` and `normalize(display_name)`.
2. Drop **stopwords**, **size tokens** (`ml`, `l`, and bare numbers like `750`), and **vintage years** (`19xx`/`20xx`).
3. `name_score = Jaccard(remaining_tokens_a, remaining_tokens_b)`.

Stopword list (initial, tunable): generic wine words and geography that add no discriminating power —
`{wine, red, white, rosé, rose, sparkling, blanc, the, de, di}` and countries/regions
`{california, italy, italian, france, french, spain, spanish, argentina, chile, australia, new, zealand, napa, valley, sonoma, county, paso, robles, lodi, marlborough}`.
Distinctive tokens (varietal, producer words, cuvée names) survive — this is where varietal matching effectively happens, and it is identical for both retailers' naming styles.

### Ranking
Sort hits by `confidence` descending (stable sort preserves search order on ties), assign `rank` 1..N, keep the **top 3**, mark `rank == 1` as `is_primary = true`. `confidence` is rounded to 3 decimals.

### Worked example — Decoy (brand "Decoy", type red, name "Decoy Cabernet Sauvignon California Red Wine")

| candidate | producer | color | name | confidence |
|---|---|---|---|---|
| Decoy, Cabernet Sauvignon | 1.0×.45 | 1×.25 | ~0.9×.30 | ≈0.97 |
| Decoy, Cabernet Sauvignon, Sonoma County | 1.0×.45 | 1×.25 | ~0.75×.30 | ≈0.93 |
| Duckhorn Vineyards, Decoy Cabernet Sauvignon, Sonoma County | 0.6×.45 | 1×.25 | ~0.7×.30 | ≈0.73 |

---

## 5. Enrichment Flow (pipeline integration)

`enrich_wine` in `enrichment/pipeline.py` keeps its shape and the two-step warm-up; only the matching middle changes.

```
enrich_wine(wine_row, force=False)
  1. Guard: is_already_enriched(wine_id) and not force → return source="cached"
  2. hits = gm.search(wine_row["name"], limit=5)   (full scraped name; retailer-agnostic)
     if not hits → return source="not_found"  (no rows written)
  3. scored = score_candidates(hits, brand, wine_type, name)   [matching/scorer.py, pure]
     top3   = scored[:3]
  4. persist_candidates(wine_id, top3):
       DELETE existing rows for wine_id, INSERT top3 (rank, is_primary, matched_at)
  5. primary = top3[0]
     enrich primary into wine_details via existing get_wine + warm-up + get_drinking_period
     write wine_details.match_confidence = primary.confidence
```

- Candidates are persisted **before** the detail fetch, so they survive even if the primary's content is still generating (warm-up returns nulls → partial `wine_details` + 60s refetch, unchanged).
- `is_already_enriched` (checks `grapeminds_enriched_at`) still guards re-work.
- The scorer is a **pure module** (`enrichment/matching/scorer.py`) — no I/O, like `recommendation/scorer.py`.

---

## 6. Effectiveness Evaluation Harness

Two layers: deterministic unit tests for correctness (Section 8) and a measured offline eval for **quality**.

### Gold set
A **stratified ~50-wine sample** drawn from the `wines` table joined to `retail_inventory`:
- H-E-B mainstream (Decoy, Meiomi, Josh Cellars, …) — expect high match
- Geraldine's natural/obscure — expect low match / often absent from GrapeMinds
- spread across red/white/sparkling/rosé

Sampling is deterministic (fixed random seed) so runs are reproducible.

### Workflow

```
fetch_eval_searches.py
   • selects the ~50-wine stratified sample
   • 1 GrapeMinds search per wine (~50 calls, run ONCE)
   • caches raw hits → eval/eval_searches.json
   • runs the scorer and writes eval/eval_candidates.csv for labeling

  → USER labels eval/eval_candidates.csv in Excel/Sheets (the `correct` column)

run_eval.py
   • reads the labeled CSV + cached hits
   • computes metrics (re-runnable offline for free while tuning weights)
   • writes eval/eval_report.md
```

Caching is the key move: ~50 search calls spent once, then weight/stopword tuning iterates offline at zero cost.

### Labeling CSV (`eval_candidates.csv`)

One row per (wine, candidate), grouped by wine, sorted by rank. The user fills the **`correct`** column with `1` on the single row that is the true match for that wine, or leaves all of a wine's rows blank if no candidate is correct. Wines with zero search hits appear as a single row with empty GrapeMinds fields and `gm_display_name = "NO_HITS"`.

| column | meaning |
|---|---|
| `wine_id` | FK (groups candidate rows) |
| `wine_name`, `brand`, `wine_type`, `source` | the wine under test |
| `rank` | 1..N from our scorer |
| `grapeminds_id` | candidate id |
| `gm_display_name`, `gm_producer`, `gm_color` | candidate summary (from search) |
| `confidence` | our score |
| `is_primary` | TRUE on rank 1 |
| `correct` | **user-filled**: `1` on the true match, else blank |

Interpretation on re-import:
- A wine with `correct=1` on its `is_primary` row → **precision@1 hit**.
- A wine with `correct=1` on any of its rows → **top-3 recall hit**.
- A wine with all rows blank → **no correct GrapeMinds match exists** (counts against coverage, not precision).

### Metrics (overall + per-retailer)

| Metric | Definition |
|---|---|
| **Coverage** | fraction of eval wines that have any correct GrapeMinds match (`correct=1` somewhere) |
| **Precision@1** | among wines with coverage, fraction whose `is_primary` row is the `correct` one |
| **Top-3 recall** | among wines with coverage, fraction with `correct=1` on any retained row |
| **Confidence calibration** | bucket by primary confidence (≥0.8 / 0.5–0.8 / <0.5); correctness rate per bucket |

### Success criteria (bar to clear before trusting the method)
- Precision@1 ≥ **0.85** on high-confidence (≥0.7) picks.
- Top-3 recall ≥ **0.95** where a correct match exists.
- Confidence is **monotonic** (higher bucket ⇒ higher correctness) — validates `match_confidence` as a hedging signal and identifies where an LLM-judge would pay off (the muddy <0.5 bucket).
- Per-retailer coverage **documented** in the report (e.g., "naturals: ~40% coverage"), so the method's real limits are known.

### Sequencing
Build **scorer + eval harness first**, run it, tune weights against the labeled gold set, **then** wire persistence + pipeline integration. We validate the method on real data before writing matches for ~2,200 wines.

---

## 7. Error Handling & Edge Cases

| Case | Behavior |
|---|---|
| No search hits | Write no candidate rows, no `wine_details`; return `source="not_found"`. Wine stays un-enriched (retry cadence is a follow-on refresh concern). |
| Hits exist but all low-confidence | Still enrich rank 1; store its `match_confidence`. No skip branch. |
| Primary detail returns nulls (generating) | Candidates persisted already (from search); `wine_details` partial → 60s → refetch (existing warm-up). |
| Re-run / `force=True` | Delete this wine's candidate rows, re-score, re-insert. Idempotent; primary may change; `wine_details` re-enriched. |
| Duplicate `grapeminds_id` in hits | `UNIQUE(wine_id, grapeminds_id)` + defensive dedupe before insert. |
| Null `brand` | `producer_score = 0.0`; name + color still score. |
| Null `wine_type` or unmapped `color` | `color_score = 0.5` (neutral). |
| Candidate-persist DB error | Log and continue to primary enrichment (best-effort; candidates are supplementary). Primary enrichment failure propagates as today. |

---

## 8. Testing

1. **Scorer unit tests** (`test_matching_scorer.py`) — deterministic, no API. Fixtures in both retailers' name styles: exact/contains/token producer matches; color match & mismatch & null; name stopword/size/vintage stripping; ranking + top-3 + single `is_primary`; null brand; ties; zero/one hit.
2. **Effectiveness eval** (Section 6) — offline, against cached real search responses + labeled CSV. Not CI; run manually to validate and tune. Produces `eval_report.md`.
3. **Pipeline integration tests** (`test_pipeline_matching.py`) — mocked `GrapeMindsClient`. Verify: top-3 candidate persistence, `is_primary`/rank correctness, primary enrichment into `wine_details`, `match_confidence` written, idempotency on re-run (`force`), `not_found` path writes nothing.

---

## 9. Components / File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260614000001_grapeminds_matches.sql` | Create | New table + `wine_details.match_confidence` + RLS/grants |
| `backend/enrichment/matching/__init__.py` | Create | Package marker |
| `backend/enrichment/matching/scorer.py` | Create | Pure rule-based scorer (`score_candidates`, normalization, stopwords) |
| `backend/enrichment/pipeline.py` | Modify | Integrate scoring; persist candidates; enrich primary; write `match_confidence` |
| `backend/enrichment/matching/eval/fetch_eval_searches.py` | Create | Sample gold set, cache searches, emit `eval_candidates.csv` |
| `backend/enrichment/matching/eval/run_eval.py` | Create | Read labeled CSV, compute metrics, write `eval_report.md` |
| `backend/tests/test_matching_scorer.py` | Create | Scorer unit tests |
| `backend/tests/test_pipeline_matching.py` | Create | Pipeline integration tests (mocked GrapeMinds) |

Eval artifacts (`eval_searches.json`, `eval_candidates.csv`, `eval_report.md`) live under `backend/enrichment/matching/eval/` and are git-ignored (data, not code).

---

## 10. Out of Scope / Future

- **LLM-judge** for low-confidence (<0.5) matches — a targeted Claude call to re-pick among candidates; informed by the calibration results.
- **(B) Bulk warm-up** — paid-tier burst; prioritize wines whose **real** UPC appears across multiple retailers (note: Geraldine's UPCs are synthetic `shopify-geraldines-*`, so cross-retailer matching keys off real UPCs only).
- **(C) Age-based refresh** — re-pull entries whose `matched_at` / `grapeminds_enriched_at` is older than ~6 months, budgeted under the free tier's 250/month.
