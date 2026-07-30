# Availability Oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make false-absence claims structurally impossible — absence becomes a deterministic computed fact, and the prompt may only assert absence under `NOT_IN_CATALOG`.

**Architecture:** New `recommendation/availability.py` (pure state logic + a parallel count-query layer). Counts fire early in `recommend.py`; states finalize at prompt-build time against the final `top`. `claude_client.py` renders a fact block, gains three licence rules, loses the denial phrase and the two ad-hoc flags. A post-stream tripwire alerts if the narrative contradicts a fact.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), supabase-py (sync), `concurrent.futures.ThreadPoolExecutor`, pytest.

**Env:** Backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`. **Run the whole test FILE before committing** (a `-k` filter has twice hidden a module-scope name collision — and when appending tests, namespace new fixtures, e.g. `_AV_NEARBY`, not `_NEARBY`).

**Reference:** spec `docs/superpowers/specs/2026-07-30-availability-oracle-design.md`; audit `docs/recommendation-architecture-audit.md`.

**CRITICAL DESIGN PROPERTY — bias to over-matching.** The oracle's predicates must be deliberately BROAD. Over-counting is safe (we merely decline to claim absence); under-counting reproduces the exact false-absence bug being eliminated. When in doubt, match more.

**Key existing shapes:**
- `_SYSTEM_PROMPT` denial bullet: `claude_client.py:131` ("…say what you *can* see doesn't match (\"nothing matching that turned up nearby\")…").
- Flags to retire: `claude_client.py:334-345` (`named_bottle`/`named_bottle_found`), `:357-368` (`requested_retailer`/`retailer_has_fit`); set at `recommend.py:450-451` and `:493-494`.
- `recommend.py`: `detected_store`/`detected_retailer` ~line 341-342; `event_gen` builds the prompt via `stream_recommendations(top, resolved, …)`; `[DONE]` + session persistence at the end of `event_gen`.
- Slack pattern to mirror (urllib POST, `SLACK_WEBHOOK_URL` from env): `scripts/backfill_grapes.py:85`.

---

### Task 1: Pure core — `availability.py`

**Files:**
- Create: `backend/recommendation/availability.py`
- Test: `backend/tests/test_availability.py`

- [ ] **Step 1: Write the failing tests**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.availability import (
    axes_from_intent, derive_state, count_shortlisted, format_fact_block,
    NOT_IN_CATALOG, PRESENT_OUT_OF_BUDGET, PRESENT_SHORTLISTED,
    PRESENT_NOT_SHORTLISTED, UNMEASURED,
)


def _res(**kw):
    base = {"regions": [], "grapes": [], "wine_type": None, "wine_name": None}
    base.update(kw)
    return base


# --- derive_state precedence ---
def test_state_unmeasured_beats_everything():
    assert derive_state(0, 0, 0, stale=True) == UNMEASURED
    assert derive_state(9, 9, 9, stale=True) == UNMEASURED


def test_state_not_in_catalog_only_when_total_zero():
    assert derive_state(0, 0, 0, stale=False) == NOT_IN_CATALOG


def test_state_out_of_budget():
    assert derive_state(3, 0, 0, stale=False) == PRESENT_OUT_OF_BUDGET


def test_state_shortlisted_and_not_shortlisted():
    assert derive_state(10, 8, 2, stale=False) == PRESENT_SHORTLISTED
    assert derive_state(10, 8, 0, stale=False) == PRESENT_NOT_SHORTLISTED


# --- axes_from_intent ---
def test_axes_each_named_kind():
    axes = axes_from_intent(_res(regions=["Barolo"], grapes=["Nebbiolo"], wine_type="red"))
    kinds = {(a["kind"], a["value"]) for a in axes}
    assert ("place", "Barolo") in kinds
    assert ("grape", "Nebbiolo") in kinds
    assert ("type", "red") in kinds
    assert all(a["scope"] is None for a in axes)


def test_axes_empty_when_nothing_named():
    assert axes_from_intent(_res()) == []


def test_axes_compound_adds_scoped_copy():
    axes = axes_from_intent(_res(regions=["Barolo"]), scope_label="Geraldine's",
                            scope_store_ids=["s1"])
    scoped = [a for a in axes if a["scope"] == "Geraldine's"]
    unscoped = [a for a in axes if a["scope"] is None]
    assert len(scoped) == 1 and scoped[0]["store_ids"] == ["s1"]
    assert len(unscoped) == 1            # both the nearby and the scoped fact


def test_axes_scope_only_when_no_content_axis():
    axes = axes_from_intent(_res(), scope_label="H-E-B", scope_store_ids=["s1"])
    assert len(axes) == 1
    assert axes[0]["kind"] == "scope" and axes[0]["scope"] == "H-E-B"


def test_axes_are_capped():
    axes = axes_from_intent(_res(regions=[f"R{i}" for i in range(10)]))
    assert len(axes) <= 6


# --- count_shortlisted ---
def test_count_shortlisted_matches_subregion_and_accent():
    top = [{"region": "Bordeaux", "sub_region": "Pauillac", "name": "X"},
           {"region": "Rhône", "name": "Y"}]
    assert count_shortlisted({"kind": "place", "value": "Pauillac"}, top) == 1
    assert count_shortlisted({"kind": "place", "value": "Rhone"}, top) == 1   # accent-folded


def test_count_shortlisted_grape_and_name():
    top = [{"varietal": "Nebbiolo", "grapes": ["Nebbiolo"], "name": "Barolo DOCG"}]
    assert count_shortlisted({"kind": "grape", "value": "Nebbiolo"}, top) == 1
    assert count_shortlisted({"kind": "name", "value": "Barolo"}, top) == 1


# --- format_fact_block ---
def test_format_empty_is_blank():
    assert format_fact_block([]) == ""


def test_format_renders_state_and_prices():
    block = format_fact_block([
        {"label": "Barolo x Geraldine's", "state": PRESENT_OUT_OF_BUDGET,
         "total": 3, "in_budget": 0, "min_price": 59, "max_price": 110},
    ])
    assert "Barolo x Geraldine's" in block
    assert "3" in block and "59" in block and "110" in block
    assert PRESENT_OUT_OF_BUDGET in block


def test_format_not_in_catalog_is_the_only_absence():
    block = format_fact_block([{"label": "Muscadet", "state": NOT_IN_CATALOG,
                                "total": 0, "in_budget": 0}])
    assert NOT_IN_CATALOG in block
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the pure core**

Create `backend/recommendation/availability.py`:

```python
"""Availability oracle — absence as a deterministic computed fact.

The recommendation shortlist is a bounded, ranked, diversity-capped sample; it can
answer "what should I recommend?" but structurally CANNOT answer "what exists nearby?".
This module answers the second question by COUNTING full nearby inventory, bypassing
every stage that narrows the shortlist (limits, budget, staleness, enrichment, type gate).

Bias to OVER-matching: over-counting merely declines to claim absence, while
under-counting reproduces the false-absence bug this exists to eliminate.
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional

NOT_IN_CATALOG = "NOT_IN_CATALOG"
PRESENT_OUT_OF_BUDGET = "PRESENT_OUT_OF_BUDGET"
PRESENT_NOT_SHORTLISTED = "PRESENT_NOT_SHORTLISTED"
PRESENT_SHORTLISTED = "PRESENT_SHORTLISTED"
UNMEASURED = "UNMEASURED"

_MAX_AXES = 6          # bounds latency/cost per request


def _fold(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def derive_state(total: int, in_budget: int, shortlisted_n: int,
                 stale: bool = False) -> str:
    """The five-state vocabulary, in precedence order. `NOT_IN_CATALOG` is the ONLY
    state that licenses an absence sentence in the narrative."""
    if stale:
        return UNMEASURED
    if not total:
        return NOT_IN_CATALOG
    if not in_budget:
        return PRESENT_OUT_OF_BUDGET
    if shortlisted_n > 0:
        return PRESENT_SHORTLISTED
    return PRESENT_NOT_SHORTLISTED


def axes_from_intent(resolved: Dict[str, Any],
                     scope_label: Optional[str] = None,
                     scope_store_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """The constraints the user actually named, as queryable axes. When a retailer or
    store is named, each content axis also gets a scoped copy (so "Barolo at Geraldine's"
    yields both the nearby and the Geraldine's fact); a scope named with no content axis
    yields a scope-only axis. Empty when nothing concrete was named — no axes, no
    queries, no added latency."""
    axes: List[Dict[str, Any]] = []

    def add(kind: str, value: str) -> None:
        if not value:
            return
        axes.append({"kind": kind, "value": str(value), "scope": None, "store_ids": None})

    for r in (resolved.get("regions") or []):
        add("place", r)
    if not (resolved.get("regions") or []) and resolved.get("region"):
        add("place", resolved["region"])
    for g in (resolved.get("grapes") or []):
        add("grape", g)
    if resolved.get("wine_type"):
        add("type", resolved["wine_type"])
    if resolved.get("wine_name"):
        add("name", resolved["wine_name"])

    if scope_label:
        scoped = [dict(a, scope=scope_label, store_ids=scope_store_ids) for a in axes]
        if scoped:
            axes = axes + scoped
        else:
            axes = [{"kind": "scope", "value": scope_label, "scope": scope_label,
                     "store_ids": scope_store_ids}]
    return axes[:_MAX_AXES]


def _cand_text(c: Dict[str, Any]) -> str:
    parts = [c.get("region"), c.get("sub_region"), c.get("country"),
             c.get("varietal"), c.get("name")]
    parts += list(c.get("grapes") or [])
    return " | ".join(_fold(p) for p in parts if p)


def count_shortlisted(axis: Dict[str, Any], top: List[Dict[str, Any]]) -> int:
    """How many of the FINAL candidates satisfy this axis (in-memory, free)."""
    v = _fold(axis.get("value"))
    if not v:
        return 0
    if axis.get("kind") == "type":
        return sum(1 for c in top if _fold(c.get("wine_type")) == v)
    if axis.get("kind") == "scope":
        return sum(1 for c in top if v in _fold(c.get("retailer")))
    n = 0
    for c in top:
        if axis.get("scope") and v not in _fold(c.get("retailer")):
            pass
        if v in _cand_text(c):
            n += 1
    return n


_SCRIPTS = {
    NOT_IN_CATALOG: "nothing nearby matches this — this is the ONLY axis you may call absent",
    PRESENT_OUT_OF_BUDGET: "exists nearby but nothing within budget — name the count and price range",
    PRESENT_NOT_SHORTLISTED: "exists nearby but none made this shortlist — never call it absent",
    PRESENT_SHORTLISTED: "present in the listings below — must appear in your picks",
    UNMEASURED: "not measurable (stale retailer data or unfilterable attribute) — say you can't confirm",
}


def format_fact_block(facts: List[Dict[str, Any]]) -> str:
    """Render the computed facts for the prompt. Empty string when there are none."""
    if not facts:
        return ""
    lines = []
    for f in facts:
        bits = [f"{f.get('label')}: [{f.get('state')}]"]
        if f.get("total") is not None:
            bits.append(f"{f['total']} nearby")
        if f.get("in_budget") is not None:
            bits.append(f"{f['in_budget']} in budget")
        if f.get("min_price") is not None and f.get("max_price") is not None:
            bits.append(f"${f['min_price']:.0f}-${f['max_price']:.0f}")
        lines.append("- " + ", ".join(bits) + f"  ({_SCRIPTS.get(f.get('state'), '')})")
    return ("\n\n[VERIFIED AVAILABILITY — these are counted facts about full nearby "
            "inventory, not the listings below. They override any impression the listings "
            "give you.]\n" + "\n".join(lines))
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/availability.py backend/tests/test_availability.py
git commit -m "feat(availability): pure oracle core — five-state derivation, axes, fact block"
```

---

### Task 2: Count-query layer (parallel I/O)

**Files:**
- Modify: `backend/recommendation/availability.py`

- [ ] **Step 1: Add `fetch_axis_counts`**

Append to `availability.py`:

```python
def _axis_or_clause(axis: Dict[str, Any]) -> Optional[str]:
    """The postgrest `or_` predicate for an axis, deliberately BROAD (over-matching is
    safe; under-matching causes false absence). None => no wines-level filter."""
    v = (axis.get("value") or "").replace(",", " ").strip()
    if not v:
        return None
    kind = axis.get("kind")
    if kind == "scope":
        return None                      # store_ids alone scope this axis
    if kind == "type":
        # intent enum says 'rose'; the column stores 'rosé' (1,017 rows vs 0) — match both
        vals = {v, v.replace("rose", "rosé")} if v.startswith("rose") else {v}
        return ",".join(f"wine_type.eq.{t}" for t in sorted(vals))
    if kind == "grape":
        return (f"varietal.ilike.%{v}%,name.ilike.%{v}%,"
                f'grapes.cs.["{v.title()}"],grapes.cs.["{v}"]')
    # place / name: the full union, INCLUDING sub_region (never queried elsewhere today)
    return (f"region.ilike.%{v}%,sub_region.ilike.%{v}%,country.ilike.%{v}%,"
            f"varietal.ilike.%{v}%,name.ilike.%{v}%")


def fetch_axis_counts(supabase, axes: List[Dict[str, Any]], nearby_store_ids: List[str],
                      budget_max: float) -> Dict[str, Dict[str, Any]]:
    """Count each axis against FULL nearby inventory — no limit, no staleness, no
    enrichment gate, no type gate. Returns {axis_key: {total, in_budget, min_price,
    max_price}}. Fails open to {} on any error (never breaks a recommendation)."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(axis: Dict[str, Any]) -> Any:
        store_ids = axis.get("store_ids") or nearby_store_ids
        clause = _axis_or_clause(axis)

        def _q(with_budget: bool):
            q = (supabase.table("retail_inventory").select("price", count="exact")
                 .in_("store_ref", store_ids).eq("in_stock", True))
            if clause:
                q = q.or_(clause, reference_table="wines")
            if with_budget:
                q = q.lte("price", budget_max)
            return q.limit(1).execute()

        total = _q(False).count or 0
        in_budget = (_q(True).count or 0) if total else 0
        out = {"total": total, "in_budget": in_budget,
               "min_price": None, "max_price": None}
        if total and not in_budget:      # only then do we need the price range
            def _edge(desc: bool):
                q = (supabase.table("retail_inventory").select("price")
                     .in_("store_ref", store_ids).eq("in_stock", True))
                if clause:
                    q = q.or_(clause, reference_table="wines")
                return q.order("price", desc=desc).limit(1).execute().data or []
            lo, hi = _edge(False), _edge(True)
            if lo:
                out["min_price"] = lo[0]["price"]
            if hi:
                out["max_price"] = hi[0]["price"]
        return out

    if not axes:
        return {}
    try:
        with ThreadPoolExecutor(max_workers=min(6, len(axes))) as ex:
            results = list(ex.map(_one, axes))
        return {axis_key(a): r for a, r in zip(axes, results)}
    except Exception:
        return {}


def axis_key(axis: Dict[str, Any]) -> str:
    return f"{axis.get('kind')}:{axis.get('value')}:{axis.get('scope') or ''}"


def axis_label(axis: Dict[str, Any]) -> str:
    base = axis.get("value")
    return f"{base} at {axis['scope']}" if axis.get("scope") else str(base)
```

Also export `axis_key`/`axis_label` (they're module-level, nothing more needed).

- [ ] **Step 2: Smoke-test against live data (the Barolo case)**

Run:
```bash
cd backend && /usr/bin/python3 -c "
from db import get_supabase_client
from utils.geo import find_nearby_store_ids
from recommendation.availability import axes_from_intent, fetch_axis_counts, derive_state, axis_key
sb=get_supabase_client(); nearby=find_nearby_store_ids('78209', sb)
meta=sb.table('stores').select('id,retailer_name').in_('id',nearby).execute().data
ger=[s['id'] for s in meta if 'Geraldine' in (s.get('retailer_name') or '')]
axes=axes_from_intent({'regions':['Barolo'],'grapes':[],'wine_type':None,'wine_name':None},
                      scope_label=\"Geraldine's\", scope_store_ids=ger)
counts=fetch_axis_counts(sb, axes, nearby, 50.0)
for a in axes:
    c=counts[axis_key(a)]
    print(a['kind'], a['value'], 'scope=', a['scope'], c, derive_state(c['total'], c['in_budget'], 0))
" 2>&1 | grep -vE "NotOpenSSL|warnings.warn"
```
Expected: the Geraldine's-scoped Barolo axis reports `total=3, in_budget=0` with a `$59–$110` range and `PRESENT_OUT_OF_BUDGET`; the unscoped one reports a larger total. Record the timing impression (should be well under ~1s for 2 axes).

- [ ] **Step 3: Run the availability tests + commit**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q` → PASS.

```bash
git add backend/recommendation/availability.py
git commit -m "feat(availability): parallel count-query layer over full nearby inventory"
```

---

### Task 3: Wire into `recommend.py` + retire the ad-hoc flags

**Files:**
- Modify: `backend/api/routers/recommend.py`

- [ ] **Step 1: Import + compute counts early**

Add near the other `recommendation.*` imports:
```python
from recommendation.availability import (axes_from_intent, fetch_axis_counts,
                                         count_shortlisted, derive_state,
                                         axis_key, axis_label)
```

After `detected_retailer = detect_retailer(...)` (~line 342) add:
```python
    _scope_label = (detected_store or {}).get("name") if detected_store else detected_retailer
    _scope_ids = ([detected_store["id"]] if detected_store
                  else retailer_to_stores.get(detected_retailer) if detected_retailer else None)
    _axes = axes_from_intent(resolved, scope_label=_scope_label, scope_store_ids=_scope_ids)
    _axis_counts = fetch_axis_counts(supabase, _axes, nearby_ids, req.budget_max) if _axes else {}
    if _axes:
        logger.info("AVAILABILITY | axes=%d counted=%d", len(_axes), len(_axis_counts))
```

- [ ] **Step 2: Finalize states at prompt-build time (inside `event_gen`)**

In `event_gen`, immediately before `gen = stream_recommendations(top, resolved, …)`, add:
```python
        facts = []
        for a in _axes:
            c = _axis_counts.get(axis_key(a))
            if not c:
                continue
            n_short = count_shortlisted(a, top)
            facts.append({
                "label": axis_label(a),
                "state": derive_state(c["total"], c["in_budget"], n_short),
                "total": c["total"], "in_budget": c["in_budget"],
                "min_price": c.get("min_price"), "max_price": c.get("max_price"),
            })
        resolved["availability_facts"] = facts
        if facts:
            logger.info("AVAILABILITY | %s",
                        {f["label"]: f["state"] for f in facts})
```

- [ ] **Step 3: Retire the two ad-hoc flags**

Delete these lines (the oracle's facts replace them):
- `resolved["requested_retailer"] = detected_retailer` and `resolved["retailer_has_fit"] = bool(retailer_pool)` (~450-451). **Keep** the `retailer_pool` filter itself and its log line — only the two `resolved[...]` assignments go.
- `resolved["named_bottle"] = resolved.get("wine_name")` and `resolved["named_bottle_found"] = bool(named)` (~493-494).

- [ ] **Step 4: Verify import + suite**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend"
/usr/bin/python3 -m pytest tests/test_recommend_api.py -q
```
Expected: import clean; suite passes (the claude_client directive tests for the retired flags are updated in Task 4 — if any fail here, note them and proceed).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py
git commit -m "feat(recommend): compute availability facts; retire named_bottle_found/retailer_has_fit"
```

---

### Task 4: Prompt binding — fact block, licence rules, delete the denial phrase

**Files:**
- Modify: `backend/recommendation/claude_client.py`
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests (and delete the retired-flag tests)**

Delete the now-obsolete tests: `test_named_found_directive_present`, `test_named_not_found_hedge_directive`, `test_no_named_bottle_no_directive`, `test_retailer_directive_has_fit`, `test_retailer_directive_no_fit_is_honest`, `test_no_retailer_directive_when_unset`, `test_retailer_has_fit_directive_demands_fresh_picks`, `test_retailer_no_fit_directive_does_not_demand_picks`. Add:

```python
from recommendation.availability import (PRESENT_OUT_OF_BUDGET, PRESENT_SHORTLISTED,
                                         NOT_IN_CATALOG)


def test_denial_phrase_is_gone_from_system_prompt():
    from recommendation.claude_client import _SYSTEM_PROMPT
    assert "nothing matching that turned up nearby" not in _SYSTEM_PROMPT


def test_fact_block_rendered_with_licence_rules():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent(
        availability_facts=[{"label": "Barolo at Geraldine's", "state": PRESENT_OUT_OF_BUDGET,
                             "total": 3, "in_budget": 0, "min_price": 59, "max_price": 110}]))
    assert "Barolo at Geraldine's" in msg
    assert PRESENT_OUT_OF_BUDGET in msg
    low = msg.lower()
    assert "not_in_catalog" in low          # the licence rule names the only absence state
    assert "must appear in your picks" in low or "must appear in" in low


def test_no_fact_block_when_no_facts():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent())
    assert "VERIFIED AVAILABILITY" not in msg
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k "denial or fact_block" -q`
Expected: FAIL.

- [ ] **Step 3: Delete the denial phrase from `_SYSTEM_PROMPT`**

Replace the bullet at `claude_client.py:131`:
```
- The wines listed are what surfaced for this search near the user — not the store's entire shelf. If nothing fits, say what you *can* see doesn't match ("nothing matching that turned up nearby") and offer the closest alternative; never claim a wine or style is absent from a store's full inventory.
```
with:
```
- The wines listed are what surfaced for this search near the user — NOT the store's full shelf. You therefore CANNOT tell from this list whether something exists nearby. Never say a wine, style, grape, region or retailer is unavailable, absent, "not in stock", or that "nothing turned up" based on this list. If a VERIFIED AVAILABILITY block is present, only it licenses statements about what does or does not exist. If a listing is a poor fit, say it is a poor fit — that is a different claim from saying it does not exist.
```

- [ ] **Step 4: Render the fact block + licence rules**

In `_build_user_message`, after the `retailer_directive` block, add:
```python
    from recommendation.availability import format_fact_block, NOT_IN_CATALOG
    fact_block = format_fact_block(intent.get("availability_facts") or [])
    availability_rules = ""
    if fact_block:
        availability_rules = (
            f"\n\nAVAILABILITY RULES (these override the listings):"
            f"\n1. You may state that something is unavailable ONLY for an axis marked "
            f"{NOT_IN_CATALOG}. For every other state use its script — never call it absent."
            f"\n2. Any listing satisfying a constraint the user literally named MUST appear in your "
            f"picks (the 'never pad' rule applies to unrequested filler, never to a constraint match)."
            f"\n3. Never contradict a verified fact."
        )
```
Then delete the `named_directive` and `retailer_directive` blocks entirely, and update the `return (...)` assembly: remove `f"{named_directive}"` and `f"{retailer_directive}"`, add `f"{fact_block}"` and `f"{availability_rules}"` (fact block before the rules).

- [ ] **Step 5: Run the whole file**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat(prompt): verified-availability fact block + absence licence rules; drop denial phrase"
```

---

### Task 5: Tripwire, acceptance, docs

**Files:**
- Modify: `backend/api/routers/recommend.py` (tripwire)
- Create: `backend/tests/test_false_absence_tripwire.py`, `backend/scripts/verify_availability_oracle.py`
- Modify: `CLAUDE.md`, `docs/reference/recommendation.md`

- [ ] **Step 1: Write the tripwire test**

Create `backend/tests/test_false_absence_tripwire.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from api.routers.recommend import _false_absence_suspects
from recommendation.availability import (PRESENT_NOT_SHORTLISTED, NOT_IN_CATALOG,
                                         PRESENT_SHORTLISTED)


def test_fires_when_absence_language_contradicts_present_fact():
    facts = [{"label": "Barolo", "state": PRESENT_NOT_SHORTLISTED}]
    hits = _false_absence_suspects("There are no Barolos nearby, sorry.", facts)
    assert hits


def test_silent_when_fact_is_not_in_catalog():
    facts = [{"label": "Muscadet", "state": NOT_IN_CATALOG}]
    assert not _false_absence_suspects("There are no Muscadets nearby.", facts)


def test_silent_without_absence_language():
    facts = [{"label": "Barolo", "state": PRESENT_SHORTLISTED}]
    assert not _false_absence_suspects("The Barolo is a lovely choice tonight.", facts)


def test_silent_with_no_facts():
    assert not _false_absence_suspects("There is nothing here.", [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_false_absence_tripwire.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement the tripwire**

In `recommend.py`, at module level:
```python
_ABSENCE_PAT = re.compile(
    r"\b(no|none|nothing|not any|isn'?t any|aren'?t any|don'?t (?:have|stock|carry)|"
    r"doesn'?t (?:have|stock|carry)|not available|not in stock|unavailable|"
    r"couldn'?t find|could not find|didn'?t turn up|nothing turned up)\b", re.I)


def _false_absence_suspects(narrative: str, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Facts that say PRESENT_* while the narrative used absence language. A non-empty
    result means Somm may have just told the user something isn't available when it is."""
    if not narrative or not facts:
        return []
    if not _ABSENCE_PAT.search(narrative):
        return []
    return [f for f in facts if str(f.get("state", "")).startswith("PRESENT_")]


def _notify_slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass
```
(Ensure `os`, `json`, `re`, `urllib.request` are imported at the top of the file — add any that are missing.)

In `event_gen`, inside the existing post-`[DONE]` block (alongside session persistence), add — wrapped so it can never break a response:
```python
        try:
            narrative = "".join(_result["narrative"])
            suspects = _false_absence_suspects(narrative, resolved.get("availability_facts") or [])
            if suspects:
                logger.warning("FALSE_ABSENCE_SUSPECT | zip=%s msg=%r facts=%s",
                               req.zip_code, req.message[:120],
                               [(s["label"], s["state"]) for s in suspects])
                _notify_slack(
                    f":rotating_light: FALSE_ABSENCE_SUSPECT zip={req.zip_code}\n"
                    f"ask: {req.message[:200]}\n"
                    f"contradicted: {[(s['label'], s['state']) for s in suspects]}\n"
                    f"narrative: {narrative[:400]}")
        except Exception:
            pass
```

- [ ] **Step 4: Run the tripwire tests + full fast suite**

Run:
```bash
cd backend && /usr/bin/python3 -m pytest tests/test_false_absence_tripwire.py -q
/usr/bin/python3 -m pytest tests/ -m "not integration" -q
```
Expected: PASS.

- [ ] **Step 5: Acceptance script**

Create `backend/scripts/verify_availability_oracle.py` — replay the real cases end to end:
```python
"""Acceptance for the availability oracle. Run from backend/:
    /usr/bin/python3 -m scripts.verify_availability_oracle"""
from db import get_supabase_client
from utils.geo import find_nearby_store_ids
from recommendation.availability import (axes_from_intent, fetch_axis_counts, derive_state,
                                         axis_key, axis_label, NOT_IN_CATALOG,
                                         PRESENT_OUT_OF_BUDGET)

ZIP = "78209"


def facts_for(sb, nearby, resolved, scope_label=None, scope_ids=None, budget=50.0):
    axes = axes_from_intent(resolved, scope_label=scope_label, scope_store_ids=scope_ids)
    counts = fetch_axis_counts(sb, axes, nearby, budget)
    out = []
    for a in axes:
        c = counts.get(axis_key(a))
        if c:
            out.append((axis_label(a), derive_state(c["total"], c["in_budget"], 0), c))
    return out


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    meta = sb.table("stores").select("id,retailer_name").in_("id", nearby).execute().data
    ger = [s["id"] for s in meta if "Geraldine" in (s.get("retailer_name") or "")]

    print("— Barolo x Geraldine's (the bug-#6 case) —")
    got = facts_for(sb, nearby, {"regions": ["Barolo"]}, "Geraldine's", ger)
    for label, state, c in got:
        print(f"  {label}: {state} total={c['total']} in_budget={c['in_budget']} "
              f"range={c.get('min_price')}-{c.get('max_price')}")
    scoped = [g for g in got if "Geraldine" in g[0]]
    assert scoped, "expected a Geraldine's-scoped fact"
    assert scoped[0][1] == PRESENT_OUT_OF_BUDGET, f"expected out-of-budget, got {scoped[0][1]}"

    print("— a genuinely absent axis —")
    absent = facts_for(sb, nearby, {"regions": ["Ktimalandia Nowhere"]})
    print(f"  {absent}")
    assert absent and absent[0][1] == NOT_IN_CATALOG

    print("OK — oracle states verified against live inventory")


if __name__ == "__main__":
    main()
```

Run: `cd backend && /usr/bin/python3 -m scripts.verify_availability_oracle 2>&1 | grep -vE "NotOpenSSL|warnings.warn"`
Expected: the Geraldine's Barolo axis prints `PRESENT_OUT_OF_BUDGET` with a `$59–$110` range; the nonsense axis prints `NOT_IN_CATALOG`; `OK`.

- [ ] **Step 6: Docs**

- `docs/reference/recommendation.md`: new "Availability oracle" section — the two-questions split, the five states, what the predicate deliberately bypasses, the over-match bias, the prompt licence rules, the tripwire, and that `named_bottle_found`/`retailer_has_fit` are retired.
- `CLAUDE.md`: new roadmap item 37 (✅ availability oracle landed 2026-07-30), referencing `docs/recommendation-architecture-audit.md` for the remaining plan items #1, #3–#9.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_false_absence_tripwire.py backend/scripts/verify_availability_oracle.py CLAUDE.md docs/reference/recommendation.md
git commit -m "feat(recommend): false-absence tripwire + oracle acceptance + docs"
```

---

## Self-Review Notes

- **Spec coverage:** §1 module→T1/T2; §2 wiring→T3; §3 prompt→T4; §4 tripwire→T5; testing→each task + T5 acceptance. All covered.
- **Type consistency:** `derive_state(total, in_budget, shortlisted_n, stale)`, `axes_from_intent(resolved, scope_label, scope_store_ids)`, `fetch_axis_counts(supabase, axes, nearby_store_ids, budget_max)`, `axis_key`/`axis_label` identical across T1–T3 and the acceptance script. Fact dicts use the same keys (`label,state,total,in_budget,min_price,max_price`) in T1 rendering, T3 construction, T4 tests, T5 tripwire.
- **Fail-open everywhere:** `fetch_axis_counts` returns `{}` on error; no axes → no queries → no latency; tripwire wrapped in try/except; the oracle never blocks a recommendation.
- **Over-match bias honored:** union predicates including `sub_region`; grape matches varietal/name/both jsonb casings; rosé enum drift handled. A false `NOT_IN_CATALOG` is the one outcome the predicates are designed to avoid.
- **Retirement is complete:** both flags removed at the producer (T3) and consumer (T4), with their tests deleted rather than left asserting dead behavior.
