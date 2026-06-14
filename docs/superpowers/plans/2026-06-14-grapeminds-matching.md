# GrapeMinds Matching + Enrichment Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace blind first-hit GrapeMinds matching with a confidence-scored, one-to-many candidate matcher that stores the top 3 candidates per wine and fully enriches only the primary — plus an offline effectiveness harness to measure match quality.

**Architecture:** A pure rule-based scorer (`enrichment/matching/scorer.py`) ranks GrapeMinds search hits using producer/color/name signals. The pipeline persists the top 3 to a new `wine_grapeminds_matches` table and enriches the primary into the existing `wine_details` table with a `match_confidence`. An eval harness caches real search responses and scores them against a CSV-labeled gold set. Everything operates on the retailer-agnostic `wines` table.

**Tech Stack:** Python 3.9 (use `Optional[...]`, not `X | None`), supabase-py, pytest, csv/json stdlib. GrapeMinds via existing `GrapeMindsClient` (curl subprocess).

**Build order (from spec §6):** scorer → eval harness → migration → pipeline integration. The scorer is validated on real data before any matches are written at scale.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/enrichment/matching/__init__.py` | Create | Package marker |
| `backend/enrichment/matching/scorer.py` | Create | Pure rule-based scorer + normalization + stopwords |
| `backend/tests/test_matching_scorer.py` | Create | Scorer unit tests (both retailer name styles) |
| `backend/enrichment/matching/eval/fetch_eval_searches.py` | Create | Sample gold set, cache searches, emit labeling CSV |
| `backend/enrichment/matching/eval/run_eval.py` | Create | Read labeled CSV, compute metrics, write report |
| `supabase/migrations/20260614000001_grapeminds_matches.sql` | Create | New table + `wine_details.match_confidence` + RLS/grants |
| `backend/enrichment/pipeline.py` | Modify | Score → persist candidates → enrich primary → `match_confidence` |
| `backend/tests/test_pipeline_matching.py` | Create | Pipeline integration tests (mocked GrapeMinds) |

All commands run from `backend/`.

---

### Task 1: Scorer — normalization + producer/color scores (TDD)

**Files:**
- Create: `backend/enrichment/matching/__init__.py`
- Create: `backend/tests/test_matching_scorer.py`
- Create: `backend/enrichment/matching/scorer.py`

- [ ] **Step 1: Create the package**

```bash
mkdir -p backend/enrichment/matching
touch backend/enrichment/matching/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/test_matching_scorer.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.matching.scorer import _normalize, _producer_score, _color_score


def test_normalize_lowercases_and_strips_punctuation():
    assert _normalize("Decoy, Cabernet-Sauvignon!") == "decoy cabernet sauvignon"
    assert _normalize("  Rosé   Wine ") == "rosé wine"


def test_producer_score_exact_match():
    assert _producer_score("Decoy", "Decoy") == 1.0


def test_producer_score_contains():
    # GrapeMinds "Duckhorn Vineyards ... Decoy ..." contains our brand "Decoy"
    assert _producer_score("Decoy", "Duckhorn Vineyards Decoy") == 0.6


def test_producer_score_token_overlap():
    # Neither string contains the other → falls through to Jaccard token overlap
    s = _producer_score("Bodega Catena", "Catena Zapata")
    assert 0.0 < s < 0.6


def test_producer_score_null_brand_is_zero():
    assert _producer_score(None, "Decoy") == 0.0


def test_color_score_match_and_mismatch():
    assert _color_score("red", "red") == 1.0
    assert _color_score("white", "red") == 0.0


def test_color_score_rose_alias():
    assert _color_score("rosé", "rose") == 1.0


def test_color_score_neutral_when_missing_or_unmapped():
    assert _color_score(None, "red") == 0.5
    assert _color_score("red", None) == 0.5
    assert _color_score("sparkling", "sparkling") == 0.5  # 'sparkling' not a GM color
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_matching_scorer.py -v
```

Expected: `ModuleNotFoundError: No module named 'enrichment.matching.scorer'`

- [ ] **Step 4: Implement normalization + producer/color scoring**

Create `backend/enrichment/matching/scorer.py`:

```python
"""
Rule-based GrapeMinds match scorer.

Scores a GrapeMinds search hit against one of our wines using only fields the
SEARCH response carries (display_name, producer_name, color) — grapes/region
are not available until the detail fetch. Pure functions, no I/O.

    confidence = producer_score * 0.45 + color_score * 0.25 + name_score * 0.30
"""
import re
from typing import Optional, List, Dict, Any

