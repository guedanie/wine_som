# Recommendation Engine v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `/api/recommend` to use a tiered candidate pool (GrapeMinds + extractor-only), knowledge-based deterministic scoring (grape/region → flavor inference), and optional natural-language intent parsing merged with explicit fields.

**Architecture:** New `flavor_profiles.py` (curated grape/region → flavor tags) feeds a rewritten `scorer.py` that scores on structured fields. New `intent.py` parses an optional NL `message` into a structured intent and merges it with explicit request fields (explicit wins). The router drops the GrapeMinds hard-filter, tags candidates by tier, and threads the resolved intent through scoring and the final Claude call.

**Tech Stack:** Python 3.9 (`Optional[X]`, not `X | None`), FastAPI, Anthropic SDK (Haiku), pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-22-recommendation-engine-v2-design.md`

---

## Canonical resolved-intent shape (used across all tasks)

```python
intent = {
    "wine_type": Optional[str],   # red|white|rose|sparkling|orange|dessert|None
    "body":      Optional[str],   # light|medium|full|None
    "flavors":   List[str],       # controlled vocab tags
    "grapes":    List[str],       # grape names
    "region":    Optional[str],   # e.g. "Rhône" (NL only)
    "avoid":     List[str],       # terms to exclude
    "budget_min": float,
    "budget_max": float,
}
```

**Controlled flavor vocabulary** (shared by `flavor_profiles` and `intent`):
`earthy, bold, savory, light, peppery, structured, herbal, red-fruit, black-fruit, dark-fruit, tart-cherry, spice, gamey, garrigue, ripe`

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/recommendation/flavor_profiles.py` | `GRAPE_FLAVORS`/`REGION_FLAVORS` + `flavor_tags_for` + `infer_body` |
| Create | `backend/tests/test_flavor_profiles.py` | tests for the lookup |
| Rewrite | `backend/recommendation/scorer.py` | `score_candidates(intent, candidates)` |
| Modify | `backend/tests/test_scorer.py` | port existing tests to new signature + new cases |
| Create | `backend/recommendation/intent.py` | `parse_message` + `merge_intent` + `intent_from_request` |
| Create | `backend/tests/test_intent.py` | tests for parse/merge |
| Modify | `backend/recommendation/claude_client.py` | accept resolved intent |
| Modify | `backend/api/routers/recommend.py` | tiered pool, intent wiring |
| Modify | `backend/tests/test_recommend_api.py` | tiered pool + NL merge + fail-soft |

---

## Task 1: `flavor_profiles.py` (TDD)

**Files:**
- Create: `backend/recommendation/flavor_profiles.py`
- Create: `backend/tests/test_flavor_profiles.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_flavor_profiles.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.flavor_profiles import flavor_tags_for, infer_body


def test_gsm_blend_is_earthy_and_savory():
    tags = flavor_tags_for(
        varietal="Grenache",
        grapes=["Grenache", "Syrah", "Mourvèdre"],
        region="Rhône",
    )
    assert "earthy" in tags
    assert "savory" in tags


def test_cabernet_is_bold():
    tags = flavor_tags_for(varietal="Cabernet Sauvignon", grapes=["Cabernet Sauvignon"], region="Napa Valley")
    assert "bold" in tags


def test_region_contributes_tags_even_without_grape_match():
    tags = flavor_tags_for(varietal=None, grapes=[], region="Tuscany")
    assert "earthy" in tags


def test_accent_insensitive_grape_lookup():
    # "Mourvedre" without accent should still match "Mourvèdre"
    tags = flavor_tags_for(varietal="Mourvedre", grapes=["Mourvedre"], region=None)
    assert "earthy" in tags


def test_unknown_grape_and_region_returns_empty():
    assert flavor_tags_for(varietal="Nonexistent", grapes=["Nonexistent"], region="Nowhere") == set()


def test_infer_body_full_from_bold_tags():
    assert infer_body({"bold", "structured"}) == "full"


def test_infer_body_light_from_light_tag():
    assert infer_body({"light", "red-fruit"}) == "light"


def test_infer_body_none_when_ambiguous():
    assert infer_body({"savory", "spice"}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_flavor_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recommendation.flavor_profiles'`

