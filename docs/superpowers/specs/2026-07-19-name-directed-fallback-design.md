# Item 31 — Name-Directed Full-Inventory Fallback (Design)

**Date:** 2026-07-19
**Roadmap item:** 31

## Problem

The recommend endpoint's breadth fetch (`_fetch_rows` in `api/routers/recommend.py`)
pulls an arbitrary 500 rows per retailer filtered only by price + wine_type + in_stock
— **no `.order()`, no grape/name/region filter.** It is effectively a random 500-row
slice of each retailer's in-budget inventory. The item-29 targeted fetch
(`_targeted_rows`) patches this for **region** and **detected store**, but nothing keys
on a **wine name** or **grape**, and the intent parser (`wine_intent` tool) has **no
field for a named bottle** at all.

Consequences:
- "Do you have Opus One?" produces no usable name signal; the name only reaches
  `detect_store` / `_detect_retailer` (store/retailer matching). A specifically-named
  bottle that isn't in the random 500 is invisible — Somm claims it isn't carried.
- A concrete grape/region ask that the random 500 happened to miss (e.g. the store
  carries 3 Chenin Blancs but none landed in the sample) surfaces nothing relevant.

## Goal

When a user names a specific bottle, **or** when the breadth sample provably missed a
concrete constraint the user expressed, run a scoped query against the *entire*
zip-scoped nearby-store inventory instead of the 500-sample — and show the user a
themed progress message while we do it.

## Design

### 1. Intent — capture the named bottle

Add a `wine_name` field to the `wine_intent` tool in `recommendation/intent.py`:

- Schema: `"wine_name": {"type": ["string", "null"]}` (not in `required`).
- System-prompt line: instruct Haiku to populate `wine_name` with a specific
  producer/bottle the user named (e.g. "Caymus Special Selection", "Opus One") and
  leave it null for generic style asks.
- `merge_intent`: thread `wine_name` as a parsed-only scalar —
  `out["wine_name"] = out.get("wine_name") or parsed.get("wine_name")`. There is no
  explicit-request equivalent, so `intent_from_request` sets `wine_name: None`.

No new model call — the parse already runs on the message.

### 2. The deep fetch (two modes, one entry point)

A new fetch that hits the full `nearby_ids` inventory, not the 500-sample. Lives in
`api/routers/recommend.py` (needs the supabase client + `nearby_ids` + budget in scope);
pure token/pool helpers live in `recommendation/candidate_filters.py` for unit testing.

- **Named mode** (`wine_name` present): for each *significant* token of the name
  (tokenized and filtered through the existing `_GENERIC_WINE_WORDS` set so "Caymus
  Cabernet Sauvignon" keys on "caymus", not the varietal words), query
  `retail_inventory` joined to `wines` with `wines.name ilike %tok%`
  (`reference_table="wines"`), scoped to `nearby_ids` + `in_stock`. **Budget is
  ignored** — a directly-named lookup must not be hidden by the slider. If a name
  yields zero significant tokens (all generic), named mode is a no-op.
- **Weak-pool mode**: extend the targeted-style constraint query to also key on
  **grapes** (`wines.grapes` array overlap via `cs`/`ov` or an ilike on the grape
  string; region and store are already covered by `_targeted_rows`). **Honors budget.**

Both modes reuse `_row_to_candidate` and the same staleness policy as the breadth /
targeted fetch (bench dead-scraper rows, fail open).

### 3. Trigger + the themed status frame

Two triggers, computed synchronously after the first scoring pass and the initial
`_select_diverse_top`:

- `resolved.get("wine_name")` is truthy, **OR**
- **weak pool**: a pure helper `pool_is_weak(resolved, top)` returns True when the user
  expressed a concrete constraint (non-empty `grapes`, or `region`, or `wine_type`) and
  *none* of the selected `top` candidates actually satisfies it. Constraint-satisfaction
  is checked directly against candidate fields (grapes intersect, region substring,
  wine_type equals) — no scorer internals. When the user gave no concrete constraint
  (pure vibe request), the pool is never "weak" and no deep fetch fires.

**Architectural change:** the deep fetch and the Claude generator construction move
inside the SSE generator (`event_gen`). When a deep fetch is warranted:

1. `event_gen` first yields a `status` frame:
   `{"type": "status", "text": "Looking deeper into the cellar…"}`.
2. Runs the deep fetch, `merge_candidates` into the pool, re-scores (`score_candidates`
   + seeded jitter), re-selects `top` via `_select_diverse_top`, rebuilds `by_id`.
3. Then calls `stream_recommendations(top, …)` and streams as today.

Trade-off accepted: today the `stream_recommendations` client-init check (recommend.py
~L427) raises an HTTP 500 *before* `StreamingResponse` starts. Moving it inside the
generator means an init failure becomes an SSE `error` frame instead. The frontend
already handles `error` frames, so this is acceptable. The common no-constraint /
well-served request skips the deep fetch entirely and streams unchanged.

### 4. Selection — pin the named bottle

When named mode matched real inventory, pin those matches to the front of `top` ahead of
score order, deduped by `wine_id` (keep the cheapest / nearest store per wine),
**capped at 3** so the rest of the list still offers alternatives. A pure helper
`pin_named_matches(top, named_candidates, cap=3)` returns the reordered list. Somm then
naturally leads with the exact bottle.

### 5. Narrative honesty

Pass `named_bottle` (the `wine_name` string) and `named_bottle_found` (bool) into
`stream_recommendations` so the narrative either confirms the exact bottle ("Yes —
H-E-B Lincoln Heights has it…") or hedges when it isn't stocked nearby ("I couldn't find
Opus One nearby, but here's the closest in spirit…"), extending the item-29
absence-hedging already in the prompt. When `wine_name` is null, behavior is unchanged.

### 6. Frontend

Handle the new `status` SSE event type in the recommend stream consumer: render it as an
ephemeral themed line, cleared the moment the first `token` arrives. No persistence.

## Testing

Pure helpers unit-tested in `tests/`:
- name tokenization (drops `_GENERIC_WINE_WORDS`, keeps producer tokens; all-generic → empty)
- `pool_is_weak` (concrete-constraint-unmet → True; constraint met → False; no constraint → False)
- `pin_named_matches` (dedup by wine_id, cap at 3, named ahead of scored)

Acceptance replays:
- "do you have &lt;a stocked bottle&gt;?" → the bottle surfaces and is pinned first.
- a grape ask the 500-sample misses → surfaces via weak-pool mode.

## Out of scope

- Fuzzy/typo tolerance on the wine name beyond `ilike` substring (future).
- Vintage-specific disambiguation (product-family key, separate roadmap item).
