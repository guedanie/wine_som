# Purge Non-Wine Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect non-wine catalog noise conservatively and soft-delete it from every wine-surfacing read path, without ever dropping a real wine.

**Architecture:** A canonical `enrichment/non_wine.py` (markers + name check + guarded `should_exclude`); a migration adding `excluded_at`/`exclusion_reason` to `wines`; a dry-run-first `scripts/purge_non_wine.py`; and `excluded_at IS NULL` filtering across recommend/search/deals/wines/region.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), supabase-py, pytest, Postgres (DDL via `DATABASE_URL`).

**Env:** Backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`. `DATABASE_URL` is set in `../.env` (direct Postgres).

**Reference:** spec `docs/superpowers/specs/2026-07-21-purge-non-wine-design.md`. Existing detector: `scripts/backfill_wine_type.py` lines ~63-87 (`_NON_WINE_MARKERS` + `_is_non_wine`, whole-word `\bmarker\b`).

---

### Task 1: Canonical `non_wine` module + refactor `backfill_wine_type`

**Files:**
- Create: `backend/enrichment/non_wine.py`
- Modify: `backend/scripts/backfill_wine_type.py` (remove local markers/`_is_non_wine`, import shared)
- Test: `backend/tests/test_non_wine.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_non_wine.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.non_wine import is_non_wine_name, should_exclude, matched_marker


def _w(name, varietal=None, grapes=None):
    return {"name": name, "varietal": varietal, "grapes": grapes or []}


# --- name matching (whole-word) ---
def test_flags_clear_non_wine_names():
    for n in ["Del Monte Fruit Cocktail in Heavy Syrup", "Pacifico Mexican Lager",
              "Gekkeikan Sake Nigori", "Stemless Champagne Glassware Set",
              "Birch Benders Organic Pancake & Waffle Mix", "Zarbee's Cough Syrup"]:
        assert is_non_wine_name(n) is True, n


def test_whole_word_does_not_flag_real_wine_names():
    for n in ["Barbera d'Alba", "Barolo Riserva", "Bardolino Classico",
              "Herdade do Alentejo Tinto", "Aleatico Passito", "Beerenauslese Riesling"]:
        assert is_non_wine_name(n) is False, n


# --- should_exclude guards ---
def test_excludes_flagged_with_no_wine_signal():
    assert should_exclude(_w("Pacifico Mexican Lager")) is True
    assert should_exclude(_w("Del Monte Fruit Cocktail")) is True


def test_barrel_guard_keeps_barrel_aged_wine():
    assert should_exclude(_w("Bota Box Bourbon Barrel Cabernet",
                             varietal="Cabernet Sauvignon")) is False
    # even if a marker somehow matched, 'barrel' in the name protects it
    assert should_exclude(_w("Some Beer Barrel Aged Red", grapes=["Zinfandel"])) is False


def test_wine_signal_guard_keeps_varietal_or_grape():
    # 'gift set' flags the name, but a real Bordeaux carries region/varietal
    assert should_exclude(_w("Chateau Calon-Segur Bordeaux Gift Set",
                             varietal="Cabernet Sauvignon")) is False
    assert should_exclude(_w("Some Lager-named Wine", grapes=["Riesling"])) is False


def test_allowlist_keeps_known_collisions():
    # these aren't flagged by the deny-list today, but the allowlist is insurance
    assert should_exclude(_w("Hampton Water Rose")) is False


def test_matched_marker_reports_reason():
    assert matched_marker("Pacifico Mexican Lager") == "lager"
    assert matched_marker("Chateau Margaux 2015") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_non_wine.py -v`
Expected: FAIL (`ModuleNotFoundError: enrichment.non_wine`).

- [ ] **Step 3: Create the module**

Create `backend/enrichment/non_wine.py`:

```python
"""Canonical non-wine detection for the catalog (CLAUDE.md item 32).

Grocery scrapers pull non-wine products into `wines` (fruit cocktail, sake, beer,
cough syrup, glassware). This module is the single source of truth for detecting
them. `is_non_wine_name` is a whole-word deny-list match (shared with the wine_type
backfill). `should_exclude` is the conservative PURGE gate — it adds guards so a real
wine is never dropped.
"""
import re
from typing import Any, Dict, List, Optional

