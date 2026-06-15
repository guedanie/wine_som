# Haiku Wine-Fact Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Haiku agent that reads each wine's name + retail description and backfills structured fields (region/sub_region/country/vintage/varietal/grapes/abv/body) onto the `wines` table, grounded by an appellation + core-grape cheat sheet with deterministic appellation→region mapping.

**Architecture:** A static cheat-sheet module (`reference.py`), a pure extraction module that calls Haiku via forced tool use and post-processes deterministically (`extractor.py`), a pure persistence-policy + writer (`persist.py`), and a runner with dry-run review + commit (`run_extraction.py`). Mirrors the `recommendation/` split.

**Tech Stack:** Python 3.9 (`Optional[...]`, not `X | None`), Anthropic SDK (`claude-haiku-4-5-20251001`, forced tool use), supabase-py, pytest. No GrapeMinds — Haiku only.

**Spec:** `docs/superpowers/specs/2026-06-15-haiku-fact-extraction-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260615000001_wine_extracted_fields.sql` | Create | `grapes`/`abv`/`body` columns |
| `backend/enrichment/extraction/__init__.py` | Create | Package marker |
| `backend/enrichment/extraction/reference.py` | Create | Cheat sheets + few-shot + `parent_region_for` |
| `backend/enrichment/extraction/extractor.py` | Create | `extract_facts` (Haiku tool-use, batched, post-process) |
| `backend/enrichment/extraction/persist.py` | Create | `compute_wine_update` + `backfill_wine_facts` |
| `backend/enrichment/extraction/run_extraction.py` | Create | Runner: select, batch, dry-run CSV / `--write` |
| `backend/tests/test_extraction_reference.py` | Create | Cheat-sheet lookup tests |
| `backend/tests/test_extraction.py` | Create | Extractor post-process + backfill policy (mocked Claude) |

All commands run from `backend/` unless noted.

---

### Task 1: Migration — grapes / abv / body columns

**Files:**
- Create: `supabase/migrations/20260615000001_wine_extracted_fields.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260615000001_wine_extracted_fields.sql`:

```sql
-- Structured fields extracted by the Haiku fact-extraction job.
ALTER TABLE wines ADD COLUMN IF NOT EXISTS grapes JSONB DEFAULT '[]';  -- full blend, e.g. ["Cabernet Sauvignon","Merlot"]
ALTER TABLE wines ADD COLUMN IF NOT EXISTS abv   NUMERIC(4,1);          -- e.g. 13.9
ALTER TABLE wines ADD COLUMN IF NOT EXISTS body  TEXT;                  -- 'light' | 'medium' | 'full'
```

- [ ] **Step 2: Apply to the cloud DB**

```bash
cd /Users/danielguerrero/Documents/ai_dev/wine_app
supabase db push --dry-run < /dev/null 2>&1 | grep -iE "would push|wine_extracted_fields"
```
Expected: lists only `20260615000001_wine_extracted_fields.sql`. Then:
```bash
supabase db push --yes < /dev/null 2>&1 | grep -iE "Applying|Finished"
```
Verify:
```bash
cd backend && python3 -c "
from db import get_service_client
c = get_service_client()
c.table('wines').select('grapes,abv,body').limit(1).execute()
print('columns present')
"
```
Expected: `columns present`.

- [ ] **Step 3: Commit**

```bash
cd /Users/danielguerrero/Documents/ai_dev/wine_app
git add supabase/migrations/20260615000001_wine_extracted_fields.sql
git commit -m "feat: wines.grapes/abv/body columns for extraction"
```

---

### Task 2: Cheat sheets + `parent_region_for` (TDD)

**Files:**
- Create: `backend/enrichment/extraction/__init__.py`
- Create: `backend/tests/test_extraction_reference.py`
- Create: `backend/enrichment/extraction/reference.py`

- [ ] **Step 1: Create the package**

