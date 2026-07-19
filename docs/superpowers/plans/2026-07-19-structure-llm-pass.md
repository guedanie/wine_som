# Blend Structure / Sweetness LLM Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill LLM-inferred `sweetness` on the ~17,509 structure profiles that lack it, and full LLM structure profiles on the ~1,273 unanchored blends, via a new `backfill_structure_llm.py` runner (qwen2.5:7b on the mini), with a table-over-llm precedence rule so llm profiles don't fossilize.

**Architecture:** Same shape as the extraction/backfill scripts. A new `scripts/backfill_structure_llm.py` with a pure, TDD'd planning core (eligibility, merge, echo-id validation + clamping) plus an ollama-calling runner; one precedence change to `structure_to_persist`. Correctness guarded by a bounded live run + a `structure_benchmark.py` gate before the full drain.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `str | None`), pytest, supabase-py, ollama (`http://localhost:11434/api/chat`, `qwen2.5:7b`). Commands from `backend/` with `/usr/bin/python3` on the mini.

**Spec:** `docs/superpowers/specs/2026-07-16-structure-llm-pass-design.md` (numbers re-measured 2026-07-19: 20,759 wines; 18,576 profiles; 17,509 missing sweetness; 1,273 unanchored blends).

---

## Reference: current-code anchors

- `enrichment/extraction/structure_benchmark.py:27` — `_SYSTEM` (the tuned prompt asking for `{wine_id, body, tannin, acidity, sweetness}`, integers 1-10). `OLLAMA_URL = "http://localhost:11434/api/chat"`, model `qwen2.5:7b`. **The prompt returns `tannin` (singular); the stored profile uses `tannins` (plural).**
- `recommendation/structure_profiles.py` — `structure_for(varietal, grapes, region)` → `{body, tannins, acidity, source:'table'}` or None; `structure_to_persist(varietal, grapes, region, existing)` → returns None when `existing.get("source") != "table"` (preserves vivino/grapeminds — and currently llm). Stored profile keys: `body, tannins, acidity, sweetness, source`.
- `scripts/persist_structure.py` — calls `structure_to_persist`; upserts `wine_details` on_conflict `wine_id`.
- `scripts/backfill_grapes.py` / `enrichment/extraction/ollama_extractor.py` — the runner + ollama-call patterns to mirror.
- `scripts/run_extraction.py` — the `scraper_runs` row lifecycle (`status="running"` → `success`/`failed`) to mirror for monitoring.
- Baseline fast suite: **584 passed, 3 deselected.** Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/<file> -v`.

---

### Task 1: Pure core — eligibility, merge, validation/clamp

**Files:**
- Create: `backend/scripts/backfill_structure_llm.py` (pure functions only; runner in Task 2)
- Test: `backend/tests/test_backfill_structure_llm.py` (new)

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_backfill_structure_llm.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.backfill_structure_llm import (
    needs_sweetness, needs_full_profile, merge_sweetness, full_profile_from,
    clamp_1_10, validate_batch)


def test_needs_sweetness():
    assert needs_sweetness({"body": 8, "tannins": 7, "acidity": 5}) is True
    assert needs_sweetness({"body": 8, "sweetness": 1}) is False
    assert needs_sweetness({"body": 8, "sweetness": None}) is True
    assert needs_sweetness(None) is False          # no profile -> not a sweetness-fill row


def test_needs_full_profile():
    # grape data but table can't anchor and no profile -> full-profile row
    assert needs_full_profile({"varietal": "Assyrtiko-Malagousia field blend",
                               "grapes": ["Assyrtiko", "Malagousia"], "region": None},
                              has_profile=False) is True
    # a known grape the table anchors -> not eligible (table handles it)
    assert needs_full_profile({"varietal": "Merlot", "grapes": ["Merlot"], "region": None},
                              has_profile=False) is False
    # already has a profile -> not a full-profile row
    assert needs_full_profile({"varietal": "X", "grapes": ["Y"], "region": None},
                              has_profile=True) is False
    # no grape data -> not eligible (Vivino territory)
    assert needs_full_profile({"varietal": None, "grapes": [], "region": "Tuscany"},
                              has_profile=False) is False


def test_clamp_1_10():
    assert clamp_1_10(7) == 7
    assert clamp_1_10("5") == 5
    assert clamp_1_10(0) is None
    assert clamp_1_10(11) is None
    assert clamp_1_10(None) is None
    assert clamp_1_10("x") is None


def test_merge_sweetness_only_touches_sweetness():
    prof = {"body": 8, "tannins": 7, "acidity": 5, "source": "table"}
    out = merge_sweetness(prof, 2)
    assert out == {"body": 8, "tannins": 7, "acidity": 5, "source": "table",
                   "sweetness": 2, "sweetness_source": "llm"}
    # original not mutated
    assert "sweetness" not in prof


def test_merge_sweetness_marks_source_unless_profile_is_llm():
    llm_prof = {"body": 5, "tannins": 4, "acidity": 6, "source": "llm"}
    out = merge_sweetness(llm_prof, 8)
    assert out["sweetness"] == 8 and "sweetness_source" not in out   # own source already llm


def test_full_profile_from_maps_tannin_and_clamps():
    # benchmark returns 'tannin' (singular); stored key is 'tannins'
    out = full_profile_from({"body": 9, "tannin": 8, "acidity": 6, "sweetness": 1})
    assert out == {"body": 9, "tannins": 8, "acidity": 6, "sweetness": 1, "source": "llm"}
    # any out-of-range value -> None (drop the whole profile, don't write partial)
    assert full_profile_from({"body": 9, "tannin": 99, "acidity": 6, "sweetness": 1}) is None


def test_validate_batch_drops_foreign_and_malformed_ids():
    batch_ids = {"a", "b"}
    resp = {"wines": [
        {"wine_id": "a", "body": 5, "tannin": 4, "acidity": 6, "sweetness": 1},
        {"wine_id": "zzz", "body": 5, "tannin": 4, "acidity": 6, "sweetness": 1},  # not in batch
        {"wine_id": "b", "body": 5, "tannin": 4, "acidity": 6, "sweetness": 99},   # bad value
    ]}
    clean, bad_id, bad_val = validate_batch(resp, batch_ids)
    assert set(clean.keys()) == {"a"}          # b dropped for bad value, zzz for bad id
    assert bad_id == 1 and bad_val == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_structure_llm.py -v`
Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Implement** — create `backend/scripts/backfill_structure_llm.py`:

```python
"""LLM structure/sweetness pass (CLAUDE.md item 12).

Two eligibility classes, one qwen2.5:7b pass on the mini:
1. SWEETNESS FILL — a wine has a structure_profile with no `sweetness`. The LLM
   value is MERGED into the existing profile (body/tannins/acidity untouched;
   the table/Vivino/GrapeMinds values stay authoritative). Marked
   `sweetness_source: "llm"` unless the profile's own source is already llm.
2. UNANCHORED BLEND — a wine has grape data the table can't anchor
   (structure_for -> None) and no profile. The LLM writes the FULL profile
   {body, tannins, acidity, sweetness, source:"llm"}.

The benchmark (structure_benchmark.py) showed qwen quantifies sweetness well
(~86% within ±1) but tannin/acidity poorly — hence sweetness is the only axis
we trust it for on already-anchored wines. llm full profiles are refreshed by
the table once grapes arrive (see structure_to_persist).

Run from backend/ on the mini:
    python3 -m scripts.backfill_structure_llm [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recommendation.structure_profiles import structure_for               # noqa: E402
from enrichment.extraction.structure_benchmark import _SYSTEM, OLLAMA_URL  # noqa: E402

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def clamp_1_10(v) -> Optional[int]:
    """Integer 1-10 or None (out-of-range / unparseable -> drop, never coerce)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 10 else None


def needs_sweetness(profile: Optional[Dict[str, Any]]) -> bool:
    return bool(profile) and profile.get("sweetness") is None


def needs_full_profile(wine: Dict[str, Any], has_profile: bool) -> bool:
    if has_profile:
        return False
    if not (wine.get("grapes") or wine.get("varietal")):
        return False
    return structure_for(wine.get("varietal"), wine.get("grapes"),
                         wine.get("region")) is None


def merge_sweetness(profile: Dict[str, Any], sweetness: int) -> Dict[str, Any]:
    """Copy the profile with sweetness set; body/tannins/acidity untouched."""
    out = dict(profile)
    out["sweetness"] = sweetness
    if out.get("source") != "llm":
        out["sweetness_source"] = "llm"
    return out


def full_profile_from(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Full llm profile from a raw response row (maps 'tannin' -> 'tannins').
    None if ANY axis is out of range (don't write a partial profile)."""
    body = clamp_1_10(resp.get("body"))
    tannins = clamp_1_10(resp.get("tannin"))
    acidity = clamp_1_10(resp.get("acidity"))
    sweetness = clamp_1_10(resp.get("sweetness"))
    if None in (body, tannins, acidity, sweetness):
        return None
    return {"body": body, "tannins": tannins, "acidity": acidity,
            "sweetness": sweetness, "source": "llm"}


def validate_batch(resp: Dict[str, Any],
                   batch_ids: set) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
    """Return ({wine_id: raw_row}, bad_id_count, bad_value_count). Drops rows
    whose wine_id isn't in the input batch (qwen echo corruption) or whose
    sweetness doesn't clamp (guards the sweetness-fill path)."""
    clean, bad_id, bad_val = {}, 0, 0
    for r in resp.get("wines", []):
        wid = str(r.get("wine_id") or "")
        if wid not in batch_ids:
            bad_id += 1
            continue
        if clamp_1_10(r.get("sweetness")) is None:
            bad_val += 1
            continue
        clean[wid] = r
    return clean, bad_id, bad_val
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_structure_llm.py -v`
Expected: ALL PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_structure_llm.py backend/tests/test_backfill_structure_llm.py
git commit -m "feat: backfill_structure_llm pure core — eligibility, sweetness merge, echo-id validation"
```

---

### Task 2: Runner — ollama call, fetch, apply, monitoring

**Files:**
- Modify: `backend/scripts/backfill_structure_llm.py` (append)

- [ ] **Step 1: Append the runner**

```python
def _call_ollama(wines: List[Dict[str, Any]], timeout: int = 180) -> Dict[str, Any]:
    """One ollama batch call using the benchmark's tuned prompt."""
    listing = "\n".join(
        f'- wine_id={w["id"]} | name="{w.get("name","")}" | type={w.get("wine_type")} '
        f'| desc="{(w.get("desc") or "")[:300]}"' for w in wines)
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": "Estimate structure:\n" + listing}],
        "stream": False, "format": "json", "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return json.loads((data.get("message") or {}).get("content") or "{}")


