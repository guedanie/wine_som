# Web Search For A Named, Off-Catalog Bottle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Somm's recommend/chat flow (`/recommend`) use Anthropic's server-side web search tool to answer a question about a specific named bottle that is confirmed absent from the catalog — gated entirely in code, never left to model discretion.

**Architecture:** The availability oracle (`recommendation/availability.py`) already resolves a named-bottle axis (`kind == "name"`) to `NOT_IN_CATALOG` every turn when applicable, as part of `recommendation/recommend.py`'s existing `resolved["availability_facts"]` pipeline. A new small module, `recommendation/web_search.py`, reads that list and decides whether to attach Anthropic's `web_search_20250305` tool to this turn's API call. When attached, `stream_recommendations` (in `recommendation/claude_client.py`) also relaxes `tool_choice` from a hard-forced `recommend_wines` to `{"type": "any"}`, because Anthropic's forced-single-tool `tool_choice` does not allow a second tool (including a server tool) to be called at all — this is a load-bearing detail the design spec did not call out and is the main technical risk in this plan. A per-turn user-message directive names exactly the off-catalog bottle(s); a small evergreen paragraph in the (cached) system prompt states the sourcing/hedging contract once.

**Tech Stack:** Python 3.9 (backend/), `anthropic` SDK 0.105.2 (already supports `web_search_20250305`, confirmed against the installed package), pytest.

**Design doc:** `docs/superpowers/specs/2026-09-23-web-search-off-catalog-bottle-design.md`

---

## Important implementation note not in the design spec

The design spec says the web_search tool is "added to the `tools` list ... alongside the existing `_TOOL`" but doesn't address `tool_choice`. Today, both `stream_recommendations` and `get_recommendations` in `recommendation/claude_client.py` call the API with:

```python
tool_choice={"type": "tool", "name": "recommend_wines"},
```