```bash
mkdir -p backend/enrichment/extraction
touch backend/enrichment/extraction/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_extraction_reference.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.extraction.reference import (
    parent_region_for, APPELLATIONS, CORE_GRAPES, FEW_SHOT,
)


def test_parent_region_for_bordeaux_appellation():
    assert parent_region_for("Saint-Émilion") == "Bordeaux"
    assert parent_region_for("Pomerol") == "Bordeaux"


def test_parent_region_for_is_case_and_accent_insensitive():
    assert parent_region_for("saint-emilion") == "Bordeaux"
    assert parent_region_for("SAINT-ÉMILION") == "Bordeaux"
    assert parent_region_for("  margaux ") == "Bordeaux"


def test_parent_region_for_napa_and_other_regions():
    assert parent_region_for("Oakville") == "Napa Valley"
    assert parent_region_for("Russian River Valley") == "Sonoma"
    assert parent_region_for("Barolo") == "Piedmont"
    assert parent_region_for("Uco Valley") == "Mendoza"


def test_parent_region_for_unknown_returns_none():
    assert parent_region_for("Nowhere Valley") is None
    assert parent_region_for("") is None
    assert parent_region_for(None) is None


def test_cheat_sheets_are_populated():
    assert len(APPELLATIONS) >= 20          # many regions
    assert "Cabernet Sauvignon" in CORE_GRAPES["red"]
    assert "Chardonnay" in CORE_GRAPES["white"]
    assert len(FEW_SHOT) >= 4
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_extraction_reference.py -v
```
Expected: `ModuleNotFoundError: No module named 'enrichment.extraction.reference'`.

- [ ] **Step 4: Implement `backend/enrichment/extraction/reference.py`**

