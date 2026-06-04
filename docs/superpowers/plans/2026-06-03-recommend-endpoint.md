# `/api/recommend` Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `POST /api/recommend` — a single-turn Claude Haiku recommendation endpoint that retrieves enriched local wines, scores candidates, and returns a narrative + structured picks via tool use.

**Architecture:** Rule-based Python scorer narrows enriched inventory candidates to top 12, which are passed to Claude Haiku using forced tool use to return structured `(narrative, picks)`. Sessions are saved to Supabase for future multi-turn extension.

**Tech Stack:** FastAPI, Anthropic SDK (`anthropic ^0.40`, model `claude-haiku-4-5-20251001`), supabase-py, Pydantic v2, pytest-asyncio, unittest.mock

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/recommendation/__init__.py` | Create | Package marker |
| `backend/recommendation/scorer.py` | Create | Rule-based candidate scoring + filtering |
| `backend/recommendation/claude_client.py` | Create | Anthropic Haiku tool-use call |
| `backend/api/routers/recommend.py` | Create | `POST /api/recommend` endpoint |
| `backend/api/schemas.py` | Modify | Add `WinePick`, update `RecommendResponse` |
| `backend/api/main.py` | Modify | Register `recommend` router |
| `backend/tests/test_scorer.py` | Create | 3 unit tests for scorer |
| `backend/tests/test_recommend_api.py` | Create | 4 integration tests for endpoint |

All commands run from `backend/`.

---

### Task 1: Scorer — TDD

**Files:**
- Create: `backend/recommendation/__init__.py`
- Create: `backend/tests/test_scorer.py`
- Create: `backend/recommendation/scorer.py`

- [ ] **Step 1: Create the recommendation package**

```bash
mkdir -p backend/recommendation
touch backend/recommendation/__init__.py
```

- [ ] **Step 2: Write the three failing scorer tests**

Create `backend/tests/test_scorer.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.scorer import score_candidates


def _wine(name, wine_type="red", varietal="Malbec", region="Mendoza",
          country="Argentina", tasting_notes="dark fruit", flavor_profile=None, price=25.0):
    return {
        "wine_id": "test-id",
        "name": name,
        "wine_type": wine_type,
        "varietal": varietal,
        "region": region,
        "country": country,
        "tasting_notes": tasting_notes,
        "flavor_profile": flavor_profile or [],
        "structure_profile": {},
        "price": price,
        "retailer": "Geraldine's",
    }


def test_wine_type_match_scores_higher():
    red = _wine("Bold Red", wine_type="red")
    white = _wine("Crisp White", wine_type="white")
    result = score_candidates(
        candidates=[white, red],
        wine_type="red",
        style_preferences=[],
        avoid=[],
        budget_min=10.0,
        budget_max=50.0,
    )
    assert result[0]["name"] == "Bold Red"


def test_avoid_list_excludes_wines():
    sweet = _wine("Sweet Riesling", wine_type="white", varietal="Riesling",
                  tasting_notes="sweet honey peach")
    dry = _wine("Dry Chardonnay", wine_type="white", varietal="Chardonnay",
                tasting_notes="crisp citrus oak")
    result = score_candidates(
        candidates=[sweet, dry],
        wine_type=None,
        style_preferences=[],
        avoid=["sweet"],
        budget_min=10.0,
        budget_max=50.0,
    )
    names = [w["name"] for w in result]
    assert "Sweet Riesling" not in names
    assert "Dry Chardonnay" in names


def test_price_proximity_scores_midrange_higher():
    cheap = _wine("Budget Red", price=10.0)
    mid = _wine("Mid Red", price=25.0)
    result = score_candidates(
        candidates=[cheap, mid],
        wine_type=None,
        style_preferences=[],
        avoid=[],
        budget_min=20.0,
        budget_max=30.0,
    )
    assert result[0]["name"] == "Mid Red"
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_scorer.py -v
```

Expected: 3 failures — `ModuleNotFoundError: No module named 'recommendation.scorer'`

- [ ] **Step 4: Implement scorer.py**

Create `backend/recommendation/scorer.py`:

```python
from typing import List, Dict, Any, Optional


