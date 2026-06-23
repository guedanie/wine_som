# Recommendation Engine v2 Design

**Date:** 2026-06-22
**Status:** Approved

## Problem

The current `/api/recommend` engine has three limits:
1. **Tiny candidate pool** — it hard-filters to wines with `grapeminds_enriched_at` set. GrapeMinds is budget-capped (250 calls/month), so this ignores nearly the entire ~8,400-wine catalog, even though every wine now has Haiku-extracted `region/varietal/grapes/abv/body` plus scraped descriptions.
2. **Crude matching** — `score_candidates` does keyword substring matching against a concatenated text blob. It can't match fuzzy flavor language (a query for "earthy" misses a Grenache/Syrah/Mourvèdre blend whose notes never say "earthy"), and it ignores the structured extracted fields.
3. **Unused free-text** — `RecommendRequest.message` exists but is never parsed into intent.

## Decisions

- **Candidate pool:** tiered — GrapeMinds-enriched wines (tier 1, rich structure data) preferred, extractor-only wines (tier 2) as fallback. No hard gate.
- **Input model:** structured fields AND an optional NL `message`. When `message` is present, parse it into structured intent and merge with the explicit fields; **explicit fields win on conflict**.
- **Scoring:** knowledge-based deterministic. A curated grape/region → flavor-tag lookup lets the scorer infer flavor as a *fact about the wine* (GSM → earthy/savory) without embeddings or per-query model cost. (Semantic/embedding matching is a deliberate future option, not this version.)

## Architecture

All new/changed code lives under `backend/recommendation/` plus the router.

| File | Status | Responsibility |
|---|---|---|
| `backend/recommendation/flavor_profiles.py` | new | `GRAPE_FLAVORS` / `REGION_FLAVORS` lookups + `flavor_tags_for(varietal, grapes, region)` → `set[str]` |
| `backend/recommendation/intent.py` | new | `parse_message(message)` (Haiku tool-use → intent dict) + `merge_intent(parsed, explicit)` |
| `backend/recommendation/scorer.py` | rewrite | knowledge-based deterministic scoring |
| `backend/recommendation/claude_client.py` | light edit | receives resolved intent; same pick + narrative |
| `backend/api/routers/recommend.py` | edit | tiered candidate query, drop GrapeMinds gate, call parse/merge, tag tiers |

### Data flow

```
POST /api/recommend {zip, budget_min/max, wine_type, style_preferences[], avoid[], message?}
  → zip → nearby store_ids (unchanged radius lookup)
  → if message: parsed = parse_message(message)
        resolved = merge_intent(parsed, explicit fields)   # explicit wins
     else: resolved = intent built from explicit fields only
  → query nearby in-stock inventory within budget, joined to wines + wine_details
        tier 1 = grapeminds_enriched_at set
        tier 2 = extractor-only (has varietal or region)
        skip wines with neither (no basis to match)
  → score_candidates(resolved, candidates)
  → top N → Claude (Haiku) picks 3-5 + narrative, given resolved intent
  → persist session, return
```

## Component: `flavor_profiles.py`

Two curated lookups (following the `enrichment/extraction/reference.py` cheat-sheet pattern) and a resolver:

```python
GRAPE_FLAVORS = {
    "Sangiovese": {"earthy", "savory", "tart-cherry", "herbal"},
    "Grenache":   {"earthy", "red-fruit", "spice"},
    "Mourvèdre":  {"earthy", "savory", "gamey"},
    "Syrah":      {"peppery", "savory", "dark-fruit"},
    "Cabernet Sauvignon": {"bold", "structured", "black-fruit"},
    "Pinot Noir": {"light", "red-fruit", "earthy"},
    # ... seeded from the ~30 names in extraction.reference.CORE_GRAPES
}
REGION_FLAVORS = {
    "Rhône":   {"earthy", "garrigue", "savory", "peppery"},
    "Tuscany": {"earthy", "savory", "tart-cherry"},
    "Napa Valley": {"bold", "ripe", "black-fruit"},
    # ... seeded from the region keys in extraction.reference.APPELLATIONS
}

def flavor_tags_for(varietal, grapes, region) -> set:
    """Union the flavor tags implied by a wine's grape(s) + region.
    Grape/region name matching is case- and accent-insensitive (reuse reference._norm)."""
```

- The flavor-tag vocabulary is a **small controlled set** (`earthy, bold, savory, light, peppery, structured, herbal, red-fruit, black-fruit, dark-fruit, tart-cherry, spice, gamey, garrigue, ripe`). The same vocabulary is pinned in the intent parser so query flavors and wine tags speak the same language.
- v1 seeds from the existing `CORE_GRAPES` and `APPELLATIONS` keys; unknown grapes/regions return no tags (empty set) — safe.

