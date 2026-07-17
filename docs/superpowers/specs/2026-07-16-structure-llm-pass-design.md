# Blend Structure / Sweetness LLM Pass — Design (CLAUDE.md item 12)

**Date:** 2026-07-16 · **Status:** approved design, pre-implementation
**Prior art:** `enrichment/extraction/structure_benchmark.py` (2026-07-05 benchmark: qwen2.5:7b sweetness 86% within ±1 — its one strong axis; tannin 59% / acidity 22% — the table wins those; hybrid marginally best overall).

## Problem

Measured 2026-07-16 (19,732 wines):

- 17,339 have `wine_details.structure_profile` (12,485 table · 3,879 GrapeMinds/real · 975 Vivino) — but only **887 include `sweetness`** (4.5% of the catalog). The taste-profile interview already captures a dry/off-dry/sweet preference and the Somm's pick context already consumes `sweetness` when present — the preference can't bite without the data.
- **916 wines** carry grape data the table can't anchor (multi-grape blends outside the ~55-grape table) → no structure at all → no body resolution in the scorer.
- (2,393 total lack structure; 205 became table-anchorable this week and Sunday's `persist_structure` picks them up automatically; 1,272 have no grape data — Vivino-queue territory, out of scope here.)

## Decisions (user-approved)

1. **Gaps only** — no whole-catalog ±2 LLM refinement of table profiles (marginal benchmark gain, large weekly compute; revisit later if wanted).
2. **LLM sweetness everywhere** — one uniform pass over all profile classes including reds (user chose this over a deterministic-reds split; the benchmark prompt already encodes "1 = bone dry (most reds)").
3. **Data-only** — no scorer changes this pass; mechanical sweetness matching joins the item-25 personalization batch.

## Design

### Work classes (one runner, two eligibility sets)

1. **Sweetness fill** (~16,452 wines): has a `structure_profile`, `sweetness` is absent/None. LLM infers sweetness ONLY; the integer is merged into the existing profile dict — body/tannins/acidity are never touched. Applies additively to `table`, `vivino`, and GrapeMinds profiles alike (adding a missing key does not violate "real data wins"). Provenance: set `"sweetness_source": "llm"` unless the profile's own `source` is already `llm`.
2. **Unanchored blends** (916 wines): has grapes and/or varietal, `structure_for(...)` returns None, no existing profile. LLM produces the full `{body, tannins, acidity, sweetness}`, written with `source: "llm"` (insert or fill-empty only).

### Precedence (explicit, one code change)

`vivino / grapeminds > table > llm`. `scripts/persist_structure.py` gains one rule: when the table can NOW anchor a wine whose profile has `source: "llm"`, the table overwrites the llm body/tannins/acidity (keeping the llm `sweetness` and marking `sweetness_source: "llm"`) — the benchmark says the table is strictly better on tannin/acidity, so llm profiles must not fossilize once grapes arrive. Vivino/GrapeMinds profiles remain untouchable by both table and llm (existing behavior).

### Runner — `scripts/backfill_structure_llm.py`

Mirrors the `run_extraction` / `backfill_grapes` patterns:

- Pure planning core (TDD): eligibility selection (`needs_sweetness(row)` / `needs_full_profile(row)`), merge logic (`merge_sweetness(profile, n)`), and response validation, all free of I/O.
- Ollama calls reuse `structure_benchmark.py`'s tuned `_PROMPT` and its `_call_ollama`-style plumbing (qwen2.5:7b, `format:"json"`, temp 0, batch=8; two-mode prompt: sweetness-only for class 1, full-structure for class 2).
- **Echo-id validation** (lesson from the known qwen malformed-UUID fragility): a returned `wine_id` must be a member of the input batch; anything else is dropped and counted (`bad_id` stat), never written. This also kills the valid-but-swapped-UUID silent-corruption risk for this runner.
- Values clamped to integers 1–10; out-of-range → dropped and counted, not coerced silently.
- `--dry-run`, `--limit N`, paged fetch, idempotent (eligibility re-check excludes anything already filled), per-class counts, Slack summary, and a `scraper_runs` row (`retailer_name="Structure LLM (local qwen)"`) like the extraction job so `verify_scrape_runs.py` can see it.

### Weekly integration

One new step appended to the mini's extraction LaunchAgent chain (`run_extraction_launchd.sh`): extraction → `persist_structure` → `backfill_structure_llm --limit 500` (incremental; weekly volume is only newly scraped/extracted wines).

## Testing

- TDD the pure core: eligibility for both classes (incl. "already has sweetness" and "vivino profile gains sweetness additively"), merge never touches other keys, `sweetness_source` marking, echo-id validation drops foreign/malformed ids, clamping drops out-of-range, persist_structure's new table-over-llm rule (keeps llm sweetness).
- Ollama calls mocked in unit tests (existing `test_extractor_backend.py` pattern).
- **Acceptance gate before the full drain:** bounded live run (~50 wines) with spot checks (Moscato/Port high, Napa Cab 1–2, demi-sec Vouvray mid), then re-run `structure_benchmark.py` against Vivino ground truth — sweetness must hold ≥ ~86% within ±1 and body/tannin/acidity must not regress (the merge path can't touch them, so this guards the full-profile class).

## Rollout

1. Land code + tests; fast suite green.
2. Bounded live run + spot checks + benchmark gate (above).
3. Full drain from the mini in chunks (`--limit 2000` × ~9 runs, background like the 07-10 extraction drain; ~17k short prompts ≈ a few hours of qwen).
4. Verify: sweetness coverage 4.5% → ≥90% of profiled wines; structure coverage 88% → ~93%; Slack summaries per chunk.
5. Docs: CLAUDE.md item 12 → ✅ with numbers; `docs/reference/enrichment.md` structure section; `docs/mini-agent-tasks.md` run record; LaunchAgent chain note in `docs/mac-mini-enrichment-server.md`.

## Out of scope

- Scorer/mechanical sweetness matching (item 25 batch).
- Whole-catalog ±2 refinement of table profiles.
- The 1,272 no-grape-data wines (Vivino queue) and 205 now-anchorable wines (Sunday's persist run).
- GrapeMinds spend (untouched).