def _fetch_eligible(db, limit: int) -> Tuple[List[dict], List[dict]]:
    """Return (sweetness_rows, blend_rows). Each row: {id,name,desc,wine_type,
    varietal,grapes,region,profile}. Paged; filtered client-side (postgrest JSON
    predicates are awkward and the pool is ~19k)."""
    sweetness, blends, page = [], [], 0
    while True:
        rows = (db.table("wines")
                .select("id,name,varietal,region,grapes,wine_type,"
                        "wine_details(structure_profile,tasting_notes)")
                .order("id").range(page * 1000, (page + 1) * 1000 - 1).execute().data)
        if not rows:
            break
        for w in rows:
            wd = w.get("wine_details") or {}
            wd = wd[0] if isinstance(wd, list) else wd
            profile = wd.get("structure_profile")
            base = {"id": w["id"], "name": w.get("name"),
                    "desc": wd.get("tasting_notes"), "wine_type": w.get("wine_type"),
                    "varietal": w.get("varietal"), "grapes": w.get("grapes") or [],
                    "region": w.get("region"), "profile": profile}
            if needs_sweetness(profile):
                sweetness.append(base)
            elif needs_full_profile(w, has_profile=bool(profile)):
                blends.append(base)
        page += 1
        if limit and (len(sweetness) + len(blends)) >= limit:
            break
    if limit:
        merged = (sweetness + blends)[:limit]
        s_ids = {r["id"] for r in sweetness}
        sweetness = [r for r in merged if r["id"] in s_ids]
        blends = [r for r in merged if r["id"] not in s_ids]
    return sweetness, blends


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
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    from db import get_service_client
    import uuid
    from datetime import datetime, timezone
    db = get_service_client()

    run_id = str(uuid.uuid4())
    if not args.dry_run:
        db.table("scraper_runs").insert({
            "id": run_id, "retailer_name": "Structure LLM (local qwen)",
            "status": "running"}).execute()

    sweetness, blends, filled_s, filled_b, bad = [], [], 0, 0, 0
    try:
        sweetness, blends = _fetch_eligible(db, args.limit)
        print(f"eligible: {len(sweetness)} sweetness-fill, {len(blends)} unanchored blends", flush=True)

        def _run(rows, is_full):
            nonlocal filled_s, filled_b, bad
            for i in range(0, len(rows), args.batch):
                chunk = rows[i:i + args.batch]
                ids = {r["id"] for r in chunk}
                try:
                    resp = _call_ollama(chunk)
                except Exception as e:
                    print(f"  batch {i // args.batch} call failed: {e}", flush=True)
                    continue
                clean, bad_id, bad_val = validate_batch(resp, ids)
                bad += bad_id + bad_val
                by_id = {r["id"]: r for r in chunk}
                for wid, row in clean.items():
                    if is_full:
                        prof = full_profile_from(row)
                        if prof is None:
                            bad += 1
                            continue
                    else:
                        prof = merge_sweetness(by_id[wid]["profile"],
                                               clamp_1_10(row["sweetness"]))
                    if not args.dry_run:
                        db.table("wine_details").upsert(
                            {"wine_id": wid, "structure_profile": prof},
                            on_conflict="wine_id").execute()
                    if is_full:
                        filled_b += 1
                    else:
                        filled_s += 1
                print(f"  {('blend' if is_full else 'sweetness')} {i + len(chunk)}/{len(rows)} "
                      f"| filled s={filled_s} b={filled_b} bad={bad}", flush=True)

        _run(sweetness, is_full=False)
        _run(blends, is_full=True)

        summary = (f"Structure LLM{' (dry run)' if args.dry_run else ''}: "
                   f"{filled_s} sweetness filled, {filled_b} blends profiled, "
                   f"{bad} dropped (bad id/value)")
        print(summary, flush=True)
        if not args.dry_run:
            db.table("scraper_runs").update({
                "status": "success", "records_updated": filled_s + filled_b,
                "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
            _notify_slack(f":test_tube: {summary}")
    except Exception as e:
        if not args.dry_run:
            db.table("scraper_runs").update({
                "status": "failed", "error_message": str(e)[:500],
                "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
        raise


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sanity — tests still pass + import**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_backfill_structure_llm.py -q && /usr/bin/python3 -c "import scripts.backfill_structure_llm"`
Expected: PASS; import clean. (Do NOT run against ollama/DB here — that's Task 4.)

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/backfill_structure_llm.py
git commit -m "feat: backfill_structure_llm runner — ollama batches, paged fetch, scraper_runs, Slack"
```

---

### Task 3: `structure_to_persist` — table refreshes llm profiles (keeps llm sweetness)

Precedence must become `vivino/grapeminds > table > llm`: once grapes arrive and the table can anchor a wine whose profile is `source:"llm"`, the table overwrites body/tannins/acidity but **keeps the llm sweetness** (the table has none).

**Files:**
- Modify: `backend/recommendation/structure_profiles.py`
- Test: `backend/tests/test_structure_profiles.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_persist_refreshes_llm_profile_keeping_its_sweetness():
    from recommendation.structure_profiles import structure_to_persist
    llm = {"body": 5, "tannins": 4, "acidity": 6, "sweetness": 8, "source": "llm",
           "sweetness_source": "llm"}
    out = structure_to_persist("Cabernet Sauvignon", ["Cabernet Sauvignon"], "Napa Valley", llm)
    assert out is not None                       # table now anchors -> refresh
    assert out["source"] == "table"
    assert out["sweetness"] == 8                 # llm sweetness preserved
    assert out["body"] >= 7                       # table's Cab body wins over the llm 5


def test_persist_still_preserves_vivino_and_grapeminds():
    from recommendation.structure_profiles import structure_to_persist
    assert structure_to_persist("Merlot", ["Merlot"], None,
                                {"body": 6, "source": "vivino"}) is None
    assert structure_to_persist("Merlot", ["Merlot"], None,
                                {"body": 6}) is None   # grapeminds (no source key)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_structure_profiles.py -k "refreshes_llm or preserves_vivino" -v`
Expected: FAIL — the llm profile is currently preserved (returns None), so no refresh.

- [ ] **Step 3: Implement** — in `structure_to_persist`, change the guard from "only table is refreshable" to "table and llm are refreshable; llm sweetness carries over". Replace the early-return block:

```python
    if existing and existing.get("source") not in ("table", "llm"):
        return None   # vivino / grapeminds — authoritative, never overwrite
    base = structure_for(varietal, grapes, region)
    if base is None:
        return None   # no grape to anchor — leave the existing profile as-is
    # Refreshing an llm profile: keep its sweetness (the table has none).
    if existing and existing.get("source") == "llm" and existing.get("sweetness") is not None:
        base = dict(base)
        base["sweetness"] = existing["sweetness"]
        if existing.get("sweetness_source"):
            base["sweetness_source"] = existing["sweetness_source"]
    return base
```

(Keep the function's existing tail if it already computes `base` — reconcile so the final return matches: a `table`-sourced dict, with llm sweetness merged when refreshing an llm profile. Read the current body first and adapt; do not duplicate the `structure_for` call.)

- [ ] **Step 4: Run tests**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/test_structure_profiles.py tests/test_persist_structure.py -v` (the second only if it exists — grep first)
Expected: ALL PASS, including existing precedence tests (vivino/grapeminds still preserved).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/structure_profiles.py backend/tests/test_structure_profiles.py
git commit -m "feat: structure_to_persist refreshes llm profiles from the table, keeping llm sweetness"
```

---

### Task 4: Bounded live run + benchmark gate (controller runs, on the mini)

- [ ] **Step 1: Full fast suite**

Run: `cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: ALL PASS (584 + the new tests).

- [ ] **Step 2: Confirm ollama is up** — `curl -s http://localhost:11434/api/tags | head -c 200` shows `qwen2.5:7b`. If not, `ollama serve` / `ollama pull qwen2.5:7b`.

- [ ] **Step 3: Bounded live run (~50 wines)** — `/usr/bin/python3 -m scripts.backfill_structure_llm --limit 50 2>&1 | tail -5`. Then spot-check the writes in the DB: a Moscato/Port should read sweetness high (≥7), a dry Napa Cab low (1-2), a demi-sec Vouvray mid (4-6); an unanchored blend should get a full 4-axis profile. Query a handful by name and eyeball the `structure_profile`.

- [ ] **Step 4: Benchmark gate** — `/usr/bin/python3 -m enrichment.extraction.structure_benchmark` (against Vivino ground truth). Sweetness must hold ≥ ~86% within ±1 and body/tannin/acidity must not regress (the merge path never touches them; the full-profile class is the only new writer of those). If sweetness drops materially below the benchmark, STOP and investigate the prompt/model before the full drain.

---

### Task 5: Full drain (controller runs, background on the mini)

- [ ] **Step 1: Drain in chunks** — run `python3 -m scripts.backfill_structure_llm --limit 2000` repeatedly (≈9 chunks for ~17.5k eligible; each re-fetches so already-filled rows drop out — idempotent). Run in the background like the 2026-07-10 extraction drain; watch the per-chunk Slack summaries. ~17.5k short prompts ≈ a few hours of qwen.

- [ ] **Step 2: Verify coverage** —
```bash
cd /Users/danielguerrero/dev/wine_app/backend && /usr/bin/python3 -c "
from db import get_service_client
db = get_service_client()
det, page = [], 0
while True:
    r = db.table('wine_details').select('structure_profile').not_.is_('structure_profile','null').range(page*1000,(page+1)*1000-1).execute().data
    det += r; page += 1
    if len(r) < 1000: break
sweet = sum(1 for d in det if (d['structure_profile'] or {}).get('sweetness') is not None)
print(f'profiles: {len(det)} | with sweetness: {sweet} ({sweet/len(det)*100:.0f}%)')
"
```
Expected: sweetness coverage ~6% → ≥90% of profiled wines; structure coverage up by ~1,273 (the blends).

---

### Task 6: Weekly integration + docs

**Files:**
- Modify: `scripts/run_extraction_launchd.sh` (the mini's chain — append a step), `CLAUDE.md` (item 12), `docs/reference/enrichment.md`, `docs/mac-mini-enrichment-server.md`, `docs/mini-agent-tasks.md`

- [ ] **Step 1: Weekly chain** — append to the mini's extraction LaunchAgent wrapper (`run_extraction_launchd.sh`), after the `persist_structure` step: `"$PY" -m scripts.backfill_structure_llm --limit 500` (incremental; weekly volume is only newly scraped/extracted wines). Mirror the existing step's logging/Slack wrapping.

- [ ] **Step 2: Docs** — `CLAUDE.md` item 12 → ✅ with the live numbers (sweetness coverage %, blends profiled); `docs/reference/enrichment.md` structure section (the llm pass, precedence, echo-id validation); `docs/mac-mini-enrichment-server.md` (new chain step); `docs/mini-agent-tasks.md` run record.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/run_extraction_launchd.sh CLAUDE.md docs/
git commit -m "docs: structure/sweetness LLM pass landed + weekly chain step (item 12)"
```