```python
"""
Cheat sheets for wine-fact extraction. Used both in the Haiku prompt and for
deterministic post-processing (appellation -> parent region).
"""
import re
import unicodedata
from typing import Optional

# Appellation / sub-region -> grouped under its parent region (what we store in wines.region).
APPELLATIONS = {
    "Bordeaux": ["Médoc", "Haut-Médoc", "Margaux", "Pauillac", "Saint-Julien",
                 "Saint-Estèphe", "Listrac-Médoc", "Moulis-en-Médoc", "Pessac-Léognan",
                 "Graves", "Saint-Émilion", "Pomerol", "Lalande-de-Pomerol", "Fronsac",
                 "Canon-Fronsac", "Sauternes", "Barsac", "Entre-Deux-Mers"],
    "Burgundy": ["Chablis", "Gevrey-Chambertin", "Morey-Saint-Denis", "Chambolle-Musigny",
                 "Vougeot", "Vosne-Romanée", "Nuits-Saint-Georges", "Aloxe-Corton",
                 "Pommard", "Volnay", "Meursault", "Puligny-Montrachet",
                 "Chassagne-Montrachet", "Beaune", "Pouilly-Fuissé", "Mâcon"],
    "Rhône": ["Côte-Rôtie", "Condrieu", "Hermitage", "Crozes-Hermitage", "Saint-Joseph",
              "Cornas", "Châteauneuf-du-Pape", "Gigondas", "Vacqueyras", "Côtes du Rhône",
              "Tavel", "Lirac"],
    "Loire": ["Sancerre", "Pouilly-Fumé", "Vouvray", "Chinon", "Bourgueil", "Saumur",
              "Saumur-Champigny", "Muscadet", "Savennières", "Anjou"],
    "Beaujolais": ["Morgon", "Fleurie", "Moulin-à-Vent", "Brouilly", "Côte de Brouilly",
                   "Juliénas", "Chénas", "Chiroubles", "Régnié", "Saint-Amour"],
    "Languedoc": ["Minervois", "Corbières", "Fitou", "Faugères", "Pic Saint-Loup",
                  "Saint-Chinian", "Picpoul de Pinet"],
    "Provence": ["Bandol", "Côtes de Provence", "Cassis", "Bellet"],
    "Southwest France": ["Cahors", "Madiran", "Bergerac", "Jurançon"],
    "Tuscany": ["Chianti", "Chianti Classico", "Brunello di Montalcino",
                "Rosso di Montalcino", "Vino Nobile di Montepulciano", "Bolgheri",
                "Carmignano", "Morellino di Scansano"],
    "Piedmont": ["Barolo", "Barbaresco", "Barbera d'Alba", "Barbera d'Asti",
                 "Dolcetto d'Alba", "Langhe", "Gavi", "Roero", "Nebbiolo d'Alba"],
    "Veneto": ["Valpolicella", "Amarone della Valpolicella", "Soave", "Bardolino",
               "Prosecco", "Ripasso"],
    "Other Italy": ["Franciacorta", "Etna", "Taurasi", "Montepulciano d'Abruzzo",
                    "Primitivo di Manduria", "Vermentino di Sardegna"],
    "Rioja": ["Rioja Alta", "Rioja Alavesa", "Rioja Oriental", "Rioja Baja"],
    "Other Spain": ["Ribera del Duero", "Priorat", "Rías Baixas", "Rueda", "Toro",
                    "Jumilla", "Penedès", "Cava", "Montsant"],
    "Douro": ["Douro", "Port"],
    "Other Portugal": ["Dão", "Alentejo", "Vinho Verde", "Bairrada"],
    "Napa Valley": ["Oakville", "Rutherford", "Stags Leap District", "Howell Mountain",
                    "Mount Veeder", "Spring Mountain", "Diamond Mountain", "Calistoga",
                    "St. Helena", "Carneros", "Atlas Peak", "Coombsville", "Yountville",
                    "Oak Knoll"],
    "Sonoma": ["Russian River Valley", "Alexander Valley", "Dry Creek Valley",
               "Sonoma Coast", "Knights Valley", "Chalk Hill", "Bennett Valley",
               "Sonoma Valley", "Fountaingrove", "Rockpile"],
    "Central Coast": ["Paso Robles", "Santa Maria Valley", "Sta. Rita Hills",
                      "Ballard Canyon", "Edna Valley", "Arroyo Grande", "Monterey",
                      "Santa Lucia Highlands"],
    "Other California": ["Lodi", "Mendocino", "Sierra Foothills", "Livermore Valley",
                         "Santa Cruz Mountains", "Anderson Valley", "Clarksburg"],
    "Willamette Valley": ["Dundee Hills", "Eola-Amity Hills", "Ribbon Ridge",
                          "Yamhill-Carlton", "Chehalem Mountains", "McMinnville"],
    "Columbia Valley": ["Walla Walla Valley", "Yakima Valley", "Red Mountain",
                        "Horse Heaven Hills", "Wahluke Slope"],
    "Texas": ["Texas Hill Country", "Texas High Plains"],
    "Mendoza": ["Uco Valley", "Luján de Cuyo", "Maipú"],
    "Other Argentina": ["Cafayate", "Salta", "Patagonia"],
    "Chile": ["Maipo Valley", "Colchagua Valley", "Casablanca Valley", "Aconcagua",
              "Maule Valley", "Limarí Valley"],
    "Barossa Valley": ["Eden Valley"],
    "Other Australia": ["McLaren Vale", "Coonawarra", "Clare Valley", "Margaret River",
                        "Yarra Valley", "Hunter Valley"],
    "Marlborough": [],
    "Other New Zealand": ["Central Otago", "Hawke's Bay", "Martinborough"],
    "Germany": ["Mosel", "Rheingau", "Pfalz", "Rheinhessen", "Nahe"],
    "South Africa": ["Stellenbosch", "Swartland", "Franschhoek", "Paarl", "Constantia"],
}

CORE_GRAPES = {
    "red": ["Cabernet Sauvignon", "Merlot", "Pinot Noir", "Syrah", "Shiraz", "Malbec",
            "Grenache", "Garnacha", "Tempranillo", "Sangiovese", "Nebbiolo", "Zinfandel",
            "Primitivo", "Cabernet Franc", "Petit Verdot", "Petite Sirah", "Mourvèdre",
            "Monastrell", "Carmenère", "Gamay", "Barbera", "Dolcetto", "Montepulciano",
            "Nero d'Avola", "Touriga Nacional", "Tannat", "Cinsault", "Carignan",
            "Aglianico", "Corvina", "Pinotage"],
    "white": ["Chardonnay", "Sauvignon Blanc", "Riesling", "Pinot Grigio", "Pinot Gris",
              "Chenin Blanc", "Viognier", "Gewürztraminer", "Albariño", "Grüner Veltliner",
              "Sémillon", "Vermentino", "Torrontés", "Moscato", "Muscat", "Marsanne",
              "Roussanne", "Verdejo", "Garganega", "Trebbiano", "Cortese",
              "Melon de Bourgogne", "Fiano", "Greco", "Assyrtiko", "Furmint"],
    "rose": ["Grenache", "Cinsault", "Mourvèdre", "Pinot Noir", "Syrah", "Tempranillo",
             "Sangiovese"],
}

# (name, description) -> expected extracted dict. Seeds the prompt's few-shot section.
FEW_SHOT = [
    ("Decoy Cabernet Sauvignon California Red Wine",
     "Rich Californian red with dark cherry and supple tannins. ABV: 14.5%",
     {"region": "California", "sub_region": None, "country": "US", "vintage_year": None,
      "varietal": "Cabernet Sauvignon", "grapes": ["Cabernet Sauvignon"], "abv": 14.5,
      "body": "full"}),
    ("Château du Cauze Saint-Émilion Grand Cru 2019", "",
     {"region": "Bordeaux", "sub_region": "Saint-Émilion", "country": "France",
      "vintage_year": 2019, "varietal": "Merlot", "grapes": ["Merlot", "Cabernet Franc"],
      "abv": None, "body": "full"}),
    ("Les Lunes Rouge 2021", "A fresh, low-tannin red blend from Mendocino.",
     {"region": "Mendocino", "sub_region": None, "country": "US", "vintage_year": 2021,
      "varietal": "Red Blend", "grapes": [], "abv": None, "body": "medium"}),
    ("Whitehaven Sauvignon Blanc New Zealand White Wine",
     "Zesty Marlborough white, grapefruit and passionfruit.",
     {"region": "Marlborough", "sub_region": None, "country": "New Zealand",
      "vintage_year": None, "varietal": "Sauvignon Blanc", "grapes": ["Sauvignon Blanc"],
      "abv": None, "body": "light"}),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    return re.sub(r"\s+", " ", s).strip().lower()


# Inverted index: normalized appellation -> parent region
_APPELLATION_INDEX = {}
for _region, _apps in APPELLATIONS.items():
    for _app in _apps:
        _APPELLATION_INDEX[_norm(_app)] = _region


def parent_region_for(appellation: Optional[str]) -> Optional[str]:
    """Return the parent region for an appellation (case/accent-insensitive), else None."""
    if not appellation:
        return None
    return _APPELLATION_INDEX.get(_norm(appellation))
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_extraction_reference.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/enrichment/extraction/__init__.py backend/enrichment/extraction/reference.py backend/tests/test_extraction_reference.py
git commit -m "feat: extraction cheat sheets + appellation->region lookup (TDD)"
```

