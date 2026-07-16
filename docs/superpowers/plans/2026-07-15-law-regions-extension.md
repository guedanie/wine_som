# Law-Regions Defaults Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the law-blend defaults to Champagne, Douro/Port, Tuscany's Sangiovese DOCGs, Cava/Penedès, and Provence rosé, then re-run the grapes backfill (~355 more rows filled).

**Architecture:** Pure data extension of the machinery shipped 2026-07-14: region-level defaults generalize from a red-only dict to color-aware rules (mirroring `_DEFAULT_RULES`), new appellation entries slot into the existing table, and `scripts/backfill_grapes.py` only grows its `TARGET_REGIONS` tuple. The extractor needs zero changes. One one-row data correction (Madeira) precedes the run.

**Tech Stack:** Python 3.9 (`Optional[str]`, never `str | None`), pytest, supabase-py. Commands run from `backend/` with `/usr/bin/python3`.

**Spec:** `docs/superpowers/specs/2026-07-15-law-regions-extension-design.md` — the **conservative governing rule** in it is binding: hard-law entries only, plus the four explicitly-approved conventions (Port big-three, Cava trio, Penedès sparkling, Provence rosé). Do NOT add entries beyond the spec (no Bolgheri, no Madeira, no Cassis, no Tuscany region-level).

---

## Reference: current-code anchors

- `backend/enrichment/extraction/reference.py:421-436` — the block Task 1 replaces:

```python
# Region-level fallback for rows with no (recognized) appellation — reds only:
# Bordeaux AOC rouge is Merlot-led by law; region-only Rhône reds are
# overwhelmingly southern Côtes-du-Rhône GSM.
REGION_DEFAULT_GRAPES = {
    "bordeaux": ("Merlot", "Cabernet Sauvignon", "Cabernet Franc"),
    "rhone": _GSM_BLEND,
}


def default_grapes_for_region(region: Optional[str],
                              wine_type: Optional[str]) -> Optional[list]:
    """Region-level default blend; fires only when wine_type is exactly red."""
    if not region or _norm(wine_type or "") != "red":
        return None
    blend = REGION_DEFAULT_GRAPES.get(_norm(region))
    return list(blend) if blend else None
```

- `backend/enrichment/extraction/reference.py:441-443` — `ALL_DEFAULT_BLENDS` derivation (its `| frozenset(REGION_DEFAULT_GRAPES.values())` term changes in Task 1).
- `backend/scripts/backfill_grapes.py:33` — `TARGET_REGIONS = ("Bordeaux", "Rhône")`.
- Baselines: `tests/test_extraction_reference.py` has 29 tests; `tests/test_backfill_grapes.py` has 9; full fast suite is **521 passed, 3 deselected**.
- Run tests as: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/<file> -v` (fast suite: `tests/ -m "not integration" -q`).
- Grep check before assuming: `REGION_DEFAULT_GRAPES` has NO consumers outside `reference.py` (verify with `grep -rn REGION_DEFAULT_GRAPES backend/ --include="*.py"` — expect only reference.py) so renaming it is safe.

---

### Task 1: Color-aware region rules + the four new region entries

**Files:**
- Modify: `backend/enrichment/extraction/reference.py:421-443`
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests** (append to `test_extraction_reference.py`)

```python
def test_region_rules_champagne_sparkling_and_rose():
    """Champagne AOC permits 7 grapes; PN/Chard/Meunier are 99.7% of
    plantings. Rosé Champagne uses the same grapes. Tier A (hard law)."""
    from enrichment.extraction.reference import default_grapes_for_region
    champagne = ["Pinot Noir", "Chardonnay", "Pinot Meunier"]
    assert default_grapes_for_region("Champagne", "sparkling") == champagne
    assert default_grapes_for_region("Champagne", "rosé") == champagne   # accent folds
    assert default_grapes_for_region("Champagne", "red") is None
    assert default_grapes_for_region("Champagne", None) is None


