# Producer-Facts Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the model recalling a producer's region when our own catalog knows it — "Epoch is a Texas Hill Country producer" (it is Paso Robles).

**Architecture:** A new `recommendation/producer_facts.py` with a pure, self-validating core (bounded + region-concentrated) and one catalog-wide query; wired into `recommend.py` alongside the availability facts; rendered as a `[VERIFIED PRODUCER]` section with a hedging rule. Plus a report-only data-contradiction detector.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), supabase-py, pytest.

**Env:** Backend from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`. **Run whole test FILES before committing** (a `-k` filter has hidden module-scope fixture collisions repeatedly; namespace new fixtures `_PF_*`).

**Reference:** spec `docs/superpowers/specs/2026-08-08-producer-facts-design.md`.

**Existing shapes to reuse:**
- `recommendation/candidate_filters.py` → `significant_name_tokens(name)` (strips generic wine words).
- `recommendation/availability.py` → `_fold`, `format_fact_block`, and the `fetch_axis_counts` pattern (bounded query, fail-open with `logger.exception`).
- `api/routers/recommend.py` → availability facts are computed early (~line 350, `_axes`/`_axis_counts`) and finalized inside `event_gen` before `stream_recommendations`; `resolved["availability_facts"]` is set there.
- `recommendation/claude_client.py` → `format_fact_block(...)` + `availability_rules` are assembled into the returned message; add the producer section beside them.

**Measured constants (do not "tune" without re-measuring):** `_PRODUCER_MAX_ROWS = 60`, `_PRODUCER_MIN_CONCENTRATION = 0.5`, minimum 2 rows with a region. Epoch is 3/4 = 0.75 and must pass; a generic token like "estate" must not.

---

### Task 1: Pure core — `producer_facts.py`

**Files:**
- Create: `backend/recommendation/producer_facts.py`
- Test: `backend/tests/test_producer_facts.py`

- [ ] **Step 1: Write the failing tests**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.producer_facts import (summarize_producer, format_producer_block,
                                           _PRODUCER_MAX_ROWS)


def _PF_rows(*pairs):
    return [{"name": f"W{i}", "region": r, "country": c}
            for i, (r, c) in enumerate(pairs)]


def test_majority_outvotes_a_single_bad_row():
    """The Epoch shape: 3 Paso Robles + 1 mislabelled Ribeira Sacra."""
    rows = _PF_rows(("Paso Robles", "United States"), ("Paso Robles", "United States"),
                    ("Paso Robles", "United States"), ("Ribeira Sacra", "Spain"))
    f = summarize_producer("epoch", rows)
    assert f is not None
    assert f["regions"][0][0] == "Paso Robles"
    assert f["regions"][0][1] == 3
    assert f["total"] == 4


def test_scattered_token_emits_nothing():
    """A generic word matches unrelated wines everywhere — not a producer."""
    rows = _PF_rows(("Napa Valley", "US"), ("Rioja", "Spain"), ("Tuscany", "Italy"),
                    ("Mendoza", "Argentina"), ("Loire", "France"), ("Douro", "Portugal"))
    assert summarize_producer("estate", rows) is None


def test_too_many_rows_emits_nothing():
    rows = _PF_rows(*[("Napa Valley", "US")] * (_PRODUCER_MAX_ROWS + 1))
    assert summarize_producer("reserve", rows) is None


def test_needs_at_least_two_regioned_rows():
    assert summarize_producer("solo", _PF_rows(("Paso Robles", "US"))) is None
    assert summarize_producer("none", []) is None


def test_multi_region_producer_keeps_both_with_counts():
    rows = _PF_rows(*([("Napa Valley", "US")] * 9 + [("Alexander Valley", "US")] * 2))
    f = summarize_producer("silver oak", rows)
    assert f["regions"][0] == ("Napa Valley", 9)
    assert f["regions"][1] == ("Alexander Valley", 2)


def test_rows_without_a_region_do_not_break_it():
    rows = _PF_rows(("Paso Robles", "US"), ("Paso Robles", "US"), (None, None))
    f = summarize_producer("epoch", rows)
    assert f and f["regions"][0][0] == "Paso Robles"


def test_format_block_renders_counts_and_is_empty_when_none():
    assert format_producer_block([]) == ""
    block = format_producer_block([
        {"token": "epoch", "regions": [("Paso Robles", 3)], "country": "United States", "total": 4},
    ])
    assert "VERIFIED PRODUCER" in block
    assert "epoch" in block.lower() and "Paso Robles" in block and "3" in block
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_producer_facts.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the pure core**

Create `backend/recommendation/producer_facts.py`:

```python
"""Producer identity as a looked-up fact, not a recalled one.

Somm told a user "Epoch is a Texas Hill Country producer" — it is Paso Robles, and our
own catalog held 4 Epoch rows, three labelled Paso Robles. Same structural mistake as
the false-absence class: the model inferring what we can look up.

Self-validating by design: a token only yields a fact when the wines it matches look
like a real producer — a BOUNDED set that is REGION-CONCENTRATED. A generic word
("estate") matches thousands scattered everywhere and emits nothing, so no maintained
vocabulary is needed and it self-updates with the catalog.
"""
import logging
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PRODUCER_MAX_ROWS = 60          # a producer has a handful; "estate" has thousands
_PRODUCER_MIN_CONCENTRATION = 0.5  # top region must hold >= half the regioned rows
_PRODUCER_MIN_ROWS = 2           # one row is not evidence of a producer
_MAX_PRODUCERS = 2               # bound the prompt block