This **forces the model to call only `recommend_wines` and nothing else** — with this set, adding `web_search` to `tools` would have no effect; the model is structurally prevented from ever invoking it. So on a gated turn, `tool_choice` must relax to `{"type": "any"}` (must use *some* tool, model's choice — still guarantees a tool is called, unlike `{"type": "auto"}` which could return plain text and break the "must always call recommend_wines" contract downstream). The system/user prompt must then explicitly instruct the model that it may call `web_search` but **must still** call `recommend_wines` afterward — Anthropic's web_search is a *server tool*, executed and injected within the same API turn, so the model can call it and then continue on to call `recommend_wines` in the same response without a round trip.

Confirmed against the installed SDK (`venv/lib/python3.14/site-packages/anthropic/types/`):
- `web_search_20250305` tool fields: `type`, `name` (must be `"web_search"`), `max_uses`, `allowed_domains`.
- A web-search content block has `type == "server_tool_use"` (its own input, not our tool's), and the result block is `web_search_tool_result` — neither matches the existing `b.type == "tool_use"` filter used to find the `recommend_wines` block in `final.content`, so that lookup keeps working unmodified regardless of tool order.
- The streaming narrative parser (`_parse_narrative_fragments` / `_fragments()` in `claude_client.py`) concatenates `input_json_delta` fragments from **any** content block without filtering by block index, and only cares about finding the literal substring `"narrative":"` in the concatenated buffer. A leading `web_search` tool call's own small JSON input (e.g. `{"query": "..."}`) merely becomes harmless leading text in that buffer before the real marker appears — **no change needed to the parser.**

`get_recommendations` (the non-streaming variant) is used only by tests per its own docstring ("kept for tests that mock anthropic.Anthropic directly") and is never called from `api/routers/recommend.py` (confirmed by grep — its only two call sites are `recommendation/claude_client.py`'s own definition and `tests/test_claude_client.py`). **Do not modify it** — out of scope, no production behavior depends on it.

**Failure handling (design spec section 5) needs no new code.** Anthropic's web_search is a server tool: if the search itself errors, the API injects an error result into the same turn and the model continues (no round trip, no exception raised to us). If something more fundamental fails (e.g. the tool type is rejected), it surfaces as an exception from `_anthropic_client.messages.stream(...)`, which the existing `except Exception` in `stream_recommendations._gen()` already catches and turns into `("error", "Recommendation service unavailable")` — the same fail-open path every other error in this function already takes. No task below adds exception handling because none is needed.

## Multi-bottle behavior (per spec's self-review)

`recommendation/availability.py:axes_from_intent` today creates **at most one** `kind == "name"` axis per turn (from `resolved["wine_name"]`, the single primary bottle — plural `wine_names` from a comparison query is not turned into multiple name axes; that's a pre-existing characteristic of the oracle, out of scope to change here). So in practice, at most one off-catalog bottle can be gated per turn today. The gate function in this plan is written generically over the whole facts list (loops and collects all matching axes) so it requires no changes if `axes_from_intent` is ever extended to emit more than one `name` axis — this is forward compatibility, not scope creep; it costs nothing extra to write it as a loop instead of a single lookup.

---

## Task 1: Web search gate module

**Files:**
- Create: `backend/recommendation/web_search.py`
- Test: `backend/tests/test_web_search.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_web_search.py`:

```python
"""Tests for the web-search gate — recommendation/web_search.py.

The gate is a pure function over the availability oracle's already-computed
facts list (recommendation/availability.py); no network, no DB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.availability import NOT_IN_CATALOG, PRESENT_SHORTLISTED, PRESENT_OUT_OF_BUDGET
from recommendation.web_search import (
    off_catalog_bottles, should_offer_web_search, off_catalog_directive, WEB_SEARCH_TOOL,
)


def _fact(kind, value, state, scope=None):
    return {"label": value, "state": state,
            "axis": {"kind": kind, "value": value, "scope": scope}}


def test_named_bottle_not_in_catalog_is_off_catalog():
    facts = [_fact("name", "Chateau Talbot", NOT_IN_CATALOG)]
    assert off_catalog_bottles(facts) == ["Chateau Talbot"]
    assert should_offer_web_search(facts) is True


def test_named_bottle_present_is_not_off_catalog():
    facts = [_fact("name", "Chateau Talbot", PRESENT_SHORTLISTED)]
    assert off_catalog_bottles(facts) == []
    assert should_offer_web_search(facts) is False


def test_named_bottle_present_out_of_budget_is_not_off_catalog():
    """Out of budget still means it EXISTS in the catalog -- no search license."""
    facts = [_fact("name", "Chateau Talbot", PRESENT_OUT_OF_BUDGET)]
    assert off_catalog_bottles(facts) == []


def test_no_bottle_named_is_not_off_catalog():
    facts = [_fact("place", "Mendoza", NOT_IN_CATALOG)]
    assert off_catalog_bottles(facts) == []
    assert should_offer_web_search(facts) is False


def test_no_facts_at_all_is_not_off_catalog():
    assert off_catalog_bottles([]) == []
    assert should_offer_web_search([]) is False


def test_mixed_facts_only_the_off_catalog_name_axis_counts():
    facts = [
        _fact("place", "Mendoza", NOT_IN_CATALOG),
        _fact("name", "Chateau Talbot", NOT_IN_CATALOG),
        _fact("grape", "Malbec", PRESENT_SHORTLISTED),
    ]
    assert off_catalog_bottles(facts) == ["Chateau Talbot"]


def test_multiple_named_bottles_mixed_states_only_off_catalog_ones_gate():
    """axes_from_intent today only ever emits one 'name' axis per turn (see the
    plan's multi-bottle note), but the gate itself is a pure function over
    the whole facts list -- write it to handle several name axes correctly
    now, at zero extra cost, so it needs no change if that ever expands."""
    facts = [
        _fact("name", "Chateau Talbot", PRESENT_SHORTLISTED),
        _fact("name", "Screaming Eagle", NOT_IN_CATALOG),
        _fact("name", "Opus One", NOT_IN_CATALOG),
    ]
    assert off_catalog_bottles(facts) == ["Screaming Eagle", "Opus One"]
    assert should_offer_web_search(facts) is True
    directive = off_catalog_directive(off_catalog_bottles(facts))
    assert "Screaming Eagle" in directive
    assert "Opus One" in directive
    assert "Chateau Talbot" not in directive


def test_directive_names_the_bottle_singular():
    directive = off_catalog_directive(["Chateau Talbot"])
    assert "Chateau Talbot" in directive
    assert "OFF-CATALOG BOTTLE" in directive
    assert "recommend_wines" in directive


def test_directive_empty_when_no_bottles():
    assert off_catalog_directive([]) == ""


def test_directive_handles_multiple_bottles_grammatically():
    directive = off_catalog_directive(["Chateau Talbot", "Screaming Eagle"])
    assert "Chateau Talbot" in directive
    assert "Screaming Eagle" in directive
    assert "these bottles" in directive


def test_web_search_tool_shape():
    assert WEB_SEARCH_TOOL["type"] == "web_search_20250305"
    assert WEB_SEARCH_TOOL["name"] == "web_search"
    assert WEB_SEARCH_TOOL["max_uses"] == 1
    assert "wine-searcher.com" in WEB_SEARCH_TOOL["allowed_domains"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_web_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'recommendation.web_search'`

- [ ] **Step 3: Write the implementation**

Create `backend/recommendation/web_search.py`:

```python
"""Web search for a named bottle confirmed absent from the catalog.

The gate is computed here from data recommendation/availability.py already
produces every turn (the availability oracle's fact list) -- never left to
model discretion, matching the architecture's existing rule that absence and
identity are counted facts, not recalled ones (see items 39-42 of the build
log). Design: docs/superpowers/specs/2026-09-23-web-search-off-catalog-bottle-design.md
"""
from typing import Any, Dict, List

from recommendation.availability import NOT_IN_CATALOG

# Anthropic's server-side web search tool. Attached to the API call ONLY when
# off_catalog_bottles() below returns something -- never on an ordinary turn.
# max_uses=1 caps one gated turn to a single search (cost/safety control).
# allowed_domains is deliberately small: fewer, trustworthy wine sources over
# broad recall, matching the app's conservative-enrichment stance. Revisit only
# if a real query comes back empty because a legitimate source was excluded --
# don't pre-expand speculatively.
WEB_SEARCH_TOOL = {
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


def off_catalog_bottles(facts: List[Dict[str, Any]]) -> List[str]:
    """Named bottles (availability axis kind 'name') that resolved NOT_IN_CATALOG
    this turn. Empty in the common case -- nothing to search for."""
    out = []
    for f in facts:
        axis = f.get("axis") or {}
        if axis.get("kind") == "name" and f.get("state") == NOT_IN_CATALOG:
            value = axis.get("value")
            if value:
                out.append(value)
    return out


def should_offer_web_search(facts: List[Dict[str, Any]]) -> bool:
    """True when at least one named bottle this turn is confirmed off-catalog."""
    return bool(off_catalog_bottles(facts))


def off_catalog_directive(bottles: List[str]) -> str:
    """Per-turn user-message directive naming exactly the off-catalog bottle(s) a
    search may cover -- never the whole catalog, never a bottle already resolved
    PRESENT_*. Empty string when there's nothing to license."""
    if not bottles:
        return ""
    joined = ", ".join(f'"{b}"' for b in bottles)
    subject = "this bottle" if len(bottles) == 1 else "these bottles"
    return (
        f"\n\n[OFF-CATALOG BOTTLE]\n{joined} -- not in the local catalog. A web "
        f"search tool is available this turn if it would help answer the "
        f"user's question about {subject}. If you use it, you must still call "
        f"recommend_wines with your narrative and picks -- never end the turn "
        f"on a search alone."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_web_search.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add backend/recommendation/web_search.py backend/tests/test_web_search.py
git commit -m "feat: web search gate for a named, off-catalog bottle"
```

---

## Task 2: Wire the per-turn directive into the user message

**Files:**
- Modify: `backend/recommendation/claude_client.py:1-9` (imports), `:430-474` (`_build_user_message`)
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_claude_client.py` (after the existing producer-block tests, e.g. after `test_no_producer_block_when_no_facts` around line 491 -- exact placement doesn't matter, just keep it near the other fact-block tests):

```python
# ── web search directive ──────────────────────────────────────────────

from recommendation.availability import NOT_IN_CATALOG as _NOT_IN_CATALOG


def test_web_search_directive_present_for_off_catalog_bottle():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent(
        availability_facts=[{"label": "Chateau Talbot", "state": _NOT_IN_CATALOG,
                             "axis": {"kind": "name", "value": "Chateau Talbot", "scope": None}}]))
    assert "OFF-CATALOG BOTTLE" in msg
    assert "Chateau Talbot" in msg


def test_no_web_search_directive_when_bottle_is_present():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent(
        availability_facts=[{"label": "Chateau Talbot", "state": PRESENT_SHORTLISTED,
                             "axis": {"kind": "name", "value": "Chateau Talbot", "scope": None}}]))
    assert "OFF-CATALOG BOTTLE" not in msg


def test_no_web_search_directive_without_facts():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent())
    assert "OFF-CATALOG BOTTLE" not in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k web_search_directive -v`
Expected: FAIL — `assert "OFF-CATALOG BOTTLE" in msg` fails (directive doesn't exist yet)

- [ ] **Step 3: Write the implementation**

In `backend/recommendation/claude_client.py`, add the import at the top (after the existing `from recommendation.producer_facts import format_producer_block` line):

```python
from recommendation.producer_facts import format_producer_block
from recommendation.web_search import off_catalog_bottles, off_catalog_directive
```

Then in `_build_user_message`, immediately after the `producer_rules = ...` block (right after the line `producer_rules = f"\n\nPRODUCER RULES (these override recall):\n1. {producer_rule_text}"`, before the `# Aisle mode sends a wide-range sentinel...` comment for `budget_line`), add:

```python
    # Web search license: a named bottle that resolved NOT_IN_CATALOG this turn
    # may be looked up via the web_search tool, which claude_client attaches to
    # the API call only when this directive is non-empty (see
    # stream_recommendations). Per-turn data, so it lives here, not in the
    # cached system prompt.
    web_search_directive = off_catalog_directive(
        off_catalog_bottles(intent.get("availability_facts") or []))
```

Then add `f"{web_search_directive}"` to the returned f-string, placed after `f"{producer_rules}"` and before `f"{followup_directive}"`:

```python
        f"{fact_block}"
        f"{producer_block}"
        f"{availability_rules}"
        f"{producer_rules}"
        f"{web_search_directive}"
        f"{followup_directive}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k web_search_directive -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full claude_client test file to check nothing else broke**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -v`
Expected: PASS, all tests (previous count + 3)

- [ ] **Step 6: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat: per-turn off-catalog-bottle directive in the user message"
```

---

## Task 3: Gate the tool list and tool_choice in stream_recommendations

**Files:**
- Modify: `backend/recommendation/claude_client.py:653-731` (`stream_recommendations`)
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_claude_client.py`:

```python
def test_ordinary_turn_keeps_single_forced_tool():
    """No off-catalog bottle -> tools/tool_choice are exactly today's shape,
    unaffected by this feature."""
    from unittest.mock import patch
    from recommendation.claude_client import stream_recommendations
    intent = {"wine_type": "red", "flavors": [], "avoid": [],
              "budget_min": 10, "budget_max": 50}
    with patch("recommendation.claude_client._anthropic_client") as mock_client:
        mock_client.messages.stream.side_effect = Exception("stop here")
        list(stream_recommendations(_cands(), intent))
    kwargs = mock_client.messages.stream.call_args.kwargs
    assert kwargs["tools"] == [_TOOL]
    assert kwargs["tool_choice"] == {"type": "tool", "name": "recommend_wines"}


def test_gated_turn_adds_web_search_tool_and_relaxes_tool_choice():
    """A confirmed off-catalog bottle attaches web_search AND relaxes tool_choice
    to 'any' -- forcing recommend_wines alone would make web_search uncallable."""
    from unittest.mock import patch
    from recommendation.claude_client import stream_recommendations
    from recommendation.web_search import WEB_SEARCH_TOOL
    intent = {"wine_type": "red", "flavors": [], "avoid": [],
              "budget_min": 10, "budget_max": 50,
              "availability_facts": [{"label": "Chateau Talbot", "state": _NOT_IN_CATALOG,
                                      "axis": {"kind": "name", "value": "Chateau Talbot",
                                               "scope": None}}]}
    with patch("recommendation.claude_client._anthropic_client") as mock_client:
        mock_client.messages.stream.side_effect = Exception("stop here")
        list(stream_recommendations(_cands(), intent))
    kwargs = mock_client.messages.stream.call_args.kwargs
    assert kwargs["tools"] == [_TOOL, WEB_SEARCH_TOOL]
    assert kwargs["tool_choice"] == {"type": "any"}


def test_gated_turn_still_finds_recommend_wines_block_among_others():
    """final.content can contain server_tool_use / web_search_tool_result blocks
    ahead of our tool_use block -- the b.type == "tool_use" filter must still
    find recommend_wines regardless of order."""
    from unittest.mock import patch, MagicMock
    from recommendation.claude_client import stream_recommendations

    search_block = MagicMock(type="server_tool_use")
    result_block = MagicMock(type="web_search_tool_result")
    tool_block = MagicMock(type="tool_use")
    tool_block.input = {"narrative": "n", "picks": [{"wine_id": "w1", "why": "y"}],
                        "followup_suggestions": []}

    final = MagicMock()
    final.content = [search_block, result_block, tool_block]
    final.usage = MagicMock(cache_read_input_tokens=0, cache_creation_input_tokens=0,
                            input_tokens=10)

    stream_cm = MagicMock()
    stream_cm.__enter__.return_value.__iter__.return_value = iter([])
    stream_cm.__enter__.return_value.get_final_message.return_value = final

    intent = {"wine_type": "red", "flavors": [], "avoid": [],
              "budget_min": 10, "budget_max": 50,
              "availability_facts": [{"label": "Chateau Talbot", "state": _NOT_IN_CATALOG,
                                      "axis": {"kind": "name", "value": "Chateau Talbot",
                                               "scope": None}}]}
    with patch("recommendation.claude_client._anthropic_client") as mock_client:
        mock_client.messages.stream.return_value = stream_cm
        events = list(stream_recommendations(_cands(), intent))

    assert not [v for t, v in events if t == "error"]
    assert [v for t, v in events if t == "picks"] == [[{"wine_id": "w1", "why": "y"}]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k "gated_turn or ordinary_turn_keeps" -v`
Expected: FAIL — `KeyError: 'tools'` or mismatched tools/tool_choice (implementation doesn't gate yet; today's code always sends the single forced tool, so `test_gated_turn_adds_web_search_tool_and_relaxes_tool_choice` fails)

- [ ] **Step 3: Write the implementation**

In `backend/recommendation/claude_client.py`, update the import line added in Task 2 to also import `WEB_SEARCH_TOOL`:

```python
from recommendation.web_search import WEB_SEARCH_TOOL, off_catalog_bottles, off_catalog_directive
```

Then in `stream_recommendations`, replace:

```python
    user_msg = _build_user_message(candidates, intent, conversation_history, conversational)
    user_message = intent.get("message") or ""

    logger.info(
        "CLAUDE | streaming | message=%r history_turns=%d candidates=%d",
        user_message[:60], len(conversation_history or []), len(candidates),
    )

    def _gen():
        picks_yielded = False
        try:
            with _anthropic_client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=system_blocks(),
                messages=[{"role": "user", "content": user_msg}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "recommend_wines"},
            ) as stream:
```

with:

```python
    user_msg = _build_user_message(candidates, intent, conversation_history, conversational)
    user_message = intent.get("message") or ""

    # Anthropic's forced single-tool tool_choice (the default below) makes any
    # OTHER tool -- including a server tool like web_search -- uncallable. Only
    # relax it, and only add web_search, on a turn where the availability oracle
    # confirmed a named bottle is off-catalog (see recommendation/web_search.py).
    off_catalog = off_catalog_bottles(intent.get("availability_facts") or [])
    tools = [_TOOL, WEB_SEARCH_TOOL] if off_catalog else [_TOOL]
    tool_choice = ({"type": "any"} if off_catalog
                  else {"type": "tool", "name": "recommend_wines"})

    logger.info(
        "CLAUDE | streaming | message=%r history_turns=%d candidates=%d web_search=%s",
        user_message[:60], len(conversation_history or []), len(candidates), bool(off_catalog),
    )

    def _gen():
        picks_yielded = False
        try:
            with _anthropic_client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=system_blocks(),
                messages=[{"role": "user", "content": user_msg}],
                tools=tools,
                tool_choice=tool_choice,
            ) as stream:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k "gated_turn or ordinary_turn_keeps" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full claude_client test file**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -v`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat: attach web_search tool and relax tool_choice on off-catalog-bottle turns"
```

---

## Task 4: Evergreen system-prompt paragraph

**Files:**
- Modify: `backend/recommendation/claude_client.py:90-100` (`_SYSTEM_PROMPT`, Education Mode section)
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_claude_client.py`:

```python
def test_system_prompt_states_web_search_sourcing_contract():
    from recommendation.claude_client import _SYSTEM_PROMPT
    low = _SYSTEM_PROMPT.lower()
    assert "web search" in low
    assert "never present it as something in stock" in low or "never state a price" in low
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k web_search_sourcing -v`
Expected: FAIL — assertion on missing text

- [ ] **Step 3: Write the implementation**

In `backend/recommendation/claude_client.py`, find the `## Education Mode` section:

```python
## Education Mode

**Trigger:** User wants to understand a wine, region, grape, producer, or concept.

- Open with what makes the subject distinctive — don't lead with geography basics unless context requires it.
- Cover: regional character, defining grapes, standout vintages (be specific — growing season \
detail beats "ideal conditions"). Be opinionated.
- Use short paragraphs, not bullet lists.
- After a substantive response, offer a natural bridge: "Want me to find something available \
near you that fits this profile?"
- Return `picks: []` — Education Mode answers questions, it does not push wine cards.
```

Add a new subsection immediately after it (before `## Pairing Mode`):

```python
## Off-Catalog Bottle Search

**Trigger:** A web_search tool is present this turn (only ever offered for a bottle the \
[OFF-CATALOG BOTTLE] note confirms is not in the local catalog — never available otherwise).

- You may use web_search to answer the user's question about that specific bottle.
- Source the answer as general/web knowledge (e.g. "Wine-Searcher lists this as...") — never \
present it as something in stock or "available near you."
- Catalog inventory and web search results are two separate kinds of fact. Never blend them \
into one claim — never state a price or nearby availability from a search result.
- You must still call recommend_wines with your narrative and picks. Picks may be empty, or \
may include a catalog wine if it's a genuinely close comparison ("closer to what you're \
describing is our..."). Never end the turn on a search alone.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k web_search_sourcing -v`
Expected: PASS

- [ ] **Step 5: Run the full fast suite for this module and its neighbors**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py tests/test_web_search.py tests/test_availability.py -v`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat: evergreen system-prompt contract for off-catalog web search"
```

---

## Task 5: Acceptance script

**Files:**
- Create: `backend/scripts/verify_web_search_gate.py`

- [ ] **Step 1: Write the script**

Create `backend/scripts/verify_web_search_gate.py`:

```python
"""Acceptance for the off-catalog-bottle web search gate. Run from backend/:
    /usr/bin/python3 -m scripts.verify_web_search_gate

Live end-to-end: a real named bottle this catalog doesn't carry, run through
the actual availability oracle against live inventory, then through the gate
and the user-message builder -- confirming the directive appears and the tool
would be attached, without spending an actual Anthropic API call.
"""
from db import get_supabase_client
from utils.geo import find_nearby_store_ids
from recommendation.availability import axes_from_intent, fetch_axis_counts, derive_state, axis_key
from recommendation.web_search import off_catalog_bottles, off_catalog_directive, WEB_SEARCH_TOOL
from recommendation.claude_client import _build_user_message

ZIP = "78209"
# A specific, real, small-production bottle overwhelmingly unlikely to be in
# any of this app's scraped retailers -- the live equivalent of the "genuinely
# absent axis" case in verify_availability_oracle.py.
OFF_CATALOG_BOTTLE = "Domaine de la Romanee-Conti Montrachet 2018"


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)

    resolved = {"regions": [], "grapes": [], "wine_type": None,
                "wine_name": OFF_CATALOG_BOTTLE}
    axes = axes_from_intent(resolved)
    assert axes and axes[0]["kind"] == "name", "expected a single name axis"

    counts = fetch_axis_counts(sb, axes, nearby, 50.0)
    c = counts.get(axis_key(axes[0]))
    assert c is not None, "axis count fetch failed -- cannot verify live"
    state = derive_state(c["total"], c["in_budget"], 0)
    print(f"— {OFF_CATALOG_BOTTLE}: state={state} total={c['total']} —")

    facts = [{"label": OFF_CATALOG_BOTTLE, "state": state, "axis": axes[0]}]
    bottles = off_catalog_bottles(facts)

    if state == "NOT_IN_CATALOG":
        assert bottles == [OFF_CATALOG_BOTTLE], "gate should fire for a confirmed-absent bottle"
        directive = off_catalog_directive(bottles)
        assert "OFF-CATALOG BOTTLE" in directive and OFF_CATALOG_BOTTLE in directive
        msg = _build_user_message([], {**resolved, "flavors": [], "avoid": [],
                                       "budget_min": 10.0, "budget_max": 50.0,
                                       "availability_facts": facts})
        assert "OFF-CATALOG BOTTLE" in msg, "directive did not reach the built user message"
        print(f"  gate fired — web_search tool would be attached "
              f"(allowed_domains={WEB_SEARCH_TOOL['allowed_domains']})")
    else:
        # If this specific bottle is ever actually stocked, the test's premise
        # is stale rather than the gate being broken -- print, don't fail loud.
        print(f"  NOTE: bottle resolved {state}, not NOT_IN_CATALOG -- gate correctly "
              f"did not fire. Pick a different OFF_CATALOG_BOTTLE if this persists.")
        assert bottles == []

    print("OK — off-catalog web search gate verified against live inventory")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd backend && /usr/bin/python3 -m scripts.verify_web_search_gate`
Expected: `OK — off-catalog web search gate verified against live inventory` (or the NOTE branch, which also exits 0 — if that branch prints, re-run after picking a different `OFF_CATALOG_BOTTLE` value that's more obviously not in a Texas/Tennessee/Carolina retail catalog before considering this task done)

- [ ] **Step 3: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app
git add backend/scripts/verify_web_search_gate.py
git commit -m "test: acceptance script for the off-catalog web search gate"
```

---

## Task 6: Full suite + wrap-up

- [ ] **Step 1: Run the full fast backend suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS, all tests (no regressions in any other module)

- [ ] **Step 2: Confirm the design's cost tradeoff is visible in logs (manual spot-check, not a test)**

The `CLAUDE CACHE | read=... write=... uncached=...` log line (existing, `claude_client.py`) will show a cache write (not a hit) on any turn where `off_catalog` is non-empty, because the `tools` array differs from the ordinary-turn shape. This is expected per the design doc's "Known cost tradeoff" section — no action needed, just confirm you understand why if you see it in the mini's logs after this ships.

- [ ] **Step 3: Final commit / hand off**

No further action beyond Task 5's commit unless the full-suite run in Step 1 surfaces something — in which case fix and commit again before considering this plan complete.
