# Grapes Backfill + Vivino Queue Prioritization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the ~490 grapes-empty Bordeaux/Rhône rows with appellation-law default blends, make the scorer understand "red blend" requests, and reprioritize the Vivino queue (both-null → Bordeaux/Rhône → rest) with permission to replace default blends.

**Architecture:** All grape-law knowledge lives in `enrichment/extraction/reference.py` (color-aware defaults table + gate functions), consumed by three thin clients: the extractor post-process (weekly runs), a new one-off backfill script (`revalidate_regions.py` pattern: pure `plan_change` core + paged runner), and the Vivino runner's `write_facts`. The scorer change is two small, independent rules.

**Tech Stack:** Python 3.9 (`Optional[str]`, never `str | None`), pytest, supabase-py. All backend commands run from `backend/`; on the mini use `/usr/bin/python3`.

**Spec:** `docs/superpowers/specs/2026-07-14-grapes-backfill-design.md`

**Two deliberate spec refinements** (agreed direction, tightened while planning):
1. Hermitage / Crozes-Hermitage / Saint-Joseph legally allow whites, so they are encoded as dual-color (`requires_type=True`, red → Syrah, white → Marsanne/Roussanne) instead of red-only; Côte-Rôtie and Cornas stay red-only.
2. Cadillac / Loupiac / Sainte-Croix-du-Mont (sweet-white AOCs, Loupiac was in the uncovered-rows audit) join the Sauternes/Barsac group. Sauternes-class entries accept wine_type `dessert` as well as `white` — prod rows carry `wine_type='dessert'`.

---

## Reference: current-code anchors

- `backend/enrichment/extraction/reference.py:128-131` — `_norm` (accent-strip + whitespace-fold; no hyphen folding today).
- `backend/enrichment/extraction/reference.py:332-355` — `_LEFT_BANK`/`_RIGHT_BANK`/`_GSM`/`APPELLATION_DEFAULT_GRAPES`/`default_grapes_for` (replaced wholesale by Task 2).
- `backend/enrichment/extraction/extractor.py:99` — `def _post_process(rec, source_text=None)`.
- `backend/enrichment/extraction/extractor.py:141-146` — step 3b (appellation defaults).
- `backend/recommendation/scorer.py:113-138` — candidate loop: grape-set build + `want_grapes` boost.
- `backend/scripts/run_vivino_sample.py:66-81` — `fetch_sample`; `:103-151` — `write_facts`.

Run tests as: `cd backend && /usr/bin/python3 -m pytest tests/<file> -v` (fast suite: `-m "not integration"`).

---

### Task 1: `_norm` folds hyphens to spaces

"Lalande de Pomerol" (prod data) misses "Lalande-de-Pomerol" (table); same class as "Cote-Rotie"/"Côte-Rôtie". Folding inside `_norm` fixes appellation lookups AND makes `REGION_ALIASES` catch "Côtes-du-Rhône".

**Files:**
- Modify: `backend/enrichment/extraction/reference.py:128-131`
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests** (append to `test_extraction_reference.py`)

```python
def test_norm_folds_hyphens_so_spelling_variants_match():
    """Prod rows write 'Lalande de Pomerol' where the table says
    'Lalande-de-Pomerol' — hyphen/space variants must resolve identically."""
    assert parent_region_for("Lalande de Pomerol") == "Bordeaux"
    assert parent_region_for("Cote Rotie") == "Rhône"
    assert parent_region_for("Saint-Émilion") == "Bordeaux"   # hyphenated still fine
    from enrichment.extraction.reference import canonical_region
    assert canonical_region("Côtes-du-Rhône") == "Rhône"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py::test_norm_folds_hyphens_so_spelling_variants_match -v`
Expected: FAIL — `parent_region_for("Lalande de Pomerol")` returns None.

- [ ] **Step 3: Implement** — in `reference.py`, replace `_norm`:

```python
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    s = s.replace("-", " ")   # hyphen/space spelling variants resolve identically
    return re.sub(r"\s+", " ", s).strip().lower()
```

- [ ] **Step 4: Run the whole reference + gazetteer + extraction suites** (hyphen folding touches every `_norm` consumer)

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py tests/test_extraction_gazetteer.py tests/test_extraction.py tests/test_revalidate_regions.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: _norm folds hyphens — spelling variants resolve to one appellation"
```

---

### Task 2: Color-aware defaults table + gated `default_grapes_for`

Restructure the existing defaults into rules carrying the blend's color(s) and a `requires_type` flag. Same blends as today; new behavior: a known conflicting wine_type blocks the default (white Pessac-Léognan no longer gets a red blend), and multi-color appellations need an explicit type.

**Files:**
- Modify: `backend/enrichment/extraction/reference.py:332-355` (replace the whole `_LEFT_BANK` … `default_grapes_for` block)
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_default_grapes_left_and_right_bank_unchanged():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Pauillac") == ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert default_grapes_for("Saint-Émilion") == ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]
    assert default_grapes_for("Châteauneuf-du-Pape") == ["Grenache", "Syrah", "Mourvèdre"]
    assert default_grapes_for("Nowhere") is None
    assert default_grapes_for(None) is None


def test_default_grapes_gate_blocks_color_conflicts():
    """A white wine in a red appellation must NOT get a red blend — the
    extractor was stamping Cab/Merlot on white Pessac-Léognan."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Margaux", wine_type="white") is None
    assert default_grapes_for("Châteauneuf-du-Pape", wine_type="white") is None
    assert default_grapes_for("Margaux", wine_type="red") == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]


def test_multi_color_appellations_require_explicit_type():
    """Graves/Pessac-Léognan bottle both colors — unknown type must not guess."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Graves") is None
    assert default_grapes_for("Graves", wine_type="red") == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert default_grapes_for("Graves", wine_type="white") == \
        ["Sauvignon Blanc", "Sémillon"]
    assert default_grapes_for("Pessac-Léognan", wine_type="white") == \
        ["Sauvignon Blanc", "Sémillon"]


def test_single_color_appellations_fire_on_unknown_type():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Pauillac", wine_type=None) == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]


def test_sauternes_accepts_dessert_wine_type():
    """Prod Sauternes rows carry wine_type='dessert' — the white blend must fire."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Sauternes", wine_type="dessert") == \
        ["Sémillon", "Sauvignon Blanc"]
    assert default_grapes_for("Sauternes", wine_type="red") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -k "default_grapes or multi_color or sauternes_accepts or single_color" -v`