PRODUCER_WEIGHT = 0.45
COLOR_WEIGHT = 0.25
NAME_WEIGHT = 0.30

# Maps a GrapeMinds `color` to our wines.wine_type vocabulary.
_COLOR_MAP = {"red": "red", "white": "white", "rosé": "rosé", "rose": "rosé"}

# Generic wine words + geography that add no discriminating power.
_STOPWORDS = {
    "wine", "red", "white", "rosé", "rose", "sparkling", "blanc", "the", "de", "di",
    "california", "italy", "italian", "france", "french", "spain", "spanish",
    "argentina", "chile", "australia", "new", "zealand", "napa", "valley", "sonoma",
    "county", "paso", "robles", "lodi", "marlborough",
}
_SIZE_RE = re.compile(r"^\d+(ml|l)?$")        # 750, 750ml, 1l
_VINTAGE_RE = re.compile(r"^(19|20)\d{2}$")   # 1999, 2021


def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàáâäãåèéêëìíîïòóôöõùúûüñç]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> set:
    return {t for t in _normalize(s).split() if t}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _producer_score(brand: Optional[str], producer_name: Optional[str]) -> float:
    if not brand:
        return 0.0
    a, b = _normalize(brand), _normalize(producer_name or "")
    if not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.6
    return _jaccard(set(a.split()), set(b.split()))


def _color_score(wine_type: Optional[str], color: Optional[str]) -> float:
    if not wine_type or not color:
        return 0.5
    mapped = _COLOR_MAP.get(_normalize(color))
    if mapped is None:
        return 0.5
    return 1.0 if mapped == _normalize(wine_type) else 0.0
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_matching_scorer.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/enrichment/matching/__init__.py backend/enrichment/matching/scorer.py backend/tests/test_matching_scorer.py
git commit -m "feat: GrapeMinds scorer — normalization + producer/color scoring (TDD)"
```

---

### Task 2: Scorer — name score + score_candidates ranking (TDD)

**Files:**
- Modify: `backend/enrichment/matching/scorer.py`
- Modify: `backend/tests/test_matching_scorer.py`

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_matching_scorer.py`:

```python
from enrichment.matching.scorer import _name_score, score_candidates


def test_name_score_strips_retailer_noise():
    # Only "decoy" + "cabernet" + "sauvignon" survive stopword/size stripping → strong overlap
    s = _name_score(
        "Decoy Cabernet Sauvignon California Red Wine 750 ml",
        "Decoy, Cabernet Sauvignon",
    )
    assert s == 1.0


def test_name_score_strips_vintage_for_geraldines_style():
    s = _name_score("Les Lunes Rouge 2021", "Les Lunes, Pinot Noir, Carneros")
    # "les" + "lunes" overlap; "rouge"/"pinot"/"noir"/"carneros" differ → partial
    assert 0.0 < s < 1.0


def _hit(gm_id, display_name, producer_name, color):
    return {"id": gm_id, "display_name": display_name,
            "producer_name": producer_name, "color": color}


def test_score_candidates_ranks_and_marks_primary():
    hits = [
        _hit(240170, "Duckhorn Vineyards, Decoy Cabernet Sauvignon, Sonoma County", "Duckhorn Vineyards", "red"),
        _hit(136214, "Decoy, Cabernet Sauvignon", "Decoy", "red"),
        _hit(235600, "Decoy, Cabernet Sauvignon, Sonoma County", "Decoy", "red"),
    ]
    out = score_candidates(
        hits,
        brand="Decoy",
        wine_type="red",
        name="Decoy Cabernet Sauvignon California Red Wine",
    )
    assert [c["grapeminds_id"] for c in out][0] == "136214"   # best is exact Decoy Cab
    assert out[0]["rank"] == 1 and out[0]["is_primary"] is True
    assert out[1]["is_primary"] is False
    assert all(0.0 <= c["confidence"] <= 1.0 for c in out)
    # confidence descending
    assert out[0]["confidence"] >= out[1]["confidence"] >= out[2]["confidence"]


def test_score_candidates_keeps_top_3():
    hits = [_hit(i, f"Wine {i}", f"Producer {i}", "red") for i in range(6)]
    out = score_candidates(hits, brand="Producer 0", wine_type="red", name="Wine 0")
    assert len(out) == 3


def test_score_candidates_dedupes_grapeminds_id():
    hits = [_hit(111, "Decoy, Cabernet Sauvignon", "Decoy", "red"),
            _hit(111, "Decoy, Cabernet Sauvignon", "Decoy", "red")]
    out = score_candidates(hits, brand="Decoy", wine_type="red", name="Decoy Cabernet Sauvignon")
    assert len(out) == 1


def test_score_candidates_empty_hits():
    assert score_candidates([], brand="Decoy", wine_type="red", name="Decoy") == []
```

