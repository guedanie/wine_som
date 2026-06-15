# Haiku Wine-Fact Extraction — Design

**Date:** 2026-06-15
**Status:** Approved (design)
**Scope:** A cheap Haiku agent that reads each wine's name + retail description and backfills structured fields (`region`, `sub_region`, `country`, `vintage_year`, `varietal`, `grapes`, `abv`, `body`) onto the `wines` table, grounded by an appellation + core-grape cheat sheet.

---

## 1. Overview

The scrapers captured wine **names** and **retail descriptions** but left structured fields (`region`, `varietal`, `vintage_year`, …) almost entirely null. That gap has hurt warm-up selection, GrapeMinds matching, and recommendation quality. This job uses **Anthropic Haiku** (not GrapeMinds — no scraping budget) to extract those fields from the name + description we already have, anchored by a **cheat sheet** of appellations and core grapes to prevent hallucination and to make appellation→region mapping deterministic.

Outcome: a populated `wines` catalog (region/sub_region/varietal/grapes/vintage/abv/body) that improves candidate eligibility + scoring now, and matching for any future GrapeMinds (re-)enrichment.

---

## 2. Scope

**In scope:** schema columns for `grapes`/`abv`/`body`; a cheat-sheet reference module; a Haiku extraction module (tool-use, batched, deterministic appellation→region post-processing); a persistence layer (fill-blanks + fix-placeholders); a runner with dry-run review + commit; tests.

**Out of scope (future):** re-running GrapeMinds matching against the improved fields; the recommendation-agent changes (paused, pending this data); the long tail of obscure grapes/appellations (cheat sheet covers core; Haiku may still emit long-tail values, which we keep).

---

## 3. Schema

`wines` already has `varietal, region, sub_region, country, vintage_year`. Add three columns for the extras:

`supabase/migrations/20260615000001_wine_extracted_fields.sql`:
```sql
ALTER TABLE wines ADD COLUMN IF NOT EXISTS grapes JSONB DEFAULT '[]';  -- full blend, e.g. ["Cabernet Sauvignon","Merlot"]
ALTER TABLE wines ADD COLUMN IF NOT EXISTS abv   NUMERIC(4,1);          -- e.g. 13.9
ALTER TABLE wines ADD COLUMN IF NOT EXISTS body  TEXT;                  -- 'light' | 'medium' | 'full'
```

Field → column mapping:
| Extracted | Column |
|---|---|
| region (parent) | `wines.region` |
| sub_region (appellation) | `wines.sub_region` |
| country | `wines.country` |
| vintage_year | `wines.vintage_year` |
| varietal (primary grape) | `wines.varietal` |
| grapes[] (full blend) | `wines.grapes` |
| abv | `wines.abv` |
| body | `wines.body` |

---

## 4. Cheat sheet — `enrichment/extraction/reference.py`

Static data, used **both** in the prompt and for deterministic post-processing.