---

### Task 3: Extractor — Haiku tool-use + post-process (TDD)

**Files:**
- Create: `backend/tests/test_extraction.py`
- Create: `backend/enrichment/extraction/extractor.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_extraction.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch, MagicMock
from enrichment.extraction.extractor import _post_process, extract_facts


def test_post_process_maps_appellation_to_parent_region():
    rec = {"wine_id": "w1", "region": "wrong", "sub_region": "Saint-Émilion",
           "country": "France", "vintage_year": 2019, "varietal": "Merlot",
           "grapes": ["Merlot"], "abv": None, "body": "FULL"}
    out = _post_process(rec)
    assert out["region"] == "Bordeaux"          # overridden via cheat sheet
    assert out["sub_region"] == "Saint-Émilion"
    assert out["body"] == "full"                 # normalized


def test_post_process_coerces_ranges_and_defaults_varietal():
    rec = {"wine_id": "w1", "region": "California", "sub_region": None,
           "country": "US", "vintage_year": 1850, "varietal": None,
           "grapes": ["Zinfandel"], "abv": 99.0, "body": "rich"}
    out = _post_process(rec)
    assert out["vintage_year"] is None           # out of range -> null
    assert out["abv"] is None                    # out of range -> null
    assert out["varietal"] == "Zinfandel"        # defaults to grapes[0]
    assert out["body"] is None                   # unrecognized -> null


def test_post_process_keeps_long_tail_region_when_not_in_cheatsheet():
    rec = {"wine_id": "w1", "region": "Swartland", "sub_region": None,
           "country": "South Africa", "vintage_year": 2020, "varietal": "Syrah",
           "grapes": ["Syrah"], "abv": 13.5, "body": "medium"}
    out = _post_process(rec)
    assert out["region"] == "Swartland"


def _mock_anthropic(records):
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"wines": records}
    resp = MagicMock()
    resp.content = [block]
    cls = MagicMock()
    cls.return_value.messages.create.return_value = resp
    return cls


def test_extract_facts_returns_postprocessed_records():
    wines = [{"id": "w1", "name": "Château du Cauze Saint-Émilion Grand Cru 2019",
              "brand": "", "wine_type": "red", "description": ""}]
    model_out = [{"wine_id": "w1", "region": "France", "sub_region": "Saint-Émilion",
                  "country": "France", "vintage_year": 2019, "varietal": "Merlot",
                  "grapes": ["Merlot"], "abv": None, "body": "full"}]
    with patch("enrichment.extraction.extractor.anthropic.Anthropic", _mock_anthropic(model_out)):
        out = extract_facts(wines, batch_size=15)
    assert len(out) == 1
    assert out[0]["region"] == "Bordeaux"


def test_extract_facts_batches_calls():
    wines = [{"id": f"w{i}", "name": f"Wine {i}", "brand": "", "wine_type": "red",
              "description": ""} for i in range(32)]
    cls = _mock_anthropic([])   # each call returns no wines; we only count calls
    with patch("enrichment.extraction.extractor.anthropic.Anthropic", cls):
        extract_facts(wines, batch_size=15)
    # 32 wines / 15 per batch = 3 calls
    assert cls.return_value.messages.create.call_count == 3
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_extraction.py -v
```
Expected: ImportError on `enrichment.extraction.extractor`.