def test_region_rules_douro_penedes_provence():
    """Approved Tier B conventions: Port big-three (red+dessert), Penedès
    sparkling = Cava trio, Provence rosé template."""
    from enrichment.extraction.reference import default_grapes_for_region
    port = ["Touriga Nacional", "Touriga Franca", "Tinta Roriz"]
    assert default_grapes_for_region("Douro", "dessert") == port
    assert default_grapes_for_region("Douro", "red") == port
    assert default_grapes_for_region("Douro", "white") is None
    assert default_grapes_for_region("Penedès", "sparkling") == \
        ["Macabeo", "Xarel·lo", "Parellada"]
    assert default_grapes_for_region("Penedes", "sparkling") is not None  # accent variant
    assert default_grapes_for_region("Penedès", "rosé") is None
    assert default_grapes_for_region("Provence", "rosé") == \
        ["Grenache", "Cinsault", "Syrah"]
    assert default_grapes_for_region("Provence", "red") is None


def test_region_rules_never_fire_without_explicit_type():
    """Region granularity is too coarse to guess on unknown type — the
    conservative invariant from the 07-14 design, now spanning all colors."""
    from enrichment.extraction.reference import default_grapes_for_region
    for region in ("Bordeaux", "Rhône", "Champagne", "Douro", "Penedès", "Provence"):
        assert default_grapes_for_region(region, None) is None, region
        assert default_grapes_for_region(region, "") is None, region


def test_all_default_blends_gains_the_new_trios():
    from enrichment.extraction.reference import ALL_DEFAULT_BLENDS
    assert ("Pinot Noir", "Chardonnay", "Pinot Meunier") in ALL_DEFAULT_BLENDS
    assert ("Touriga Nacional", "Touriga Franca", "Tinta Roriz") in ALL_DEFAULT_BLENDS
    assert ("Macabeo", "Xarel·lo", "Parellada") in ALL_DEFAULT_BLENDS
    assert ("Grenache", "Cinsault", "Syrah") in ALL_DEFAULT_BLENDS
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -k "region_rules or gains_the_new_trios" -v`
Expected: the three new region tests FAIL (Champagne/Douro/Penedès/Provence return None); the trios test FAILS on membership. `test_region_level_defaults_fire_only_for_explicit_red` (existing) still PASSES.

- [ ] **Step 3: Implement** — replace `reference.py` lines 421-436 (the `REGION_DEFAULT_GRAPES` dict + `default_grapes_for_region`, shown in the anchors above) with:

```python
# Region-level fallback for rows with no (recognized) appellation. Colors are
# REQUIRED at region granularity: these rules never fire on an unknown
# wine_type — a region is too coarse to guess a blend without the bottle's
# color confirming the law/convention applies. Tier A = hard law; Tier B =
# convention the user explicitly approved (multi-grape, Vivino-correctable).
_REGION_DEFAULT_RULES = [
    # (regions, grapes, wine_types the blend may fill)
    (("Bordeaux",), ("Merlot", "Cabernet Sauvignon", "Cabernet Franc"), ("red",)),
    (("Rhône",), _GSM_BLEND, ("red",)),
    # Champagne AOC: 7 legal grapes, these three are 99.7% of plantings (Tier A)
    (("Champagne",), ("Pinot Noir", "Chardonnay", "Pinot Meunier"),
     ("sparkling", "rose")),
    # Port/Douro tinto share the modern big three (Tier B — law permits 80+)
    (("Douro",), ("Touriga Nacional", "Touriga Franca", "Tinta Roriz"),
     ("red", "dessert")),
    # Penedès sparkling ≈ Cava; traditional trio ≈ 85-90% of production (Tier B)
    (("Penedès",), ("Macabeo", "Xarel·lo", "Parellada"), ("sparkling",)),
    # Provence rosé template; proportions are free by law (Tier B)
    (("Provence",), ("Grenache", "Cinsault", "Syrah"), ("rose",)),
]

_REGION_DEFAULTS = {}
for _regs, _grapes, _colors in _REGION_DEFAULT_RULES:
    for _r in _regs:
        _REGION_DEFAULTS.setdefault(_norm(_r), []).append((_grapes, _colors))


def default_grapes_for_region(region: Optional[str],
                              wine_type: Optional[str]) -> Optional[list]:
    """Region-level default blend; requires an explicit, matching wine_type
    (never fires on unknown — region granularity is too coarse to guess)."""
    wt = _norm(wine_type) if wine_type else None
    if not region or not wt:
        return None
    for grapes, colors in _REGION_DEFAULTS.get(_norm(region), []):
        if wt in colors:
            return list(grapes)
    return None
