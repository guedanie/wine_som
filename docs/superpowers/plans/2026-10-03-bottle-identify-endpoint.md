# Bottle Identify Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `POST /api/identify`, a backend endpoint that accepts a bottle photo and returns a wine identification, wiring together the already-built-and-tested `enrichment/label_scan.py` (Claude vision label read) and `recommendation/label_match.py` (pure catalog-matching logic) with no changes to either.

**Architecture:** One new router file (`api/routers/identify.py`) owns all the I/O: reading the uploaded file, calling the vision read, running a catalog-wide candidate fetch, and calling the existing pure classifier. Registered in `api/main.py` like every other router. Rate-limited with the existing `RateLimiter` pattern.

**Tech Stack:** Python 3.9 (backend/), FastAPI (`UploadFile` for multipart), `anthropic` SDK (already used by `label_scan.py`), pytest + `httpx.AsyncClient`/`ASGITransport` for endpoint tests.

**Design doc:** `docs/superpowers/specs/2026-10-03-bottle-identify-endpoint-design.md`

---

## Task 1: Candidate fetch + router skeleton

**Files:**
- Create: `backend/api/routers/identify.py`
- Test: `backend/tests/test_identify_api.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_identify_api.py`:

```python
"""Tests for POST /api/identify — the bottle-photo identification endpoint.

No real Anthropic calls: enrichment.label_scan.read_label is always mocked.
Real vision accuracy is validated manually against the live endpoint with
real photos, per the design doc — not something a mocked test can measure.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes-for-testing"


def _read_and_meta(producer="Tablas Creek", wine_name="Esprit de Tablas",
                   vintage="2021", confidence=0.9, is_wine=True):
    read = {"producer": producer, "wine_name": wine_name, "vintage": vintage,
            "appellation": "Paso Robles", "varietal": None,
            "confidence": confidence, "is_wine": is_wine}
    meta = {"latency_s": 1.4, "input_tokens": 1200, "output_tokens": 40,
            "model": "claude-haiku-4-5-20251001"}
    return read, meta


@pytest.mark.asyncio
async def test_exact_match_returns_200_with_wine():
    candidates = [{"id": "w1", "name": "Esprit de Tablas", "brand": "Tablas Creek",
                   "vintage_year": 2021, "region": "Paso Robles", "varietal": None}]
    with patch("api.routers.identify.read_label", return_value=_read_and_meta()), \
         patch("api.routers.identify._fetch_candidates", return_value=candidates):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/identify",
                                 files={"photo": ("bottle.jpg", _JPEG_BYTES, "image/jpeg")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "exact"
    assert body["wine"]["id"] == "w1"
    assert "_debug" in body
    assert body["_debug"]["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_unreadable_label_returns_200_with_unreadable_status():
    with patch("api.routers.identify.read_label", return_value=(None, _read_and_meta()[1])), \
         patch("api.routers.identify._fetch_candidates", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/identify",
                                 files={"photo": ("bottle.jpg", _JPEG_BYTES, "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json()["status"] == "unreadable"


@pytest.mark.asyncio
async def test_non_image_upload_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/identify",
                             files={"photo": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_vision_call_failure_returns_502():
    with patch("api.routers.identify.read_label", side_effect=Exception("Anthropic down")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/identify",
                                 files={"photo": ("bottle.jpg", _JPEG_BYTES, "image/jpeg")})
    assert resp.status_code == 502


def test_fetch_candidates_queries_name_and_brand_tokens():
    from api.routers.identify import _fetch_candidates
    mock_sb = MagicMock()
    mock_table = MagicMock()
    mock_sb.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.is_.return_value = mock_table
    mock_table.or_.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "w1", "name": "Esprit de Tablas"}])

    read = {"producer": "Tablas Creek", "wine_name": "Esprit de Tablas"}
    result = _fetch_candidates(mock_sb, read)

    assert result == [{"id": "w1", "name": "Esprit de Tablas"}]
    mock_sb.table.assert_called_with("wines")
    mock_table.is_.assert_called_with("excluded_at", "null")
    assert mock_table.or_.called


def test_fetch_candidates_returns_empty_for_no_tokens():
    from api.routers.identify import _fetch_candidates
    mock_sb = MagicMock()
    result = _fetch_candidates(mock_sb, {"producer": None, "wine_name": None})
    assert result == []
    mock_sb.table.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_identify_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.routers.identify'` (and a 404 on the route once the module exists but isn't registered — you'll see the import error first)

- [ ] **Step 3: Write the implementation**

Create `backend/api/routers/identify.py`:

```python
"""Bottle-photo identification: label photo -> vision read -> catalog match.

Wires together two already-built, already-tested pieces with no changes to
either: enrichment.label_scan (Claude vision reads the label) and
recommendation.label_match (pure catalog-matching logic, the five-state
scanResult classifier). This router owns all the I/O -- reading the upload,
the DB candidate fetch, the vision call -- the same split recommend.py uses
between router-level I/O and pure recommendation/* logic.

Catalog-wide matching, no zip scoping, Haiku only -- see the design doc
(docs/superpowers/specs/2026-10-03-bottle-identify-endpoint-design.md) for
why: this endpoint exists for manual validation against real photos, not
as a finished public feature yet.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from db import get_supabase_client
from enrichment.label_scan import HAIKU, read_label
from recommendation.candidate_filters import significant_name_tokens
from recommendation.label_match import classify_scan
from api.ratelimit import RateLimiter, limit_dependency

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["identify"])

# A vision call per request -- cap per IP per hour. Generous: this endpoint
# exists for manual validation with real photos, not production traffic yet.
_identify_limiter = RateLimiter(limit=30, window_seconds=3600)

_CANDIDATE_LIMIT = 120
_MAX_TOKENS_FOR_SEARCH = 6


def _fetch_candidates(supabase, read: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Catalog-wide token search over name/brand -- mirrors
    scripts/spike_vision_match.py's fetch_candidates. Not shared with that
    script: production routers shouldn't import from scripts/, and both
    sides are small enough that the duplication is cheaper than a shared
    module for two call sites."""
    text = " ".join(filter(None, [read.get("producer"), read.get("wine_name")]))
    tokens = significant_name_tokens(text)
    if not tokens:
        return []
    conds = []
    for t in tokens[:_MAX_TOKENS_FOR_SEARCH]:
        conds.append(f"name.ilike.%{t}%")
        conds.append(f"brand.ilike.%{t}%")
    return (supabase.table("wines")
            .select("id, name, brand, vintage_year, region, varietal")
            .is_("excluded_at", "null")
            .or_(",".join(conds))
            .limit(_CANDIDATE_LIMIT)
            .execute().data or [])


@router.post("/identify", dependencies=[Depends(limit_dependency(_identify_limiter, "identify"))])
async def identify_bottle(photo: UploadFile = File(...)):
    content_type = photo.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400,
                            detail="Upload an image file (jpeg/png/heic).")

    image_bytes = await photo.read()

    try:
        read, meta = read_label(image_bytes, content_type, model=HAIKU)
    except Exception as e:
        logger.exception("IDENTIFY | vision call failed: %s", e)
        raise HTTPException(status_code=502,
                            detail="Couldn't reach the vision service — try again.")

    supabase = get_supabase_client()
    candidates = _fetch_candidates(supabase, read) if read else []
    result = classify_scan(read, candidates)
    result["_debug"] = {
        "read": read,
        "latency_s": meta.get("latency_s"),
        "model": meta.get("model"),
        "input_tokens": meta.get("input_tokens"),
        "output_tokens": meta.get("output_tokens"),
    }
    return result
```

Then register it in `backend/api/main.py`. Change:

```python
from api.routers import wines, enrichment, recommend, region, feedback, somm, search, deals, stores
```

to:

```python
from api.routers import wines, enrichment, recommend, region, feedback, somm, search, deals, stores, identify
```

and add, alongside the other `app.include_router(...)` calls:

```python
app.include_router(identify.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_identify_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full fast suite to confirm no regressions**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS, 874 + 6 = 880 tests

- [ ] **Step 6: Commit**

```bash
cd /Users/danielguerrero/dev/wine_app/.worktrees/bottle-identify-endpoint
git add backend/api/routers/identify.py backend/api/main.py backend/tests/test_identify_api.py
git commit -m "feat: POST /api/identify — bottle photo identification endpoint"
```

---

## Task 2: Manual live validation (not automated — this is the owner's job)

This task has no code changes. It exists in the plan so the workflow is explicit:

- [ ] Start the backend locally from the worktree: `cd backend && python3 -m uvicorn api.main:app --reload`
- [ ] Send a real bottle photo: `curl -F "photo=@/path/to/bottle.jpg" http://localhost:8000/api/identify`
- [ ] Try a few different real photos (varying lighting/angle per `frontend/design-system/handoffs/bottle-scan/PHOTO-GUIDELINES.md`'s difficulty tiers, if more than a couple are tried)
- [ ] Report back in conversation what the responses look like — right status, right wine, confidence that seems reasonable or not, anything surprising
- [ ] Iterate on the branch based on that feedback before merging to `main`
