# NULL wine_type Backfill (+ infer_wine_type hardening) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the deterministically-inferable NULL `wine_type` rows (~3,985 of 5,443) by hardening `infer_wine_type` (accent-folding + sparkling method terms + grape-vocab parity with `CORE_GRAPES`) and adding law-backed appellation→type inference, then a one-off backfill.

**Architecture:** Same shape as the 2026-07-14 grapes backfill. Shared `infer_wine_type` (`utils/__init__.py`) is hardened once (benefits every caller incl. the runtime type gate); a new `wine_type_for_appellation` (`reference.py`) adds single-color-appellation typing; a new `scripts/backfill_wine_type.py` (pure `plan_change` core + paged runner) writes fill-only. Correctness is guarded by determinism + a dry-run precision audit.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `str | None`), pytest, supabase-py, `unicodedata` (stdlib). Commands from `backend/` with `/usr/bin/python3`.

**Spec:** `docs/superpowers/specs/2026-07-17-wine-type-backfill-design.md`

---

## Reference: current-code anchors

- `utils/__init__.py:1-70` — `RED_VARIETALS`/`WHITE_VARIETALS`/`SPARKLING_TERMS`/`ROSE_TERMS`/`DESSERT_TERMS` (curated lowercase sets, some with accents) + `infer_wine_type(text)`. It lowercases input but does NOT strip accents; word-boundary `_has()` matching; precedence sparkling→rosé→dessert→red→white→generic-color.
- `enrichment/extraction/reference.py` — `CORE_GRAPES` dict (`red`/`white`/`rose` lists, accented spellings), `_norm(s)` (NFKD accent-strip + lowercase + hyphen-fold + whitespace-collapse), `APPELLATIONS` (region → sub-region list).
- `scripts/backfill_grapes.py` — the runner pattern to mirror (`plan_change`, `fetch_target_wines`, `_notify_slack`, `main` with `--dry-run`/`--limit`, per-rule counts, Slack).
- Baseline fast suite: **558 passed, 3 deselected.** Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/<file> -v` (fast: `tests/ -m "not integration" -q`).
- `infer_wine_type` callers to keep green: `scrapers/*`, `enrichment/extraction/*`, `recommendation/candidate_filters.py` (`resolve_wine_type`). Its test file: `tests/test_infer_wine_type.py` (if present) or `tests/test_utils.py` — grep first: `grep -rl infer_wine_type backend/tests`.

---

### Task 1: Accent-fold `infer_wine_type` + add sparkling method terms

Accent-folding is prerequisite for `CORE_GRAPES` parity (its entries are accented). It only makes matching more permissive (accented inputs now match ASCII vocab), never less.

**Files:**
- Modify: `backend/utils/__init__.py`
- Test: `backend/tests/test_infer_wine_type.py` (create if it doesn't exist; if `infer_wine_type` tests already live in `tests/test_utils.py`, append there instead — grep first)

- [ ] **Step 1: Write the failing tests**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from utils import infer_wine_type


def test_accent_folded_varietals_resolve():
    assert infer_wine_type("Mourvèdre") == "red"
    assert infer_wine_type("Gewürztraminer") == "white"
    assert infer_wine_type("Sémillon") == "white"


def test_pet_nat_and_col_fondo_are_sparkling_not_red():
    # 'Zinfandel Pet Nat' matched the Zinfandel red-word before this fix
    assert infer_wine_type("Zinfandel Pet Nat") == "sparkling"
    assert infer_wine_type("Pétillant Naturel Rosé") == "sparkling"
    assert infer_wine_type("Col Fondo") == "sparkling"


def test_existing_behavior_preserved():
    assert infer_wine_type("Cabernet Sauvignon") == "red"
    assert infer_wine_type("Red Wine") == "red"
    assert infer_wine_type("Sauvignon Blanc") == "white"
    assert infer_wine_type("Rosé") == "rosé"
    assert infer_wine_type("Sparkling Wine") == "sparkling"
    assert infer_wine_type("Portuguese") is None   # 'port' substring must NOT fire
    assert infer_wine_type("Fruit Cocktail") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_infer_wine_type.py -v`
Expected: FAIL — `Mourvèdre` returns None (accent), `Zinfandel Pet Nat` returns "red".

- [ ] **Step 3: Implement**

At the top of `utils/__init__.py`, add `import unicodedata` next to `import re`. Add a fold helper and apply it to the input; add the sparkling terms:

```python
def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
```

Extend `SPARKLING_TERMS` (all entries must be accent-folded ASCII):

```python
SPARKLING_TERMS = {"prosecco", "champagne", "cava", "sparkling", "cremant",
                   "frizzante", "espumante", "spumante", "pet nat", "pet-nat",
                   "petnat", "petillant", "col fondo", "methode ancestrale",
                   "ancestral", "lambrusco", "franciacorta"}
```

(Drop the now-redundant accented `"crémant"` — folding covers it.) In `infer_wine_type`, change the first line from `s = text.lower()` to:

```python
    s = _fold(text)
```

The existing vocab sets already store lowercase; `_fold` also strips accents from input, so accented inputs like "Mourvèdre" match the ASCII vocab in Task 2. Leave the rest of the function unchanged.

- [ ] **Step 4: Run the new tests + all `infer_wine_type` callers' suites**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_infer_wine_type.py tests/test_extraction.py tests/test_candidate_filters.py -v`
Expected: ALL PASS. (Accent-folding is strictly more permissive; existing behavior preserved by `test_existing_behavior_preserved`.)

- [ ] **Step 5: Commit**

```bash
git add backend/utils/__init__.py backend/tests/test_infer_wine_type.py
git commit -m "feat: infer_wine_type accent-folds input + recognizes Pet Nat/Col Fondo sparkling"
```

---

### Task 2: Grape-vocab parity with `CORE_GRAPES`

**Files:**
- Modify: `backend/utils/__init__.py` (`RED_VARIETALS`, `WHITE_VARIETALS`)
- Test: `backend/tests/test_infer_wine_type.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_newly_added_grapes_resolve():
    for red in ["Nero d'Avola", "Gamay", "Corvina", "Cinsault", "Carignan",
                "Aglianico", "Pinotage", "Monastrell", "Cabernet Franc"]:
        assert infer_wine_type(red) == "red", red
    for white in ["Grüner Veltliner", "Sémillon", "Furmint", "Melon de Bourgogne",
                  "Garganega", "Trebbiano", "Cortese", "Fiano", "Greco",
                  "Assyrtiko", "Vermentino"]:
        assert infer_wine_type(white) == "white", white


def test_infer_covers_core_grapes():
    """Drift guard: every CORE_GRAPES red/white entry must resolve to its color,
    so the two vocabularies can't silently diverge."""
    from enrichment.extraction.reference import CORE_GRAPES
    for g in CORE_GRAPES["red"]:
        assert infer_wine_type(g) == "red", g
    for g in CORE_GRAPES["white"]:
        assert infer_wine_type(g) == "white", g
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_infer_wine_type.py -k "newly_added or covers_core" -v`
Expected: FAIL — e.g. "Nero d'Avola", "Furmint" return None.

- [ ] **Step 3: Implement** — replace the `RED_VARIETALS` and `WHITE_VARIETALS` sets in `utils/__init__.py` with these (accent-folded ASCII, superset covering every `CORE_GRAPES` entry):

```python
RED_VARIETALS = {
    "cabernet sauvignon", "cabernet", "cabernet franc", "merlot", "pinot noir",
    "syrah", "shiraz", "malbec", "zinfandel", "sangiovese", "tempranillo",
    "grenache", "garnacha", "red blend", "petit verdot", "petite sirah",
    "mourvedre", "monastrell", "nebbiolo", "barbera", "dolcetto", "montepulciano",
    "primitivo", "carmenere", "tannat", "gamay", "cinsault", "carignan",
    "aglianico", "corvina", "pinotage", "nero d'avola",
    "touriga nacional", "touriga", "baga", "trincadeira", "tinto",
}
WHITE_VARIETALS = {
    "chardonnay", "sauvignon blanc", "pinot grigio", "pinot gris", "riesling",
    "albarino", "alvarinho", "viognier", "white blend", "moscato", "muscat",
    "gewurztraminer", "chenin blanc", "gruner veltliner", "vermentino",
    "torrontes", "roussanne", "marsanne", "verdejo", "semillon", "garganega",
    "trebbiano", "cortese", "melon de bourgogne", "fiano", "greco", "assyrtiko",
    "furmint", "loureiro", "encruzado", "rabigato", "arinto", "branco", "blanco",
}
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_infer_wine_type.py -v`
Expected: ALL PASS incl. the `CORE_GRAPES` parity guard.

- [ ] **Step 5: Commit**

```bash
git add backend/utils/__init__.py backend/tests/test_infer_wine_type.py
git commit -m "feat: infer_wine_type vocab covers all CORE_GRAPES (Nero d'Avola, Furmint, Gamay…)"
```

---

### Task 3: `wine_type_for_appellation` — single-color appellation → type

**Files:**
- Modify: `backend/enrichment/extraction/reference.py` (append near the grape-default helpers)
- Test: `backend/tests/test_extraction_reference.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_wine_type_for_appellation_single_color():
    from enrichment.extraction.reference import wine_type_for_appellation
    assert wine_type_for_appellation("Burgundy", "Chablis") == "white"
    assert wine_type_for_appellation("Champagne", None) == "sparkling"
    assert wine_type_for_appellation("Tuscany", "Brunello di Montalcino") == "red"
    assert wine_type_for_appellation("Bordeaux", "Sauternes") == "dessert"
    assert wine_type_for_appellation("Other Spain", "Jerez") == "fortified"
    assert wine_type_for_appellation("Douro", "Port") == "fortified"


def test_wine_type_for_appellation_rejects_multicolor_and_unknown():
    from enrichment.extraction.reference import wine_type_for_appellation
    # multi-color appellations/regions can't be typed from place
    assert wine_type_for_appellation("Burgundy", "Meursault") is None   # white AND used red? Meursault is white but not mapped -> None is fine
    assert wine_type_for_appellation("Bordeaux", "Margaux") is None     # red+white communes excluded
    assert wine_type_for_appellation("Tuscany", None) is None           # bare region, multi-color
    assert wine_type_for_appellation("Douro", None) is None             # Douro does red+white+port
    assert wine_type_for_appellation(None, None) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -k wine_type_for_appellation -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement** — append to `reference.py`:

```python
# Definitionally single-color/style appellations (and a few single-style
# regions) → wine_type. Multi-color places (Burgundy villages, Bordeaux
# communes, Rhône, Alsace, bare regions like Tuscany/Piedmont/Douro) are
# deliberately absent — they can't be typed from place alone. Keyed by _norm.
_APPELLATION_TYPE_RAW = {
    "white": ["Chablis", "Petit Chablis", "Sancerre", "Pouilly-Fumé", "Muscadet",
              "Savennières", "Gavi", "Soave", "Vinho Verde", "Rueda",
              "Rías Baixas", "Entre-Deux-Mers"],
    "red": ["Brunello di Montalcino", "Rosso di Montalcino", "Barolo", "Barbaresco",
            "Chianti", "Chianti Classico", "Vino Nobile di Montepulciano",
            "Morellino di Scansano", "Amarone della Valpolicella"],
    "sparkling": ["Champagne", "Cava", "Prosecco", "Franciacorta", "Lambrusco",
                  "Crémant"],
    "dessert": ["Sauternes", "Barsac", "Tokaji", "Recioto", "Vin Santo"],
    "fortified": ["Port", "Porto", "Sherry", "Jerez", "Fino", "Manzanilla",
                  "Amontillado", "Oloroso", "Madeira", "Marsala", "Banyuls"],
}
APPELLATION_WINE_TYPE = {}
for _t, _names in _APPELLATION_TYPE_RAW.items():
    for _n in _names:
        APPELLATION_WINE_TYPE[_norm(_n)] = _t


def wine_type_for_appellation(region, sub_region) -> Optional[str]:
    """Wine type from a definitionally single-color/style appellation, checking
    the (finer) sub_region first, then the region. None when the place is
    multi-color or unknown."""
    for place in (sub_region, region):
        if place:
            t = APPELLATION_WINE_TYPE.get(_norm(place))
            if t:
                return t
    return None
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_extraction_reference.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: wine_type_for_appellation — single-color appellations (Chablis, Champagne, Brunello…)"
```

---

### Task 4: Backfill `plan_change` core

**Files:**
- Create: `backend/scripts/backfill_wine_type.py` (planning core only)
- Test: `backend/tests/test_backfill_wine_type.py` (new)

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_backfill_wine_type.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.backfill_wine_type import plan_change


def _row(**kw):
    base = {"id": "w1", "name": "", "varietal": None, "grapes": [],
            "region": None, "sub_region": None, "wine_type": None}
    base.update(kw); return base


def test_resolves_from_varietal():
    assert plan_change(_row(varietal="Nero d'Avola")) == {"wine_type": "red"}


def test_resolves_from_name_when_varietal_missing():
    assert plan_change(_row(name="Domaine X Chablis 2022", varietal=None)) == {"wine_type": "white"}


def test_resolves_from_grape_when_varietal_and_name_miss():
    assert plan_change(_row(name="Domaine X 2022", grapes=["Furmint"])) == {"wine_type": "white"}


def test_resolves_from_appellation_last():
    # no varietal/grape and a name with no type word, but region is single-color
    assert plan_change(_row(name="Canalicchio Di Sopra 2019", region="Tuscany",
                            sub_region="Brunello di Montalcino")) == {"wine_type": "red"}


def test_fill_only_never_overwrites():
    assert plan_change(_row(varietal="Merlot", wine_type="white")) == {}


def test_noop_when_unresolvable():
    assert plan_change(_row(name="Del Monte Fruit Cocktail in Heavy Syrup")) == {}
    assert plan_change(_row(name="Domaine Lignier Morey-Saint-Denis", region="Burgundy")) == {}


def test_pet_nat_resolves_sparkling_not_red():
    assert plan_change(_row(name="Old World Winery Zinfandel Pet Nat")) == {"wine_type": "sparkling"}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_wine_type.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement** — create `backend/scripts/backfill_wine_type.py`:

```python
"""One-off wine_type backfill for NULL-wine_type wines (CLAUDE.md item 30).

27.5% of wines have wine_type NULL, invisible to DB-level type surfaces (search
filter, /deals, /discover, stats). Per row (fill-only, never overwrites), resolve
type deterministically in precedence order:

1. infer_wine_type(varietal)
2. infer_wine_type(name)
3. infer_wine_type(first grape)
4. wine_type_for_appellation(region, sub_region)   # single-color appellations

None resolves -> no-op (non-wine junk + signal-less producers stay NULL for
Vivino/LLM). wine_type is fill-only and Vivino can't overwrite it, so writes are
permanent — the resolvers are deterministic/law-backed only.

Run from backend/ (../.env resolves):
    python3 -m scripts.backfill_wine_type [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import infer_wine_type                                       # noqa: E402
from enrichment.extraction.reference import wine_type_for_appellation   # noqa: E402


def plan_change(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return {"wine_type": <resolved>} to write, or {} for a no-op."""
    if row.get("wine_type"):
        return {}
    for text in (row.get("varietal"), row.get("name"),
                 (row.get("grapes") or [None])[0]):
        if text:
            t = infer_wine_type(text)
            if t:
                return {"wine_type": t}
    t = wine_type_for_appellation(row.get("region"), row.get("sub_region"))
    return {"wine_type": t} if t else {}
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_wine_type.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_wine_type.py backend/tests/test_backfill_wine_type.py
git commit -m "feat: backfill_wine_type plan_change — varietal>name>grape>appellation, fill-only"
```

---

### Task 5: Backfill runner

**Files:**
- Modify: `backend/scripts/backfill_wine_type.py` (append)

- [ ] **Step 1: Append the runner**

```python
def fetch_null_type_wines(db, limit: int = 0) -> List[Dict[str, Any]]:
    """All wines with wine_type NULL (paged)."""
    wines, page, page_size = [], 0, 1000
    while True:
        rows = (db.table("wines")
                .select("id,name,varietal,grapes,region,sub_region,wine_type")
                .is_("wine_type", "null")
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

    wines = fetch_null_type_wines(db, limit=args.limit)
    print(f"examining {len(wines)} NULL-wine_type wines", flush=True)

    by_type: Dict[str, int] = {}
    changed = 0
    for w in wines:
        changes = plan_change(w)
        if not changes:
            continue
        changed += 1
        t = changes["wine_type"]
        by_type[t] = by_type.get(t, 0) + 1
        tag = "DRY " if args.dry_run else ""
        print(f'{tag}{w["id"][:8]} | {(w["name"] or "")[:55]} | {t}', flush=True)
        if not args.dry_run:
            db.table("wines").update(changes).eq("id", w["id"]).execute()

    dist = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items(), key=lambda x: -x[1]))
    summary = (f"wine_type backfill{' (dry run)' if args.dry_run else ''}: "
               f"{changed} of {len(wines)} NULL-type wines filled ({dist}), "
               f"{len(wines) - changed} left NULL")
    print(summary, flush=True)
    if not args.dry_run:
        _notify_slack(f":wine_glass: {summary}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sanity — tests + bounded read-only dry run**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_wine_type.py -v && /usr/bin/python3 -m scripts.backfill_wine_type --dry-run --limit 100`
Expected: tests PASS; dry run prints ~60-75 `DRY … | <type>` lines + a summary, writes nothing (verify no `db.table(...).update` runs outside the `if not args.dry_run` guard by reading the code path).

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/backfill_wine_type.py
git commit -m "feat: backfill_wine_type runner — paged fetch, dry-run, per-type counts, Slack"
```

---

### Task 6: Full suite + production dry-run precision audit (controller runs)

- [ ] **Step 1: Full fast suite**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: ALL PASS (558 + the new tests).

- [ ] **Step 2: Full dry-run to a log**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m scripts.backfill_wine_type --dry-run > <scratchpad>/wine_type_dryrun.log 2>&1; tail -1 <scratchpad>/wine_type_dryrun.log`
Expected summary: `~3,985 of 5,443 … filled (~2,085 red, ~980 white, ~140 sparkling, …), ~1,460 left NULL`. Reconcile against the spec estimate; if `filled` is far off (< 3,600 or > 4,300), STOP and investigate.

- [ ] **Step 3: Precision audit of the risky tiers.** From the dry-run log:
  - `grep -iE "fruit|cocktail|pancake|waffle|sake|soda|syrup|cookies|snack|peach|juice|cider" <log>` — **must be empty** (non-wine junk must NOT be typed). If any appear, patch `infer_wine_type` (the offending term is matching a color/varietal word) and re-run before the live pass.
  - Hand-eyeball ~30 lines that resolved via name or appellation for mislabels (a brand-color "Red Car" Chardonnay → white must not read red; a still wine → not sparkling). Spot-check a Chablis→white, a Brunello→red, a Champagne→sparkling, a Sherry→fortified, an Arneis/Furmint→white.
  - Confirm no row with a stored non-null wine_type appears (fill-only) — `grep -c "| " <log>` sanity vs the summary's filled count.

---

### Task 7: Live run + verification (controller runs)

- [ ] **Step 1: Live run**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m scripts.backfill_wine_type > <scratchpad>/wine_type_live.log 2>&1; tail -1 <scratchpad>/wine_type_live.log`
Expected: summary matching the dry run; Slack `:wine_glass:` message arrives.

- [ ] **Step 2: Verify catalog-wide**

```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "
from db import get_service_client
db = get_service_client()
total = db.table('wines').select('id', count='exact').execute().count
vnull = db.table('wines').select('id', count='exact').is_('wine_type','null').execute().count
print(f'wine_type NULL: {vnull}/{total} ({vnull/total*100:.1f}%)  [was 5443 / 27.5%]')
"
```

Expected: NULL rate ~27.5% → ~10-11% (≈ the 1,460 unresolvable + any new wines).

- [ ] **Step 3: Surface spot-check** — pick one formerly-NULL wine now typed (e.g. a Chablis → white or an Arneis → white from the live log) and confirm it now appears when filtering that type on the search screen (or via the search API's type filter). Record the wine + result in run notes.

---

### Task 8: Docs

**Files:**
- Modify: `CLAUDE.md` (item 30), `docs/reference/enrichment.md`

- [ ] **Step 1: Update docs**
- `CLAUDE.md` item 30: mark DONE with the live numbers (filled count, per-type, new NULL rate); note the `infer_wine_type` hardening (accent-fold, Pet Nat/Col Fondo sparkling, CORE_GRAPES parity guard) and `wine_type_for_appellation`; note the ~1,460 remainder (non-wine junk → item 32 purge; signal-less producers → Vivino/LLM).
- `docs/reference/enrichment.md`: document the hardened `infer_wine_type` (accent-folding, sparkling method terms, CORE_GRAPES parity test) + `wine_type_for_appellation` (single-color map) + the backfill script and its run numbers.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/reference/enrichment.md
git commit -m "docs: NULL wine_type backfill landed + infer_wine_type hardening"
```