## Component: `scorer.py` (rewrite)

`score_candidates(resolved_intent, candidates) -> List[dict]` — sums weighted, independent axes; pure function, no I/O.

| Axis | Rule | Weight |
|---|---|---|
| type | `wine_type == resolved.type` | 3.0 |
| body | `body == resolved.body`; if wine `body` is null, infer body bucket from grape flavor tags (e.g. "bold"/"structured" → full; "light" → light) | 2.0 |
| grape | size of `resolved.grapes ∩ wine.grapes` | 2.0 |
| region | `resolved.region == wine.region` | 1.5 |
| flavor | overlap of `resolved.flavors` with `flavor_tags_for(varietal, grapes, region)` PLUS literal keyword hits of `resolved.flavors` in tasting notes/description | up to 3.0 |
| budget | proximity to budget midpoint (existing formula) | 1.0 |
| tier | tier-1 (GrapeMinds) bonus over tier-2 | 0.5 |
| avoid | any `resolved.avoid` term found in grapes/region/flavor tags/notes → **exclude candidate** | exclude |

Returns candidates sorted by total score descending, each annotated with `_score` (and retains existing fields for the Claude step).

## Component: `intent.py` (new)

```python
def parse_message(message: str) -> dict:
    """One Haiku tool-use call. Returns:
    { "wine_type": red|white|rose|sparkling|orange|dessert|None,
      "body": light|medium|full|None,
      "flavors": [<controlled vocab tags>],
      "grapes": [<grape names>],
      "max_price": float|None,
      "avoid": [str] }
    The system prompt pins `flavors` to the scorer's controlled vocabulary."""

def merge_intent(parsed: dict, explicit: dict) -> dict:
    """Resolve final intent. Explicit request fields WIN on conflict; parsed
    values only fill gaps. List fields (flavors, avoid) are unioned.
    Explicit budget overrides parsed max_price."""
```

`parse_message` uses model `claude-haiku-4-5-20251001` with `tool_choice` forcing the intent schema (same pattern as `claude_client.py`).

## Component: `recommend.py` (edit)

- Add `grapes, abv, body` to the `wines(...)` select.
- Remove the `if not details.get("grapeminds_enriched_at"): continue` gate.
- Tag each candidate: `tier = 1` if `grapeminds_enriched_at` set; else `tier = 2` if it has `varietal` or `region`; else skip.
- Build `resolved` intent via `parse_message` + `merge_intent` when `req.message` is non-default, else from explicit fields.
- Pass `resolved` to `score_candidates` and to `get_recommendations`.

## Error Handling (all fail soft)

- `parse_message` raises or returns malformed data → log, fall back to explicit-fields-only intent. Never blocks the request.
- No candidates after filtering → existing 400 ("No enriched wines found… widen your budget").
- Final Claude call fails → existing 500 ("Recommendation service unavailable").

## Testing

- `tests/test_flavor_profiles.py` — GSM grapes + Rhône region → set includes `earthy`/`savory`; Cabernet → `bold`; unknown grape → empty set; case/accent-insensitive lookup.
- `tests/test_intent.py` — mocked Haiku tool block → structured intent; `merge_intent`: explicit `wine_type` overrides parsed, explicit budget overrides `max_price`, `flavors`/`avoid` unioned.
- `tests/test_scorer.py` (expand) — for an "earthy red" intent, a GSM/Rhône wine outranks a jammy fruit-forward red via grape/region flavor inference; body inferred when wine `body` is null; tier-1 outranks equal-scoring tier-2; an avoid term excludes a candidate; budget proximity orders within a tier.
- `tests/test_recommend_api.py` (expand) — tiered pool returns an extractor-only (tier-2) wine when no GrapeMinds wine matches; an NL `message` merges with explicit fields and explicit wins; parse failure falls back to explicit fields and still returns 200.

## Out of Scope

- Semantic/embedding matching (future upgrade if fuzzy free-text demands it; needs pgvector + an embedding provider).
- Personalization from saved wines / session history.
- Expanding the flavor lookups beyond the existing CORE_GRAPES / APPELLATIONS spine (curate more entries later as needed).

## Implementation Order

1. `flavor_profiles.py` + tests (TDD)
2. `scorer.py` rewrite + tests (TDD)
3. `intent.py` + tests (TDD)
4. `recommend.py` tiered pool + intent wiring + API tests (TDD)
