# Scheduled Scrape + HEB Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded HEB store list with a CSV-driven registry (so new stores are a config change, not a code change), generate a `requirements.txt`, and create a GitHub Actions workflow that scrapes all retailers and runs fact extraction every week.

**Architecture:** A `data/heb-stores.csv` file owns the full HEB store list with an `active` flag. `heb.py` reads it at import time, replacing the hardcoded `STORE_REGISTRY` dict. A GitHub Actions cron workflow runs each scraper as an independent step (`continue-on-error: true`), then runs `run_extraction --null-only` to enrich any new wines. All secrets are injected via GitHub repository secrets; no `.env` file is needed in CI.

**Tech Stack:** Python 3.9, csv stdlib, GitHub Actions (ubuntu-latest + python 3.9), pydantic-settings (reads env vars that override `.env`)

## Global Constraints

- Python 3.9.6 — use `Optional[str]` from `typing`, NOT `str | None` syntax
- Run all backend commands from the `backend/` working directory
- Do not commit `.env` or any secrets
- `STORE_REGISTRY` dict interface must not change — downstream callers (`SA_STORES`, `run_full`, tests) must work without modification
- CSV lives at `data/heb-stores.csv` relative to the project root (two levels above `backend/scrapers/heb.py`)
- Scraper steps in GitHub Actions use `continue-on-error: true` so a single scraper failure doesn't abort the whole run
- GitHub Actions schedule: `'0 8 * * 0'` (Sunday 8:00 UTC = Sunday 2:00 CT)

---

### Task 1: Data-driven HEB store registry

**Files:**
- Create: `data/heb-stores.csv`
- Modify: `backend/scrapers/heb.py` (replace hardcoded `STORE_REGISTRY` with CSV loader)
- Test: `backend/tests/test_heb_store_registry.py`

**Interfaces:**
- Produces: `STORE_REGISTRY: Dict[str, Dict[str, str]]` — same shape as before: `{store_id: {name, address, zip, city, state}}`. Active-only rows included.
- Produces: `SA_STORES` alias — still works (derived from `STORE_REGISTRY` where `city == "San Antonio"`).

- [ ] **Step 1: Create `data/heb-stores.csv`**

Create `data/heb-stores.csv` with these columns: `store_id,name,address,zip,city,state,active`

The file contains all 18 currently-active stores (`active=true`) plus the full SA Region store list from `data/heb-store-list.csv` marked `active=false`. The inactive stores are there so adding a new store is just flipping a flag.