- [ ] **Step 3: Implement `backend/enrichment/extraction/extractor.py`**

```python
"""
Haiku wine-fact extractor. Reads name + retail description, returns structured
facts (region/sub_region/country/vintage/varietal/grapes/abv/body). Grounded by
the reference cheat sheet; appellation->region is fixed deterministically.
"""
import datetime
import anthropic
from typing import List, Dict, Any, Optional
from config import settings
from enrichment.extraction.reference import (
    APPELLATIONS, CORE_GRAPES, FEW_SHOT, parent_region_for,
)

MODEL = "claude-haiku-4-5-20251001"
_BODY_VALUES = {"light", "medium", "full"}

_TOOL = {
    "name": "extract_facts",
    "description": "Return structured wine facts for each input wine.",
    "input_schema": {
        "type": "object",
        "properties": {
            "wines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "wine_id": {"type": "string"},
                        "region": {"type": ["string", "null"]},
                        "sub_region": {"type": ["string", "null"]},
                        "country": {"type": ["string", "null"]},
                        "vintage_year": {"type": ["integer", "null"]},
                        "varietal": {"type": ["string", "null"]},
                        "grapes": {"type": "array", "items": {"type": "string"}},
                        "abv": {"type": ["number", "null"]},
                        "body": {"type": ["string", "null"]},
                    },
                    "required": ["wine_id"],
                },
            },
        },
        "required": ["wines"],
    },
}


def _system_prompt() -> str:
    appellations = "\n".join(
        f"  {region}: {', '.join(apps)}" for region, apps in APPELLATIONS.items() if apps
    )
    grapes = "\n".join(f"  {color}: {', '.join(names)}" for color, names in CORE_GRAPES.items())
    examples = "\n".join(
        f'  name="{n}" desc="{d[:80]}" -> {ex}' for n, d, ex in FEW_SHOT
    )
    return (
        "You extract structured facts about a wine from its name and retail description.\n"
        "Return null for any field the name/description does not determine — NEVER invent a "
        "vintage, region, or grape. `grapes` is the full blend (empty list if unknown); "
        "`varietal` is the single primary grape. `body` is exactly one of light|medium|full. "
        "`region` is the broad region and `sub_region` is the specific appellation if named.\n\n"
        "APPELLATION -> REGION reference (if you see the appellation, the region is the group):\n"
        f"{appellations}\n\n"
        "CORE GRAPES by color (prefer these spellings; other grapes are allowed):\n"
        f"{grapes}\n\n"
        "EXAMPLES:\n"
        f"{examples}"
    )


def _post_process(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    # 1. appellation -> parent region (deterministic, overrides the model)
    parent = parent_region_for(out.get("sub_region"))
    if parent:
        out["region"] = parent
    # 2. body normalization
    body = (out.get("body") or "").strip().lower()
    out["body"] = body if body in _BODY_VALUES else None
    # 3. vintage range
    vy = out.get("vintage_year")
    next_year = datetime.date.today().year + 1
    if not (isinstance(vy, int) and 1900 <= vy <= next_year):
        out["vintage_year"] = None
    # 4. abv range
    abv = out.get("abv")
    try:
        abv = float(abv)
        out["abv"] = abv if 0 < abv <= 25 else None
    except (TypeError, ValueError):
        out["abv"] = None
    # 5. varietal defaults to first grape
    grapes = out.get("grapes") or []
    if not out.get("varietal") and grapes:
        out["varietal"] = grapes[0]
    out["grapes"] = grapes
    return out


def extract_facts(wines: List[Dict[str, Any]], batch_size: int = 15) -> List[Dict[str, Any]]:
    """Extract structured facts for a list of wine rows. Returns post-processed records."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system = _system_prompt()
    results = []
    for i in range(0, len(wines), batch_size):
        batch = wines[i:i + batch_size]
        listing = "\n".join(
            f'- wine_id={w["id"]} | name="{w.get("name","")}" | type={w.get("wine_type")} '
            f'| desc="{(w.get("description") or w.get("description_long") or "")[:400]}"'
            for w in batch
        )
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content":
                           "Extract facts for these wines:\n" + listing}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "extract_facts"},
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            if not block:
                continue
            for rec in block.input.get("wines", []):
                if rec.get("wine_id"):
                    results.append(_post_process(rec))
        except Exception as e:
            print(f"  extraction batch {i // batch_size} failed: {e}")
    return results
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_extraction.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/extractor.py backend/tests/test_extraction.py
git commit -m "feat: Haiku fact extractor with deterministic post-process (TDD)"
```