```python
APPELLATIONS = {
    "Bordeaux": ["Médoc", "Haut-Médoc", "Margaux", "Pauillac", "Saint-Julien",
                 "Saint-Estèphe", "Pessac-Léognan", "Graves", "Saint-Émilion",
                 "Pomerol", "Lalande-de-Pomerol", "Listrac", "Moulis", "Fronsac"],
    "Burgundy":  ["Chablis", "Gevrey-Chambertin", "Vosne-Romanée", "Nuits-Saint-Georges",
                  "Pommard", "Volnay", "Meursault", "Puligny-Montrachet", "Beaune"],
    "Rhône":     ["Châteauneuf-du-Pape", "Côte-Rôtie", "Hermitage", "Crozes-Hermitage",
                  "Gigondas", "Vacqueyras", "Côtes du Rhône"],
    "Napa Valley": ["Oakville", "Rutherford", "Stags Leap", "Howell Mountain",
                    "Mount Veeder", "Spring Mountain", "Diamond Mountain", "Calistoga"],
    "Sonoma":    ["Russian River Valley", "Alexander Valley", "Dry Creek Valley",
                  "Sonoma Coast", "Knights Valley", "Chalk Hill"],
    "Tuscany":   ["Chianti", "Chianti Classico", "Brunello di Montalcino",
                  "Vino Nobile di Montepulciano", "Bolgheri"],
    "Piedmont":  ["Barolo", "Barbaresco", "Barbera d'Alba", "Langhe"],
    "Rioja":     ["Rioja Alta", "Rioja Alavesa", "Rioja Oriental"],
    "Ribera del Duero": [],
    "Mendoza":   ["Uco Valley", "Luján de Cuyo", "Maipú"],
    "Paso Robles": [], "Willamette Valley": [], "Marlborough": [],
    # implementation expands these lists; this is the representative core
}

CORE_GRAPES = {
    "red":   ["Cabernet Sauvignon", "Merlot", "Pinot Noir", "Syrah", "Shiraz", "Malbec",
              "Grenache", "Tempranillo", "Sangiovese", "Nebbiolo", "Zinfandel",
              "Cabernet Franc", "Petit Verdot", "Petite Sirah", "Mourvèdre",
              "Carmenère", "Gamay", "Barbera"],
    "white": ["Chardonnay", "Sauvignon Blanc", "Riesling", "Pinot Grigio", "Pinot Gris",
              "Chenin Blanc", "Viognier", "Gewürztraminer", "Albariño",
              "Grüner Veltliner", "Sémillon", "Vermentino", "Torrontés", "Moscato"],
    "rose":  ["Grenache", "Cinsault", "Mourvèdre", "Pinot Noir", "Syrah", "Tempranillo"],
}

FEW_SHOT = [
    # (name, description) -> expected extracted dict  (4-6 worked examples)
    ("Decoy Cabernet Sauvignon California Red Wine",
     "Rich Californian red with dark cherry and supple tannins. ABV: 14.5%",
     {"region": "California", "sub_region": None, "country": "US", "vintage_year": None,
      "varietal": "Cabernet Sauvignon", "grapes": ["Cabernet Sauvignon"], "abv": 14.5, "body": "full"}),
    ("Château du Cauze Saint-Émilion Grand Cru 2019", "",
     {"region": "Bordeaux", "sub_region": "Saint-Émilion", "country": "France", "vintage_year": 2019,
      "varietal": "Merlot", "grapes": ["Merlot", "Cabernet Franc"], "abv": None, "body": "full"}),
    ("Les Lunes Rouge 2021", "A fresh, low-tannin red blend from Mendocino.",
     {"region": "Mendocino", "sub_region": None, "country": "US", "vintage_year": 2021,
      "varietal": "Red Blend", "grapes": [], "abv": None, "body": "medium"}),
    ("Whitehaven Sauvignon Blanc New Zealand White Wine",
     "Zesty Marlborough white, grapefruit and passionfruit.",
     {"region": "Marlborough", "sub_region": None, "country": "New Zealand", "vintage_year": None,
      "varietal": "Sauvignon Blanc", "grapes": ["Sauvignon Blanc"], "abv": None, "body": "light"}),
]


def parent_region_for(appellation: str) -> Optional[str]:
    """Deterministic appellation -> parent region, case/accent-insensitive. None if unknown."""
```

`parent_region_for` is built from an inverted index of `APPELLATIONS` (appellation → parent), matched on a normalized (lowercased, accent-folded) key.

---

## 5. Extraction — `enrichment/extraction/extractor.py`

`extract_facts(wines: List[Dict], batch_size: int = 15) -> List[Dict]`

- **Input** per wine: `{id, name, brand, wine_type, description, description_long}`.
- **Batches** ~15 wines per Haiku call to cut calls/cost.
- **Forced tool use** — tool `extract_facts` with input `{wines: [{wine_id, region, country, vintage_year, varietal, grapes, abv, body, sub_region}]}`; every field nullable; the model is instructed to return `null` rather than guess.
- **Model:** `claude-haiku-4-5-20251001`.
- **System prompt:** a wine-data-extractor role + a condensed cheat sheet (appellation→region map + core grapes by color) + the `FEW_SHOT` worked examples. Explicit instruction: *use null when the name/description doesn't determine a field; never invent a vintage or region.*
- **Post-processing (deterministic), per returned record:**
  1. If `sub_region` is set and `parent_region_for(sub_region)` is known, set `region` = that parent (overriding whatever the model put for region). This is the appellation→region guarantee.
  2. Normalize `body` to one of `light|medium|full` or null.
  3. Coerce `vintage_year` to int in a sane range (1900–current+1) or null; `abv` to float 0–25 or null.
  4. Leave `grapes` as-is (long-tail allowed); `varietal` defaults to `grapes[0]` if varietal null and grapes present.
- **Returns** a list of records keyed by `wine_id` with the cleaned fields.

Pure of DB I/O — testable by mocking `anthropic.Anthropic`.