def _fold(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def summarize_producer(token: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Region summary for the wines a token matched, or None when the match doesn't
    look like a producer. PURE — `rows` come from the caller's query."""
    if not token or not rows or len(rows) > _PRODUCER_MAX_ROWS:
        return None
    regioned = [r for r in rows if (r.get("region") or "").strip()]
    if len(regioned) < _PRODUCER_MIN_ROWS:
        return None
    counts = Counter(r["region"].strip() for r in regioned)
    top_region, top_n = counts.most_common(1)[0]
    if top_n / float(len(regioned)) < _PRODUCER_MIN_CONCENTRATION:
        return None                      # scattered => not a coherent producer
    ctry = Counter((r.get("country") or "").strip()
                   for r in regioned if (r.get("country") or "").strip())
    return {
        "token": token,
        "regions": counts.most_common(2),
        "country": ctry.most_common(1)[0][0] if ctry else None,
        "total": len(rows),
    }


def format_producer_block(facts: List[Dict[str, Any]]) -> str:
    """Render producer facts for the prompt. Empty string when there are none."""
    if not facts:
        return ""
    lines = []
    for f in facts:
        regions = ", ".join(f"{r} ({n} of {f['total']} bottles we carry)"
                            for r, n in (f.get("regions") or []))
        ctry = f" — {f['country']}" if f.get("country") else ""
        lines.append(f"- {f.get('token')}: {regions}{ctry}")
    return ("\n\n[VERIFIED PRODUCER — drawn from our own catalog, not recalled. Use these "
            "regions when you describe the producer.]\n" + "\n".join(lines))
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_producer_facts.py -q`
Expected: PASS (whole file).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/producer_facts.py backend/tests/test_producer_facts.py
git commit -m "feat(producer): self-validating producer-region summary from the catalog"
```

---

### Task 2: The catalog query layer

**Files:**
- Modify: `backend/recommendation/producer_facts.py`

- [ ] **Step 1: Add `fetch_producer_facts`**

Append:

```python
def producer_tokens(message: str, wine_name: Optional[str] = None) -> List[str]:
    """Candidate producer tokens: the parser's wine_name when present, plus the
    message's distinctive tokens. The parser is unreliable here — it returned None for
    "close to epoch in style", the case that produced the hallucination — so the token
    scan is the deterministic floor."""
    from recommendation.candidate_filters import significant_name_tokens
    toks = []
    for t in significant_name_tokens(wine_name) + significant_name_tokens(message):
        if len(t) >= 4 and t not in toks:      # 3-char tokens are too noisy
            toks.append(t)
    return toks[:6]


def fetch_producer_facts(supabase, message: str,
                         wine_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Catalog-WIDE producer lookup: no nearby-store scoping and no price filter.

    Both are load-bearing. Epoch is stocked only in Dallas at $55-$103 while the user
    was in San Antonio — a nearby-scoped or budget-clamped lookup returns nothing in
    exactly the situation where the model falls back on recall.

    Fails open to [] (logged) — never breaks a recommendation."""
    facts: List[Dict[str, Any]] = []
    try:
        for tok in producer_tokens(message, wine_name):
            if len(facts) >= _MAX_PRODUCERS:
                break
            rows = (supabase.table("wines").select("name,region,country")
                    .ilike("name", f"%{tok}%")
                    .limit(_PRODUCER_MAX_ROWS + 1).execute().data or [])
            f = summarize_producer(tok, rows)
            if f:
                facts.append(f)
    except Exception:
        logger.exception("PRODUCER | fact lookup failed — no producer facts this turn")
        return []
    return facts
```

- [ ] **Step 2: Smoke-test against live data**

Run:
```bash
cd backend && /usr/bin/python3 -c "
from db import get_supabase_client
from recommendation.producer_facts import fetch_producer_facts
sb=get_supabase_client()
for m in ['Looking for something from willow creek - close to epoch in style',
          'is the Caymus worth \$80?',
          'something bold and structured please']:
    print(repr(m[:46]), '->', fetch_producer_facts(sb, m))
" 2>&1 | grep -vE "NotOpenSSL|warnings.warn"
```
Expected: the epoch message yields a Paso Robles fact (NOT Texas Hill Country); Caymus yields Napa Valley; the generic message yields `[]`. Report the ACTUAL output — if a generic message produces a fact, the concentration/bound constants need re-measuring, not the test loosening.

- [ ] **Step 3: Run the test file + commit**

```bash
/usr/bin/python3 -m pytest tests/test_producer_facts.py -q
git add backend/recommendation/producer_facts.py
git commit -m "feat(producer): catalog-wide, price-blind producer fact lookup"
```

---

### Task 3: Wire into `recommend.py` + prompt binding

**Files:**
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/recommendation/claude_client.py`
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing prompt tests**

Add to `backend/tests/test_claude_client.py`:

```python
def test_producer_block_renders_with_hedging_rule():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent(
        producer_facts=[{"token": "epoch", "regions": [("Paso Robles", 3)],
                         "country": "United States", "total": 4}]))
    assert "VERIFIED PRODUCER" in msg
    assert "Paso Robles" in msg
    low = msg.lower()
    assert "hedge" in low or "i believe" in low     # the absent-producer rule


def test_no_producer_block_when_no_facts():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent())
    assert "VERIFIED PRODUCER" not in msg
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -q`
Expected: the two new tests FAIL.

- [ ] **Step 3: Render the block + rule in `claude_client.py`**

Import `format_producer_block` from `recommendation.producer_facts` at module level (it imports
only stdlib + `candidate_filters`, so no cycle — verify). In `_build_user_message`, after the
availability fact block, add:

```python
    producer_block = format_producer_block(intent.get("producer_facts") or [])
    producer_rule = ""
    if producer_block:
        producer_rule = (
            "\n4. When a producer appears in VERIFIED PRODUCER, use THAT region — it is drawn "
            "from our catalog, not memory. For a producer that does NOT appear there, you may "
            "share what you know but must hedge (\"I believe Epoch is from Paso Robles\"), never "
            "assert it flatly."
        )
