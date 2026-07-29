# Retailer-Scoped Requests (Design)

**Date:** 2026-07-29
**Roadmap:** recommender capability follow-on (named-retailer fetch)

## Problem

"Anything from H-E-B?" (as a request or follow-up) made Somm say *"Nothing from H-E-B
turned up in this search — none of the wines currently showing are stocked there,"* even
though H-E-B near 78230 stocks **60+ light reds under $60** (Black Box Pinot, Elk Cove
Willamette Pinot $24, Belle Glos, Etude, Flowers…). Users can't tell whether that means
"H-E-B has no light reds" or "none of the current picks are at H-E-B."

Root cause in `recommendation`:
- `_detect_retailer(message)` matches a **hardcoded 3-retailer substring alias map**
  (H-E-B, Spec's, Geraldine's only) and then **filters the already-fetched candidate
  pool**: `retailer_pool = [c for c in candidates if R in c.retailer]; if retailer_pool:
  candidates = retailer_pool`. When the generic fetch surfaced a boutique-heavy pool with
  no H-E-B wine, the filter finds nothing → silently no-ops → Somm concludes "nothing from
  H-E-B."
- There is a **targeted fetch for region / store / named-bottle** (items 29/31) but **none
  for a named retailer chain** — so a retailer-scoped request never queries that retailer's
  inventory.

## Decisions (locked)

- **Detection: derive from nearby retailers + robust aliasing** (not the hardcoded list).
- **Aliasing must catch H-E-B variants** — `heb`, `HEB`, `h-e-b`, `h.e.b` all resolve.
- **Filter firmness: when the named retailer HAS fits, show only that retailer's wines**;
  if it has none, fall back to alternatives elsewhere with honest wording.

## Design

### 1. Data-driven retailer detection — `detect_retailer(message, nearby_retailers)`

Move detection into `recommendation/candidate_filters.py` (pure, testable; mirrors
`detect_store`). Signature: `detect_retailer(message: str, nearby_retailers: List[str]) ->
Optional[str]` — returns a canonical name drawn from `nearby_retailers`, or None.

Matching (case- and punctuation-insensitive):
- **Per-token normalization** `_norm_retailer(tok) = lower(tok) with all non-alphanumerics
  stripped`, so a single token `H-E-B` / `HEB` / `h.e.b` / `h-e-b` all become `heb`.
- **Alias map** (normalized keys → canonical) for shorthands that don't appear in the name:
  `heb→H-E-B`, `specs/spec→Spec's`, `cm→Central Market`, `twin→Twin Liquors`,
  `ht→Harris Teeter`, `geraldines/geraldine→Geraldine's`, `pogos→Pogo's`. Only used when
  the alias's canonical target is among `nearby_retailers`.
- **Derive-from-nearby:** for each name in `nearby_retailers`, tokenize + normalize it
  (`"Central Market"→{central, market}`, `"H-E-B"→{heb}`, `"Twin Liquors"→{twin, liquors}`)
  and match if the message's normalized tokens cover the retailer's distinctive tokens
  (drop generic words like "wine"/"market"/"liquors" from the *required* set, à la
  `detect_store`, so "central" alone can hit Central Market). Fuzzy (typo-tolerant) via the
  same `difflib` cutoff `detect_store` uses.
- Return the first/nearest match; None if nothing distinctive matches. **Only ever returns
  a retailer that is actually nearby.**

`recommend.py` deletes its local `_detect_retailer` + `_RETAILER_ALIASES` and calls
`detect_retailer(req.message, list(retailer_to_stores))`.

### 2. Targeted retailer fetch (the core fix)

In `recommend.py`, when `detect_retailer` returns a retailer R with nearby stores
(`retailer_to_stores[R]`), run a fetch scoped to R's store IDs — `in_stock`, within the
budget window, carrying any resolved region/grape constraints (same `or_(...)` machinery as
`_targeted_rows`) — and `merge_candidates` it into the pool. Mirrors the existing
region/store/name targeted fetches; it just scopes by a retailer's store set instead of a
place. Now the pool genuinely contains R's inventory, so the type gate + scorer rank R's
light reds instead of never seeing them.

### 3. Filter — retailer-only when it has fits

The existing `retailer_pool` filter stays, now operating on a pool that contains R's wines:
- R has fitting candidates → `candidates = retailer_pool` (**show only R**; diverse-top
  fills up to the normal count from R).
- R has none → keep the full pool (alternatives elsewhere) — the fallback.

### 4. Honest narrative wording

Set `resolved["requested_retailer"] = R` and `resolved["retailer_has_fit"] =
bool(retailer_pool)`. `_build_user_message` (`claude_client.py`) renders a directive:
- **has fit:** "The user asked for {R}; every listing below is from {R} — recommend from
  these."
- **no fit:** "The user asked for {R}, but {R} doesn't stock a wine matching their profile.
  Say that plainly, then offer the closest fits from other nearby shops." — replaces the
  ambiguous "nothing turned up in this search."
Renders nothing when `requested_retailer` is unset (non-retailer requests unchanged).

### 5. Testing

- `test_candidate_filters.py` — `detect_retailer`: **all H-E-B variants** (`heb`, `HEB`,
  `h-e-b`, `h.e.b`) → "H-E-B"; multi-word ("central market"→Central Market, "twin
  liquors"→Twin Liquors); shorthand ("cm", "twin"); typo ("centrl market"); None when no
  retailer named; never returns a retailer not in `nearby_retailers`.
- `test_claude_client.py` — retailer directive present (has-fit vs no-fit wording), absent
  when unset.
- Acceptance `scripts/verify_retailer_fetch.py` — replay: light & elegant red at 78230 →
  detect "heb" → H-E-B targeted fetch → pool contains H-E-B Pinots (Black Box, Elk Cove…),
  `retailer_pool` non-empty, final candidates all H-E-B.

## Out of scope (follow-up)

- **Cards vs. text:** the follow-up is sent `conversational: true`, so even with this fix
  Claude may answer in text ("yes, H-E-B has Black Box Pinot…") rather than spawning new
  cards. Making a retailer-named follow-up count as a "re-ask" that shows fresh cards is a
  separate frontend heuristic (`naturalChatMode` / re-ask detection in `ChatRecommend`).
  The backend fix here already makes the answer correct and honest — the reported bug.
- Retailers not present in the user's nearby set (nothing to scope to).