Full file content:
```csv
store_id,name,address,zip,city,state,active
567,Lincoln Heights Market H-E-B,999 East Basse Rd,78209,San Antonio,TX,true
372,Oak Park H-E-B,1955 Nacogdoches,78209,San Antonio,TX,true
585,Austin Highway H-E-B,1520 Austin Hwy,78218,San Antonio,TX,true
385,Olmos Park H-E-B,300 Olmos Dr,78212,San Antonio,TX,true
568,Perrin Beitel H-E-B,12018 Perrin Beitel Rd,78217,San Antonio,TX,true
556,Deco District H-E-B,2118 Fredericksburg Rd,78201,San Antonio,TX,true
68,Slaughter & Escarpment H-E-B,5800 W. Slaughter Lane,78749,Austin,TX,true
765,Oak Hill H-E-B,7901 US-290,78735,Austin,TX,true
229,I-35 & William Cannon H-E-B,6607 South IH 35,78745,Austin,TX,true
428,Brodie Lane H-E-B,6900 Brodie Lane,78745,Austin,TX,true
227,Slaughter & Manchaca H-E-B,2110 West Slaughter Ln,78748,Austin,TX,true
710,Slaughter & S Congress H-E-B,8801 South Congress Ave,78748,Austin,TX,true
780,Nutty Brown H-E-B,12021 W US 290,78736,Austin,TX,true
754,SoCo H-E-B,2400 S. Congress Ave.,78704,Austin,TX,true
768,Lake Austin H-E-B,2652 Lake Austin Blvd,78703,Austin,TX,true
91,Riverside H-E-B plus!,2508 East Riverside Drive,78741,Austin,TX,true
465,7th Street H-E-B,2701 East 7th,78702,Austin,TX,true
425,Hancock Center H-E-B,1000 East 41st,78751,Austin,TX,true
19,Lytle H-E-B plus!,19337 McDonald Street,78052,Lytle,TX,false
25,Floresville H-E-B,925 10th Street,78114,Floresville,TX,false
26,McCreless Market H-E-B plus!,4100 South New Braunfels,78223,San Antonio,TX,false
74,New Braunfels H-E-B at Hwy 46,1655 W State Highway 46,78130,New Braunfels,TX,false
84,Zarzamora and Military H-E-B plus!,6818 South Zarzamora,78224,San Antonio,TX,false
85,Potranco and 1604 H-E-B plus!,10718 Potranco Road,78251,San Antonio,TX,false
102,Alon Market H-E-B,8503 NW Military Hwy,78231,San Antonio,TX,false
106,W.W. White H-E-B,1015 S.W.W. White Road,78220,San Antonio,TX,false
108,281 and Evans Road H-E-B plus!,20935 US Highway 281 North,78258,San Antonio,TX,false
164,Brook Hollow H-E-B,15000 San Pedro,78232,San Antonio,TX,false
178,San Pedro and Oblate H-E-B,6839 San Pedro,78216,San Antonio,TX,false
189,El Mercado H-E-B,2130 Culebra,78228,San Antonio,TX,false
195,Blanco and West Ave H-E-B,11551 West Ave.,78213,San Antonio,TX,false
205,Las Palmas H-E-B,721 Castroville Rd,78237,San Antonio,TX,false
211,New Braunfels and Houston H-E-B,415 N. New Braunfels,78202,San Antonio,TX,false
224,Bandera and Guilbeau H-E-B,7951 Guilbeau Rd.,78250,San Antonio,TX,false
230,Nacogdoches and O'Connor H-E-B,14087 O'Connor Rd,78247,San Antonio,TX,false
235,Grissom and Tezel H-E-B,9255 Grissom Rd,78251,San Antonio,TX,false
262,Marketplace H-E-B,5601 Bandera Road,78238,San Antonio,TX,false
621,Boerne H-E-B plus!,420 West Bandera Road,78006,Boerne,TX,false
622,Bulverde H-E-B plus!,20725 Hwy 46 West,78070,Spring Branch,TX,false
623,Bandera and 1604 H-E-B plus!,9238 N. Loop 1604 West,78249,San Antonio,TX,false
655,Kerrville H-E-B on Sidney Baker St,313 Sidney Baker South,78028,Kerrville,TX,false
658,The Market at Stone Oak,23635 Wilderness Oak,78258,San Antonio,TX,false
678,Valley Hi H-E-B,368 Valley Hi Drive,78227,San Antonio,TX,false
694,New Braunfels H-E-B plus!,2965 IH35 North,78130,New Braunfels,TX,false
699,Nogalitos H-E-B,1601 Nogalitos,78204,San Antonio,TX,false
716,Seguin H-E-B,1340 E Court St,78155,Seguin,TX,false
718,South Flores Market H-E-B,516 S Flores Street,78204,San Antonio,TX,false
732,Bulverde and 1604 H-E-B,17238 Bulverde Road,78247,San Antonio,TX,false
733,Alamo Ranch H-E-B,12125 Alamo Ranch Pkwy,78253,San Antonio,TX,false
770,Kerrville H-E-B On Main Street,300 W. Main St.,78028,Kerrville,TX,false
771,211 and Potranco H-E-B,14325 Potranco Rd.,78253,San Antonio,TX,false
775,New Braunfels H-E-B at Walnut,651 S. Walnut,78130,New Braunfels,TX,false
785,H-E-B Cibolo,850 FM 1103 Suite 100,78108,Cibolo,TX,false
793,Fair Oaks H-E-B,29388 I-10 West,78006,Boerne,TX,false
799,College Park H-E-B,7330 N Loop 1604,78249,San Antonio,TX,false
807,Culebra and 211 H-E-B,15489 Culebra Rd.,78253,San Antonio,TX,false
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_heb_store_registry.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.heb import STORE_REGISTRY, SA_STORES


def test_active_stores_loaded():
    """All 18 currently-active stores appear in the registry."""
    expected_active = {
        "567", "372", "585", "385", "568", "556",  # SA
        "68", "765", "229", "428", "227", "710",   # Austin
        "780", "754", "768", "91", "465", "425",
    }
    assert expected_active.issubset(set(STORE_REGISTRY.keys()))


def test_inactive_stores_excluded():
    """Stores marked active=false in the CSV are not in STORE_REGISTRY."""
    inactive_ids = {"26", "84", "85", "102", "178", "262"}
    for sid in inactive_ids:
        assert sid not in STORE_REGISTRY, f"store {sid} should be inactive"


def test_store_record_shape():
    """Each registry entry has the expected keys."""
    for sid, info in STORE_REGISTRY.items():
        for key in ("name", "address", "zip", "city", "state"):
            assert key in info, f"store {sid} missing key '{key}'"


def test_sa_stores_alias():
    """SA_STORES contains only San Antonio stores from STORE_REGISTRY."""
    assert len(SA_STORES) >= 6
    for sid, info in SA_STORES.items():
        assert info["city"] == "San Antonio", f"store {sid} city mismatch"
    assert set(SA_STORES.keys()).issubset(set(STORE_REGISTRY.keys()))
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend
python3 -m pytest tests/test_heb_store_registry.py -v
```