Expected: FAIL — `default_grapes_for()` takes 1 positional argument / Graves returns a red blend.

- [ ] **Step 3: Implement** — in `reference.py`, replace lines 332-355 (`_LEFT_BANK` through the old `default_grapes_for`) with:

```python
# Appellation law → default blend when the model returned no grapes.
# Order matters: first grape becomes the varietal. Each rule carries the
# colors the blend is valid for; it fires when the caller's wine_type is in
# them, or when wine_type is unknown (None) AND the appellation is
# single-color (requires_type=False). Multi-color appellations (Graves,
# Pessac-Léognan, …) never fire on an unknown type.
_BDX_LEFT   = ("Cabernet Sauvignon", "Merlot", "Cabernet Franc")
_BDX_RIGHT  = ("Merlot", "Cabernet Franc", "Cabernet Sauvignon")
_BDX_WHITE  = ("Sauvignon Blanc", "Sémillon")
_GSM_BLEND  = ("Grenache", "Syrah", "Mourvèdre")
_SAUT_WHITE = ("Sémillon", "Sauvignon Blanc")

# (appellations, grapes, wine_types the blend may fill, requires_type)
_DEFAULT_RULES = [
    (("Médoc", "Haut-Médoc", "Margaux", "Pauillac", "Saint-Julien",
      "Saint-Estèphe", "Listrac-Médoc", "Listrac", "Moulis-en-Médoc"),
     _BDX_LEFT, ("red",), False),
    (("Pessac-Léognan", "Graves"), _BDX_LEFT, ("red",), True),
    (("Pessac-Léognan", "Graves"), _BDX_WHITE, ("white",), True),
    (("Saint-Émilion", "Pomerol", "Lalande-de-Pomerol", "Fronsac",
      "Canon-Fronsac"), _BDX_RIGHT, ("red",), False),
    (("Châteauneuf-du-Pape", "Gigondas", "Vacqueyras", "Côtes du Rhône"),
     _GSM_BLEND, ("red",), False),
    (("Sauternes", "Barsac"), _SAUT_WHITE, ("white", "dessert"), False),
]

_APPELLATION_DEFAULTS = {}
for _apps, _grapes, _colors, _req in _DEFAULT_RULES:
    for _a in _apps:
        _APPELLATION_DEFAULTS.setdefault(_norm(_a), []).append((_grapes, _colors, _req))


def default_grapes_for(appellation, wine_type=None) -> Optional[list]:
    """Appellation-law default blend, gated by wine color ('rosé' folds to
    'rose' via _norm). Unknown wine_type fires only single-color appellations;
    a known wine_type must be among the rule's colors."""
    if not appellation:
        return None
    rules = _APPELLATION_DEFAULTS.get(_norm(appellation))
    if not rules:
        return None
    wt = _norm(wine_type) if wine_type else None
    for grapes, colors, requires_type in rules:
        if (wt in colors) or (wt is None and not requires_type):
            return list(grapes)
    return None
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py tests/test_extraction.py -v`
Expected: ALL PASS (extractor's `default_grapes_for(out.get("sub_region"))` call is signature-compatible).

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: color-aware appellation defaults — wine_type gate blocks red blends on whites"
```

---

### Task 3: Expand the defaults table (satellites, whites, northern Rhône, Tavel, variants)

**Files:**
- Modify: `backend/enrichment/extraction/reference.py` (`_DEFAULT_RULES` from Task 2)
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_right_bank_satellites_and_grand_cru_get_merlot_led_blend():
    """30 uncovered Bordeaux rows in the 07-14 audit sit in these appellations."""
    from enrichment.extraction.reference import default_grapes_for
    merlot_led = ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]
    for app in ["Saint-Émilion Grand Cru", "Lussac-Saint-Émilion",
                "Montagne-Saint-Émilion", "Puisseguin-Saint-Émilion",
                "Castillon", "Castillon Côtes de Bordeaux", "Côtes de Castillon",
                "Côtes de Francs", "Blaye Côtes de Bordeaux", "Côtes de Bourg",
                "Bordeaux Supérieur"]:
        assert default_grapes_for(app) == merlot_led, app
    # Côtes de Bordeaux (whites exist) requires an explicit type
    assert default_grapes_for("Côtes de Bordeaux") is None
    assert default_grapes_for("Côtes de Bordeaux", wine_type="red") == merlot_led


def test_bordeaux_white_appellations():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Entre-Deux-Mers") == ["Sauvignon Blanc", "Sémillon"]
    assert default_grapes_for("Entre-Deux-Mers", wine_type="red") is None
    assert default_grapes_for("Loupiac", wine_type="dessert") == \
        ["Sémillon", "Sauvignon Blanc"]
    assert default_grapes_for("Cadillac") == ["Sémillon", "Sauvignon Blanc"]


def test_northern_rhone_syrah_and_whites():
    from enrichment.extraction.reference import default_grapes_for
    # red-only crus fire on unknown type
    assert default_grapes_for("Côte-Rôtie") == ["Syrah"]
    assert default_grapes_for("Cornas") == ["Syrah"]
    # dual-color crus require explicit type
    assert default_grapes_for("Hermitage") is None
    assert default_grapes_for("Hermitage", wine_type="red") == ["Syrah"]
    assert default_grapes_for("Crozes-Hermitage", wine_type="white") == \
        ["Marsanne", "Roussanne"]
    assert default_grapes_for("Saint-Joseph", wine_type="red") == ["Syrah"]
    assert default_grapes_for("Condrieu") == ["Viognier"]


def test_tavel_is_grenache_rose():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Tavel", wine_type="rose") == ["Grenache"]
    assert default_grapes_for("Tavel", wine_type="rosé") == ["Grenache"]   # accent folds
    assert default_grapes_for("Tavel") == ["Grenache"]                     # rosé-only AOC
    assert default_grapes_for("Tavel", wine_type="red") is None


def test_southern_rhone_satellites_and_spelling_variants():
    """'Côte du Rhône' (singular) is a real prod variant — 4 rows."""
    from enrichment.extraction.reference import default_grapes_for
    gsm = ["Grenache", "Syrah", "Mourvèdre"]
    for app in ["Côtes du Rhône Villages", "Côte du Rhône", "Ventoux",
                "Cairanne", "Rasteau", "Vinsobres"]:
        assert default_grapes_for(app) == gsm, app
    assert default_grapes_for("Lalande de Pomerol") == \
        ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]   # hyphen fold, Task 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -k "satellites or white_appellations or northern_rhone or tavel" -v`
Expected: FAIL — new appellations return None.

- [ ] **Step 3: Implement** — append to `_DEFAULT_RULES` (before the closing `]`):

```python
    # right-bank satellites, Grand Cru label, Castillon/Francs/Blaye/Bourg
    (("Saint-Émilion Grand Cru", "Lussac-Saint-Émilion",
      "Montagne-Saint-Émilion", "Puisseguin-Saint-Émilion",
      "Castillon", "Castillon Côtes de Bordeaux", "Côtes de Castillon",
      "Côtes de Francs", "Francs Côtes de Bordeaux",
      "Blaye Côtes de Bordeaux", "Côtes de Blaye", "Côtes de Bourg",
      "Bordeaux Supérieur"), _BDX_RIGHT, ("red",), False),
    # umbrella Côtes de Bordeaux bottles whites too — explicit type only
    (("Côtes de Bordeaux",), _BDX_RIGHT, ("red",), True),
    # Bordeaux whites
    (("Entre-Deux-Mers",), _BDX_WHITE, ("white",), False),
    (("Cadillac", "Loupiac", "Sainte-Croix-du-Mont"),
     _SAUT_WHITE, ("white", "dessert"), False),
    # northern Rhône: red-only crus vs dual-color crus
    (("Côte-Rôtie", "Cornas"), ("Syrah",), ("red",), False),
    (("Hermitage", "Crozes-Hermitage", "Saint-Joseph"),
     ("Syrah",), ("red",), True),
    (("Hermitage", "Crozes-Hermitage", "Saint-Joseph"),
     ("Marsanne", "Roussanne"), ("white",), True),
    (("Condrieu",), ("Viognier",), ("white",), False),
    (("Tavel",), ("Grenache",), ("rose",), False),
    # southern-Rhône satellites + the singular 'Côte du Rhône' prod variant
    (("Côtes du Rhône Villages", "Côte du Rhône", "Ventoux", "Cairanne",
      "Rasteau", "Vinsobres"), _GSM_BLEND, ("red",), False),
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: appellation defaults cover satellites, whites, northern Rhône, Tavel"
```

---

### Task 4: Region-level red defaults + `ALL_DEFAULT_BLENDS`

**Files:**
- Modify: `backend/enrichment/extraction/reference.py` (append after `default_grapes_for`)
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_region_level_defaults_fire_only_for_explicit_red():
    """68 prod rows have region but no sub_region — Bordeaux AOC rouge is
    Merlot-led by law; region-only Rhône reds are overwhelmingly southern GSM."""
    from enrichment.extraction.reference import default_grapes_for_region
    assert default_grapes_for_region("Bordeaux", "red") == \
        ["Merlot", "Cabernet Sauvignon", "Cabernet Franc"]
    assert default_grapes_for_region("Rhône", "red") == \
        ["Grenache", "Syrah", "Mourvèdre"]
    assert default_grapes_for_region("Rhone", "red") is not None   # accent variant
    assert default_grapes_for_region("Bordeaux", None) is None
    assert default_grapes_for_region("Bordeaux", "white") is None
    assert default_grapes_for_region("Napa Valley", "red") is None
    assert default_grapes_for_region(None, "red") is None


def test_all_default_blends_contains_every_law_blend():
    """Vivino's write_facts uses this to recognize (and replace) law-book
    approximations without a schema change."""
    from enrichment.extraction.reference import ALL_DEFAULT_BLENDS
    assert ("Cabernet Sauvignon", "Merlot", "Cabernet Franc") in ALL_DEFAULT_BLENDS
    assert ("Merlot", "Cabernet Franc", "Cabernet Sauvignon") in ALL_DEFAULT_BLENDS
    assert ("Merlot", "Cabernet Sauvignon", "Cabernet Franc") in ALL_DEFAULT_BLENDS
    assert ("Grenache", "Syrah", "Mourvèdre") in ALL_DEFAULT_BLENDS
    assert ("Syrah",) in ALL_DEFAULT_BLENDS
    assert ("Viognier",) in ALL_DEFAULT_BLENDS
    assert ("Zinfandel",) not in ALL_DEFAULT_BLENDS
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -k "region_level or all_default_blends" -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement** — append to `reference.py` after `default_grapes_for`:

```python
# Region-level fallback for rows with no (recognized) appellation — reds only:
# Bordeaux AOC rouge is Merlot-led by law; region-only Rhône reds are
# overwhelmingly southern Côtes-du-Rhône GSM.
REGION_DEFAULT_GRAPES = {
    "bordeaux": ("Merlot", "Cabernet Sauvignon", "Cabernet Franc"),
    "rhone": _GSM_BLEND,
}


def default_grapes_for_region(region, wine_type) -> Optional[list]:
    """Region-level default blend; fires only when wine_type is exactly red."""
    if not region or _norm(wine_type or "") != "red":
        return None
    blend = REGION_DEFAULT_GRAPES.get(_norm(region))
    return list(blend) if blend else None


# Every default blend (appellation + region level) as tuples — lets Vivino
# recognize law-book approximations and replace them with real per-wine data.
ALL_DEFAULT_BLENDS = frozenset(
    _g for _rules in _APPELLATION_DEFAULTS.values() for _g, _, _ in _rules
) | frozenset(REGION_DEFAULT_GRAPES.values())
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: red-gated region-level default blends + ALL_DEFAULT_BLENDS registry"
```

---

### Task 5: `is_specific_grape` — generic-vs-real varietal test

**Files:**
- Modify: `backend/enrichment/extraction/reference.py` (append after `canonical_grape`, ~line 232)
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_is_specific_grape_accepts_real_grapes_rejects_generics():
    """Backfill rule: a specific-grape varietal is trusted (grapes=[varietal]);
    generics fall through to the appellation blend. 'Sauternes' as a varietal
    (2 prod rows) is a place, not a grape — generic."""
    from enrichment.extraction.reference import is_specific_grape
    for real in ["Merlot", "merlot", "Shiraz", "Sémillon", "Semillon", "Viognier"]:
        assert is_specific_grape(real), real
    for generic in ["Red Blend", "White Blend", "Red Wine", "White Wine",
                    "Other", "Sauternes", None, ""]:
        assert not is_specific_grape(generic), generic
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py::test_is_specific_grape_accepts_real_grapes_rejects_generics -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement** — append to `reference.py` after `canonical_grape` (line ~232):

```python
# Every canonical grape we know — membership test for "the varietal names an
# actual grape" (vs. generic retail labels like 'Red Blend').
KNOWN_GRAPES = (
    {_norm(g) for _names in CORE_GRAPES.values() for g in _names}
    | {_norm(g) for g in GRAPE_SYNONYMS.values()}
)


def is_specific_grape(varietal) -> bool:
    """True when the varietal names an actual grape (post-canonicalization)."""
    if not varietal:
        return False
    return _norm(canonical_grape(varietal)) in KNOWN_GRAPES
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: is_specific_grape — real grape vs generic varietal label"
```

---

### Task 6: Thread wine_type through the extractor + region fallback in step 3b

Weekly extraction (both backends) gains the gate + region fallback. `run_extraction.py` already selects `wine_type` and puts it on each wine dict — only the batch loops and `_post_process` need changes.

**Files:**
- Modify: `backend/enrichment/extraction/extractor.py:11-14` (imports), `:99` (signature), `:141-146` (step 3b), `:198-204` (batch loop)
- Modify: `backend/enrichment/extraction/ollama_extractor.py:78-86` (batch loop)
- Test: `backend/tests/test_extraction.py`

- [ ] **Step 1: Write the failing tests** (append to `test_extraction.py`)

```python
def test_post_process_wine_type_gates_default_blend():
    """A white wine in a red appellation must not get the red default blend."""
    rec = {"wine_id": "w1", "sub_region": "Margaux", "grapes": [], "varietal": None}
    out = _post_process(rec, wine_type="white")
    assert out["grapes"] == []
    out_red = _post_process(rec, wine_type="red")
    assert out_red["grapes"] == ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert out_red["varietal"] == "Cabernet Sauvignon"


def test_post_process_region_fallback_for_red_without_appellation():
    rec = {"wine_id": "w1", "region": "Bordeaux", "sub_region": None,
           "grapes": [], "varietal": None}
    out = _post_process(rec, wine_type="red")
    assert out["grapes"] == ["Merlot", "Cabernet Sauvignon", "Cabernet Franc"]
    out_unknown = _post_process(rec)
    assert out_unknown["grapes"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction.py -k "wine_type_gates or region_fallback" -v`
Expected: FAIL — unexpected keyword argument 'wine_type'.

- [ ] **Step 3: Implement**

In `extractor.py` imports (line 13), add `default_grapes_for_region` next to `default_grapes_for`.

Signature (line 99):

```python
def _post_process(rec: Dict[str, Any], source_text: Optional[str] = None,
                  wine_type: Optional[str] = None) -> Dict[str, Any]:
```

Step 3b (lines 141-146) becomes:

```python
    # 3b. appellation law -> default blend when the model gave no grapes
    #     (left bank Cab-led, right bank Merlot-led, S. Rhône GSM, Sauternes
    #     Sémillon), gated by wine color; region-level fallback for reds with
    #     no recognized appellation. Never overwrites model-supplied grapes.
    if not out.get("grapes"):
        blend = (default_grapes_for(out.get("sub_region"), wine_type)
                 or default_grapes_for_region(out.get("region"), wine_type))
        if blend:
            out["grapes"] = list(blend)
```

In `extractor.py`'s `extract_facts` batch loop, next to the existing `sources = {...}` dict add:

```python
        types = {w["id"]: w.get("wine_type") for w in batch}
```

and change the `_post_process` call to:

```python
                    results.append(_post_process(rec, source_text=sources.get(rec["wine_id"]),
                                                 wine_type=types.get(rec["wine_id"])))
```

Make the identical two changes in `ollama_extractor.py`'s `extract_facts_ollama` (its `sources` dict is at line ~79, the call at line ~85).

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_extraction.py tests/test_extractor_backend.py tests/test_run_extraction_lifecycle.py tests/test_revalidate_regions.py -v`
Expected: ALL PASS (revalidate passes no wine_type → gate simply never fills grapes there; it only writes place fields anyway).

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/extractor.py backend/enrichment/extraction/ollama_extractor.py backend/tests/test_extraction.py
git commit -m "feat: extraction threads wine_type into the blend-default gate + region fallback"
```

---

### Task 7: Backfill `plan_change` (pure core, TDD)

**Files:**
- Create: `backend/scripts/backfill_grapes.py` (planning core only; runner in Task 8)
- Test: `backend/tests/test_backfill_grapes.py` (new)

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_backfill_grapes.py`:

```python
"""Tests for the grapes backfill (scripts/backfill_grapes.py).

plan_change(row) decides, per grapes-empty Bordeaux/Rhône wine, what to write:
a trusted specific varietal ([varietal]), the appellation-law blend (color-
gated), or the red-only region-level blend — in that precedence. varietal is
set to the blend's lead grape only when NULL. Returns (changes, rule).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.backfill_grapes import plan_change


def _row(**kw):
    base = {
        "id": "w1", "name": "Château Test", "region": "Bordeaux",
        "sub_region": None, "varietal": None, "wine_type": "red", "grapes": [],
    }
    base.update(kw)
    return base


def test_specific_varietal_is_trusted_over_the_appellation_blend():
    """varietal='Merlot' on a left-bank row: the label gave us the grape —
    appellation law must not contradict it."""
    changes, rule = plan_change(_row(varietal="Merlot", sub_region="Margaux"))
    assert changes == {"grapes": ["Merlot"]}          # varietal untouched
    assert rule == "specific-varietal"


def test_generic_varietal_gets_blend_and_keeps_its_label():
    changes, rule = plan_change(_row(varietal="Red Blend", sub_region="Pauillac"))
    assert changes == {"grapes": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]}
    assert rule == "appellation"


def test_null_varietal_gets_blend_plus_lead_grape():
    changes, _ = plan_change(_row(sub_region="Saint-Émilion"))
    assert changes["grapes"] == ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]
    assert changes["varietal"] == "Merlot"


def test_white_wine_in_red_appellation_left_for_vivino():
    changes, rule = plan_change(_row(sub_region="Margaux", wine_type="white"))
    assert changes == {}
    assert rule is None


def test_sauternes_dessert_rows_get_the_semillon_blend():
    changes, _ = plan_change(_row(sub_region="Sauternes", wine_type="dessert"))
    assert changes["grapes"] == ["Sémillon", "Sauvignon Blanc"]
    assert changes["varietal"] == "Sémillon"


def test_region_only_red_gets_region_default():
    changes, rule = plan_change(_row(region="Rhône"))
    assert changes == {"grapes": ["Grenache", "Syrah", "Mourvèdre"],
                       "varietal": "Grenache"}
    assert rule == "region"


def test_region_only_unknown_type_left_for_vivino():
    changes, rule = plan_change(_row(wine_type=None))
    assert changes == {}
    assert rule is None


def test_rows_with_grapes_or_foreign_regions_are_untouched():
    assert plan_change(_row(grapes=["Zinfandel"]))[0] == {}
    assert plan_change(_row(region="Napa Valley", sub_region="Oakville"))[0] == {}
    assert plan_change(_row(region=None))[0] == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_backfill_grapes.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement** — create `backend/scripts/backfill_grapes.py`:

```python
"""One-off grapes backfill for Bordeaux/Rhône rows the weekly extraction can't
reach (CLAUDE.md item 27).

Rows extracted before the appellation-law blend defaults shipped have
grapes=[] with region set, so --null-only extraction never revisits them and
the scorer's grape matching can't see them. Per row, in precedence order:

1. varietal names an actual grape           -> grapes=[varietal] (trusted)
2. appellation default (color-gated)        -> grapes=blend
3. region default (Bordeaux/Rhône, red only)-> grapes=blend
4. else no-op — left for the Vivino queue.

varietal is set to the blend's lead grape only when NULL. Writes only changed
fields; whites in red appellations are never touched.

Run from backend/ (../.env resolves):
    python3 -m scripts.backfill_grapes [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrichment.extraction.reference import (canonical_grape,           # noqa: E402
                                             default_grapes_for,
                                             default_grapes_for_region,
                                             is_specific_grape)

TARGET_REGIONS = ("Bordeaux", "Rhône")


def plan_change(row: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """Return (update payload, rule name) for one wine; ({}, None) when no-op."""
    if row.get("region") not in TARGET_REGIONS or (row.get("grapes") or []):
        return {}, None
    varietal = row.get("varietal")
    if is_specific_grape(varietal):
        grapes, rule = [canonical_grape(varietal)], "specific-varietal"
    else:
        grapes = default_grapes_for(row.get("sub_region"), row.get("wine_type"))
        rule = "appellation"
        if not grapes:
            grapes = default_grapes_for_region(row.get("region"), row.get("wine_type"))
            rule = "region"
        if not grapes:
            return {}, None
    changes = {"grapes": grapes}
    if not varietal:
        changes["varietal"] = grapes[0]
    return changes, rule
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_backfill_grapes.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_grapes.py backend/tests/test_backfill_grapes.py
git commit -m "feat: backfill_grapes plan_change — trusted varietal > appellation > region default"
```

---

### Task 8: Backfill runner (fetch, main, Slack)

Thin I/O shell around the tested core — mirrors `revalidate_regions.py`, which has no runner tests either.

**Files:**
- Modify: `backend/scripts/backfill_grapes.py` (append)

- [ ] **Step 1: Append the runner**

```python
def fetch_target_wines(db, limit: int = 0) -> List[Dict[str, Any]]:
    """All Bordeaux/Rhône rows; plan_change skips the ones that have grapes
    (postgrest can't cleanly filter 'empty JSON array', so filter client-side
    — it's ~1,450 rows, 2 pages)."""
    wines, page, page_size = [], 0, 1000
    while True:
        rows = (db.table("wines")
                .select("id,name,region,sub_region,varietal,wine_type,grapes")
                .in_("region", list(TARGET_REGIONS))
                .order("id")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute().data)
        wines.extend(rows)
        page += 1
        if len(rows) < page_size or (limit and len(wines) >= limit):
            break
    if limit:
        wines = wines[:limit]
    return wines


def _notify_slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"slack notify failed: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from db import get_service_client
    db = get_service_client()

    wines = fetch_target_wines(db, limit=args.limit)
    empty = sum(1 for w in wines if not (w.get("grapes") or []))
    print(f"examining {len(wines)} Bordeaux/Rhône wines ({empty} grapes-empty)", flush=True)

    by_rule = {"specific-varietal": 0, "appellation": 0, "region": 0}
    changed = 0
    for w in wines:
        changes, rule = plan_change(w)
        if not changes:
            continue
        changed += 1
        by_rule[rule] += 1
        tag = "DRY " if args.dry_run else ""
        print(f'{tag}{w["id"][:8]} | {(w["name"] or "")[:55]} | {rule} | {changes}', flush=True)
        if not args.dry_run:
            db.table("wines").update(changes).eq("id", w["id"]).execute()

    summary = (f"Grapes backfill{' (dry run)' if args.dry_run else ''}: "
               f"{empty} empty of {len(wines)} Bordeaux/Rhône wines, {changed} filled "
               f"({by_rule['specific-varietal']} trusted varietal, "
               f"{by_rule['appellation']} appellation blends, "
               f"{by_rule['region']} region blends), "
               f"{empty - changed} left for Vivino")
    print(summary, flush=True)
    if not args.dry_run:
        _notify_slack(f":grapes: {summary}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sanity-run the fast suite + a bounded dry run**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_backfill_grapes.py -v && /usr/bin/python3 -m scripts.backfill_grapes --dry-run --limit 50`
Expected: tests PASS; dry run prints ~a dozen `DRY … | appellation | {...}` lines and a summary, writes nothing.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/backfill_grapes.py
git commit -m "feat: backfill_grapes runner — paged fetch, dry-run, per-rule counts, Slack"
```

---

### Task 9: Scorer — varietal in the candidate grape set + blend-aware matching

**Files:**
- Modify: `backend/recommendation/scorer.py:113-138`
- Test: `backend/tests/test_scorer.py`

- [ ] **Step 1: Write the failing tests** (append to `test_scorer.py`; note each test puts the expected LOSER first in the candidate list so a stable-sort tie can't fake a pass — CLAUDE.md TDD note)

```python
def test_red_blend_request_boosts_multi_grape_reds_and_blend_varietals():
    """'Red blend' asks used to boost almost nothing: literal 'Red Blend' sits
    in grapes on 7 wines but in varietal on 819, and candidates matched on the
    grapes column only. Both a backfilled Bordeaux (3-grape array) and a
    varietal='Red Blend' wine must now outrank a single-grape red."""
    single = _wine("Straight Malbec", varietal="Malbec", grapes=["Malbec"])
    labeled = _wine("Labeled Red Blend", varietal="Red Blend", grapes=[])
    bordeaux = _wine("Backfilled Pauillac", varietal="Cabernet Sauvignon",
                     grapes=["Cabernet Sauvignon", "Merlot", "Cabernet Franc"],
                     region="Bordeaux", country="France")
    result = score_candidates(_intent(grapes=["Red Blend"]),
                              [single, labeled, bordeaux])
    names = [w["name"] for w in result]
    assert names.index("Straight Malbec") == 2


def test_blend_rule_respects_wine_type():
    red_mix = _wine("Red Mix", wine_type="red", varietal=None,
                    grapes=["Grenache", "Syrah"])
    white_mix = _wine("White Mix", wine_type="white", varietal=None,
                      grapes=["Marsanne", "Roussanne"])
    result = score_candidates(_intent(grapes=["White Blend"]),
                              [red_mix, white_mix])
    assert result[0]["name"] == "White Mix"


def test_candidate_varietal_now_counts_for_grape_requests():
    """Symmetry with _norm_liked: a wine whose grapes array is empty but whose
    varietal matches the requested grape earns the grape boost."""
    other = _wine("Other", varietal="Malbec", grapes=["Malbec"])
    varietal_only = _wine("Varietal Only", varietal="Tempranillo", grapes=[],
                          region="Rioja", country="Spain")
    result = score_candidates(_intent(grapes=["Tempranillo"]),
                              [other, varietal_only])
    assert result[0]["name"] == "Varietal Only"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k "red_blend_request or blend_rule or varietal_now_counts" -v`
Expected: FAIL on all three.

- [ ] **Step 3: Implement**

In `scorer.py`, add near the weights (after line 31):

```python
# 'Red blend' / 'white blend' asks match any wine of that type with a 2+
# grape blend — Bordeaux/GSM wines carry real grape arrays, not the literal
# label, so set-intersection alone can't see them.
_BLEND_WANTS = {"red blend": "red", "white blend": "white"}


def _blend_match(want_grapes: set, wine_type, grapes_col) -> bool:
    if len(grapes_col or []) < 2:
        return False
    return any(want in want_grapes and wine_type == wtype
               for want, wtype in _BLEND_WANTS.items())
```

In the candidate loop, replace line 118 (`grapes = {...}`):

```python
        grapes = {_norm(g) for g in (wine.get("grapes") or [])}
        if wine.get("varietal"):
            grapes.add(_norm(wine["varietal"]))   # symmetric with _norm_liked
```

Replace lines 137-138 (`if want_grapes and (want_grapes & grapes): score += _W_GRAPE`):

```python
        if want_grapes and (
                (want_grapes & grapes)
                or _blend_match(want_grapes, wine.get("wine_type"), wine.get("grapes"))):
            score += _W_GRAPE
```

- [ ] **Step 4: Run the scorer + recommend suites** (varietal joins the avoid-haystack and personalization similarity — deliberate, verify nothing depended on its absence)

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py tests/test_recommend_api.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat: scorer counts varietal for candidates + blend-aware 'red blend' matching"
```

---

### Task 10: Vivino queue tiers

**Files:**
- Modify: `backend/scripts/run_vivino_sample.py:66-81` (`fetch_sample`)
- Test: `backend/tests/test_vivino_runner.py`

- [ ] **Step 1: Write the failing tests** (append to `test_vivino_runner.py`)

```python
class _FakeTier:
    """Stands in for a built postgrest query: .limit(n).execute().data"""
    def __init__(self, rows):
        self._rows = rows

    def limit(self, n):
        self._n = n
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self._rows[:self._n])


def _rows(*ids):
    return [{"id": i} for i in ids]


def test_fetch_sample_fills_limit_in_tier_order_with_dedup():
    """Item 13 + item 27: both-null wines (invisible to the recommender) first,
    then un-enriched Bordeaux/Rhône, then the rest. A wine surfacing in two
    tiers must be picked once."""
    tiers = [_FakeTier(_rows("a", "b")),
             _FakeTier(_rows("b", "c")),          # 'b' duplicates tier 1
             _FakeTier(_rows("d", "e", "f"))]
    with patch.object(runner, "_tier_queries", return_value=tiers):
        picked = runner.fetch_sample(db=None, limit=4)
    assert [w["id"] for w in picked] == ["a", "b", "c", "d"]


def test_fetch_sample_stops_at_limit_within_first_tier():
    tiers = [_FakeTier(_rows("a", "b", "c")), _FakeTier(_rows("d")), _FakeTier([])]
    with patch.object(runner, "_tier_queries", return_value=tiers):
        picked = runner.fetch_sample(db=None, limit=2)
    assert [w["id"] for w in picked] == ["a", "b"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_vivino_runner.py -k fetch_sample -v`
Expected: FAIL — no `_tier_queries` attribute.

- [ ] **Step 3: Implement** — in `run_vivino_sample.py`, replace `fetch_sample` (lines 66-81):

```python
_SAMPLE_COLS = "id,name,brand,vintage_year,varietal,region,country,wine_type,grapes,abv"

# Non-wine catalog noise that will never match on Vivino
_JUNK_NAMES = ("%sake%", "%cocktail%", "%margarita%", "%daiquiri%",
               "%pina colada%", "%spiked%", "%lemonade%")


def _junk_filter(q):
    for junk in _JUNK_NAMES:
        q = q.not_.ilike("name", junk)
    return q


def _tier_queries(db):
    """Priority tiers, all un-enriched + junk-filtered: (1) both-null wines are
    fully invisible to the recommender (item 13 — the Pogo's residue);
    (2) Bordeaux/Rhône rows need ratings + real blends (item 27); (3) the rest."""
    def base():
        return _junk_filter(db.table("wines").select(_SAMPLE_COLS)
                            .is_("vivino_enriched_at", "null"))
    return [
        base().is_("varietal", "null").is_("region", "null"),
        base().in_("region", ["Bordeaux", "Rhône"]),
        base(),
    ]


def fetch_sample(db, limit, missing_images_only=False):
    if missing_images_only:
        # Only HEB/CM wines lack images (all other scrapers capture CDN URLs),
        # so this flag effectively targets the HEB catalog — the mainstream
        # brands with the best Vivino match rates.
        q = (db.table("wines").select(_SAMPLE_COLS)
             .is_("vivino_enriched_at", "null").is_("image_url", "null"))
        return _junk_filter(q).limit(limit).execute().data
    picked, seen = [], set()
    for q in _tier_queries(db):
        if len(picked) >= limit:
            break
        for r in q.limit(limit).execute().data:
            if r["id"] not in seen and len(picked) < limit:
                seen.add(r["id"])
                picked.append(r)
    return picked
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_vivino_runner.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/run_vivino_sample.py backend/tests/test_vivino_runner.py
git commit -m "feat: Vivino queue tiers — both-null, then Bordeaux/Rhône, then the rest"
```

---

### Task 11: Vivino may replace default blends

**Files:**
- Modify: `backend/scripts/run_vivino_sample.py:103-124` (`write_facts`, wines-table half)
- Test: `backend/tests/test_vivino_runner.py`

- [ ] **Step 1: Write the failing tests** (append; `MagicMock` chains `.table().update().eq().execute()` automatically)

```python
def _facts_wine(**kw):
    base = {"id": "w1", "grapes": [], "abv": 13.5,
            "region": "Bordeaux", "country": "France"}
    base.update(kw)
    return base


def test_write_facts_replaces_appellation_default_blend():
    """Law-book approximations (backfill/extraction defaults) yield to real
    per-wine Vivino data; everything else stays fill-only."""
    from unittest.mock import MagicMock
    db = MagicMock()
    w = _facts_wine(grapes=["Merlot", "Cabernet Franc", "Cabernet Sauvignon"])
    filled = runner.write_facts(db, w, {"grapes": ["Merlot", "Cabernet Franc"]})
    assert "grapes" in filled
    payload = db.table.return_value.update.call_args[0][0]
    assert payload["grapes"] == ["Merlot", "Cabernet Franc"]


def test_write_facts_never_replaces_scraped_or_extracted_grapes():
    from unittest.mock import MagicMock
    db = MagicMock()
    w = _facts_wine(grapes=["Zinfandel"])
    filled = runner.write_facts(db, w, {"grapes": ["Merlot"]})
    assert filled == []
    db.table.return_value.update.assert_not_called()


def test_write_facts_still_fills_empty_grapes():
    from unittest.mock import MagicMock
    db = MagicMock()
    filled = runner.write_facts(db, _facts_wine(), {"grapes": ["Malbec"]})
    assert "grapes" in filled
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_vivino_runner.py -k write_facts -v`
Expected: `test_write_facts_replaces_appellation_default_blend` FAILS (fill-only today); the other two PASS (behavior guards).

- [ ] **Step 3: Implement**

Add to `run_vivino_sample.py` imports (below the `enrichment.vivino` import):

```python
from enrichment.extraction.reference import ALL_DEFAULT_BLENDS
```

In `write_facts`, replace the grapes clause (lines 114-115):

```python
    # Grapes: fill when empty, and REPLACE when the current value is a
    # law-book default blend (backfill/extraction approximation) — real
    # per-wine data wins. Scraped/extracted grapes are never overwritten.
    current_grapes = w.get("grapes") or []
    if attrs.get("grapes") and attrs["grapes"] != current_grapes and (
            not current_grapes or tuple(current_grapes) in ALL_DEFAULT_BLENDS):
        wine_update["grapes"] = attrs["grapes"]
```

- [ ] **Step 4: Run tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_vivino_runner.py tests/test_vivino.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/run_vivino_sample.py backend/tests/test_vivino_runner.py
git commit -m "feat: Vivino replaces law-book default blends with real per-wine grapes"
```

---

### Task 12: Full suite + production dry run

- [ ] **Step 1: Full fast suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration"`
Expected: ALL PASS, no new warnings beyond the known LibreSSL one.

- [ ] **Step 2: Full dry run against prod**

Run: `cd backend && /usr/bin/python3 -m scripts.backfill_grapes --dry-run 2>&1 | tail -5`
Expected summary shape: `~490 empty of ~1,450 Bordeaux/Rhône wines, ~430–460 filled (…), ~40–60 left for Vivino`. **Reconcile before proceeding:** filled should be ≥ 368 (the rows covered even before expansion); "left for Vivino" should be roughly the non-red region-only rows + unknown-type multi-color-appellation rows. If "filled" is far below 368, stop and debug the gate.

- [ ] **Step 3: Spot-check the dry-run output** for one row of each class: a Pauillac (Cab-led), a Saint-Émilion (Merlot-led), a Sauternes/dessert (Sémillon-led), a region-only red, a trusted specific varietal, and confirm NO row with wine_type='white' receives a red blend (`grep -i white` over the log).

---

### Task 13: Live run + verification

- [ ] **Step 1: Live run**

Run: `cd backend && /usr/bin/python3 -m scripts.backfill_grapes 2>&1 | tail -3`
Expected: summary matching the dry run; Slack message `:grapes: Grapes backfill: …` arrives.

- [ ] **Step 2: Verify in the database**

```bash
cd backend && /usr/bin/python3 -c "
from db import get_service_client
db = get_service_client()
for region in ('Bordeaux', 'Rhône'):
    rows = []
    page = 0
    while True:
        r = db.table('wines').select('id,grapes').eq('region', region).order('id').range(page*1000,(page+1)*1000-1).execute().data
        rows.extend(r); page += 1
        if len(r) < 1000: break
    empty = sum(1 for x in rows if not (x['grapes'] or []))
    print(region, 'total', len(rows), 'still-empty', empty)
"
```

Expected: Bordeaux still-empty ≤ ~60 (was 361), Rhône still-empty ≤ ~30 (was 130).

- [ ] **Step 3: End-to-end scorer check** — run one recommend request (local backend) asking for a red blend in a Bordeaux-stocked zip and confirm a Bordeaux wine appears in the shortlist. (Manual: `cd backend && python3 -m uvicorn api.main:app` + one POST to `/api/recommend`, or via the frontend.)

---

### Task 14: Docs + wrap-up

**Files:**
- Modify: `CLAUDE.md` (items 13, 27), `docs/reference/enrichment.md`, `docs/reference/recommendation.md`, `docs/mini-agent-tasks.md`

- [ ] **Step 1: Update docs**

- `CLAUDE.md` item 27: mark the grapes backfill DONE with the fill counts from the live run; note the Vivino queue prioritization is live and that Vivino may now replace default blends; remaining: optional scorer region-fallback only.
- `CLAUDE.md` item 13: note the Vivino queue now front-loads both-null wines (Pogo's residue) — the fix path is live, drain pace is the weekly `VIVINO_LIMIT`.
- `docs/reference/enrichment.md`: document the color-aware defaults table, region-level red defaults, `ALL_DEFAULT_BLENDS`/replacement rule, and the queue tiers.
- `docs/reference/recommendation.md`: document the blend-aware grape matching + candidate varietal union.
- `docs/mini-agent-tasks.md`: append the run record (date, counts) under a short "grapes backfill" entry.

- [ ] **Step 2: Final commit**

```bash
git add CLAUDE.md docs/reference/enrichment.md docs/reference/recommendation.md docs/mini-agent-tasks.md
git commit -m "docs: item 27 grapes backfill + Vivino queue prioritization landed"
```