# Whole-word markers of clearly non-wine products. Deliberately EXCLUDES tokens that
# collide with real wines: bourbon/rum/brandy (barrel-aged wines), water/soda
# (Hampton Water rosé, Soda Canyon), martini (Martini Asti), stout (Stout Family),
# opener ("Road Opener"), punch. Wine-adjacent products (vermouth, sangria,
# wine-cocktails) are intentionally NOT here — they're kept.
NON_WINE_MARKERS = (
    # fermented non-grape / rice
    "sake", "junmai", "daiginjo", "ginjo", "nigori", "mead",
    # beer
    "beer", "ale", "lager", "ipa", "pilsner", "kombucha",
    # non-alcoholic / soft
    "non-alcoholic", "non alcoholic", "nonalcoholic", "alcohol removed",
    "alcohol-removed", "zero proof", "seltzer", "hard cider", "cider",
    "lemonade", "limeade", "iced tea", "sweet tea", "sparkling water",
    "tonic water", "energy drink",
    # cocktails / RTD noise (fruit cocktail is food; wine-cocktails carry a varietal
    # and are protected by the wine-signal guard)
    "cocktail", "cocktails",
    # food / grocery
    "maple syrup", "pancake", "waffle", "grapefruit", "fruit cup", "oatmeal",
    "grits", "fruit wine", "apple wine", "peach wine", "plum wine", "syrup",
    "cookies and cream", "cookies & cream", "cough syrup", "cough",
    # merchandise / accessories
    "gift set", "gift basket", "glassware", "corkscrew", "decanter", "tumbler",
    "wine opener",
)

# Insurance for un-enriched real wines that collide with a marker. Normalized
# (lowercase) name fragments — if present, never exclude.
_ALLOWLIST = (
    "hampton water", "summer water", "road opener",
)


def matched_marker(name: Optional[str]) -> Optional[str]:
    """The first non-wine marker that whole-word matches `name`, else None."""
    low = (name or "").lower()
    for m in NON_WINE_MARKERS:
        if re.search(rf"\b{re.escape(m)}\b", low):
            return m
    return None


def is_non_wine_name(name: Optional[str]) -> bool:
    """True when the name whole-word matches a non-wine marker."""
    return matched_marker(name) is not None


def should_exclude(wine: Dict[str, Any]) -> bool:
    """Conservative purge gate: True only when the name is flagged AND every guard
    passes — barrel guard (barrel-aged wines), wine-signal guard (a real varietal or
    grape), and the allowlist. Errs toward keeping."""
    name = wine.get("name") or ""
    if not is_non_wine_name(name):
        return False
    low = name.lower()
    if "barrel" in low:
        return False
    if wine.get("varietal") or (wine.get("grapes") or []):
        return False
    if any(frag in low for frag in _ALLOWLIST):
        return False
    return True
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_non_wine.py -v`
Expected: PASS.

- [ ] **Step 5: Refactor `backfill_wine_type.py` to import the shared name check**

In `backend/scripts/backfill_wine_type.py`: delete the local `_NON_WINE_MARKERS` tuple and `_is_non_wine` function (~lines 63-80). Add an import near the top:

```python
from enrichment.non_wine import is_non_wine_name as _is_non_wine
```

(The alias keeps the existing call site `if _is_non_wine(row.get("name")):` unchanged. The marker list is now broader, which correctly makes the type-backfill skip beer/merchandise too.)

- [ ] **Step 6: Run the backfill_wine_type tests + non_wine tests**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_non_wine.py tests/test_backfill_wine_type.py -v`
Expected: PASS (no regression). If `test_backfill_wine_type.py` doesn't exist, run the wine_type-related tests: `/usr/bin/python3 -m pytest tests/ -k "wine_type or non_wine" -q`.

