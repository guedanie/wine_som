# Phrasing-Robust Axis Extraction (Design)

**Date:** 2026-07-30
**Source:** `docs/oracle-production-verification.md` — prioritized next step #3 (silent fail-open),
plus #7 (per-axis isolation) and the duplicate-axis defect.

## Problem

The availability oracle only counts what the intent parser names. Production red-teaming found
that **negative and rhetorical framings defeat the parser**, so the oracle never runs — exactly
where absence-bait questions live:

| probe | parser extracted | axes emitted |
|---|---|---|
| `"nothing from Mendoza right?"` | `region=None`, `regions=None` | `[]` |
| `"anything from heb?"` | `wine_name="HEB"` (a retailer, not a bottle) | `[name:HEB]` |
| `"do you have Champagne at Central Market?"` | Champagne twice; no Central Market | duplicate rows |

The Mendoza probe **scored PASS** in the sweep — but only because no `PRESENT_*` fact existed to
contradict. A silent fail-open graded as a success. This is the precondition of all six original
false-absence incidents, and it means the sweep's pass rate is inflated for this whole class.

Structurally: the audit's thesis was *never let an LLM inference be the only path to a fact*. The
oracle honors that for counting, but its **axes** still depend entirely on a Haiku parse — the same
architectural smell one level up.

Two adjacent robustness defects, same code path:
- `fetch_axis_counts` catches exceptions around the whole fan-out, so a single transient
  `httpx.ReadError` degrades **every** axis to no-fact (verified in the sweep) — the safety net
  vanishes silently.
- Axes are not deduped: `"Champagne at Central Market"` emits `place:Champagne` and
  `name:Champagne`, and the H-E-B probe emitted `H-E-B` and `H-E-B at H-E-B`.

## Decision: catalog-derived vocabulary, not a curated gazetteer

Measured coverage of the 11 probe terms:

| source | size | probe terms missed |
|---|---|---|
| curated (`reference.py` APPELLATIONS + REGION_COUNTRY + ALIASES + KNOWN_GRAPES) | 146 | **6** — Barolo, Chablis, Sancerre, Pauillac, Brunello di Montalcino, Vinho Verde |
| catalog (`DISTINCT region, sub_region, country, varietal` + grape arrays) | 2,292 | **0** |

The curated table misses the most commonly asked appellations and would need hand-editing forever.
The catalog vocabulary is **complete by construction** — if a wine is in inventory, the term that
describes it is matchable — and it self-updates as scrapers add wines.

Accepted trade-off: the catalog contains some scraper-mangled strings, so the fallback could match a
term that is nonsense as a user constraint. Contained by (a) the stopword guard, (b) whole-word
longest-match, and (c) the fallback running **only when the parse found no content axis**.

## Design

### 1. Catalog vocabulary (`recommendation/availability.py`)

`catalog_terms(supabase) -> Set[str]` — normalized (accent-folded, lowercased) terms from
`DISTINCT region, sub_region, country, varietal` plus grape-array values, paginated with
`.order("id")`. Cached at module level with a TTL (default 1 hour) so it costs one query per
process, not per request. Fails open to an empty set (fallback simply does nothing).

`_STOPWORD_TERMS` — generic catalog values that must never self-match: `red`, `white`, `rosé`,
`wine`, `red wine`, `white wine`, `valley`, `other`, `blend`, `red blend`, `sparkling`, `dessert`,
`france`-style bare countries are KEPT (a country is a legitimate constraint) but single generic
words are dropped.

`terms_in_message(message, terms) -> List[str]` — whole-word, accent-folded, **longest-match-first**
scan so `"Brunello di Montalcino"` wins over `"Montalcino"`, and an already-claimed span is not
re-matched. Returns the surface terms found, capped.

### 2. Two-layer extraction

**Layer 1 — parser prompt** (`recommendation/intent.py`): instruct Haiku to extract the named
entity **even when the user is asserting or questioning its absence** ("nothing from Mendoza
right?", "surely you have no Barolo", "I assume there's no rosé") — the entity is still the subject
of the request. Also: a retailer/store name is NOT a `wine_name`; leave `wine_name` null for
"anything from HEB?".

**Layer 2 — deterministic fallback** (`availability.py`): `axes_from_intent` gains an optional
`fallback_terms: Optional[List[str]]`. When the parse produced **no content axes** (no regions, no
grapes, no type, no name), synthesize `place`-kind axes from `fallback_terms`. This is a **floor,
not a replacement** — whenever the parse works, it leads. The caller (`recommend.py`) computes
`fallback_terms = terms_in_message(req.message, catalog_terms(supabase))` only when needed.

### 3. Robustness fixes (same change)

- **Per-axis isolation**: move the try/except *inside* `_one(axis)` so a failing axis returns
  `None` (omitted ⇒ no fact for that axis) while every other axis still counts. The outer guard
  stays for a total-failure case; both log.
- **Dedupe** axes by `(kind, value_normalized, scope)` before the cap, so `Champagne` and
  `H-E-B at H-E-B` collapse.
- **Scope-equals-value guard**: skip a scoped copy whose value equals its scope (that's the
  `H-E-B at H-E-B` shape).

### 4. Testing

- `tests/test_availability.py`: `terms_in_message` (longest-match wins, whole-word only, accent
  folding, stopwords never match, empty vocab safe); `axes_from_intent` with `fallback_terms`
  (used only when no content axes; ignored when the parse succeeded); dedupe; scope-equals-value.
- `tests/test_intent.py`: negative-framing parse ("nothing from Mendoza right?" ⇒ region/regions
  contains Mendoza) — marked `integration` if it calls live Haiku, otherwise assert the prompt text
  contains the instruction.
- Per-axis isolation: a fake supabase whose second axis raises ⇒ other axes still return counts.
- Acceptance: extend `scripts/verify_availability_oracle.py` with the Mendoza case — assert a
  `place` axis is emitted and its fact is `PRESENT_*`.

## Out of scope

- The remaining verification items: zero-pick turns when a `PRESENT_*` axis has stock (Chateau
  Musar), retailer entity resolution (H-E-B total of 8 at 78209 looks implausible), and the
  scraper-name defect that produced "Australian cool-climate Pinot" for a California wine.
- The full 25-probe serialized sweep — runs after this lands, as the clean verification.