Expected: 4 failures — `STORE_REGISTRY` still comes from the hardcoded dict (no CSV yet).

- [ ] **Step 4: Replace the hardcoded STORE_REGISTRY in `heb.py` with the CSV loader**

In `backend/scrapers/heb.py`, replace lines 29–55 (the `STORE_REGISTRY` dict and `SA_STORES` alias) with:

```python
import csv as _csv
from pathlib import Path as _Path

_CSV_PATH = _Path(__file__).parents[2] / "data" / "heb-stores.csv"


def _load_store_registry() -> Dict[str, Dict[str, str]]:
    """Load active HEB stores from data/heb-stores.csv.

    To add a new store: set active=true in the CSV. No code change needed.
    """
    registry: Dict[str, Dict[str, str]] = {}
    with open(_CSV_PATH, newline="") as f:
        for row in _csv.DictReader(f):
            if row["active"].strip().lower() == "true":
                registry[row["store_id"].strip()] = {
                    "name":    row["name"].strip(),
                    "address": row["address"].strip(),
                    "zip":     row["zip"].strip(),
                    "city":    row["city"].strip(),
                    "state":   row["state"].strip(),
                }
    return registry


# All active HEB stores, keyed by store_id string.
# To add a store: flip active=true in data/heb-stores.csv.
STORE_REGISTRY: Dict[str, Dict[str, str]] = _load_store_registry()

# Kept for backward compatibility — callers that imported SA_STORES directly still work.
SA_STORES = {k: v for k, v in STORE_REGISTRY.items() if v["city"] == "San Antonio"}
```

Keep the existing imports at the top of `heb.py`; `_csv` and `_Path` are added alongside them. The `Dict` type is already imported from `typing`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
python3 -m pytest tests/test_heb_store_registry.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -v
```

Expected: all unit tests pass (previously 161 passing).

- [ ] **Step 7: Commit**

```bash
git add data/heb-stores.csv backend/scrapers/heb.py backend/tests/test_heb_store_registry.py
git commit -m "feat: data-driven HEB store registry (CSV with active flag)

Moves STORE_REGISTRY from hardcoded dict to data/heb-stores.csv.
Active flag controls which stores scrape. 37 inactive SA/suburb stores
included so adding a store is just flipping active=true, no code change.
SA_STORES alias preserved for backward compat."
```

---

### Task 2: requirements.txt + GitHub Actions weekly scrape workflow

**Files:**
- Create: `backend/requirements.txt`
- Create: `.github/workflows/weekly-scrape.yml`

**Interfaces:**
- Consumes: `STORE_REGISTRY` from Task 1 (active stores scraped automatically)
- Produces: A weekly scheduled workflow visible in the GitHub Actions tab; manual trigger via `workflow_dispatch`

- [ ] **Step 1: Create `backend/requirements.txt`**

Create `backend/requirements.txt` with pinned direct dependencies:

```
anthropic==0.105.2
fastapi==0.128.8
httpx==0.28.1
numpy==2.0.2
pgeocode==0.4.1
postgrest==2.30.1
pydantic==2.13.4
pydantic-settings==2.11.0
python-dotenv==1.2.1
realtime==2.30.1
storage3==2.30.1
supabase==2.30.1
supabase-auth==2.30.1
supabase-functions==2.30.1
uvicorn==0.39.0
pytest==8.4.2
pytest-asyncio==1.2.0
```

- [ ] **Step 2: Create `.github/workflows/weekly-scrape.yml`**

Create the directory and file:

```bash
mkdir -p .github/workflows
```

Then create `.github/workflows/weekly-scrape.yml`:

```yaml
name: Weekly Scrape + Extraction

