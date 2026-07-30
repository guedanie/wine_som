# Phrasing-Robust Axis Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The availability oracle must emit axes regardless of phrasing, so "nothing from Mendoza right?" can never silently bypass the safety net.

**Architecture:** A catalog-derived term vocabulary (2,292 terms vs 146 curated, 0 probe misses vs 6) powers a deterministic fallback that runs only when the LLM parse yields no content axis. Plus a parser-prompt fix, per-axis failure isolation, and axis dedupe.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), supabase-py, pytest.

**Env:** Backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`. **Run whole test FILES, not `-k` filters, before committing** (a `-k` filter has hidden a module-scope fixture collision twice this session; namespace any new fixtures, e.g. `_AX_*`).

**Reference:** spec `docs/superpowers/specs/2026-07-30-axis-extraction-robustness-design.md`; verification report `docs/oracle-production-verification.md`.

**Current shapes:**
- `recommendation/availability.py`: `_fold`, `derive_state`, `axes_from_intent(resolved, scope_label, scope_store_ids)`, `count_shortlisted`, `format_fact_block`, `_axis_or_clause`, `fetch_axis_counts(supabase, axes, nearby_store_ids, budget_max)` (outer try/except around the whole `ThreadPoolExecutor.map`), `axis_key`, `axis_label`, `_MAX_AXES = 6`.
- `recommendation/intent.py`: `_TOOL` schema + `parse_message` system prompt (already instructs on `wine_name` and `regions`).
- `api/routers/recommend.py`: `_axes = axes_from_intent(resolved, scope_label=_scope_label, scope_store_ids=_scope_ids)` then `_axis_counts = fetch_axis_counts(...)`, both ~line 350.

---

### Task 1: Catalog vocabulary + message scan

**Files:**
- Modify: `backend/recommendation/availability.py`
- Test: `backend/tests/test_availability.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_availability.py` (namespace fixtures `_AX_*`):

```python
from recommendation.availability import terms_in_message, _STOPWORD_TERMS

_AX_TERMS = {"mendoza", "barolo", "montalcino", "brunello di montalcino", "rhone",
             "chablis", "nebbiolo", "red", "wine", "valley"}


def test_terms_longest_match_wins():
    found = terms_in_message("any brunello di montalcino under $50?", _AX_TERMS)
    assert "brunello di montalcino" in found
    assert "montalcino" not in found          # subsumed by the longer match


def test_terms_whole_word_only():
    # 'red' is a stopword anyway, but a substring must never match a longer word
    assert terms_in_message("a barolotto please", {"barolo"}) == []


def test_terms_accent_folded():
    assert "rhone" in terms_in_message("anything from the Rhône?", _AX_TERMS)


def test_terms_stopwords_never_match():
    found = terms_in_message("just a red wine from the valley", _AX_TERMS)
    assert found == []


def test_terms_negative_framing_still_found():
    assert "mendoza" in terms_in_message("nothing from Mendoza right?", _AX_TERMS)


def test_terms_empty_vocab_is_safe():
    assert terms_in_message("anything from Mendoza?", set()) == []


def test_stopwords_cover_generic_catalog_values():
    for w in ("red", "white", "wine", "valley", "other", "blend"):
        assert w in _STOPWORD_TERMS
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement the vocabulary + scan**

Add to `backend/recommendation/availability.py`:

```python
import time

# Generic catalog values that must never be treated as a user constraint.
_STOPWORD_TERMS = {
    "red", "white", "rose", "rosé", "wine", "wines", "red wine", "white wine",
    "rose wine", "sparkling", "dessert", "fortified", "orange", "blend", "red blend",
    "white blend", "valley", "other", "unknown", "n/a", "none", "misc", "assorted",
    "table wine", "usa", "us",
}

_CATALOG_TTL_SECONDS = 3600
_catalog_cache = {"terms": None, "at": 0.0}


def catalog_terms(supabase, ttl: int = _CATALOG_TTL_SECONDS) -> set:
    """Normalized place/grape vocabulary drawn from the catalog itself.

    Complete by construction — if a wine is in inventory, the term describing it is
    matchable. A curated gazetteer measured 146 terms and missed 6 of 11 probe terms
    (Barolo, Chablis, Sancerre, Pauillac, Brunello di Montalcino, Vinho Verde); the
    catalog yields ~2,300 and missed none. Cached per process; fails open to empty."""
    now = time.time()
    if _catalog_cache["terms"] is not None and (now - _catalog_cache["at"]) < ttl:
        return _catalog_cache["terms"]
    terms = set()
    try:
        page = 0
        while True:
            rows = (supabase.table("wines")
                    .select("region,sub_region,country,varietal,grapes")
                    .order("id").range(page * 1000, page * 1000 + 999)
                    .execute().data or [])
            if not rows:
                break
            for w in rows:
                for key in ("region", "sub_region", "country", "varietal"):
                    v = _fold(w.get(key))
                    if v and v not in _STOPWORD_TERMS and len(v) > 2:
                        terms.add(v)
                for g in (w.get("grapes") or []):
                    v = _fold(g)
                    if v and v not in _STOPWORD_TERMS and len(v) > 2:
                        terms.add(v)
            page += 1
    except Exception:
        logger.exception("AVAILABILITY | catalog vocabulary fetch failed — fallback disabled")
        return _catalog_cache["terms"] or set()
    _catalog_cache["terms"], _catalog_cache["at"] = terms, now
    return terms


def terms_in_message(message: str, terms: set, cap: int = 4) -> List[str]:
    """Catalog terms named in the message — whole-word, accent-folded, longest first
    (so "Brunello di Montalcino" wins over "Montalcino"). Claimed spans are not
    re-matched. Deterministic: no LLM involved."""
    low = _fold(message)
    if not low or not terms:
        return []
    found: List[str] = []
    claimed: List[tuple] = []
    for t in sorted(terms, key=len, reverse=True):
        if len(found) >= cap:
            break
        if t in _STOPWORD_TERMS:
            continue
        for m in re.finditer(r"(?<!\w)" + re.escape(t) + r"(?!\w)", low):
            if any(m.start() < ce and cs < m.end() for cs, ce in claimed):
                continue
            claimed.append((m.start(), m.end()))
            found.append(t)
            break
    return found
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: PASS (whole file).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/availability.py backend/tests/test_availability.py
git commit -m "feat(availability): catalog-derived term vocabulary + deterministic message scan"
```

---

### Task 2: Fallback axes + dedupe + scope guard

**Files:**
- Modify: `backend/recommendation/availability.py` (`axes_from_intent`)
- Test: `backend/tests/test_availability.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_fallback_used_only_when_no_content_axis():
    axes = axes_from_intent({"regions": [], "grapes": [], "wine_type": None,
                             "wine_name": None}, fallback_terms=["mendoza"])
    assert [(a["kind"], a["value"]) for a in axes] == [("place", "mendoza")]


def test_fallback_ignored_when_parse_succeeded():
    axes = axes_from_intent({"regions": ["Rioja"], "grapes": [], "wine_type": None,
                             "wine_name": None}, fallback_terms=["mendoza"])
    vals = {a["value"] for a in axes}
    assert "Rioja" in vals and "mendoza" not in vals


def test_axes_are_deduped():
    axes = axes_from_intent({"regions": ["Champagne"], "grapes": [], "wine_type": None,
                             "wine_name": "Champagne"})
    keys = [(a["kind"], a["value"].lower(), a["scope"]) for a in axes]
    assert len(keys) == len(set(keys))


def test_scoped_copy_skipped_when_value_equals_scope():
    axes = axes_from_intent({"regions": [], "grapes": [], "wine_type": None,
                             "wine_name": "H-E-B"},
                            scope_label="H-E-B", scope_store_ids=["s1"])
    assert not any(a["value"].lower() == "h-e-b" and a["scope"] == "H-E-B"
                   and a["kind"] != "scope" for a in axes)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: FAIL (unexpected `fallback_terms` kwarg / duplicates present).

- [ ] **Step 3: Extend `axes_from_intent`**

Change the signature to:
```python
def axes_from_intent(resolved: Dict[str, Any],
                     scope_label: Optional[str] = None,
                     scope_store_ids: Optional[List[str]] = None,
                     fallback_terms: Optional[List[str]] = None) -> List[Dict[str, Any]]:
```
After the existing content-axis extraction (regions/region/grapes/type/name) and BEFORE the scope handling, add:
```python
    # Deterministic floor: when the LLM parse named nothing, fall back to catalog terms
    # actually present in the message. Negative/rhetorical framings ("nothing from
    # Mendoza right?") defeat the parser, and an axis-less turn silently bypasses the
    # oracle entirely — the precondition of the original false-absence incidents.
    if not axes and fallback_terms:
        for t in fallback_terms:
            add("place", t)