def score_candidates(
    candidates: List[Dict[str, Any]],
    wine_type: Optional[str],
    style_preferences: List[str],
    avoid: List[str],
    budget_min: float,
    budget_max: float,
) -> List[Dict[str, Any]]:
    budget_mid = (budget_min + budget_max) / 2.0
    avoid_lower = [a.lower() for a in avoid]
    pref_lower = [p.lower() for p in style_preferences]
    scored = []

    for wine in candidates:
        searchable = " ".join(filter(None, [
            wine.get("varietal") or "",
            wine.get("wine_type") or "",
            wine.get("region") or "",
            wine.get("country") or "",
            wine.get("tasting_notes") or "",
            " ".join(wine.get("flavor_profile") or []),
        ])).lower()

        if any(a in searchable for a in avoid_lower):
            continue

        score = 0.0

        if wine_type and wine.get("wine_type") == wine_type:
            score += 3.0

        for pref in pref_lower:
            if pref in searchable:
                score += 1.0

        price = float(wine.get("price") or 0.0)
        if budget_max > budget_min:
            distance = abs(price - budget_mid) / (budget_max - budget_min)
            score += max(0.0, 1.0 - distance)

        scored.append({**wine, "_score": score})

    scored.sort(key=lambda w: w["_score"], reverse=True)
    return scored
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_scorer.py -v
```

Expected:
```
test_scorer.py::test_wine_type_match_scores_higher PASSED
test_scorer.py::test_avoid_list_excludes_wines PASSED
test_scorer.py::test_price_proximity_scores_midrange_higher PASSED
3 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/recommendation/__init__.py backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat: rule-based wine candidate scorer with TDD"
```

---

### Task 2: Claude Client

**Files:**
- Create: `backend/recommendation/claude_client.py`

No dedicated test file — covered by router integration tests in Task 4.

- [ ] **Step 1: Implement claude_client.py**

Create `backend/recommendation/claude_client.py`:

```python
import anthropic
from typing import List, Dict, Any, Optional, Tuple
from config import settings


_TOOL = {
    "name": "recommend_wines",
    "description": "Return wine recommendations with narrative and structured picks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {"type": "string"},
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "wine_id":  {"type": "string"},
                        "name":     {"type": "string"},
                        "price":    {"type": "number"},
                        "retailer": {"type": "string"},
                        "why":      {"type": "string"},
                    },
                    "required": ["wine_id", "name", "price", "retailer", "why"],
                },
            },
        },
        "required": ["narrative", "picks"],
    },
}


def _format_wine(wine: Dict[str, Any]) -> str:
    location = ", ".join(filter(None, [
        wine.get("varietal") or "",
        wine.get("region") or "",
        wine.get("country") or "",
    ]))
    price = float(wine.get("price") or 0.0)
    line = f"{wine.get('name', 'Unknown')} — {location} — ${price:.2f}"

    notes = wine.get("tasting_notes") or ""
    structure = wine.get("structure_profile") or {}
    struct_parts = [
        f"{k} {v}" for k, v in structure.items()
        if k in ("body", "tannins", "acidity", "sweetness") and v is not None
    ]

    if notes:
        line += f"\n   Tasting notes: {notes}"
    if struct_parts:
        line += f". Structure: {', '.join(struct_parts)}."
    return line


def get_recommendations(
    candidates: List[Dict[str, Any]],
    budget_min: float,
    budget_max: float,
    style_preferences: List[str],
    avoid: List[str],
    wine_type: Optional[str],
) -> Tuple[str, List[Dict[str, Any]]]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    listings = "\n\n".join(f"{i + 1}. {_format_wine(w)}" for i, w in enumerate(candidates))
    count_instruction = "3–5" if len(candidates) >= 3 else "as many as you can"
    style_str = ", ".join(style_preferences) if style_preferences else "no specific style"
    avoid_str = ", ".join(avoid) if avoid else "nothing"
    type_str = f" {wine_type}" if wine_type else ""

    user_msg = (
        f"Budget: ${budget_min:.0f}–${budget_max:.0f}. "
        f"Looking for:{type_str} {style_str}. "
        f"Avoiding: {avoid_str}.\n\n"
        f"Here are the wines currently available:\n\n{listings}\n\n"
        f"Recommend {count_instruction} wines that best match my preferences. "
        f"When explaining each pick, reference the wine's region and what makes "
        f"it characteristic of that area."
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=(
            "You are a knowledgeable sommelier helping someone find wines available "
            "at local shops near them. Be warm, specific, and practical. Reference "
            "the wine's actual characteristics when explaining your picks."
        ),
        messages=[{"role": "user", "content": user_msg}],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "recommend_wines"},
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ValueError("Claude did not return a tool use block")

    result = tool_block.input
    return result["narrative"], result["picks"]
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && python3 -c "from recommendation.claude_client import get_recommendations; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/recommendation/claude_client.py
git commit -m "feat: Claude Haiku tool-use client for wine recommendations"
```

---

### Task 3: Update Schemas

**Files:**
- Modify: `backend/api/schemas.py`

- [ ] **Step 1: Add WinePick and update RecommendResponse**

Edit `backend/api/schemas.py`. Replace the existing `RecommendResponse` and add `WinePick` so the file reads:

```python
from typing import Optional, List
from pydantic import BaseModel