- [ ] **Step 2: Run tests to confirm the new ones fail**

```bash
cd backend && python3 -m pytest tests/test_matching_scorer.py -v
```

Expected: failures on `ImportError` for `_name_score` / `score_candidates`.

- [ ] **Step 3: Append name score + score_candidates**

Append to `backend/enrichment/matching/scorer.py`:

```python
def _content_tokens(s: str) -> set:
    out = set()
    for t in _tokens(s):
        if t in _STOPWORDS or _SIZE_RE.match(t) or _VINTAGE_RE.match(t):
            continue
        out.add(t)
    return out


def _name_score(our_name: Optional[str], display_name: Optional[str]) -> float:
    return _jaccard(_content_tokens(our_name or ""), _content_tokens(display_name or ""))


def _score_hit(hit: Dict[str, Any], brand, wine_type, name) -> float:
    score = (
        _producer_score(brand, hit.get("producer_name")) * PRODUCER_WEIGHT
        + _color_score(wine_type, hit.get("color")) * COLOR_WEIGHT
        + _name_score(name, hit.get("display_name")) * NAME_WEIGHT
    )
    return round(max(0.0, min(1.0, score)), 3)


def score_candidates(
    hits: List[Dict[str, Any]],
    brand: Optional[str],
    wine_type: Optional[str],
    name: Optional[str],
    keep: int = 3,
) -> List[Dict[str, Any]]:
    """
    Rank GrapeMinds search hits and return the top `keep` as candidate dicts:
      {grapeminds_id, display_name, producer_name, color, confidence, rank, is_primary}
    Dedupes by grapeminds_id, sorts by confidence desc (stable), marks rank 1 primary.
    """
    seen = set()
    scored = []
    for hit in hits:
        gid = str(hit.get("id", ""))
        if not gid or gid in seen:
            continue
        seen.add(gid)
        scored.append({
            "grapeminds_id": gid,
            "display_name": hit.get("display_name"),
            "producer_name": hit.get("producer_name"),
            "color": hit.get("color"),
            "confidence": _score_hit(hit, brand, wine_type, name),
        })

    scored.sort(key=lambda c: c["confidence"], reverse=True)
    top = scored[:keep]
    for i, c in enumerate(top):
        c["rank"] = i + 1
        c["is_primary"] = (i == 0)
    return top
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_matching_scorer.py -v
```

Expected: 14 passed (8 from Task 1 + 6 here).

- [ ] **Step 5: Commit**

```bash
git add backend/enrichment/matching/scorer.py backend/tests/test_matching_scorer.py
git commit -m "feat: GrapeMinds scorer — name score + ranked top-3 candidates (TDD)"
```

---

### Task 3: Eval harness — fetch + cache + labeling CSV

**Files:**
- Create: `backend/enrichment/matching/eval/fetch_eval_searches.py`

No unit test — this is an offline operator script. Verified by a dry import + a live run later.

- [ ] **Step 1: Implement the fetch/cache/CSV script**

Create `backend/enrichment/matching/eval/fetch_eval_searches.py`:

```python
"""
Effectiveness eval — step 1: sample a stratified gold set, fetch + cache GrapeMinds
search hits, and emit a labeling CSV.

Run ONCE (spends ~50 GrapeMinds search calls):
  cd backend && python3 -m enrichment.matching.eval.fetch_eval_searches

Outputs (git-ignored):
  enrichment/matching/eval/eval_searches.json   — raw cached hits per wine
  enrichment/matching/eval/eval_candidates.csv  — open in Excel/Sheets, fill `correct`
"""
import csv
import json
import random
from pathlib import Path

from db import get_service_client
from config import settings
from enrichment.grapeminds import GrapeMindsClient
from enrichment.matching.scorer import score_candidates

OUT_DIR = Path(__file__).parent
SEED = 42
PER_RETAILER = 25  # ~50 total


def _sample_wines():
    """Stratified sample: PER_RETAILER wines each from H-E-B and Geraldine's."""
    c = get_service_client()
    rng = random.Random(SEED)
    sample = []
    for retailer in ("H-E-B", "Geraldine's Natural Wines"):
        rows = (
            c.table("retail_inventory")
            .select("wines(id,name,brand,wine_type)")
            .eq("retailer_name", retailer)
            .limit(1000)
            .execute()
        )
        wines, seen = [], set()
        for r in (rows.data or []):
            w = r.get("wines") or {}
            if w.get("id") and w["id"] not in seen and w.get("name"):
                seen.add(w["id"])
                wines.append(w)
        rng.shuffle(wines)
        sample.extend(wines[:PER_RETAILER])
    return sample


def main():
    gm = GrapeMindsClient(api_key=settings.grapeminds_api_key)
    wines = _sample_wines()
    print(f"Sampled {len(wines)} wines. Fetching GrapeMinds searches...")

    cache = {}
    csv_rows = []
    for i, w in enumerate(wines, 1):
        hits = gm.search(w["name"], limit=5)
        cache[w["id"]] = {"wine": w, "hits": hits}
        candidates = score_candidates(hits, w.get("brand"), w.get("wine_type"), w["name"])
        if not candidates:
            csv_rows.append({
                "wine_id": w["id"], "wine_name": w["name"], "brand": w.get("brand"),
                "wine_type": w.get("wine_type"), "rank": "", "grapeminds_id": "",
                "gm_display_name": "NO_HITS", "gm_producer": "", "gm_color": "",
                "confidence": "", "is_primary": "", "correct": "",
            })
        for cand in candidates:
            csv_rows.append({
                "wine_id": w["id"], "wine_name": w["name"], "brand": w.get("brand"),
                "wine_type": w.get("wine_type"), "rank": cand["rank"],
                "grapeminds_id": cand["grapeminds_id"],
                "gm_display_name": cand["display_name"], "gm_producer": cand["producer_name"],
                "gm_color": cand["color"], "confidence": cand["confidence"],
                "is_primary": cand["is_primary"], "correct": "",
            })
        print(f"  [{i}/{len(wines)}] {w['name'][:50]} → {len(hits)} hits")

    (OUT_DIR / "eval_searches.json").write_text(json.dumps(cache, indent=2, ensure_ascii=False))

    fields = ["wine_id", "wine_name", "brand", "wine_type", "rank", "grapeminds_id",
              "gm_display_name", "gm_producer", "gm_color", "confidence", "is_primary", "correct"]
    with open(OUT_DIR / "eval_candidates.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nWrote {OUT_DIR/'eval_searches.json'} and {OUT_DIR/'eval_candidates.csv'}")
    print("Now open eval_candidates.csv and put 1 in `correct` on each wine's true match (blank = none).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add eval artifacts to .gitignore**

Append to `/Users/danielguerrero/Documents/ai_dev/wine_app/.gitignore`:

```
backend/enrichment/matching/eval/eval_searches.json
backend/enrichment/matching/eval/eval_candidates.csv
backend/enrichment/matching/eval/eval_report.md
```

- [ ] **Step 3: Verify it imports cleanly (no live call)**

```bash
cd backend && python3 -c "import enrichment.matching.eval.fetch_eval_searches as m; print('ok', bool(m.main))"
```

Expected: `ok True`

- [ ] **Step 4: Commit**

```bash
git add backend/enrichment/matching/eval/fetch_eval_searches.py .gitignore
git commit -m "feat: eval harness — fetch+cache GrapeMinds searches, emit labeling CSV"
```

---

### Task 4: Eval harness — metrics report from labeled CSV (TDD)

**Files:**
- Create: `backend/enrichment/matching/eval/run_eval.py`
- Create: `backend/tests/test_eval_metrics.py`

- [ ] **Step 1: Write failing test for the metrics function**

Create `backend/tests/test_eval_metrics.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.matching.eval.run_eval import compute_metrics