---

### Task 4: Persistence — fill-blanks + fix-placeholders (TDD)

**Files:**
- Create: `backend/enrichment/extraction/persist.py`
- Modify: `backend/tests/test_extraction.py`

- [ ] **Step 1: Append failing tests** to `backend/tests/test_extraction.py`:

```python
from enrichment.extraction.persist import compute_wine_update, CATEGORY_PLACEHOLDERS


def test_compute_update_fills_blank_columns():
    current = {"region": None, "sub_region": None, "country": None,
               "vintage_year": None, "varietal": None, "grapes": [], "abv": None, "body": None}
    extracted = {"region": "California", "country": "US", "varietal": "Zinfandel",
                 "grapes": ["Zinfandel"], "vintage_year": 2020, "abv": 14.5,
                 "body": "full", "sub_region": None}
    upd = compute_wine_update(current, extracted)
    assert upd["region"] == "California"
    assert upd["varietal"] == "Zinfandel"
    assert upd["grapes"] == ["Zinfandel"]
    assert upd["abv"] == 14.5


def test_compute_update_skips_already_populated():
    current = {"region": "Napa Valley", "varietal": "Cabernet Sauvignon",
               "country": "US", "vintage_year": 2019, "grapes": ["Cabernet Sauvignon"],
               "sub_region": "Oakville", "abv": 14.0, "body": "full"}
    extracted = {"region": "California", "varietal": "Merlot", "country": "France"}
    upd = compute_wine_update(current, extracted)
    assert "region" not in upd and "varietal" not in upd and "country" not in upd


def test_compute_update_overwrites_varietal_placeholder():
    current = {"varietal": "Red Wine", "region": None, "grapes": []}
    extracted = {"varietal": "Cabernet Sauvignon", "grapes": ["Cabernet Sauvignon"]}
    upd = compute_wine_update(current, extracted)
    assert upd["varietal"] == "Cabernet Sauvignon"     # placeholder overwritten


def test_compute_update_never_writes_null_extracted():
    current = {"region": None, "varietal": None, "grapes": []}
    extracted = {"region": None, "varietal": None, "grapes": []}
    upd = compute_wine_update(current, extracted)
    assert upd == {}
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_extraction.py -v
```
Expected: ImportError on `enrichment.extraction.persist`.