- [ ] **Step 3: Implement `flavor_profiles.py`**

Create `backend/recommendation/flavor_profiles.py`:

```python
"""
Curated grape/region -> flavor-tag knowledge for the recommendation scorer.
Lets the deterministic scorer infer flavor as a fact about the wine (e.g. a
Grenache/Syrah/Mourvèdre Rhône blend is 'earthy/savory') without embeddings.

Follows the cheat-sheet pattern of enrichment/extraction/reference.py.
Flavor tags are a small controlled vocabulary shared with recommendation.intent.
"""
import re
import unicodedata
from typing import Optional, List, Set

# Controlled flavor vocabulary (keep in sync with recommendation.intent prompt).
FLAVOR_VOCAB = {
    "earthy", "bold", "savory", "light", "peppery", "structured", "herbal",
    "red-fruit", "black-fruit", "dark-fruit", "tart-cherry", "spice", "gamey",
    "garrigue", "ripe",
}

GRAPE_FLAVORS = {
    "Cabernet Sauvignon": {"bold", "structured", "black-fruit"},
    "Merlot": {"red-fruit", "ripe", "herbal"},
    "Pinot Noir": {"light", "red-fruit", "earthy"},
    "Syrah": {"peppery", "savory", "dark-fruit"},
    "Shiraz": {"bold", "ripe", "dark-fruit", "spice"},
    "Malbec": {"bold", "dark-fruit", "ripe"},
    "Grenache": {"earthy", "red-fruit", "spice"},
    "Garnacha": {"earthy", "red-fruit", "spice"},
    "Tempranillo": {"savory", "red-fruit", "earthy"},
    "Sangiovese": {"earthy", "savory", "tart-cherry", "herbal"},
    "Nebbiolo": {"structured", "earthy", "tart-cherry"},
    "Zinfandel": {"bold", "ripe", "spice"},
    "Primitivo": {"bold", "ripe", "spice"},
    "Cabernet Franc": {"herbal", "red-fruit", "earthy"},
    "Petite Sirah": {"bold", "structured", "dark-fruit"},
    "Mourvèdre": {"earthy", "savory", "gamey"},
    "Monastrell": {"earthy", "savory", "gamey"},
    "Carmenère": {"herbal", "dark-fruit", "peppery"},
    "Gamay": {"light", "red-fruit"},
    "Barbera": {"savory", "tart-cherry", "red-fruit"},
    "Montepulciano": {"savory", "dark-fruit", "earthy"},
    "Tannat": {"bold", "structured", "dark-fruit"},
    "Touriga Nacional": {"bold", "dark-fruit", "structured"},
    "Chardonnay": {"ripe", "structured"},
    "Sauvignon Blanc": {"herbal", "light"},
    "Riesling": {"light", "spice"},
    "Pinot Grigio": {"light"},
    "Pinot Gris": {"light"},
    "Chenin Blanc": {"light", "ripe"},
    "Viognier": {"ripe", "spice"},
    "Albariño": {"light", "savory"},
    "Grüner Veltliner": {"herbal", "spice", "savory"},
}

REGION_FLAVORS = {
    "Rhône": {"earthy", "garrigue", "savory", "peppery"},
    "Burgundy": {"earthy", "red-fruit"},
    "Bordeaux": {"structured", "black-fruit", "herbal"},
    "Beaujolais": {"light", "red-fruit"},
    "Tuscany": {"earthy", "savory", "tart-cherry"},
    "Piedmont": {"structured", "earthy", "tart-cherry"},
    "Rioja": {"savory", "red-fruit", "earthy"},
    "Napa Valley": {"bold", "ripe", "black-fruit"},
    "Sonoma": {"ripe", "red-fruit"},
    "Central Coast": {"ripe", "red-fruit"},
    "Willamette Valley": {"light", "earthy", "red-fruit"},
    "Mendoza": {"bold", "dark-fruit", "ripe"},
    "Barossa Valley": {"bold", "ripe", "spice"},
    "Texas": {"bold", "ripe"},
}


def _norm(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    return re.sub(r"\s+", " ", s).strip().lower()


_GRAPE_INDEX = {_norm(k): v for k, v in GRAPE_FLAVORS.items()}
_REGION_INDEX = {_norm(k): v for k, v in REGION_FLAVORS.items()}


def flavor_tags_for(varietal: Optional[str], grapes: Optional[List[str]],
                    region: Optional[str]) -> Set[str]:
    """Union of flavor tags implied by a wine's grape(s) + region. Empty if unknown."""
    tags: Set[str] = set()
    names = list(grapes or [])
    if varietal:
        names.append(varietal)
    for name in names:
        tags |= _GRAPE_INDEX.get(_norm(name), set())
    if region:
        tags |= _REGION_INDEX.get(_norm(region), set())
    return tags


def infer_body(tags: Set[str]) -> Optional[str]:
    """Infer a body bucket from flavor tags when a wine's body column is null."""
    if "light" in tags:
        return "light"
    if "bold" in tags or "structured" in tags:
        return "full"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_flavor_profiles.py -v`
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/flavor_profiles.py backend/tests/test_flavor_profiles.py
git commit -m "feat: grape/region flavor knowledge lookup for scorer (TDD)"
```

---

## Task 2: `scorer.py` rewrite (TDD)

**Files:**
- Rewrite: `backend/recommendation/scorer.py`
- Modify: `backend/tests/test_scorer.py`

The signature changes from `score_candidates(candidates, wine_type, style_preferences, avoid, budget_min, budget_max)` to `score_candidates(intent, candidates)` where `intent` is the canonical resolved-intent dict.

- [ ] **Step 1: Replace `backend/tests/test_scorer.py` with the new-signature tests**

Overwrite `backend/tests/test_scorer.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.scorer import score_candidates