- [ ] **Step 7: Commit**

```bash
git add backend/enrichment/non_wine.py backend/scripts/backfill_wine_type.py backend/tests/test_non_wine.py
git commit -m "feat(enrichment): canonical non_wine detection module + guarded should_exclude"
```

---

### Task 2: Migration — soft-delete columns

**Files:**
- Create: `supabase/migrations/20260721000001_wines_excluded.sql`
- Create (temporary, deleted after): `backend/scripts/_apply_migration.py`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260721000001_wines_excluded.sql`:

```sql
-- Item 32: soft-delete non-wine catalog noise. Nullable; NULL = active.
ALTER TABLE public.wines
    ADD COLUMN IF NOT EXISTS excluded_at timestamptz,
    ADD COLUMN IF NOT EXISTS exclusion_reason text;

COMMENT ON COLUMN public.wines.excluded_at IS
    'Set when a row is soft-deleted as non-wine (item 32). NULL = active wine.';
```

(No new GRANT/RLS needed — `wines` is already anon-readable and the grant is table-level, covering new columns.)

- [ ] **Step 2: Apply it via DATABASE_URL**

Ensure a Postgres driver is available (system python lacks one):

Run: `cd backend && /usr/bin/python3 -m pip install --user psycopg2-binary`
Expected: installs (or "already satisfied").

Create `backend/scripts/_apply_migration.py`:

```python
import os, sys
import psycopg2
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
sql = open(sys.argv[1]).read()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(sql)
print("applied:", sys.argv[1])
conn.close()
```

Run: `cd backend && /usr/bin/python3 scripts/_apply_migration.py ../supabase/migrations/20260721000001_wines_excluded.sql`
Expected: `applied: ...`. (Fallback if `DATABASE_URL` connect fails: paste the migration SQL into the Supabase dashboard SQL editor.)

- [ ] **Step 3: Verify the column exists**

Run:
```bash
cd backend && /usr/bin/python3 -c "
from db import get_service_client
r=get_service_client().table('wines').select('id,excluded_at,exclusion_reason').limit(1).execute()
print('column present:', 'excluded_at' in r.data[0])" 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn
```
Expected: `column present: True`.

- [ ] **Step 4: Delete the temp apply script + commit the migration**

```bash
rm backend/scripts/_apply_migration.py
git add supabase/migrations/20260721000001_wines_excluded.sql
git commit -m "feat(db): wines.excluded_at + exclusion_reason for non-wine soft-delete"
```

---

### Task 3: Purge script (dry-run first)

**Files:**
- Create: `backend/scripts/purge_non_wine.py`
- Test: `backend/tests/test_purge_non_wine.py`

- [ ] **Step 1: Write the failing test for the pure selection helper**

Create `backend/tests/test_purge_non_wine.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.purge_non_wine import rows_to_exclude


def test_rows_to_exclude_filters_and_attaches_reason():
    rows = [
        {"id": "1", "name": "Pacifico Mexican Lager", "varietal": None, "grapes": []},
        {"id": "2", "name": "Chateau Margaux", "varietal": "Cabernet Sauvignon", "grapes": []},
        {"id": "3", "name": "Bota Box Bourbon Barrel Cabernet", "varietal": "Cabernet Sauvignon", "grapes": []},
        {"id": "4", "name": "Del Monte Fruit Cocktail", "varietal": None, "grapes": []},
    ]
    out = rows_to_exclude(rows)
    ids = {r["id"]: r["reason"] for r in out}
    assert set(ids) == {"1", "4"}          # only clear non-wine, no signal
    assert ids["1"] == "lager"
    assert ids["4"] == "cocktail"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_purge_non_wine.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write the script**

Create `backend/scripts/purge_non_wine.py`:

```python
"""Soft-delete non-wine catalog noise (CLAUDE.md item 32).

DRY-RUN by default — prints what WOULD be excluded (count, sample, reason). Pass
--apply to set wines.excluded_at = now() + exclusion_reason. Idempotent: only rows
where excluded_at IS NULL and should_exclude() is true.

Reverse: UPDATE public.wines SET excluded_at = NULL, exclusion_reason = NULL WHERE ...

Run from backend/:
    /usr/bin/python3 -m scripts.purge_non_wine            # dry-run
    /usr/bin/python3 -m scripts.purge_non_wine --apply
"""
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List

from db import get_service_client
from enrichment.non_wine import should_exclude, matched_marker

_COLS = "id,name,varietal,grapes,wine_type,excluded_at"


def rows_to_exclude(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pure: the subset of rows that should be soft-deleted, each annotated with the
    marker that fired (`reason`). Skips rows already excluded."""
    out = []
    for r in rows:
        if r.get("excluded_at"):
            continue
        if should_exclude(r):
            out.append({**r, "reason": matched_marker(r.get("name"))})
    return out


def _fetch_all(db) -> List[Dict[str, Any]]:
    rows, page, size = [], 0, 1000
    while True:
        chunk = (db.table("wines").select(_COLS)
                 .order("id").range(page * size, page * size + size - 1)
                 .execute().data or [])
        if not chunk:
            break
        rows.extend(chunk)
        page += 1
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write excluded_at (default: dry-run)")
    args = ap.parse_args()

    db = get_service_client()
    targets = rows_to_exclude(_fetch_all(db))
    print(f"non-wine to exclude: {len(targets)}")
    from collections import Counter
    by_reason = Counter(t["reason"] for t in targets)
    print(f"by reason: {dict(by_reason.most_common())}")
    for t in targets[:25]:
        print(f"  [{t['reason']}] {t['name'][:60]}")

    if not args.apply:
        print("\nDRY-RUN — nothing written. Re-run with --apply to soft-delete.")
        return

    now = datetime.now(timezone.utc).isoformat()
    for t in targets:
        db.table("wines").update(
            {"excluded_at": now, "exclusion_reason": t["reason"]}
        ).eq("id", t["id"]).execute()
    print(f"\nAPPLIED — soft-deleted {len(targets)} rows.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_purge_non_wine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/purge_non_wine.py backend/tests/test_purge_non_wine.py
git commit -m "feat(scripts): purge_non_wine dry-run/apply soft-delete"
```

---

### Task 4: Read-path filtering — `excluded_at IS NULL` everywhere

**Files:**
- Modify: `backend/api/routers/recommend.py`, `backend/api/routers/search.py`,
  `backend/api/routers/deals.py`, `backend/api/routers/wines.py`,
  `backend/api/routers/region.py`

- [ ] **Step 1: Recommend — select the column + drop excluded candidates**

In `backend/api/routers/recommend.py`:

Add `excluded_at` to the wines embed in `INVENTORY_SELECT` (the `wines!inner(...)` list):
change `"wines!inner(id, name, varietal, region, country, wine_type, grapes, abv, body,"` so the field list includes `excluded_at` (add `excluded_at,` after `id,`).

In `_row_to_candidate`, right after `wine = row.get("wines") or {}` and the empty check, add:
```python
        if wine.get("excluded_at"):
            return None
```

- [ ] **Step 2: Search — filter the discovery query**

In `backend/api/routers/search.py`, the `db.table("wines").select(...).or_(...)` query (~line 90-95): append `.is_("excluded_at", "null")` to the chain (before `.limit`/`.execute`).

- [ ] **Step 3: Deals — filter the wines fetch**

In `backend/api/routers/deals.py`, the `client.table("wines").select(...)` (~line 80): append `.is_("excluded_at", "null")`.

- [ ] **Step 4: Wines discovery list**

In `backend/api/routers/wines.py`, `search_wines` (~line 17): append `.is_("excluded_at", "null")` to the `client.table("wines").select(...)` chain. Leave `get_wine` (direct-id dossier lookup) unchanged.

- [ ] **Step 5: Region browse**