def _row(wine_id, source, rank, is_primary, confidence, correct):
    return {"wine_id": wine_id, "source": source, "rank": str(rank),
            "is_primary": str(is_primary), "confidence": str(confidence), "correct": correct}


def test_compute_metrics_precision_recall_coverage():
    rows = [
        # wine A: correct == primary  -> covered, p@1 hit, recall hit
        _row("A", "H-E-B", 1, True, 0.92, "1"),
        _row("A", "H-E-B", 2, False, 0.80, ""),
        # wine B: correct is rank 2   -> covered, p@1 MISS, recall hit
        _row("B", "H-E-B", 1, True, 0.70, ""),
        _row("B", "H-E-B", 2, False, 0.55, "1"),
        # wine C: no correct           -> not covered
        _row("C", "Geraldine's Natural Wines", 1, True, 0.30, ""),
    ]
    m = compute_metrics(rows)
    assert m["overall"]["n_wines"] == 3
    assert m["overall"]["coverage"] == round(2/3, 3)
    assert m["overall"]["precision_at_1"] == 0.5     # A hit, B miss
    assert m["overall"]["top3_recall"] == 1.0        # A and B both found
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && python3 -m pytest tests/test_eval_metrics.py -v
```

Expected: `ModuleNotFoundError` / `ImportError` on `run_eval`.

- [ ] **Step 3: Implement run_eval with a testable compute_metrics**

Create `backend/enrichment/matching/eval/run_eval.py`:

```python
"""
Effectiveness eval — step 2: read the labeled CSV, compute metrics, write a report.

  cd backend && python3 -m enrichment.matching.eval.run_eval

Reads  enrichment/matching/eval/eval_candidates.csv  (with `correct` filled)
Writes enrichment/matching/eval/eval_report.md
"""
import csv
from collections import defaultdict
from pathlib import Path
from typing import List, Dict

OUT_DIR = Path(__file__).parent


def _bucket(conf: float) -> str:
    if conf >= 0.8:
        return ">=0.8"
    if conf >= 0.5:
        return "0.5-0.8"
    return "<0.5"


def compute_metrics(rows: List[Dict]) -> dict:
    """Aggregate labeled candidate rows into coverage / precision@1 / recall / calibration."""
    by_wine = defaultdict(list)
    for r in rows:
        by_wine[r["wine_id"]].append(r)

    def _is_true(v):
        return str(v).strip() == "1"

    def _is_primary(v):
        return str(v).strip().lower() in ("true", "1")

    def metrics_for(wine_ids):
        n = len(wine_ids)
        covered = p1_hits = recall_hits = 0
        buckets = defaultdict(lambda: [0, 0])  # bucket -> [hits, total]
        for wid in wine_ids:
            cands = by_wine[wid]
            correct_rows = [c for c in cands if _is_true(c.get("correct"))]
            primary = next((c for c in cands if _is_primary(c.get("is_primary"))), None)
            if correct_rows:
                covered += 1
                if any(_is_primary(c.get("is_primary")) for c in correct_rows):
                    p1_hits += 1
                recall_hits += 1
            if primary and primary.get("confidence"):
                b = _bucket(float(primary["confidence"]))
                buckets[b][1] += 1
                if any(_is_primary(c.get("is_primary")) for c in correct_rows):
                    buckets[b][0] += 1
        return {
            "n_wines": n,
            "coverage": round(covered / n, 3) if n else 0.0,
            "precision_at_1": round(p1_hits / covered, 3) if covered else 0.0,
            "top3_recall": round(recall_hits / covered, 3) if covered else 0.0,
            "calibration": {b: {"correct": h, "total": t, "rate": round(h / t, 3) if t else 0.0}
                            for b, (h, t) in sorted(buckets.items())},
        }

    all_ids = list(by_wine.keys())
    result = {"overall": metrics_for(all_ids)}
    by_source = defaultdict(list)
    for wid, cands in by_wine.items():
        by_source[cands[0].get("source", "?")].append(wid)
    result["by_retailer"] = {src: metrics_for(ids) for src, ids in by_source.items()}
    return result