- [ ] **Step 3: Implement `backend/enrichment/extraction/persist.py`**

```python
"""
Persist extracted wine facts to the wines table: fill blank columns, and fix
varietal category placeholders left by the Geraldine's scraper.
"""
from typing import List, Dict, Any
from db import get_service_client

CATEGORY_PLACEHOLDERS = {
    "red wine", "white wine", "rosé wine", "rose wine", "orange wine",
    "sparkling wine", "dessert wine", "fortified wine", "vermouth",
}

# fields written only when the current column is null/empty
_FILL_FIELDS = ("region", "sub_region", "country", "vintage_year", "grapes", "abv", "body")


def _is_blank(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def compute_wine_update(current: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Return the subset of extracted fields to write, per fill-blanks + fix-placeholders."""
    upd = {}
    for f in _FILL_FIELDS:
        val = extracted.get(f)
        if not _is_blank(val) and _is_blank(current.get(f)):
            upd[f] = val
    # varietal: fill blank OR overwrite a category placeholder
    val = extracted.get("varietal")
    cur = current.get("varietal")
    if not _is_blank(val):
        if _is_blank(cur) or str(cur).strip().lower() in CATEGORY_PLACEHOLDERS:
            upd["varietal"] = val
    return upd


def backfill_wine_facts(records: List[Dict[str, Any]]) -> int:
    """Fetch current wines rows for the records, apply the update policy, write. Returns count updated."""
    if not records:
        return 0
    client = get_service_client()
    by_id = {r["wine_id"]: r for r in records if r.get("wine_id")}
    ids = list(by_id)
    current_rows = (
        client.table("wines")
        .select("id,region,sub_region,country,vintage_year,varietal,grapes,abv,body")
        .in_("id", ids)
        .execute()
    )
    updated = 0
    for row in (current_rows.data or []):
        extracted = by_id.get(row["id"])
        if not extracted:
            continue
        upd = compute_wine_update(row, extracted)
        if upd:
            client.table("wines").update(upd).eq("id", row["id"]).execute()
            updated += 1
    return updated
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_extraction.py -v
```
Expected: 9 passed (5 extractor + 4 persistence).

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/extraction/persist.py backend/tests/test_extraction.py
git commit -m "feat: extraction persistence — fill-blanks + fix placeholders (TDD)"
```

---

### Task 5: Runner — select, dry-run CSV, commit

**Files:**
- Create: `backend/enrichment/extraction/run_extraction.py`

No unit test — operator script, verified by import check + the live operator run later.

- [ ] **Step 1: Implement `backend/enrichment/extraction/run_extraction.py`**

```python
"""
Wine-fact extraction runner.

  cd backend && python3 -m enrichment.extraction.run_extraction [--sample N] [--write]

Selects wines that have a retail description and are missing structured data,
runs the Haiku extractor, and either writes a review CSV (default) or backfills
the wines table (--write).
"""
import argparse
import csv
from pathlib import Path

from db import get_service_client
from enrichment.extraction.extractor import extract_facts
from enrichment.extraction.persist import backfill_wine_facts, CATEGORY_PLACEHOLDERS

OUT = Path(__file__).parent / "extraction_review.csv"


