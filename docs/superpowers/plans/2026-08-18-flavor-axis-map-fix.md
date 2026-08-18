# Flavor-Axis Map-Fixable Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the map-fixable ~8-10% of the flavor-axis coverage gap (CLAUDE.md item 34c) by adding 3 new flavor-vocab words and mapping 4 grapes + 3 regions to them, so the scorer can recognize Moscato/Glera/Prosecco/Nero d'Avola and California/Champagne/Alsace wines as floral/citrus/mineral/etc.

**Architecture:** Two files change together (`recommendation/flavor_profiles.py`'s curated maps + `recommendation/intent.py`'s parser vocab string, which must stay in sync) plus their test files. No scorer changes — this only expands what tags exist, not how they're weighted.

**Tech Stack:** Python 3.9 (`Optional[str]`, never `X | None`), pytest.

**Env:** Backend commands run from `/Users/danielguerrero/dev/wine_app/backend`. Use `/usr/bin/python3`, not bare `python3` (broken stub on this machine).

**Reference:** design spec `docs/superpowers/specs/2026-08-18-flavor-axis-map-fix-design.md`.

**Verified against the live catalog before writing this plan:** `Moscato`, `Glera`, `Prosecco`, `Nero d'Avola` all appear as clean standalone values in `wines.grapes`/`wines.varietal`; `California`, `Champagne`, `Alsace` all appear as exact `wines.region` values. The lookup in `flavor_tags_for` is an exact-match (post `_norm`), not substring, so these are the only key spellings that matter.

---

### Task 1: New vocab words + drift guard

**Files:**
- Modify: `backend/recommendation/flavor_profiles.py` (lines 14-18)
- Modify: `backend/recommendation/intent.py` (lines 19-22)
- Test: `backend/tests/test_flavor_profiles.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_flavor_profiles.py`:

```python
def test_new_vocab_words_present():
    from recommendation.flavor_profiles import FLAVOR_VOCAB
    assert {"floral", "citrus", "mineral"} <= FLAVOR_VOCAB


def test_intent_flavor_vocab_stays_in_sync_with_flavor_profiles():
    """intent.py's _FLAVOR_VOCAB is a hand-written prompt string — this guards against
    it silently drifting from the real vocabulary set, the way CORE_GRAPES is guarded
    elsewhere in the codebase."""
    from recommendation.flavor_profiles import FLAVOR_VOCAB
    from recommendation.intent import _FLAVOR_VOCAB
    words = {w.strip() for w in _FLAVOR_VOCAB.split(",")}
    assert words == FLAVOR_VOCAB
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_flavor_profiles.py -k "vocab" -v`
Expected: both FAIL — `test_new_vocab_words_present` because the 3 words aren't in
`FLAVOR_VOCAB` yet, `test_intent_flavor_vocab_stays_in_sync_with_flavor_profiles` because the
two sets don't match yet either (same reason).

- [ ] **Step 3: Add the words to `flavor_profiles.py`**

In `backend/recommendation/flavor_profiles.py`, replace lines 14-18:

```python
# Controlled flavor vocabulary (keep in sync with recommendation.intent prompt).
FLAVOR_VOCAB = {
    "earthy", "bold", "savory", "light", "peppery", "structured", "herbal",
    "red-fruit", "black-fruit", "dark-fruit", "tart-cherry", "spice", "gamey",
    "garrigue", "ripe",
}
```

with:

```python
# Controlled flavor vocabulary (keep in sync with recommendation.intent prompt).
FLAVOR_VOCAB = {
    "earthy", "bold", "savory", "light", "peppery", "structured", "herbal",
    "red-fruit", "black-fruit", "dark-fruit", "tart-cherry", "spice", "gamey",
    "garrigue", "ripe", "floral", "citrus", "mineral",
}
```

- [ ] **Step 4: Add the words to `intent.py`'s parser prompt string**

In `backend/recommendation/intent.py`, replace lines 19-22:

```python
# Keep `flavors` aligned with recommendation.flavor_profiles.FLAVOR_VOCAB.
_FLAVOR_VOCAB = (
    "earthy, bold, savory, light, peppery, structured, herbal, red-fruit, "
    "black-fruit, dark-fruit, tart-cherry, spice, gamey, garrigue, ripe"
)
```

with:

```python
# Keep `flavors` aligned with recommendation.flavor_profiles.FLAVOR_VOCAB.
_FLAVOR_VOCAB = (
    "earthy, bold, savory, light, peppery, structured, herbal, red-fruit, "
    "black-fruit, dark-fruit, tart-cherry, spice, gamey, garrigue, ripe, "
    "floral, citrus, mineral"
)
```

(The system prompt at line 55 interpolates `_FLAVOR_VOCAB` via f-string, so it picks up the
new words automatically — no separate edit needed there.)

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_flavor_profiles.py -v`
Expected: PASS (whole file, including the two new tests and all pre-existing ones).

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/flavor_profiles.py backend/recommendation/intent.py backend/tests/test_flavor_profiles.py
git commit -m "feat(flavor): add floral/citrus/mineral to the flavor vocabulary"
```

---

### Task 2: New grape entries (Moscato, Glera, Prosecco, Nero d'Avola)

**Files:**
- Modify: `backend/recommendation/flavor_profiles.py` (`GRAPE_FLAVORS` dict, currently lines 20-53)
- Test: `backend/tests/test_flavor_profiles.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_flavor_profiles.py`:

```python
def test_moscato_is_floral():
    tags = flavor_tags_for(varietal="Moscato", grapes=["Moscato"], region=None)
    assert "floral" in tags
    assert "light" in tags


def test_glera_and_prosecco_are_aliases_with_matching_tags():
    glera_tags = flavor_tags_for(varietal=None, grapes=["Glera"], region=None)
    prosecco_tags = flavor_tags_for(varietal="Prosecco", grapes=["Prosecco"], region=None)
    assert glera_tags == prosecco_tags
    assert "floral" in glera_tags
    assert "citrus" in glera_tags


def test_nero_davola_is_bold_and_savory():
    tags = flavor_tags_for(varietal="Nero d'Avola", grapes=["Nero d'Avola"], region=None)
    assert "bold" in tags
    assert "dark-fruit" in tags
    assert "savory" in tags
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_flavor_profiles.py -k "moscato or glera or nero" -v`
Expected: all 3 FAIL (empty tag sets — none of these grapes are in `GRAPE_FLAVORS` yet).

- [ ] **Step 3: Add the grape entries**

In `backend/recommendation/flavor_profiles.py`, the `GRAPE_FLAVORS` dict currently ends with:

```python
    "Grüner Veltliner": {"herbal", "spice", "savory"},
}
```

Replace that closing entry + brace with:

```python
    "Grüner Veltliner": {"herbal", "spice", "savory"},
    "Moscato": {"floral", "light", "ripe"},
    "Glera": {"floral", "citrus", "light"},
    "Prosecco": {"floral", "citrus", "light"},   # alias — catalog stores both as
                                                  # standalone grape/varietal values
    "Nero d'Avola": {"bold", "dark-fruit", "savory"},
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_flavor_profiles.py -v`
Expected: PASS (whole file).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/flavor_profiles.py backend/tests/test_flavor_profiles.py
git commit -m "feat(flavor): map Moscato, Glera/Prosecco, and Nero d'Avola to flavor tags"
```

---

### Task 3: New region entries (California, Champagne, Alsace) + documented skips

**Files:**
- Modify: `backend/recommendation/flavor_profiles.py` (`REGION_FLAVORS` dict, currently lines 55-70)
- Test: `backend/tests/test_flavor_profiles.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_flavor_profiles.py`:

```python
def test_california_region_is_ripe():
    tags = flavor_tags_for(varietal=None, grapes=[], region="California")
    assert tags == {"ripe"}


def test_champagne_region_is_mineral_and_light():
    tags = flavor_tags_for(varietal=None, grapes=[], region="Champagne")
    assert "mineral" in tags
    assert "light" in tags


def test_alsace_region_is_floral_and_spice():
    tags = flavor_tags_for(varietal=None, grapes=[], region="Alsace")
    assert "floral" in tags
    assert "spice" in tags