on:
  schedule:
    - cron: '0 8 * * 0'   # Sunday 08:00 UTC = Sunday 02:00 CT
  workflow_dispatch:       # allow manual trigger from GitHub UI

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 180   # 3-hour ceiling; Spec's alone takes ~30 min

    defaults:
      run:
        working-directory: backend

    env:
      SUPABASE_URL:              ${{ secrets.SUPABASE_URL }}
      SUPABASE_ANON_KEY:         ${{ secrets.SUPABASE_ANON_KEY }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      ANTHROPIC_API_KEY:         ${{ secrets.ANTHROPIC_API_KEY }}
      GRAPEMINDS_API_KEY:        ${{ secrets.GRAPEMINDS_API_KEY }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.9
        uses: actions/setup-python@v5
        with:
          python-version: '3.9'
          cache: pip
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: pip install -r requirements.txt

      # ── scrapers ─────────────────────────────────────────────────────────
      - name: Scrape Geraldine's
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.geraldines import GeraldinesScraper
          asyncio.run(GeraldinesScraper().run_full())
          "

      - name: Scrape H-E-B (all active stores)
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.heb import HebScraper
          asyncio.run(HebScraper().run_full())
          "

      - name: Scrape Central Market (Austin stores 61 + 420)
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.central_market import CentralMarketScraper
          asyncio.run(CentralMarketScraper().run_full())
          "

      - name: Scrape AOC Selections (San Antonio)
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.aoc_selections import AOCSelectionsScraper
          asyncio.run(AOCSelectionsScraper().run_full())
          "

      - name: Scrape US Natural Wine (Austin)
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.us_natural_wine import USNaturalWineScraper
          asyncio.run(USNaturalWineScraper().run_full())
          "

      - name: Scrape Antonelli's (Austin)
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.antonellis import AntonellisScraper
          asyncio.run(AntonellisScraper().run_full())
          "

      - name: Scrape Spec's (12 SA stores — ~30 min)
        continue-on-error: true
        run: |
          python3 -c "
          import asyncio
          from scrapers.specs import SpecsScraper
          asyncio.run(SpecsScraper().run_full())
          "

      # ── extraction ───────────────────────────────────────────────────────
      - name: Extract facts for new wines (--null-only)
        continue-on-error: true
        run: python3 -m enrichment.extraction.run_extraction --null-only
```

- [ ] **Step 3: Add secrets to GitHub repository**

In the GitHub repo → Settings → Secrets and variables → Actions → New repository secret, add each of these (values from your local `.env`):

| Secret name               | Value source in `.env`         |
|---------------------------|-------------------------------|
| `SUPABASE_URL`            | `SUPABASE_URL`                |
| `SUPABASE_ANON_KEY`       | `SUPABASE_ANON_KEY`           |
| `SUPABASE_SERVICE_ROLE_KEY` | `SUPABASE_SERVICE_ROLE_KEY` |
| `ANTHROPIC_API_KEY`       | `ANTHROPIC_API_KEY`           |
| `GRAPEMINDS_API_KEY`      | `GRAPEMINDS_API_KEY`          |

> **Note:** This step is manual and cannot be automated. The workflow will fail silently if secrets are missing — check the Actions tab after the first run.

- [ ] **Step 4: Verify YAML syntax locally**

```bash
# From project root
python3 -c "
import yaml, sys
with open('.github/workflows/weekly-scrape.yml') as f:
    yaml.safe_load(f)
print('YAML valid')
"
```

Expected output: `YAML valid` (install `pyyaml` if missing: `pip3 install pyyaml`)

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt .github/workflows/weekly-scrape.yml
git commit -m "feat: weekly GitHub Actions scrape + extraction workflow

Schedules all scrapers + --null-only fact extraction every Sunday 02:00 CT.
Each scraper is an independent step (continue-on-error) so one failure
doesn't abort the run. Requires 5 GitHub repo secrets (see plan for names).
Includes requirements.txt for reproducible CI installs."
```

- [ ] **Step 6: Test via manual trigger**

Push the commit, then in GitHub → Actions → Weekly Scrape + Extraction → Run workflow. Watch the step-by-step log. Geraldine's should finish in under 2 minutes; use it to verify secrets are wired up before waiting for Spec's.

---

## Self-Review

**Spec coverage:**
- Data-driven HEB registry: ✅ Task 1
- Active flag for new stores: ✅ Task 1 CSV + loader
- Backward compat for `SA_STORES` and `STORE_REGISTRY`: ✅ Task 1 Step 4
- GitHub Actions cron schedule: ✅ Task 2
- All scrapers in workflow: ✅ Task 2 Step 2 (7 scrapers)
- Extraction after scrape: ✅ Task 2 Step 2 (--null-only step)
- Just logs, no Slack: ✅ Task 2 (no notification step)
- Same repo: ✅ `.github/workflows/` in project root
- Requirements file for CI: ✅ Task 2 Step 1

**Placeholder scan:** None found.

**Type consistency:** `STORE_REGISTRY: Dict[str, Dict[str, str]]` — same shape before and after. `SA_STORES` alias preserved.

**Adding new SA stores (operator runbook):** Edit `data/heb-stores.csv`, change `false` → `true` for the desired store row, commit. The next scrape run picks it up automatically.