```
Add `f"{producer_block}"` and `f"{producer_rule}"` into the `return (...)` assembly — the block
next to the availability fact block, the rule appended to the availability rules (renumber that
list if needed so the numbering stays sequential).

- [ ] **Step 4: Compute the facts in `recommend.py`**

Add `from recommendation.producer_facts import fetch_producer_facts` to the imports. Next to the
early availability-axes computation (~line 350, where `_axes`/`_axis_counts` are built), add:

```python
    _producer_facts = fetch_producer_facts(supabase, req.message, resolved.get("wine_name"))
    if _producer_facts:
        logger.info("PRODUCER | %s",
                    {f["token"]: f["regions"][0][0] for f in _producer_facts})
```
and inside `event_gen`, alongside `resolved["availability_facts"] = facts`, add:
```python
        resolved["producer_facts"] = _producer_facts
```

- [ ] **Step 5: Verify + run suites**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend, recommendation.claude_client"
/usr/bin/python3 -m pytest tests/test_claude_client.py tests/test_producer_facts.py -q
/usr/bin/python3 -m pytest tests/ -m "not integration" -q
```
Expected: import clean; all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat(recommend): verified producer facts in the prompt + hedging rule"
```

---

### Task 4: Data defects — fix Epoch, build the detector (report only)

**Files:**
- Create: `backend/scripts/detect_region_contradictions.py`
- Create: `backend/scripts/verify_producer_facts.py`

- [ ] **Step 1: Fix the known bad row**

`Epoch Estate Wines Block B Paso Robles 2018` is labelled `region=Ribeira Sacra, country=Spain`.
Correct it to `region=Paso Robles, country=United States` (match its siblings). Use the service
client, target it by exact `id` (look the id up first and print it), and print a before/after.
This is a SINGLE deliberate row edit, not a sweep.

- [ ] **Step 2: Write the detector (REPORT ONLY — no writes)**

Create `backend/scripts/detect_region_contradictions.py`: page all `wines` with
`.order("id")`, and flag rows whose NAME contains a place term that contradicts the `region`/
`country` fields. Build the place vocabulary from the catalog itself
(`recommendation.availability.catalog_terms`) so it needs no maintenance, and require the name's
place to be absent from the row's own region/sub_region/country before flagging.

Print a grouped report (`name | region | country | place found in name`) and a total. **It must
never write.** Add a `--limit` for spot-checking.

- [ ] **Step 3: Run the detector and report**

Run: `cd backend && /usr/bin/python3 -m scripts.detect_region_contradictions 2>&1 | grep -vE "NotOpenSSL|warnings.warn" | head -40`
Report the total and a representative sample. Expected to include the `Walt Blue Jay Pinot Noir
Australian Red Wine` shape (a California wine whose name says Australian). **Do not fix anything
it finds** — per the standing conservative-enrichment rule, a human decides.

- [ ] **Step 4: Acceptance script**

Create `backend/scripts/verify_producer_facts.py`: assert that "epoch" resolves to Paso Robles
(and NOT Texas Hill Country), that "Caymus" resolves to Napa Valley, and that a generic message
produces no facts. Run it and report the actual output.

- [ ] **Step 5: Full suite + commit**

```bash
cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q
git add backend/scripts/detect_region_contradictions.py backend/scripts/verify_producer_facts.py
git commit -m "test+data: fix Epoch Block B region; add report-only contradiction detector"
```

---

### Task 5: Docs

**Files:**
- Modify: `CLAUDE.md` (item 42 → ✅), `docs/reference/recommendation.md`

- [ ] **Step 1: Update the reference doc**

Add a "Producer facts" subsection to `docs/reference/recommendation.md` next to the availability
oracle: why (the Epoch hallucination), the two detection layers and why `wine_name` alone was
insufficient (measured), the self-validating bound + concentration test, majority vote with
counts, catalog-wide/price-blind rationale, the hedging rule, and the report-only detector.

- [ ] **Step 2: Flip roadmap item 42**

Mark item 42 ✅ with the landed summary and the detector's finding count. **Pull before editing
`CLAUDE.md`** — the other machine edits the same roadmap tail and this has already caused a
numbering collision and a merge conflict.

- [ ] **Step 3: Full suites + commit**

```bash
cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q
cd ../frontend && npx vitest run
git add CLAUDE.md docs/reference/recommendation.md
git commit -m "docs: item 42 producer facts landed"
```

---

## Self-Review Notes

- **Spec coverage:** §1 detection→T2 `producer_tokens`; §2 self-validation→T1; §3 majority vote→T1; §4 prompt→T3; §5 data defects→T4; testing→each + T4 acceptance. All covered.
- **Type consistency:** `summarize_producer(token, rows)`, `format_producer_block(facts)`,
  `producer_tokens(message, wine_name)`, `fetch_producer_facts(supabase, message, wine_name)`
  identical across T1–T4. Fact dicts use the same keys (`token, regions, country, total`) in T1
  rendering, T2 construction, T3 tests.
- **Fails open everywhere:** `fetch_producer_facts` → `[]` on error (logged, never silent — the
  lesson from the oracle's PGRST108 near-miss); no tokens → no queries → no latency.
- **Constants are measured, not guessed:** Epoch 3/4 = 0.75 passes the 0.5 concentration bar; a
  generic token scatters and fails it. T2 Step 2 re-measures against live data before wiring.
- **Conservative rule honored:** the detector reports and never writes; only the one known Epoch
  row is edited, deliberately and by id.