```
Then, immediately before the `return axes[:_MAX_AXES]`, dedupe and drop degenerate scoped copies:
```python
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for a in axes:
        if (a.get("scope") and a.get("kind") != "scope"
                and _fold(a.get("value")) == _fold(a.get("scope"))):
            continue                      # "H-E-B at H-E-B" is not a second axis
        k = (a.get("kind"), _fold(a.get("value")), a.get("scope"))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(a)
    return deduped[:_MAX_AXES]
```
(Also update the docstring to mention the fallback.)

- [ ] **Step 4: Run the whole file**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: PASS — including the pre-existing `test_axes_*` tests.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/availability.py backend/tests/test_availability.py
git commit -m "feat(availability): deterministic fallback axes + dedupe + scope guard"
```

---

### Task 3: Per-axis failure isolation

**Files:**
- Modify: `backend/recommendation/availability.py` (`fetch_axis_counts`)
- Test: `backend/tests/test_availability.py`

- [ ] **Step 1: Write the failing test**

```python
def test_one_failing_axis_does_not_void_the_others():
    """A single transient DB error must not collapse every axis to no-fact — that
    silently voids the whole safety net (observed in production verification)."""
    class _FlakyDB:
        def __init__(self):
            self.calls = 0

        def table(self, _name):
            return self

        def select(self, *a, **k):
            return self

        def in_(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def or_(self, clause, **k):
            if "boom" in clause:
                raise RuntimeError("simulated transient error")
            return self

        def lte(self, *a, **k):
            return self

        def gte(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            class R:
                count = 7
                data = [{"price": 20.0}]
            return R()

    axes = [{"kind": "place", "value": "boom", "scope": None, "store_ids": None},
            {"kind": "place", "value": "rioja", "scope": None, "store_ids": None}]
    counts = fetch_axis_counts(_FlakyDB(), axes, ["s1"], 50.0)
    assert axis_key(axes[0]) not in counts        # the failing axis is simply absent
    assert counts[axis_key(axes[1])]["total"] == 7  # the healthy one still counted
```