def _format_report(m: dict) -> str:
    lines = ["# GrapeMinds Matching — Effectiveness Report", ""]
    for scope, data in [("Overall", m["overall"])] + list(m["by_retailer"].items()):
        lines.append(f"## {scope}")
        lines.append(f"- wines: {data['n_wines']}")
        lines.append(f"- coverage: {data['coverage']}")
        lines.append(f"- precision@1: {data['precision_at_1']}")
        lines.append(f"- top-3 recall: {data['top3_recall']}")
        lines.append("- calibration (primary confidence bucket → correctness):")
        for b, c in data["calibration"].items():
            lines.append(f"    {b}: {c['correct']}/{c['total']} = {c['rate']}")
        lines.append("")
    return "\n".join(lines)


def main():
    csv_path = OUT_DIR / "eval_candidates.csv"
    # Tag each row with its wine's source by reading source off the eval CSV if present,
    # else default "?". The fetch script does not emit source per row, so derive from cache.
    import json
    cache_path = OUT_DIR / "eval_searches.json"
    source_by_wine = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
        for wid, entry in cache.items():
            # source is not on the wine row; infer from retailer via DB-free heuristic is not
            # possible, so the fetch script tags it. Fall back to "?".
            source_by_wine[wid] = entry.get("source", "?")

    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            r["source"] = source_by_wine.get(r["wine_id"], r.get("source", "?"))
            rows.append(r)

    m = compute_metrics(rows)
    (OUT_DIR / "eval_report.md").write_text(_format_report(m))
    print(_format_report(m))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add `source` to the fetch script's cache and CSV**

So `run_eval` has retailer info, update `fetch_eval_searches.py` to tag source. In `_sample_wines`, set `w["source"] = retailer` on each sampled wine, include `"source": w.get("source")` in `cache[w["id"]]`, and add a `source` column to the CSV rows + `fields` list.

Edit `backend/enrichment/matching/eval/fetch_eval_searches.py`:

1. In `_sample_wines`, inside the dedupe loop, after `wines.append(w)` is chosen, set source — change the append block to:

```python
            if w.get("id") and w["id"] not in seen and w.get("name"):
                seen.add(w["id"])
                w["source"] = retailer
                wines.append(w)
```

2. Change the cache line to include source:

```python
        cache[w["id"]] = {"wine": w, "source": w.get("source"), "hits": hits}
```

3. Add `"source": w.get("source")` to BOTH `csv_rows.append({...})` dicts, and add `"source"` to the `fields` list (after `"wine_type"`).

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_eval_metrics.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/enrichment/matching/eval/run_eval.py backend/enrichment/matching/eval/fetch_eval_searches.py backend/tests/test_eval_metrics.py
git commit -m "feat: eval harness — metrics report from labeled CSV (TDD)"
```

---

### Task 5: Migration — matches table + match_confidence

**Files:**
- Create: `supabase/migrations/20260614000001_grapeminds_matches.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260614000001_grapeminds_matches.sql`:

```sql
-- One-to-many GrapeMinds candidate matches per wine (top 3 by confidence).
CREATE TABLE wine_grapeminds_matches (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id       UUID NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
  grapeminds_id TEXT NOT NULL,
  display_name  TEXT,
  producer_name TEXT,
  color         TEXT,
  confidence    NUMERIC(4,3),
  rank          INTEGER,
  is_primary    BOOLEAN DEFAULT FALSE,
  matched_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (wine_id, grapeminds_id)
);

CREATE INDEX idx_gm_matches_wine    ON wine_grapeminds_matches(wine_id);
CREATE INDEX idx_gm_matches_primary ON wine_grapeminds_matches(wine_id) WHERE is_primary;

ALTER TABLE wine_grapeminds_matches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read gm matches" ON wine_grapeminds_matches FOR SELECT USING (TRUE);
GRANT SELECT ON wine_grapeminds_matches TO anon, authenticated;
GRANT ALL    ON wine_grapeminds_matches TO service_role;

-- Confidence of the primary match, denormalized for easy recommender reads.
ALTER TABLE wine_details ADD COLUMN IF NOT EXISTS match_confidence NUMERIC(4,3);
```

- [ ] **Step 2: Apply to the cloud DB**

The migration history was repaired earlier, so `db push` applies only new migrations. Apply it:

```bash
cd /Users/danielguerrero/Documents/ai_dev/wine_app
supabase db push --yes < /dev/null
```

Expected: `Applying migration 20260614000001_grapeminds_matches.sql...` then `Finished supabase db push.`

Then verify the column and table exist:

```bash
cd backend && python3 -c "
from db import get_service_client
c = get_service_client()
c.table('wine_grapeminds_matches').select('id').limit(1).execute()
c.table('wine_details').select('match_confidence').limit(1).execute()
print('table + column present')
"
```

Expected: `table + column present`

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260614000001_grapeminds_matches.sql
git commit -m "feat: wine_grapeminds_matches table + wine_details.match_confidence"
```