class WineSearchResult(BaseModel):
    id: str
    name: str
    brand: Optional[str] = None
    varietal: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    avg_price: Optional[float] = None
    wine_type: Optional[str] = None


class RecommendRequest(BaseModel):
    zip_code: str
    budget_min: float = 10.0
    budget_max: float = 50.0
    style_preferences: List[str] = []
    avoid: List[str] = []
    wine_type: Optional[str] = None
    message: str = "Recommend wines based on my preferences"


class WinePick(BaseModel):
    wine_id: str
    name: str
    price: float
    retailer: str
    why: str


class RecommendResponse(BaseModel):
    narrative: str
    picks: List[WinePick]
    session_id: str
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && python3 -c "from api.schemas import WinePick, RecommendResponse; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/api/schemas.py
git commit -m "feat: add WinePick schema, update RecommendResponse with narrative + picks"
```

---

### Task 4: Recommend Router — TDD

**Files:**
- Create: `backend/tests/test_recommend_api.py`
- Create: `backend/api/routers/recommend.py`

- [ ] **Step 1: Write the four failing router tests**

Create `backend/tests/test_recommend_api.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app


WINE_ROW = {
    "price": 22.0,
    "retailer_name": "Geraldine's",
    "wine_id": "abc-123",
    "wines": {
        "id": "abc-123",
        "name": "Test Malbec",
        "varietal": "Malbec",
        "region": "Mendoza",
        "country": "Argentina",
        "wine_type": "red",
        "wine_details": [{
            "tasting_notes": "dark fruit, plum, chocolate",
            "flavor_profile": ["dark fruit", "plum"],
            "structure_profile": {"body": 8, "tannins": 7, "acidity": 5},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        }],
    },
}

PICKS = [{
    "wine_id": "abc-123",
    "name": "Test Malbec",
    "price": 22.0,
    "retailer": "Geraldine's",
    "why": "A classic Mendoza Malbec from Argentina with bold dark fruit.",
}]


def _make_db_mock(data):
    qb = MagicMock()
    qb.table.return_value = qb
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.gte.return_value = qb
    qb.lte.return_value = qb
    qb.insert.return_value = qb
    execute_result = MagicMock()
    execute_result.data = data
    qb.execute.return_value = execute_result
    return qb


def _make_anthropic_mock(narrative="Here are my top picks.", picks=None):
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.input = {"narrative": narrative, "picks": picks or PICKS}
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_cls = MagicMock()
    mock_cls.return_value.messages.create.return_value = mock_response
    return mock_cls


@pytest.mark.asyncio
async def test_recommend_returns_200():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
                "style_preferences": ["bold", "earthy"],
                "avoid": [],
            })
    assert response.status_code == 200
    body = response.json()
    assert "narrative" in body
    assert "picks" in body
    assert "session_id" in body


@pytest.mark.asyncio
async def test_recommend_no_enriched_wines_returns_400():
    with patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "No enriched wines" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recommend_missing_zip_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/recommend", json={
            "budget_min": 15.0,
            "budget_max": 35.0,
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recommend_picks_have_required_fields():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 200
    for pick in response.json()["picks"]:
        assert all(k in pick for k in ["wine_id", "name", "price", "retailer", "why"])
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_recommend_api.py -v
```

Expected: failures — `ImportError` or `404` because the router doesn't exist yet.

- [ ] **Step 3: Implement the recommend router**

Create `backend/api/routers/recommend.py`:

```python
import uuid
from fastapi import APIRouter, HTTPException
from api.schemas import RecommendRequest, RecommendResponse, WinePick
from db import get_supabase_client, get_service_client
from recommendation.scorer import score_candidates
from recommendation.claude_client import get_recommendations

