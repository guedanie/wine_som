# Web search for a named, off-catalog bottle — design

**Date:** 2026-09-23
**Status:** approved, not yet implemented

## Problem

Somm's recommend/chat flow (`recommendation/claude_client.py`, the `/recommend` endpoint backing PLAN and ASK/aisle mode) can already talk about wine in general via **Education Mode** ("tell me about," "what is") — but it answers purely from Claude's trained knowledge. When a user is standing in a store this app doesn't cover and names a specific bottle, that bottle is either absent from Claude's training data or the training is stale, and today the model can only hedge from memory ("I believe this is..."), per the producer-facts hedging rule from item 42 of the build log.

Real scenario: a user in an uncovered store asks "what is Chateau X like?" — a specific named bottle, not a request to buy something from inventory, not a request the availability oracle can satisfy from catalog data because the bottle genuinely isn't in the catalog.

## Scope

**In scope:** the recommend/chat flow only (`/recommend`, `recommendation/claude_client.py`), where a named-bottle axis can already resolve to `NOT_IN_CATALOG` via the availability oracle (item 39 of the build log).

**Out of scope (this spec):** the wine-dossier Somm overlay (`/api/somm`, `api/routers/somm.py`). A related but distinct use case surfaced during design — "I'm looking at wine A in the dossier; is it similar to wine B, which isn't in our catalog?" — belongs there, but that router has none of the named-bottle-detection or availability-oracle machinery this spec relies on. It gets a separate, short follow-up design once this ships and proves out. Do not fold it into this implementation.

## Design

### 1. Gate — code-enforced, not model discretion

Consistent with the existing architecture's core lesson (items 39–42: compute facts in Python, hand the model a verdict, never let it infer): the web_search tool is attached to the Anthropic API call **only when both are true, computed before the call**:

1. The turn's intent parse extracted a named bottle (`wine_name`/`wine_names`, or the `producer_tokens()` message-level floor from item 42 when the parser itself returns nothing).
2. That bottle's availability axis resolved to `NOT_IN_CATALOG` via the existing oracle (`recommendation/availability.py`).

If either is false, the web_search tool is never present in the request — normal turns are completely unaffected. This is a pure function of data the pipeline already computes every turn regardless (the oracle runs unconditionally), so no new fetch is needed to decide the gate — just a new boolean derived from existing outputs.