def _intent(wine_type=None, body=None, flavors=None, grapes=None, region=None,
            avoid=None, budget_min=10.0, budget_max=50.0):
    return {
        "wine_type": wine_type,
        "body": body,
        "flavors": flavors or [],
        "grapes": grapes or [],
        "region": region,
        "avoid": avoid or [],
        "budget_min": budget_min,
        "budget_max": budget_max,
    }


def _wine(name, wine_type="red", varietal="Malbec", grapes=None, region="Mendoza",
          country="Argentina", body=None, tasting_notes="dark fruit",
          flavor_profile=None, price=25.0, tier=2):
    return {
        "wine_id": "test-id",
        "name": name,
        "wine_type": wine_type,
        "varietal": varietal,
        "grapes": grapes or [],
        "region": region,
        "country": country,
        "body": body,
        "tasting_notes": tasting_notes,
        "flavor_profile": flavor_profile or [],
        "structure_profile": {},
        "price": price,
        "retailer": "Geraldine's",
        "tier": tier,
    }


def test_wine_type_match_scores_higher():
    red = _wine("Bold Red", wine_type="red")
    white = _wine("Crisp White", wine_type="white", varietal="Chardonnay")
    result = score_candidates(_intent(wine_type="red"), [white, red])
    assert result[0]["name"] == "Bold Red"


def test_avoid_list_excludes_wines():
    sweet = _wine("Sweet Riesling", wine_type="white", varietal="Riesling",
                  tasting_notes="sweet honey peach")
    dry = _wine("Dry Chardonnay", wine_type="white", varietal="Chardonnay",
                tasting_notes="crisp citrus oak")
    result = score_candidates(_intent(avoid=["sweet"]), [sweet, dry])
    names = [w["name"] for w in result]
    assert "Sweet Riesling" not in names
    assert "Dry Chardonnay" in names


def test_price_proximity_scores_midrange_higher():
    cheap = _wine("Budget Red", price=10.0)
    mid = _wine("Mid Red", price=25.0)
    result = score_candidates(_intent(budget_min=20.0, budget_max=30.0), [cheap, mid])
    assert result[0]["name"] == "Mid Red"