---

### Task 6: Pipeline integration — persist candidates + enrich primary (TDD)

**Files:**
- Modify: `backend/enrichment/pipeline.py`
- Create: `backend/tests/test_pipeline_matching.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/test_pipeline_matching.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import patch, MagicMock
from enrichment.pipeline import persist_candidates


def _capture_table():
    """A fake Supabase table that records delete/insert calls."""
    calls = {"deleted": False, "inserted": None}

    class FakeTable:
        def delete(self):
            calls["deleted"] = True
            return self
        def eq(self, *a, **k):
            return self
        def insert(self, records):
            calls["inserted"] = records
            return self
        def execute(self):
            return MagicMock(data=[])

    client = MagicMock()
    client.table.return_value = FakeTable()
    return client, calls


def test_persist_candidates_deletes_then_inserts_top3():
    client, calls = _capture_table()
    candidates = [
        {"grapeminds_id": "136214", "display_name": "Decoy, Cabernet Sauvignon",
         "producer_name": "Decoy", "color": "red", "confidence": 0.97, "rank": 1, "is_primary": True},
        {"grapeminds_id": "235600", "display_name": "Decoy, Cab, Sonoma",
         "producer_name": "Decoy", "color": "red", "confidence": 0.93, "rank": 2, "is_primary": False},
    ]
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        persist_candidates("wine-1", candidates)

    assert calls["deleted"] is True
    assert calls["inserted"] is not None
    assert len(calls["inserted"]) == 2
    first = calls["inserted"][0]
    assert first["wine_id"] == "wine-1"
    assert first["grapeminds_id"] == "136214"
    assert first["is_primary"] is True


def test_persist_candidates_empty_is_noop():
    client, calls = _capture_table()
    with patch("enrichment.pipeline.get_service_client", return_value=client):
        persist_candidates("wine-1", [])
    assert calls["inserted"] is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_pipeline_matching.py -v
```

Expected: `ImportError: cannot import name 'persist_candidates'`.

- [ ] **Step 3: Add `persist_candidates` and wire it into `enrich_wine`**

In `backend/enrichment/pipeline.py`, add the imports near the top (after the existing imports):

```python
from enrichment.matching.scorer import score_candidates
```

Add this function (e.g., after `_persist`):

```python
def persist_candidates(wine_id: str, candidates: list):
    """Replace this wine's GrapeMinds candidate rows with a fresh top-N set."""
    if not candidates:
        return
    client = get_service_client()
    now = datetime.now(timezone.utc).isoformat()
    client.table("wine_grapeminds_matches").delete().eq("wine_id", wine_id).execute()
    records = [{
        "wine_id": wine_id,
        "grapeminds_id": c["grapeminds_id"],
        "display_name": c.get("display_name"),
        "producer_name": c.get("producer_name"),
        "color": c.get("color"),
        "confidence": c.get("confidence"),
        "rank": c.get("rank"),
        "is_primary": c.get("is_primary", False),
        "matched_at": now,
    } for c in candidates]
    client.table("wine_grapeminds_matches").insert(records).execute()
```

Then replace the matching middle of `enrich_wine`. Change this block:

```python
    # ── Step 1: Search for the wine by name ───────────────────────────────────
    hits = gm.search(wine_name, limit=3)
    if not hits:
        return EnrichmentResult(wine_id=wine_id, source="not_found", needs_refetch=False)

    gm_id = hits[0]["id"]
```

to:

```python
    # ── Step 1: Search, score, and persist top-3 candidates ───────────────────
    hits = gm.search(wine_name, limit=5)
    if not hits:
        return EnrichmentResult(wine_id=wine_id, source="not_found", needs_refetch=False)

    candidates = score_candidates(
        hits,
        brand=wine_row.get("brand"),
        wine_type=wine_row.get("wine_type"),
        name=wine_name,
    )
    persist_candidates(wine_id, candidates)
    primary = candidates[0]
    primary_confidence = primary["confidence"]
    gm_id = int(primary["grapeminds_id"])
```