router = APIRouter(prefix="/api", tags=["recommend"])

_MAX_CANDIDATES = 12


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    supabase = get_supabase_client()

    result = (
        supabase.table("retail_inventory")
        .select(
            "price, retailer_name, wine_id,"
            "wines(id, name, varietal, region, country, wine_type,"
            "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
        )
        .eq("zip_code", req.zip_code)
        .eq("in_stock", True)
        .gte("price", req.budget_min)
        .lte("price", req.budget_max)
        .execute()
    )

    candidates = []
    for row in (result.data or []):
        wine = row.get("wines") or {}
        if not wine:
            continue
        details_list = wine.get("wine_details") or []
        details = details_list[0] if isinstance(details_list, list) and details_list else {}
        if not details.get("grapeminds_enriched_at"):
            continue
        candidates.append({
            "wine_id": wine.get("id"),
            "name": wine.get("name"),
            "varietal": wine.get("varietal"),
            "region": wine.get("region"),
            "country": wine.get("country"),
            "wine_type": wine.get("wine_type"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"),
            "retailer": row.get("retailer_name"),
        })

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No enriched wines found matching your criteria. Try widening your budget or style preferences.",
        )

    top = score_candidates(
        candidates=candidates,
        wine_type=req.wine_type,
        style_preferences=req.style_preferences,
        avoid=req.avoid,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
    )[:_MAX_CANDIDATES]

    try:
        narrative, picks_data = get_recommendations(
            candidates=top,
            budget_min=req.budget_min,
            budget_max=req.budget_max,
            style_preferences=req.style_preferences,
            avoid=req.avoid,
            wine_type=req.wine_type,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")

    session_id = str(uuid.uuid4())
    try:
        service = get_service_client()
        service.table("recommendation_sessions").insert({
            "id": session_id,
            "conversation_history": [
                {"role": "user", "content": req.message},
                {"role": "assistant", "content": {"narrative": narrative, "picks": picks_data}},
            ],
            "recommendations": picks_data,
            "preference_snapshot": req.model_dump(),
        }).execute()
    except Exception:
        pass

    return RecommendResponse(
        narrative=narrative,
        picks=[WinePick(**p) for p in picks_data],
        session_id=session_id,
    )
```

- [ ] **Step 4: Register the router in main.py**

Edit `backend/api/main.py`:

```python
from fastapi import FastAPI
from api.routers import wines, enrichment, recommend

app = FastAPI(
    title="Terroir API",
    description="Wine recommendation backend",
    version="0.1.0",
)

app.include_router(wines.router)
app.include_router(enrichment.router)
app.include_router(recommend.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "terroir-api"}
```

- [ ] **Step 5: Run the new tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_recommend_api.py -v
```

Expected:
```
test_recommend_api.py::test_recommend_returns_200 PASSED
test_recommend_api.py::test_recommend_no_enriched_wines_returns_400 PASSED
test_recommend_api.py::test_recommend_missing_zip_returns_422 PASSED
test_recommend_api.py::test_recommend_picks_have_required_fields PASSED
4 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py backend/api/main.py backend/tests/test_recommend_api.py
git commit -m "feat: POST /api/recommend endpoint with Haiku tool-use and session persistence"
```

---

### Task 5: Full Suite Verification

**Files:** No new files.

- [ ] **Step 1: Run the complete test suite**

```bash
cd backend && python3 -m pytest tests/ -v
```

Expected: **33 tests passing** (26 existing + 3 scorer + 4 recommend API)

```
tests/test_geraldines.py::... (10 tests) PASSED
tests/test_grapeminds.py::... (3 tests) PASSED  
tests/test_pipeline.py::... (6 tests) PASSED
tests/test_wines_api.py::... (3 tests) PASSED
tests/test_scorer.py::... (3 tests) PASSED
tests/test_recommend_api.py::... (4 tests) PASSED
33 passed
```

If any pre-existing tests fail, investigate before proceeding — do not skip or delete them.

- [ ] **Step 2: Commit if not already clean**

```bash
git status
```

If there are uncommitted changes:

```bash
git add -p  # stage only relevant files
git commit -m "chore: verify full test suite passes after recommend endpoint"
```