```

and change the `ALL_DEFAULT_BLENDS` derivation (lines 441-443) to:

```python
ALL_DEFAULT_BLENDS = frozenset(
    _g for _rules in _APPELLATION_DEFAULTS.values() for _g, _, _ in _rules
) | frozenset(_g for _regs, _g, _ in _REGION_DEFAULT_RULES)
```

(`REGION_DEFAULT_GRAPES` disappears; the anchors section documents that nothing else references it — verify with the grep before committing.)

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py tests/test_extraction.py tests/test_backfill_grapes.py -v`
Expected: ALL PASS — 33 in the reference file (29 + 4 new), and the existing Bordeaux/Rhône region tests (`test_region_level_defaults_fire_only_for_explicit_red`, backfill's `test_region_only_red_gets_region_default`, extractor's region-fallback tests) pass unchanged, proving behavior preservation.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: color-aware region default rules — Champagne, Douro, Penedès, Provence"
```

---

### Task 2: New appellation entries (Sangiovese DOCGs, Carmignano, Cava, Bandol, Blanc de Blancs)

**Files:**
- Modify: `backend/enrichment/extraction/reference.py` (`_DEFAULT_RULES`, append before its closing `]`)
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_tuscany_sangiovese_docgs():
    """Red-only DOCGs fire on unknown type. Brunello/Rosso are 100% Sangiovese
    by law; the others guarantee >=70-85% — 'contains Sangiovese' is never
    wrong, which is the bar for a Vivino-permanent single-grape value."""
    from enrichment.extraction.reference import default_grapes_for
    for app in ["Chianti", "Chianti Classico", "Brunello di Montalcino",
                "Rosso di Montalcino", "Montalcino",
                "Vino Nobile di Montepulciano", "Morellino di Scansano"]:
        assert default_grapes_for(app) == ["Sangiovese"], app
        assert default_grapes_for(app, wine_type="white") is None, app
    # Carmignano DOCG legally REQUIRES 10-20% Cabernet
    assert default_grapes_for("Carmignano") == ["Sangiovese", "Cabernet Sauvignon"]


def test_cava_and_blanc_de_blancs():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Cava") == ["Macabeo", "Xarel·lo", "Parellada"]
    assert default_grapes_for("Cava", wine_type="sparkling") == \
        ["Macabeo", "Xarel·lo", "Parellada"]
    assert default_grapes_for("Cava", wine_type="red") is None
    assert default_grapes_for("Blanc de Blancs") == ["Chardonnay"]


def test_bandol_requires_explicit_type():
    """Bandol bottles red, rosé AND white — unknown type must not guess.
    Red is law-backed (>=50% Mourvèdre); rosé is the approved convention."""
    from enrichment.extraction.reference import default_grapes_for
    mourvedre_led = ["Mourvèdre", "Grenache", "Cinsault"]
    assert default_grapes_for("Bandol") is None
    assert default_grapes_for("Bandol", wine_type="red") == mourvedre_led
    assert default_grapes_for("Bandol", wine_type="rosé") == mourvedre_led
    assert default_grapes_for("Bandol", wine_type="white") is None


def test_dropped_regions_stay_dropped():
    """Conservative rule: permissive/uncertain appellations must NOT gain
    defaults — Bolgheri (style, not law), Toscana IGT, Cassis, Madeira."""
    from enrichment.extraction.reference import (default_grapes_for,
                                                 default_grapes_for_region)
    for app in ["Bolgheri", "Toscana IGT", "Cassis", "Madeira"]:
        assert default_grapes_for(app) is None, app
        assert default_grapes_for(app, wine_type="red") is None, app
    assert default_grapes_for_region("Tuscany", "red") is None
    assert default_grapes_for_region("Other Spain", "sparkling") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -k "sangiovese or cava_and or bandol or dropped_regions" -v`