- [ ] **Step 4: Record `match_confidence` on the enrichment result**

In `pipeline.py`, add a field to `EnrichmentResult` (after `source`):

```python
    match_confidence: Optional[float] = None
```

In `enrich_wine`, after building `result = _result_from_wine_data(...)` for both the partial and full branches, set the confidence before persisting. The simplest single edit: right after `result = _result_from_wine_data(wine_id, gm_wine, drinking)`, add:

```python
    result.match_confidence = primary_confidence
```

And in `_persist`, add `match_confidence` to the record dict (inside the `{...}.items() if v is not None}` block):

```python
        "match_confidence": result.match_confidence,
```

- [ ] **Step 5: Give the scorer the signals it needs — select `brand` + `wine_type` for enrich callers**

`score_candidates` reads `wine_row["brand"]` and `wine_row["wine_type"]`, but the enrichment router only selects `id,name,varietal,region`. Update both queries in `backend/api/routers/enrichment.py` to include `brand,wine_type`.

In `enrich_single`, change:
```python
        .select("id,name,varietal,region")
```
to:
```python
        .select("id,name,varietal,region,brand,wine_type")
```

In `enrich_pending`, change:
```python
    all_wines = client.table("wines").select("id,name,varietal,region").limit(200).execute()
```
to:
```python
    all_wines = client.table("wines").select("id,name,varietal,region,brand,wine_type").limit(200).execute()
```

- [ ] **Step 6: Keep existing pipeline tests offline — patch `persist_candidates`**

`enrich_wine` now calls `persist_candidates`, which calls `get_service_client()` (real DB). The three existing `test_pipeline.py` tests that run past the search step must patch it so they stay offline. In `backend/tests/test_pipeline.py`, add `patch("enrichment.pipeline.persist_candidates")` to the `with` blocks of:
- `test_enrich_wine_full_enrichment_on_first_fetch`
- `test_enrich_wine_partial_first_fetch_sets_needs_refetch`
- `test_enrich_wine_with_refetch_does_second_pass`

For example, the first becomes:
```python
    with patch("enrichment.pipeline.is_already_enriched", return_value=False), \
         patch("enrichment.pipeline.GrapeMindsClient", return_value=mock_client), \
         patch("enrichment.pipeline.persist_candidates"), \
         patch("enrichment.pipeline._persist") as mock_persist:
        result = await enrich_wine(WINE_ROW)
```
Apply the same added patch line to the other two tests. (The `not_found` and `skips_already_enriched` tests return before `persist_candidates`, so they need no change.)

- [ ] **Step 7: Run the new tests + full scorer/pipeline suite**

```bash
cd backend && python3 -m pytest tests/test_pipeline_matching.py tests/test_pipeline.py tests/test_matching_scorer.py -v
```

Expected: all pass (2 new pipeline-matching + 7 existing pipeline + 14 scorer = 23).

- [ ] **Step 8: Commit**

```bash
git add backend/enrichment/pipeline.py backend/api/routers/enrichment.py backend/tests/test_pipeline_matching.py backend/tests/test_pipeline.py
git commit -m "feat: pipeline persists scored candidates + match_confidence (TDD)"
```

---

### Task 7: Full suite verification

- [ ] **Step 1: Run the whole suite**

```bash
cd backend && python3 -m pytest tests/ -q
```

Expected: all tests pass (47 prior + 14 scorer + 1 eval metrics + 2 pipeline matching = **64**). If the network-dependent `test_search_wines_returns_list` fails, confirm the Supabase project is awake; it is environmental, not a regression.

- [ ] **Step 2: Report** pass count and confirm `git status` is clean.

---

## Post-implementation (operator steps, not code)

After the code lands, validate the method on real data before any bulk matching:

1. `cd backend && python3 -m enrichment.matching.eval.fetch_eval_searches` (spends ~50 GrapeMinds searches once)
2. Open `backend/enrichment/matching/eval/eval_candidates.csv`, put `1` in `correct` on each wine's true match (blank = none)
3. `cd backend && python3 -m enrichment.matching.eval.run_eval` → review `eval_report.md` against the §6 success criteria
4. Tune weights/stopwords in `scorer.py` and re-run step 3 (free — uses cached searches) until criteria are met