(Add `fetch_axis_counts` and `axis_key` to the test file's imports.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: FAIL — today the outer except swallows everything and returns `{}`.

- [ ] **Step 3: Move the guard inside `_one`**

In `fetch_axis_counts`, wrap the body of `_one(axis)` in its own try/except returning `None`:
```python
    def _one(axis: Dict[str, Any]) -> Any:
        try:
            ...existing body...
            return out
        except Exception:
            # Isolate per axis: one flaky query must not void every other fact.
            logger.exception("AVAILABILITY | axis failed: %s", axis_key(axis))
            return None
```
And when zipping results, skip `None`:
```python
        return {axis_key(a): r for a, r in zip(axes, results) if r is not None}
```
Keep the outer try/except (with its existing `logger.exception`) for a total failure.

- [ ] **Step 4: Run the whole file + full fast suite**

Run:
```bash
cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q
/usr/bin/python3 -m pytest tests/ -m "not integration" -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/availability.py backend/tests/test_availability.py
git commit -m "fix(availability): isolate per-axis failures so one blip can't void all facts"
```

---

### Task 4: Parser prompt + wiring

**Files:**
- Modify: `backend/recommendation/intent.py` (system prompt)
- Modify: `backend/api/routers/recommend.py` (compute + pass `fallback_terms`)
- Test: `backend/tests/test_intent.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_intent.py`:
```python
def test_parse_prompt_instructs_on_negative_framing_and_retailers():
    """Negative/rhetorical framings defeated extraction in production ("nothing from
    Mendoza right?" -> region=None), and retailers were being stuffed into wine_name."""
    import inspect
    from recommendation import intent as mod
    src = inspect.getsource(mod.parse_message)
    low = src.lower()
    assert "absence" in low or "asserting" in low or "rhetorical" in low
    assert "retailer" in low and "wine_name" in low
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_intent.py -q`
Expected: FAIL.

- [ ] **Step 3: Extend the parser system prompt**

In `parse_message`, append to the system string:
```python
                " Extract the named entity EVEN WHEN the user is asserting or questioning "
                "its absence — \"nothing from Mendoza right?\", \"surely you have no Barolo\", "
                "\"I assume there's no rosé\" all still name Mendoza / Barolo / rosé, and each "
                "must be captured in `regions`/`grapes`/`wine_type` as appropriate. "
                "A shop or retailer name (H-E-B, Spec's, Central Market, Total Wine) is NOT a "
                "`wine_name` — leave `wine_name` null for \"anything from HEB?\"."
```

- [ ] **Step 4: Wire the fallback in `recommend.py`**

Add `catalog_terms` and `terms_in_message` to the `recommendation.availability` import. Replace the
`_axes = axes_from_intent(...)` line with:
```python
    _fallback_terms = terms_in_message(req.message, catalog_terms(supabase))
    _axes = axes_from_intent(resolved, scope_label=_scope_label, scope_store_ids=_scope_ids,
                             fallback_terms=_fallback_terms)
```
(`axes_from_intent` ignores `fallback_terms` whenever the parse produced content axes, so this is
safe to compute unconditionally; `catalog_terms` is cached per process.)

- [ ] **Step 5: Verify + run suites**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend"
/usr/bin/python3 -m pytest tests/test_intent.py tests/test_availability.py -q
/usr/bin/python3 -m pytest tests/ -m "not integration" -q
```
Expected: import clean; all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/intent.py backend/api/routers/recommend.py backend/tests/test_intent.py
git commit -m "feat(intent): extract entities under negative framing; wire catalog fallback axes"
```

---

### Task 5: Acceptance + docs

**Files:**
- Modify: `backend/scripts/verify_availability_oracle.py`, `docs/reference/recommendation.md`

- [ ] **Step 1: Extend the acceptance script**

Add a Mendoza case to `main()` in `scripts/verify_availability_oracle.py` — the exact production
failure:
```python
    print("— negative framing must still emit an axis (the silent fail-open) —")
    from recommendation.availability import catalog_terms, terms_in_message
    terms = terms_in_message("nothing from Mendoza right?", catalog_terms(sb))
    print(f"  fallback terms: {terms}")
    assert terms, "expected the catalog fallback to find 'mendoza'"
    got = facts_for(sb, nearby, {"regions": [], "grapes": [], "wine_type": None,
                                 "wine_name": None}, fallback_terms=terms)
    print(f"  {got}")
    assert got and got[0][1].startswith("PRESENT_"), "expected a PRESENT_* Mendoza fact"
```
Update `facts_for` to accept and forward `fallback_terms=None`.

- [ ] **Step 2: Run it**

Run: `cd backend && /usr/bin/python3 -m scripts.verify_availability_oracle 2>&1 | grep -vE "NotOpenSSL|warnings.warn"`
Expected: the Barolo case still passes, the Mendoza fallback finds `mendoza` and yields a
`PRESENT_*` fact, `OK`.

- [ ] **Step 3: Docs**

In `docs/reference/recommendation.md`, extend the "Availability oracle" section with an
"Axis extraction" subsection: the two layers (parser prompt, catalog fallback), why the vocabulary
is catalog-derived rather than curated (146 terms / 6 misses vs 2,292 / 0), longest-match +
stopwords, per-axis isolation, and dedupe.

- [ ] **Step 4: Full fast suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_availability_oracle.py docs/reference/recommendation.md
git commit -m "test+docs: negative-framing acceptance + axis-extraction reference"
```

---

## Self-Review Notes

- **Spec coverage:** §1 vocabulary→T1; §2 layer-1 parser→T4, layer-2 fallback→T2+T4; §3 isolation→T3, dedupe/scope-guard→T2; §4 testing→each + T5. All covered.
- **Type consistency:** `catalog_terms(supabase, ttl)`, `terms_in_message(message, terms, cap)`,
  `axes_from_intent(resolved, scope_label, scope_store_ids, fallback_terms)` identical across T1–T5.
- **Fallback is a floor, not a replacement:** `axes_from_intent` only consults `fallback_terms` when
  no content axis was produced, so a working parse always wins (asserted in T2).
- **Fails open everywhere:** `catalog_terms` → empty set on error (fallback simply inert);
  `terms_in_message` → `[]` on empty vocab; per-axis failure → that axis omitted, others intact.
- **Ordering:** T1 (vocabulary) precedes T2 (fallback consumes it) precedes T4 (wiring). T3 is
  independent and can land any time after T1.