def test_stylistically_diverse_regions_deliberately_have_no_region_level_tags():
    """Veneto/Sicily/Loire/Penedès span incompatible styles under one region label
    (e.g. Veneto = light Soave whites AND big Amarone reds AND Prosecco) — a single
    region-level tag set would overclaim. Region alone (no grape) must stay empty;
    this is a documented decision, not a gap to "fix" later."""
    for region in ("Veneto", "Sicily", "Loire", "Penedès"):
        assert flavor_tags_for(varietal=None, grapes=[], region=region) == set()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_flavor_profiles.py -k "california or champagne or alsace or diverse" -v`
Expected: `test_california_region_is_ripe`, `test_champagne_region_is_mineral_and_light`, and
`test_alsace_region_is_floral_and_spice` FAIL (empty tag sets — none of these 3 regions are in
`REGION_FLAVORS` yet). `test_stylistically_diverse_regions_deliberately_have_no_region_level_tags`
PASSES already (those 4 regions were never mapped, so it's already true) — that's expected;
it's a documentation test, not a red-to-green test for this task.

- [ ] **Step 3: Add the region entries**

In `backend/recommendation/flavor_profiles.py`, the `REGION_FLAVORS` dict currently ends with:

```python
    "Texas": {"bold", "ripe"},
}
```

Replace that closing entry + brace with:

```python
    "Texas": {"bold", "ripe"},
    "California": {"ripe"},      # conservative single tag, matches the existing
                                  # Napa Valley / Sonoma / Central Coast pattern
    "Champagne": {"mineral", "light"},
    "Alsace": {"floral", "spice"},
    # Deliberately NOT mapped: Veneto, Sicily, Loire, Penedès — each spans
    # stylistically incompatible wines under one region label (see
    # test_stylistically_diverse_regions_deliberately_have_no_region_level_tags).
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_flavor_profiles.py -v`
Expected: PASS (whole file, all tests from Tasks 1-3).

- [ ] **Step 5: Full suite + commit**

```bash
cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q
git add backend/recommendation/flavor_profiles.py backend/tests/test_flavor_profiles.py
git commit -m "feat(flavor): map California/Champagne/Alsace to flavor tags; document diverse-region skips"
```

Expected: full fast suite green (760+ passed).

---

### Task 4: Docs — flip roadmap item 34(c)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Pull before editing**

`CLAUDE.md`'s roadmap tail is edited from more than one machine (this has caused a merge
conflict before — see item 42's plan). Run:

```bash
cd /Users/danielguerrero/dev/wine_app && git fetch origin && git status
```

If the branch is not up to date with `origin/main`, STOP and reconcile before editing — do not
resolve a real conflict solo without checking with the user first.

- [ ] **Step 2: Rewrite item 34's map-fixable sub-bullet**

Read the current item 34 text in `CLAUDE.md` first (it has three lettered sub-causes, (a)/(b)/(c)
— this task only touches the (c) description and the item's overall status marker). Item 34
currently has no ✅/⬜/⚙️ marker at all (it's a bare `34.`) because none of its three causes were
previously addressed. After this task, causes (a) and (b) are still open (enrichment/purge
territory), so the item as a whole is NOT fully done — mark it `34. ⚙️` (in-progress, matching
the `✅→⚙️` convention used elsewhere in the file for partially-landed items) and add a line
under existing sub-bullet (c) noting what shipped: the 3 new vocab words (floral/citrus/mineral),
the 4 grape entries (Moscato/Glera/Prosecco/Nero d'Avola), the 3 region entries
(California/Champagne/Alsace), and the deliberate skip of Veneto/Sicily/Loire/Penedès with the
reasoning (stylistic diversity risk). Cite the design doc:
`docs/superpowers/specs/2026-08-18-flavor-axis-map-fix-design.md`. Keep (a) and (b)'s text as-is
— they're still open and accurately described.

- [ ] **Step 3: Full suites + commit**

```bash
cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q
git add CLAUDE.md
git commit -m "docs: item 34(c) flavor-axis map-fixable slice landed"
```

---

## Self-Review Notes

- **Spec coverage:** §1 vocab → Task 1; §2 grapes → Task 2; §3 regions (incl. deliberate
  exclusions) → Task 3; §4 testing → each task's own tests + the drift-guard and
  documented-skip tests called out explicitly in the spec. Docs flip → Task 4. All covered.
- **Type consistency:** `flavor_tags_for(varietal, grapes, region)` signature unchanged across
  all tasks — every new test calls it exactly as the existing tests do. `FLAVOR_VOCAB` (set) and
  `_FLAVOR_VOCAB` (comma-joined string) names match their actual definitions in both files.
- **No placeholders:** every step has literal code, not a description of code.
- **Ordering:** Task 1 (vocab) must land before Tasks 2-3 conceptually reference `floral`/
  `citrus`/`mineral`, but since each task's tests only assert on `flavor_tags_for`'s output (not
  on `FLAVOR_VOCAB` membership), Tasks 2 and 3 would still pass even if run before Task 1 — the
  tasks are independently testable, ordering here is just narrative/vocab-first for clarity.