Implementation: a small `should_offer_web_search(intent, availability_facts) -> bool` function (new module, `recommendation/web_search_gate.py`, or colocated in `claude_client.py` if it stays under ~20 lines) — unit-testable the same way `classify_runs`/`_false_absence_suspects` are, with fixtures:
- named bottle + `NOT_IN_CATALOG` → `True`
- named bottle + any `PRESENT_*` state → `False` (it's in the catalog; no need to leave it)
- no named bottle at all → `False`
- **multiple named bottles, only some `NOT_IN_CATALOG`** (e.g. a comparison query naming one catalog wine and one that isn't stocked): gate is `True` if *any* named bottle is `NOT_IN_CATALOG`. The per-turn `[OFF-CATALOG BOTTLE]` directive (below) names only the off-catalog one(s), so Claude knows exactly which bottle the search license covers and is not invited to re-verify ones already resolved `PRESENT_*`.

### 2. Tool wiring

Anthropic's server-side `web_search_20250305` tool, added to the `tools` list **only on gated calls**, alongside the existing `_TOOL`:

```python
{
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 1,
    "allowed_domains": [
        "wine-searcher.com",
        "vivino.com",
        "winespectator.com",
        "decanter.com",
        "jancisrobinson.com",
        "wine.com",
    ],
}
```

- `max_uses: 1` — hard cap of one search per turn, chosen cost/safety control.
- `allowed_domains` — the six listed above are the full allowlist for v1. A producer's own site is not pre-listable but is effectively reachable via Vivino/Wine-Searcher/press coverage that links to or mirrors it. Consistent with the app's conservative-enrichment stance: fewer, trustworthy sources over broad recall. Revisit the list only if a real query comes back empty because a legitimate source was excluded — don't pre-expand speculatively.
- Never attached on ungated turns — the vast majority of calls keep exactly today's `tools: [_TOOL]` shape.

### 3. Prompt changes

Split across the static system prompt and the per-turn user message, to protect item 53's prompt-caching work (the cache breakpoint is a prefix match over `tools → system → messages`; nothing per-request may be interpolated into `_SYSTEM_PROMPT` or `_TOOL`).

**Static addition to `_SYSTEM_PROMPT`** (safe — no interpolation, only added when we ship, doesn't change per-request):
> When web search results are available for a bottle not in the local inventory, answer using them and clearly source the answer as general/web knowledge (e.g. "Wine-Searcher lists this as...") — never present it as something in stock or "available near you." Catalog inventory and web search results are two separate kinds of fact; never blend them into one claim (e.g. never state a price or nearby availability from a search result).

**Per-turn addition to `_build_user_message`** (same location the `[VERIFIED AVAILABILITY]` / `[VERIFIED PRODUCER]` blocks already render), only injected on gated turns:
```
[OFF-CATALOG BOTTLE]
"{bottle name}" is not in the local catalog. A web search tool is available
this turn if it would help answer the user's question about this specific bottle.
```
This is per-turn data (the bottle name), so it belongs in the user message, not the cached system block — same pattern the oracle already uses.

### 4. Response contract

- **Narrative:** answers the question using web results, hedged/sourced, never asserted as house fact.
- **Picks:** optional, never required. If a catalog wine is a genuinely close match to what was just discussed, Claude may include 1–2 picks with a comparison framing ("closer to what you're describing is our [X]"). If nothing fits, `picks: []`. The existing one-to-one narrative/picks rule still applies — no wine named in prose without a matching pick.
- **No availability or price claims from search results.** Only the catalog + the `[VERIFIED AVAILABILITY]` block may ever license an availability or price statement — this rule already exists in `_SYSTEM_PROMPT` and is not weakened by this feature; the new static paragraph above reinforces it explicitly for the web-search case.

### 5. Failure handling

Matches the existing fail-open pattern (producer facts, availability oracle): if the search tool errors, times out, or returns nothing usable, the turn proceeds as ordinary Education Mode, hedged from trained knowledge. Never blocks or breaks the SSE stream — same discipline as item 53's cache-logging isolation (a telemetry/tooling failure must never cost the user picks they already waited for).

### 6. Known cost tradeoff

Item 53's prompt caching keys on the literal `tools` array as part of the cached prefix. A gated turn has a different tool list than the ~99% of ordinary turns, so it forms its own (rarely-reused) cache lineage — effectively paying the full uncached ~2,795 input tokens on that turn, plus Anthropic's own per-search line-item cost. Expected and acceptable given how narrowly the gate fires; stated here so it doesn't read as a regression when someone checks the `CLAUDE CACHE` logs later.

### 7. Out of scope for this implementation

- The dossier-overlay comparison use case (see Scope above) — separate follow-up spec.
- An env var kill-switch (`ENABLE_WEB_SEARCH`) — not requested; cheap to add later if needed.
- Slack/log telemetry on search usage — not requested; cheap to add later (same pattern as item 53's `CLAUDE CACHE` log line) if usage patterns warrant tuning.
- Any change to the per-IP rate limiter (`api/ratelimit.py`) — the existing 15/hr `/recommend` cap is considered sufficient; `max_uses: 1` is the only new cost control.

## Testing

- **Unit tests** for `should_offer_web_search` (or equivalent): named+not-in-catalog → `True`; named+present → `False`; no name → `False`; multiple named bottles with mixed states → `True`, and the resulting `[OFF-CATALOG BOTTLE]` directive names only the `NOT_IN_CATALOG` one(s).
- **Acceptance script** `scripts/verify_web_search_gate.py`, mirroring the existing `verify_*` scripts (e.g. `verify_availability_oracle.py`, `verify_producer_facts.py`): live end-to-end run naming a real off-catalog bottle, asserting the tool was attached, a search occurred, and the response never claims availability/price for it.
- Fast suite additions live alongside `test_claude_client.py` / a new `test_web_search_gate.py`, following the existing test-file-per-module convention.