def test_earthy_intent_ranks_gsm_over_fruit_bomb_via_grape_inference():
    # Neither wine's notes literally say "earthy"; the GSM wins on grape/region knowledge.
    gsm = _wine("Rhône GSM", varietal="Grenache",
                grapes=["Grenache", "Syrah", "Mourvèdre"], region="Rhône",
                tasting_notes="Mediterranean assemblage, blended for immediacy")
    jammy = _wine("Jammy Zin", varietal="Zinfandel", grapes=["Zinfandel"],
                  region="Napa Valley", tasting_notes="luscious smooth jam")
    result = score_candidates(_intent(wine_type="red", flavors=["earthy"]), [jammy, gsm])
    assert result[0]["name"] == "Rhône GSM"


def test_body_inferred_when_null():
    # full-body intent; wine body is null but grape implies 'full' (bold/structured)
    cab = _wine("Cab No Body", varietal="Cabernet Sauvignon",
                grapes=["Cabernet Sauvignon"], region="Napa Valley", body=None)
    light = _wine("Light Gamay", varietal="Gamay", grapes=["Gamay"],
                  region="Beaujolais", body=None)
    result = score_candidates(_intent(wine_type="red", body="full"), [light, cab])
    assert result[0]["name"] == "Cab No Body"


def test_tier1_outranks_equal_tier2():
    t1 = _wine("GrapeMinds Wine", tier=1)
    t2 = _wine("Extractor Wine", tier=2)
    result = score_candidates(_intent(), [t2, t1])
    assert result[0]["name"] == "GrapeMinds Wine"


def test_grape_match_scores():
    match = _wine("Malbec Match", varietal="Malbec", grapes=["Malbec"])
    other = _wine("Pinot", varietal="Pinot Noir", grapes=["Pinot Noir"], region="Burgundy")
    result = score_candidates(_intent(grapes=["Malbec"]), [other, match])
    assert result[0]["name"] == "Malbec Match"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_scorer.py -v`
Expected: FAIL — `score_candidates()` is called with the new `(intent, candidates)` signature the current implementation does not accept (TypeError / wrong ordering).

- [ ] **Step 3: Rewrite `backend/recommendation/scorer.py`**

Replace the entire file with:

```python
from typing import List, Dict, Any
from recommendation.flavor_profiles import flavor_tags_for, infer_body