Expected: first three FAIL (new appellations return None); `test_dropped_regions_stay_dropped` PASSES already (it pins absences — confirm that's why).

- [ ] **Step 3: Implement** — append inside `_DEFAULT_RULES` before its closing `]`:

```python
    # Tuscany Sangiovese DOCGs — red-only appellations, fire on unknown type.
    # Brunello/Rosso: 100% Sangiovese by law; the rest guarantee >=70-85%,
    # so a single 'Sangiovese' is incomplete but never wrong (single-grape
    # values are Vivino-permanent — that's the bar). NO Tuscany region rule:
    # Super Tuscans (Bolgheri) hide in region-only rows.
    (("Chianti", "Chianti Classico", "Brunello di Montalcino",
      "Rosso di Montalcino", "Montalcino", "Vino Nobile di Montepulciano",
      "Morellino di Scansano"), ("Sangiovese",), ("red",), False),
    # Carmignano DOCG legally requires 10-20% Cabernet alongside Sangiovese
    (("Carmignano",), ("Sangiovese", "Cabernet Sauvignon"), ("red",), False),
    # Cava DO is sparkling-only; traditional trio ≈ 85-90% of production
    (("Cava",), ("Macabeo", "Xarel·lo", "Parellada"), ("sparkling",), False),
    # Bandol also bottles white — unknown type must not guess. Red is
    # law-backed (>=50% Mourvèdre); rosé is the user-approved convention.
    (("Bandol",), ("Mourvèdre", "Grenache", "Cinsault"), ("red", "rose"), True),
    # A 'Blanc de Blancs' sub_region is 100% Chardonnay by definition
    (("Blanc de Blancs",), ("Chardonnay",), ("sparkling",), False),
```

Do NOT add "Montalcino" or "Blanc de Blancs" to `APPELLATIONS` — they enter only the defaults index (no evidence-gate / `parent_region_for` side effects; spec §2 note).

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -v`
Expected: ALL PASS — 37 tests (33 + 4).

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: appellation defaults — Sangiovese DOCGs, Carmignano, Cava, Bandol, Blanc de Blancs"
```

---

### Task 3: Backfill targets the new regions

**Files:**
- Modify: `backend/scripts/backfill_grapes.py:33` (TARGET_REGIONS) and the `fetch_target_wines` docstring
- Test: `backend/tests/test_backfill_grapes.py`

- [ ] **Step 1: Write the failing tests** (append to `test_backfill_grapes.py`)

```python
def test_champagne_sparkling_gets_pn_led_blend():
    changes, rule = plan_change(_row(region="Champagne", wine_type="sparkling"))
    assert changes == {"grapes": ["Pinot Noir", "Chardonnay", "Pinot Meunier"],
                       "varietal": "Pinot Noir"}
    assert rule == "region"


def test_generic_port_varietal_keeps_label_gains_blend():
    """varietal='Port' is a place-word, not a grape — is_specific_grape says
    generic, so the blend fills and the label survives."""
    changes, rule = plan_change(_row(region="Douro", wine_type="dessert",
                                     varietal="Port"))
    assert changes == {"grapes": ["Touriga Nacional", "Touriga Franca",
                                  "Tinta Roriz"]}
    assert rule == "region"


def test_chianti_classico_fills_on_unknown_type():
    changes, rule = plan_change(_row(region="Tuscany", wine_type=None,
                                     sub_region="Chianti Classico"))
    assert changes == {"grapes": ["Sangiovese"], "varietal": "Sangiovese"}
    assert rule == "appellation"


def test_tuscany_region_only_rows_left_for_vivino():
    """No Tuscany region rule (Super Tuscans) — typed red or not."""
    assert plan_change(_row(region="Tuscany", wine_type="red"))[0] == {}
    assert plan_change(_row(region="Tuscany", wine_type=None))[0] == {}


def test_provence_rose_fills_white_does_not():
    changes, rule = plan_change(_row(region="Provence", wine_type="rosé"))
    assert changes["grapes"] == ["Grenache", "Cinsault", "Syrah"]
    assert rule == "region"
    assert plan_change(_row(region="Provence", wine_type="white"))[0] == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_grapes.py -v`
Expected: the 5 new tests FAIL with `changes == {}` / rule None (regions not in TARGET_REGIONS yet — note the reference-layer rules from Tasks 1-2 are live, so the ONLY missing piece is the target list); the 9 existing tests PASS.

- [ ] **Step 3: Implement** — in `backend/scripts/backfill_grapes.py` replace line 33:

```python
TARGET_REGIONS = ("Bordeaux", "Rhône", "Champagne", "Douro", "Tuscany",
                  "Penedès", "Other Spain", "Provence")
```

and update the `fetch_target_wines` docstring's row estimate ("~1,450 rows, 2 pages" → "~2,100 rows, 3 pages").

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_grapes.py -v && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: 14 passed in the file; full fast suite **534 passed** (521 + 4 + 4 + 5), 3 deselected.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_grapes.py backend/tests/test_backfill_grapes.py
git commit -m "feat: backfill targets Champagne, Douro, Tuscany, Penedès, Other Spain, Provence"
```

---

### Task 4: Madeira retype + full dry run + reconcile (runbook — controller executes)

- [ ] **Step 1: Retype the one Madeira row.** Find it, eyeball the name to confirm it IS a Madeira, then retype — this keeps the Douro region rule from stamping a Port blend on it:

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "
from db import get_service_client
db = get_service_client()
rows = db.table('wines').select('id,name,region,sub_region,wine_type,grapes').eq('region','Douro').eq('sub_region','Madeira').execute().data
for r in rows: print(r)
"
```

Verify the printout shows a genuine Madeira (name contains 'Madeira'). If it does NOT, STOP and reassess. If it does:

```bash
/usr/bin/python3 -c "
from db import get_service_client
db = get_service_client()
db.table('wines').update({'region': 'Madeira'}).eq('region','Douro').eq('sub_region','Madeira').execute()
print('retyped')
"
```

- [ ] **Step 2: Full read-only dry run**

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m scripts.backfill_grapes --dry-run > <scratchpad>/lawregions_dryrun.log 2>&1; tail -1 <scratchpad>/lawregions_dryrun.log
```

Expected summary shape: `~490 empty of ~2,100 … wines, ~355 filled (…), ~135 left for Vivino` — the previously-filled Bordeaux/Rhône rows no longer count as empty, so "empty" ≈ 116 (old leftovers) + ~513 new-region empties − overlap. **Reconcile against the spec table:** Champagne ~147, Douro ~96, Tuscany ~13, Penedès ~26, Cava ~8, Provence ~65. If Champagne or Douro fills are >20% off the estimate, STOP and investigate before the live run.

- [ ] **Step 3: Spot-check the dry-run log**: one Champagne (PN-led + sparkling), one Port (`Touriga Nacional`-led, generic 'Port' varietal preserved), one Chianti (`Sangiovese`), one Provence rosé (Grenache-led), and confirm zero DRY lines pair a `white`-typed row with any blend, and no Tuscany region-level fills exist (every Tuscany DRY line must say `appellation`).

---

### Task 5: Live run + verification (runbook — controller executes)

- [ ] **Step 1: Live run**

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m scripts.backfill_grapes > <scratchpad>/lawregions_live.log 2>&1; tail -1 <scratchpad>/lawregions_live.log
```

Expected: summary identical to the dry run; Slack `:grapes:` message arrives.

- [ ] **Step 2: Verify in the database** — per-region still-empty counts:

```bash
/usr/bin/python3 -c "
from db import get_service_client
db = get_service_client()
for region in ('Champagne','Douro','Tuscany','Penedès','Other Spain','Provence'):
    rows, page = [], 0
    while True:
        r = db.table('wines').select('id,grapes').eq('region', region).order('id').range(page*1000,(page+1)*1000-1).execute().data
        rows.extend(r); page += 1
        if len(r) < 1000: break
    empty = sum(1 for x in rows if not (x['grapes'] or []))
    print(region, 'total', len(rows), 'still-empty', empty)
"
```

Expected: Champagne ≤ ~12, Douro ≤ ~25, Penedès ≤ ~11, Provence ≤ ~10; Tuscany stays high (~89 — unknown-type + region-only rows deliberately left).

- [ ] **Step 3: Catalog-wide effect** — rerun the grapes-empty and no-grapes-no-varietal counts (same paged snippets as yesterday); expect grapes-empty to drop from 4,840 to ≈ 4,485 and report the new percentages.

---

### Task 6: Docs

**Files:**
- Modify: `CLAUDE.md` (item 27), `docs/reference/enrichment.md`, `docs/mini-agent-tasks.md`

- [ ] **Step 1: Update docs**
- `CLAUDE.md` item 27: append a sentence to the grapes-backfill note: law-regions extension DONE 2026-07-15 (Champagne/Port/Sangiovese DOCGs/Cava/Provence rosé, ~N rows filled — use the live numbers), governed by the conservative rule (hard law + approved conventions only; Bolgheri/Madeira/Cassis deliberately excluded).
- `docs/reference/enrichment.md`: extend the color-aware defaults section with the region-rule generalization (colors at region level, explicit-type-only) and the new entries table (Tier A/B annotations).
- `docs/mini-agent-tasks.md`: append the run record under the Task 4 entry (date, per-region fills, Madeira retype note).

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/reference/enrichment.md docs/mini-agent-tasks.md
git commit -m "docs: law-regions defaults extension landed (Champagne, Port, Sangiovese DOCGs, Cava, Provence)"
```