In `backend/api/routers/region.py`:
- `get_subregion_counts` (~line 66): append `.is_("excluded_at", "null")` to the `db.table("wines").select("id, sub_region").eq("region", db_region)` chain.
- `get_region_wines` (~line 140): append `.is_("excluded_at", "null", reference_table="wines")` to the retail_inventory query (it embeds `wines` via `_REGION_INVENTORY_SELECT`). If the postgrest client rejects `reference_table` on `.is_`, instead add `excluded_at` to `_REGION_INVENTORY_SELECT`'s wines embed and return `None` from `_row_to_wine_item` when `excluded_at` is set.

- [ ] **Step 6: Verify imports + run the API test suites**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend, api.routers.search, api.routers.deals, api.routers.wines, api.routers.region"
/usr/bin/python3 -m pytest tests/ -m "not integration" -q
```
Expected: imports clean; full fast suite passes.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routers/recommend.py backend/api/routers/search.py backend/api/routers/deals.py backend/api/routers/wines.py backend/api/routers/region.py
git commit -m "feat(api): filter excluded_at non-wine rows from all read paths"
```

---

### Task 5: Dry-run acceptance, apply, and docs

**Files:**
- Modify: `CLAUDE.md` (item 32), `docs/reference/scrapers.md` or `docs/reference/enrichment.md` (note the purge)

- [ ] **Step 1: Run the purge dry-run and eyeball it**

Run: `cd backend && /usr/bin/python3 -m scripts.purge_non_wine 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn`
Expected: prints a count (~500-700), a `by reason` breakdown, and a 25-row sample. **Manually confirm the sample contains no real wines** before proceeding. Record the count + breakdown.

- [ ] **Step 2: Apply the purge**

Run: `cd backend && /usr/bin/python3 -m scripts.purge_non_wine --apply 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn`
Expected: `APPLIED — soft-deleted N rows.`

- [ ] **Step 3: Verify the recommender no longer surfaces them**

Run:
```bash
cd backend && /usr/bin/python3 -c "
from db import get_service_client
db=get_service_client()
n=db.table('wines').select('id',count='exact').not_.is_('excluded_at','null').execute().count
typed=db.table('wines').select('id',count='exact').not_.is_('excluded_at','null').not_.is_('wine_type','null').execute().count
print(f'excluded={n} | of which were typed (had leaked to recommender)={typed}')" 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn
```
Expected: `excluded=N` matching the dry-run; `typed` ~149 confirms the leak is now filtered.

- [ ] **Step 4: Update docs**

- `CLAUDE.md` item 32: change the stub to ✅ with the landed summary — canonical `enrichment/non_wine.py` (deny-list + barrel/wine-signal/allowlist guards), `wines.excluded_at` soft-delete, `scripts/purge_non_wine.py` (dry-run/apply), read-path filtering across recommend/search/deals/wines/region, and the applied count. Note the deferred weekly-pipeline wiring.
- Add a short "Non-wine purge (item 32)" note to `docs/reference/enrichment.md`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/reference/enrichment.md
git commit -m "docs: item 32 non-wine purge landed"
```

---

## Self-Review Notes

- **Spec coverage:** §1 module→T1; §2 migration→T2; §3 script→T3; §4 read-path→T4; §5 testing→T1/T3 + T5 acceptance. All covered.
- **Type consistency:** `is_non_wine_name` / `should_exclude` / `matched_marker` / `rows_to_exclude` signatures identical across T1, T3. `excluded_at` column name identical across migration (T2), fetch (T3), and all read-path filters (T4).
- **Ordering:** T2 (column) precedes T4 (which selects/filters the column) and T5 (which reads it) — correct. T1's module is imported by T3's script — correct.
- **Conservative guards:** `should_exclude` requires flagged-name AND no-barrel AND no-varietal/grape AND not-allowlisted — a real wine with any varietal/grape is never dropped; the T5 dry-run is a human checkpoint before `--apply`.
- **Reversibility:** soft-delete via a nullable column; documented one-line SQL reversal.