# Axis weights
_W_TYPE = 3.0
_W_BODY = 2.0
_W_GRAPE = 2.0
_W_REGION = 1.5
_W_FLAVOR_TAG = 1.0      # per matched flavor tag, capped
_FLAVOR_CAP = 3.0
_W_BUDGET = 1.0
_W_TIER = 0.5


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def score_candidates(intent: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Knowledge-based deterministic scoring. `intent` is the resolved-intent dict."""
    budget_min = float(intent.get("budget_min", 10.0))
    budget_max = float(intent.get("budget_max", 50.0))
    budget_mid = (budget_min + budget_max) / 2.0
    want_type = intent.get("wine_type")
    want_body = intent.get("body")
    want_region = _norm(intent.get("region")) if intent.get("region") else None
    want_grapes = {_norm(g) for g in (intent.get("grapes") or [])}
    want_flavors = {_norm(f) for f in (intent.get("flavors") or [])}
    avoid = [_norm(a) for a in (intent.get("avoid") or [])]

    scored = []
    for wine in candidates:
        tags = flavor_tags_for(wine.get("varietal"), wine.get("grapes"), wine.get("region"))
        notes = _norm(wine.get("tasting_notes")) + " " + " ".join(
            _norm(x) for x in (wine.get("flavor_profile") or []))
        grapes = {_norm(g) for g in (wine.get("grapes") or [])}
        region = _norm(wine.get("region"))

        # avoid exclusion: search grapes, region, flavor tags, and notes
        haystack = " ".join([notes, region, " ".join(grapes), " ".join(tags)])
        if any(a and a in haystack for a in avoid):
            continue

        score = 0.0

        if want_type and wine.get("wine_type") == want_type:
            score += _W_TYPE

        if want_body:
            body = wine.get("body") or infer_body(tags)
            if body == want_body:
                score += _W_BODY

        if want_grapes and (want_grapes & grapes):
            score += _W_GRAPE

        if want_region and want_region == region:
            score += _W_REGION

        if want_flavors:
            tag_hits = len(want_flavors & tags)
            kw_hits = sum(1 for f in want_flavors if f in notes)
            score += min(_FLAVOR_CAP, _W_FLAVOR_TAG * (tag_hits + kw_hits))

        price = float(wine.get("price") or 0.0)
        if budget_max > budget_min:
            distance = abs(price - budget_mid) / (budget_max - budget_min)
            score += _W_BUDGET * max(0.0, 1.0 - distance)

        if wine.get("tier") == 1:
            score += _W_TIER

        scored.append({**wine, "_score": score})

    scored.sort(key=lambda w: w["_score"], reverse=True)
    return scored
```

- [ ] **Step 4: Run the scorer tests**

Run: `cd backend && python3 -m pytest tests/test_scorer.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat: knowledge-based deterministic scorer (TDD)"
```

---

## Task 3: `intent.py` (TDD)

**Files:**
- Create: `backend/recommendation/intent.py`
- Create: `backend/tests/test_intent.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_intent.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch, MagicMock
from recommendation.intent import merge_intent, intent_from_request, parse_message


def test_intent_from_request_maps_explicit_fields():
    intent = intent_from_request(
        wine_type="red", style_preferences=["bold", "earthy"], avoid=["sweet"],
        budget_min=15.0, budget_max=35.0)
    assert intent["wine_type"] == "red"
    assert intent["flavors"] == ["bold", "earthy"]
    assert intent["avoid"] == ["sweet"]
    assert intent["budget_min"] == 15.0
    assert intent["region"] is None
    assert intent["grapes"] == []


def test_merge_intent_explicit_wine_type_wins():
    parsed = {"wine_type": "white", "body": "light", "flavors": ["crisp"],
              "grapes": ["Chardonnay"], "region": "Burgundy", "max_price": 20.0,
              "avoid": []}
    explicit = intent_from_request(wine_type="red", style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    merged = merge_intent(parsed, explicit)
    assert merged["wine_type"] == "red"           # explicit wins
    assert merged["body"] == "light"              # filled from parsed
    assert merged["grapes"] == ["Chardonnay"]     # filled from parsed
    assert merged["region"] == "Burgundy"         # filled from parsed
    assert merged["budget_max"] == 50.0           # explicit budget always wins


def test_merge_intent_unions_flavors_and_avoid():
    parsed = {"wine_type": None, "body": None, "flavors": ["earthy"], "grapes": [],
              "region": None, "max_price": None, "avoid": ["oaky"]}
    explicit = intent_from_request(wine_type=None, style_preferences=["bold"],
                                   avoid=["sweet"], budget_min=10.0, budget_max=50.0)
    merged = merge_intent(parsed, explicit)
    assert set(merged["flavors"]) == {"earthy", "bold"}
    assert set(merged["avoid"]) == {"oaky", "sweet"}


def test_parse_message_returns_structured_intent():
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"wine_type": "red", "body": "full", "flavors": ["earthy", "bold"],
                   "grapes": ["Syrah"], "region": "Rhône", "max_price": 25.0, "avoid": []}
    resp = MagicMock()
    resp.content = [block]
    mock_cls = MagicMock()
    mock_cls.return_value.messages.create.return_value = resp
    with patch("recommendation.intent.anthropic.Anthropic", mock_cls):
        out = parse_message("a bold earthy red for steak around $25")
    assert out["wine_type"] == "red"
    assert out["body"] == "full"
    assert "earthy" in out["flavors"]
    assert out["region"] == "Rhône"


def test_parse_message_fails_soft_on_no_tool_block():
    resp = MagicMock()
    resp.content = []   # no tool_use block
    mock_cls = MagicMock()
    mock_cls.return_value.messages.create.return_value = resp
    with patch("recommendation.intent.anthropic.Anthropic", mock_cls):
        out = parse_message("gibberish")
    assert out is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_intent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recommendation.intent'`

- [ ] **Step 3: Implement `backend/recommendation/intent.py`**

Create `backend/recommendation/intent.py`:

```python
"""
Natural-language intent parsing for the recommender, plus merge with explicit
request fields. Explicit fields win on conflict; lists are unioned.
"""
import anthropic
from typing import Optional, List, Dict, Any
from config import settings

MODEL = "claude-haiku-4-5-20251001"

# Keep `flavors` aligned with recommendation.flavor_profiles.FLAVOR_VOCAB.
_FLAVOR_VOCAB = (
    "earthy, bold, savory, light, peppery, structured, herbal, red-fruit, "
    "black-fruit, dark-fruit, tart-cherry, spice, gamey, garrigue, ripe"
)

_TOOL = {
    "name": "wine_intent",
    "description": "Structured wine preferences parsed from a free-text request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "wine_type": {"type": ["string", "null"],
                          "enum": ["red", "white", "rose", "sparkling", "orange", "dessert", None]},
            "body": {"type": ["string", "null"], "enum": ["light", "medium", "full", None]},
            "flavors": {"type": "array", "items": {"type": "string"}},
            "grapes": {"type": "array", "items": {"type": "string"}},
            "region": {"type": ["string", "null"]},
            "max_price": {"type": ["number", "null"]},
            "avoid": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["flavors", "grapes", "avoid"],
    },
}


def parse_message(message: str) -> Optional[Dict[str, Any]]:
    """Parse a free-text request into structured intent. Returns None on failure."""
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=(
                "Extract structured wine preferences from the user's request. "
                f"`flavors` MUST be drawn only from this vocabulary: {_FLAVOR_VOCAB}. "
                "Use null/empty when a field is not implied. Do not invent grapes or regions."
            ),
            messages=[{"role": "user", "content": message}],
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "wine_intent"},
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block is None:
            return None
        return dict(block.input)
    except Exception as e:
        print(f"  intent parse failed: {e}")
        return None


def intent_from_request(wine_type: Optional[str], style_preferences: List[str],
                        avoid: List[str], budget_min: float, budget_max: float) -> Dict[str, Any]:
    """Build a resolved-intent dict from explicit request fields only."""
    return {
        "wine_type": wine_type,
        "body": None,
        "flavors": list(style_preferences or []),
        "grapes": [],
        "region": None,
        "avoid": list(avoid or []),
        "budget_min": budget_min,
        "budget_max": budget_max,
    }


def merge_intent(parsed: Optional[Dict[str, Any]], explicit: Dict[str, Any]) -> Dict[str, Any]:
    """Merge parsed NL intent into the explicit-field intent. Explicit wins on scalar
    conflicts; flavors/avoid are unioned; budget always from explicit."""
    if not parsed:
        return explicit
    out = dict(explicit)
    # scalar fields: explicit wins if set, else take parsed
    if not out.get("wine_type"):
        out["wine_type"] = parsed.get("wine_type")
    out["body"] = out.get("body") or parsed.get("body")
    out["region"] = out.get("region") or parsed.get("region")
    if not out.get("grapes"):
        out["grapes"] = list(parsed.get("grapes") or [])
    # list unions
    out["flavors"] = list({*(out.get("flavors") or []), *(parsed.get("flavors") or [])})
    out["avoid"] = list({*(out.get("avoid") or []), *(parsed.get("avoid") or [])})
    # budget always explicit (already in `out`)
    return out
```

- [ ] **Step 4: Run the intent tests**

Run: `cd backend && python3 -m pytest tests/test_intent.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/intent.py backend/tests/test_intent.py
git commit -m "feat: NL intent parsing + merge with explicit fields (TDD)"
```

---

## Task 4: Router tiered pool + intent wiring + claude_client (TDD)

**Files:**
- Modify: `backend/recommendation/claude_client.py`
- Modify: `backend/api/routers/recommend.py`
- Modify: `backend/tests/test_recommend_api.py`

- [ ] **Step 1: Update `get_recommendations` signature in `claude_client.py`**

In `backend/recommendation/claude_client.py`, change `get_recommendations` to accept a resolved `intent` dict instead of the separate `style_preferences`, `avoid`, `wine_type` params. Replace the function signature and the lines that build `style_str`, `avoid_str`, `type_str`:

```python
def get_recommendations(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]]]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    listings = "\n\n".join(f"{i + 1}. {_format_wine(w)}" for i, w in enumerate(candidates))
    count_instruction = "3–5" if len(candidates) >= 3 else "as many as you can"
    style_str = ", ".join(intent.get("flavors") or []) or "no specific style"
    avoid_str = ", ".join(intent.get("avoid") or []) or "nothing"
    type_str = f" {intent['wine_type']}" if intent.get("wine_type") else ""
    budget_min = intent.get("budget_min", 10.0)
    budget_max = intent.get("budget_max", 50.0)

    user_msg = (
        f"Budget: ${budget_min:.0f}–${budget_max:.0f}. "
        f"Looking for:{type_str} {style_str}. "
        f"Avoiding: {avoid_str}.\n\n"
        f"Here are the wines currently available:\n\n{listings}\n\n"
        f"Recommend {count_instruction} wines that best match my preferences. "
        f"When explaining each pick, reference the wine's region and what makes "
        f"it characteristic of that area."
    )
    # ... (rest of the function body — the client.messages.create call and tool
    #      block extraction — stays exactly as it currently is)
```

Leave the `client.messages.create(...)` call, the system prompt, the `_TOOL`, and the tool-block extraction unchanged.

- [ ] **Step 2: Write the failing/updated API tests**

In `backend/tests/test_recommend_api.py`, the existing `WINE_ROW` and `_make_db_mock` represent the joined inventory row. Update the fixture so wine rows include the tier-relevant fields and add new tests. Make these changes:

1. Add `grapes`, `body` and (for tier-2 testing) a non-GrapeMinds variant to the wine fixture. Update `WINE_ROW`'s `wines` dict to include `"grapes": ["Malbec"], "body": "full"` and keep `wine_details` with `grapeminds_enriched_at` set (tier 1).

2. Add a tier-2 row builder and tests:

```python
def _wine_row(name="Test Malbec", wine_id="abc-123", enriched=True, varietal="Malbec",
              region="Mendoza", grapes=None, body="full", price=22.0):
    return {
        "price": price, "curbside_price": None, "wine_id": wine_id,
        "stores": {"retailer_name": "Spec's", "store_name": "Spec's", "zip_code": "78209"},
        "wines": {
            "id": wine_id, "name": name, "varietal": varietal, "region": region,
            "country": "Argentina", "wine_type": "red", "grapes": grapes or ["Malbec"],
            "body": body,
            "wine_details": [{
                "tasting_notes": "dark fruit, plum",
                "flavor_profile": ["dark fruit"],
                "structure_profile": {},
                "grapeminds_enriched_at": "2026-06-03T00:00:00Z" if enriched else None,
            }],
        },
    }


@pytest.mark.asyncio
async def test_recommend_includes_extractor_only_tier2_wine():
    """A wine with no GrapeMinds enrichment but with varietal/region is still a candidate."""
    row = _wine_row(enriched=False)   # tier 2
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([row])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommend_parses_nl_message_and_merges():
    captured = {}
    def fake_parse(msg):
        captured["msg"] = msg
        return {"wine_type": "white", "body": "light", "flavors": ["earthy"],
                "grapes": [], "region": None, "max_price": None, "avoid": []}
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.parse_message", side_effect=fake_parse), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "wine_type": "red", "message": "something earthy"})
    # explicit wine_type=red must win over parsed white -> still 200, parse was called
    assert response.status_code == 200
    assert captured["msg"] == "something earthy"


@pytest.mark.asyncio
async def test_recommend_fail_soft_when_parse_errors():
    with patch("recommendation.claude_client.anthropic.Anthropic", _make_anthropic_mock()), \
         patch("api.routers.recommend.parse_message", return_value=None), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "message": "anything"})
    assert response.status_code == 200
```

Keep the existing passing tests; update any that call the old fixture/flow so they still pass against the new router (they patch `find_nearby_store_ids` already). The existing `test_recommend_returns_200` etc. use `WINE_ROW` which is tier-1 (enriched) — they should keep working once the router no longer hard-requires GrapeMinds.

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `cd backend && python3 -m pytest tests/test_recommend_api.py -v`
Expected: the 3 new tests FAIL (router still gates on `grapeminds_enriched_at`, doesn't import `parse_message`, and `get_recommendations` signature mismatch).

- [ ] **Step 4: Update `backend/api/routers/recommend.py`**

Add imports near the top:

```python
from recommendation.intent import parse_message, merge_intent, intent_from_request
```

Replace the candidate-building block and the `get_recommendations` call. After computing `nearby_ids`, change the select to include the new fields and rebuild candidates with tiers:

```python
    result = (
        supabase.table("retail_inventory")
        .select(
            "price, curbside_price, wine_id,"
            "stores!inner(retailer_name, store_name, zip_code),"
            "wines(id, name, varietal, region, country, wine_type, grapes, abv, body,"
            "wine_details(tasting_notes, flavor_profile, structure_profile, grapeminds_enriched_at))"
        )
        .in_("store_ref", nearby_ids)
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
        enriched = bool(details.get("grapeminds_enriched_at"))
        has_extract = bool(wine.get("varietal") or wine.get("region"))
        if not enriched and not has_extract:
            continue  # no basis to match
        candidates.append({
            "wine_id": wine.get("id"),
            "name": wine.get("name"),
            "varietal": wine.get("varietal"),
            "region": wine.get("region"),
            "country": wine.get("country"),
            "wine_type": wine.get("wine_type"),
            "grapes": wine.get("grapes") or [],
            "body": wine.get("body"),
            "tasting_notes": details.get("tasting_notes"),
            "flavor_profile": details.get("flavor_profile") or [],
            "structure_profile": details.get("structure_profile") or {},
            "price": row.get("price"),
            "retailer": (row.get("stores") or {}).get("retailer_name"),
            "tier": 1 if enriched else 2,
        })
```

Then build the resolved intent (replacing the old `score_candidates(...)`/`get_recommendations(...)` calls):

```python
    explicit = intent_from_request(
        wine_type=req.wine_type,
        style_preferences=req.style_preferences,
        avoid=req.avoid,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
    )
    parsed = parse_message(req.message) if req.message and req.message != \
        "Recommend wines based on my preferences" else None
    resolved = merge_intent(parsed, explicit)

    top = score_candidates(resolved, candidates)[:_MAX_CANDIDATES]

    try:
        narrative, picks_data = get_recommendations(candidates=top, intent=resolved)
    except Exception:
        raise HTTPException(status_code=500, detail="Recommendation service unavailable")
```

Leave the no-candidates 400, the picks validation, session persistence, and response construction unchanged. Remove the now-unused old `score_candidates` keyword arguments.

- [ ] **Step 5: Run the full recommend API suite**

Run: `cd backend && python3 -m pytest tests/test_recommend_api.py -v`
Expected: all tests PASS (existing + 3 new).

- [ ] **Step 6: Run the entire suite**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: all PASS (was 129; now 129 + new flavor/intent/scorer/api tests, minus none).

- [ ] **Step 7: Commit**

```bash
git add backend/recommendation/claude_client.py backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat: tiered candidate pool + NL intent wiring in recommend endpoint (TDD)"
```

- [ ] **Step 8: Update CLAUDE.md**

Add a "Recommendation engine v2" note under Critical Technical Notes documenting: tiered pool (GrapeMinds tier-1 / extractor tier-2), knowledge-based scorer with `flavor_profiles`, optional NL `message` parsed via `intent.parse_message` and merged (explicit wins). Update the recommend router line in Key Files. Commit and push.

```bash
git add CLAUDE.md && git commit -m "docs: document recommendation engine v2" && git push origin main
```