---

## 6. Persistence — `enrichment/extraction/persist.py`

`compute_wine_update(current: Dict, extracted: Dict) -> Dict` (pure) decides what to write, per the **fill-blanks + fix-placeholders** policy:

- For `region, sub_region, country, vintage_year, grapes, abv, body`: include the extracted value **only if** it is non-null **and** the current column is null/empty (`grapes` empty = `[]`/None).
- For `varietal`: include the extracted value if non-null **and** (current is null/empty **OR** current is a **category placeholder**) where `CATEGORY_PLACEHOLDERS = {"red wine","white wine","rosé wine","rose wine","orange wine","sparkling wine","dessert wine","fortified wine","vermouth"}` (case-insensitive).
- Never write null/empty extracted values.

`backfill_wine_facts(records)` fetches each wine's current row (batched via `.in_("id", ids)`), computes the update with `compute_wine_update`, and applies non-empty updates via `wines.update(...).eq("id", wine_id)` using the service client.

---

## 7. Runner — `enrichment/extraction/run_extraction.py`

```
python3 -m enrichment.extraction.run_extraction [--sample N] [--write]
```
- Selects target wines: those with a `wine_details.description` (or `description_long`) present and missing structured data (`region IS NULL OR varietal IS NULL OR varietal IN (placeholders)`).
- `--sample N`: process only N (default 30 for a first pass).
- **Dry-run (default, no `--write`)**: extract → write `extraction_review.csv` (wine_id, name, description snippet, all extracted fields) for eyeball review. No DB writes.
- **`--write`**: extract → `backfill_wine_facts` (persist).

Recommended use: `--sample 30` dry-run → review the CSV → full `--write` run once quality looks right. (Haiku cost for all ~1,065 ≈ under $1.)

Artifacts (`extraction_review.csv`) are git-ignored.

---

## 8. Error Handling & Edge Cases

| Case | Behavior |
|---|---|
| Model returns no tool block | Skip the batch (log), continue; those wines stay unbackfilled. |
| `sub_region` not in cheat sheet | Keep the model's `region` as-is (long-tail region allowed). |
| `vintage_year`/`abv` out of range or non-numeric | Coerced to null. |
| Extracted field null | Not written (current value untouched). |
| `varietal` currently a category placeholder | Overwritten with extracted grape (the fix-placeholders rule). |
| Wine has no description and no vintage/region in name | Most fields come back null; row simply gets little/nothing — acceptable. |
| Batch partially malformed | Process the well-formed records; skip malformed entries. |

---

## 9. Testing

1. **`test_extraction_reference.py`** — `parent_region_for("Saint-Émilion") == "Bordeaux"`, accent/case-insensitive (`"saint-emilion"`, `"SAINT-ÉMILION"`); unknown → None; a Napa appellation (`"Oakville"` → "Napa Valley").
2. **`test_extraction.py`** (extractor, mocked `anthropic.Anthropic`):
   - post-process maps `sub_region` appellation → parent `region` even when the model put a wrong region;
   - `body` normalization + `vintage_year`/`abv` range coercion;
   - `varietal` defaults to `grapes[0]` when null;
   - batching: 32 wines → 3 Haiku calls at batch_size 15 (assert call count).
3. **`test_extraction.py`** (persistence, pure `compute_wine_update`):
   - fills a null column; skips a populated one; overwrites a `varietal` placeholder ("Red Wine" → "Cabernet Sauvignon"); never writes null extracted values; empty `grapes` treated as blank.

All existing suites still pass.

---

## 10. File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260615000001_wine_extracted_fields.sql` | Create | Add `grapes`/`abv`/`body` columns |
| `backend/enrichment/extraction/__init__.py` | Create | Package marker |
| `backend/enrichment/extraction/reference.py` | Create | Cheat sheets + few-shot + `parent_region_for` |
| `backend/enrichment/extraction/extractor.py` | Create | `extract_facts` (Haiku tool-use, batched, deterministic post-process) |
| `backend/enrichment/extraction/persist.py` | Create | `compute_wine_update` + `backfill_wine_facts` |
| `backend/enrichment/extraction/run_extraction.py` | Create | Runner: select, batch, dry-run CSV / `--write` commit |
| `backend/tests/test_extraction_reference.py` | Create | Cheat-sheet lookup tests |
| `backend/tests/test_extraction.py` | Create | Extractor post-process + backfill-policy tests (mocked Claude) |