def _select_wines(limit=None):
    """Wines with a description that still lack region or have a varietal placeholder."""
    c = get_service_client()
    rows, off = [], 0
    while True:
        r = (
            c.table("wine_details")
            .select("wine_id, description, description_long, "
                    "wines(id, name, brand, wine_type, region, varietal)")
            .not_.is_("description", "null")
            .range(off, off + 999)
            .execute()
        )
        if not r.data:
            break
        for d in r.data:
            w = d.get("wines") or {}
            if not w.get("id"):
                continue
            varietal = (w.get("varietal") or "").strip().lower()
            needs = (w.get("region") is None) or (not w.get("varietal")) or (varietal in CATEGORY_PLACEHOLDERS)
            if needs:
                rows.append({
                    "id": w["id"], "name": w.get("name"), "brand": w.get("brand"),
                    "wine_type": w.get("wine_type"),
                    "description": d.get("description") or d.get("description_long") or "",
                })
        if len(r.data) < 1000:
            break
        off += 1000
    return rows[:limit] if limit else rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--all", action="store_true", help="process all eligible wines, ignore --sample")
    args = ap.parse_args()

    wines = _select_wines(limit=None if args.all else args.sample)
    print(f"selected {len(wines)} wines; extracting with Haiku...")
    records = extract_facts(wines)
    print(f"extracted {len(records)} records")

    if args.write:
        n = backfill_wine_facts(records)
        print(f"backfilled {n} wines")
    else:
        by_id = {w["id"]: w for w in wines}
        fields = ["wine_id", "name", "region", "sub_region", "country", "vintage_year",
                  "varietal", "grapes", "abv", "body", "description_snippet"]
        with open(OUT, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=fields)
            wr.writeheader()
            for rec in records:
                src = by_id.get(rec["wine_id"], {})
                wr.writerow({
                    "wine_id": rec["wine_id"], "name": src.get("name"),
                    "region": rec.get("region"), "sub_region": rec.get("sub_region"),
                    "country": rec.get("country"), "vintage_year": rec.get("vintage_year"),
                    "varietal": rec.get("varietal"), "grapes": ", ".join(rec.get("grapes") or []),
                    "abv": rec.get("abv"), "body": rec.get("body"),
                    "description_snippet": (src.get("description") or "")[:100],
                })
        print(f"dry-run: wrote {OUT} for review (no DB writes). Re-run with --write to persist.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Gitignore the review artifact**

Append to `/Users/danielguerrero/Documents/ai_dev/wine_app/.gitignore`:

```
backend/enrichment/extraction/extraction_review.csv
```

- [ ] **Step 3: Verify import (no live call)**

```bash
cd backend && python3 -c "import enrichment.extraction.run_extraction as m; print('ok', bool(m.main))"
```
Expected: `ok True`.

- [ ] **Step 4: Commit**

```bash
git add backend/enrichment/extraction/run_extraction.py .gitignore
git commit -m "feat: extraction runner — dry-run CSV review + --write commit"
```

---

### Task 6: Full suite verification

- [ ] **Step 1: Run the whole suite**

```bash
cd backend && python3 -m pytest tests/ -q
```
Expected: all pass — the prior suite plus **15 new** tests (6 reference + 5 extractor + 4 persistence). If the network-dependent `test_search_wines_returns_list` fails, confirm the Supabase project is awake — it's environmental, not a regression.

- [ ] **Step 2: Report** the pass count and confirm `git status` is clean.

---

## Post-implementation (operator steps, not code)

1. `cd backend && python3 -m enrichment.extraction.run_extraction --sample 30` (dry-run; spends ~2 Haiku calls)
2. Open `backend/enrichment/extraction/extraction_review.csv`, eyeball the extracted region/varietal/grapes/vintage quality
3. If good: `python3 -m enrichment.extraction.run_extraction --all --write` to backfill all eligible wines (~70 Haiku calls, well under $1)
4. Spot-check the `wines` table; the improved region/varietal then feeds the (resumed) recommendation-agent eligibility decision and any future GrapeMinds matching
