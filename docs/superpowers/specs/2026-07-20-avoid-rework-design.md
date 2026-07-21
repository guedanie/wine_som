# `avoid` Hard-Exclusion Rework + Flavor De-Noise (Design)

**Date:** 2026-07-20
**Roadmap item:** 33 remainder (second capability sweep — soft axes)

## Problem

Capability sweep #2 (soft axes: flavor / avoid / body) found the recommender's
`avoid` path — the **only hard-exclusion guarantee** it makes — broken three ways.
The current code (`recommendation/scorer.py`) does a naive substring match:

```python
avoid = [_norm(a) for a in (intent.get("avoid") or [])]
...
haystack = " ".join([notes, region, " ".join(grapes), " ".join(tags)])
if any(a and a in haystack for a in avoid):
    continue
```

Measured defects (6,000-wine sample + full-catalog checks):

1. **Cannot exclude a wine *type*.** `wine_type` isn't in the haystack, so exclusion
   only fires when the word coincidentally appears in metadata. Leak: "no sparkling"
   → **210/369 (57%)** still surface; "nothing fortified" → **95/102 (93%)**;
   "no dessert" → 46/78 (59%).
2. **Substring (no word boundary) → false positives.** avoid "red" matches **3,616**
   wines (hits the `red-fruit` flavor tag) and doesn't even filter red wine; avoid
   "port" wrongly excludes **41** non-fortified wines ("Portugal"/"porto" in region).
3. **Haystack polluted with metadata.** `flavor_profile` is confirmed **100%
   metadata** — top tokens `PWSMigration, Red, White, Location_SanAntonio, 750ml,
   review-92plus, Lightspeed, Organic`, retailer collection names, winemaking tags;
   **zero** flavor-vocab words. `tasting_notes` is **100% empty** (0 / 19,566). So
   avoid matching is accidental/erratic, and the flavor `kw_hits` scoring path matches
   against metadata noise too (phantom flavor matches).

## Goal

Make `avoid` a reliable hard exclusion: exclude by *resolved wine_type* for type
words, word-boundary match structured fields for everything else, and stop matching
against metadata. Separately, remove the metadata `flavor_profile` from the flavor
scoring path.

## Design

### 1. Term → wine_type synonym map (conservative)

A module-level flat dict `_TYPE_FOR_TERM` in `scorer.py`, keys accent-folded +
lowercased (via the existing `_norm`), value = a `wine_type` enum string:

| terms | wine_type |
|---|---|
| `sparkling, bubbles, bubbly, champagne, prosecco, cava, fizz` | `sparkling` |
| `rose, rosé, pink` | `rosé` |
| `port, sherry, madeira, marsala, fortified` | `fortified` |
| `dessert, ice wine, icewine, sauternes` | `dessert` |
| `orange wine, skin contact` | `orange` |
| `red` | `red` |
| `white` | `white` |

Conservative-rule exclusions (deliberately NOT mapped): bare `sweet` (that's the
sweetness axis, not a type), bare `orange` (the fruit/flavor — only the phrases
`orange wine` / `skin contact` map), bare `green` (Vinho Verde is a *region*, reached
via region matching below, not a type).

Note on `rosé`: the DB stores the type accented (`rosé`) while the intent enum uses
`rose`; both sides go through `_norm` (accent-fold) before comparison, so they agree.

### 2. `wine_excluded_by_avoid(wine, avoid_terms, tags) -> bool`

A pure, unit-testable function in `scorer.py`, replacing the inline substring block.
`tags` is the already-computed `flavor_tags_for(...)` set from the scoring loop
(passed in to avoid recomputation). `wine["wine_type"]` is already resolved in-place by
`apply_type_gate` before scoring reaches here.

Logic, for each term (normalized via `_norm`):
- **Type synonym** (`_norm(term)` in `_TYPE_FOR_TERM`): exclude iff the wine's
  `_norm(wine_type)` equals the mapped type. If it's a type word but the wine is a
  different type, `continue` — do NOT fall through to substring matching. (This is what
  kills `port`→Portugal and `red`→red-fruit.)
- **Non-type term**: word-boundary match `re.search(r"\b" + re.escape(term) + r"\b", text)`
  against a structured text built from `varietal + name + grapes + region + country +
  flavor tags + tasting_notes`, each `_norm`'d and space-joined. **Excludes only the
  metadata `flavor_profile`** — real `tasting_notes` stays in (so "avoid oaky" matches a
  note "heavy oak"; it's empty in prod today but enriches later). No raw substring.

Returns `True` (exclude) on the first matching term, else `False`. Empty `avoid_terms`
→ `False` immediately.

Wiring: in `score_candidates`, replace the inline avoid block (the `haystack` +
`if any(...)` lines) with `if wine_excluded_by_avoid(wine, avoid, tags): continue`,
where `avoid = intent.get("avoid") or []` and `tags` is the loop's tag set.

### 3. Flavor de-noise (one line)

In `score_candidates`, change:

```python
notes = _norm(wine.get("tasting_notes")) + " " + " ".join(
    _norm(x) for x in (wine.get("flavor_profile") or []))
```

to:

```python
notes = _norm(wine.get("tasting_notes"))
```

`flavor_profile` is 100% metadata, so this only removes phantom flavor matches. The
`kw_hits` logic stays intact and will work if real tasting notes are ever enriched.
(After this, `notes` is used only by the flavor `kw_hits` path — avoid no longer reads
it.)

## Behavior after fix (acceptance targets, re-run the sweep)

- avoid "sparkling": leak 57% → ~0% (only true sparkling excluded).
- avoid "fortified": leak 93% → ~0%.
- avoid "port": 41 false positives → 0 (Portuguese table wines kept; Ports excluded).
- avoid "red": excludes red wines by type; no longer matches red-fruit whites/rosés.
- avoid "chardonnay" / "italian" / "earthy": still exclude (grape / country / tag) via
  word-boundary match.

## Components / files

- `backend/recommendation/scorer.py` — add `_TYPE_FOR_TERM`, `wine_excluded_by_avoid`;
  wire into `score_candidates`; drop `flavor_profile` from `notes`.
- `backend/tests/test_scorer.py` — unit tests for the new function + a flavor-denoise
  regression.
- Sweep re-run via the scratchpad `somm_soft_sweep.py` (acceptance evidence; not
  committed as a test).

## Out of scope (separate future item)

- Flavor-axis enrichment gap: 28% of wines are flavor-invisible (grape/region not in the
  curated tag map), and the parser clamps `flavors` to a 15-word vocab so common asks
  (buttery, oaky, smoky, jammy, mineral, floral, citrus, tropical) are dropped. Fixing
  this is a data/enrichment + vocab effort, not a scorer change.
- Sweetness-based avoid ("nothing sweet" consulting `structure_profile.sweetness`).
- Body axis: healthy at 88% resolvable; not touched.
