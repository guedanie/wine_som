# `/api/recommend` Endpoint Design

**Date:** 2026-06-03  
**Status:** Approved  
**Scope:** Single-turn wine recommendation endpoint using Claude Haiku + rule-based candidate scoring

---

## Overview

`POST /api/recommend` takes a user's zip code, budget, style preferences, and avoid list, retrieves enriched wines available locally, scores and filters candidates, then calls Claude Haiku to return a narrative + structured wine picks. Sessions are saved to Supabase for future multi-turn extension.

---

## Data Flow

```
POST /api/recommend
     │
     ▼
1. Candidate retrieval
   retail_inventory WHERE zip_code=? AND price BETWEEN min AND max AND in_stock=true
   JOIN wines + wine_details WHERE grapeminds_enriched_at IS NOT NULL
     │
     ▼
2. Python pre-filter (rule-based scoring)
   Score each wine against style_preferences, wine_type, avoid list
   Keep top 12
     │
     ▼
3. Claude Haiku call (tool use)
   System: sommelier persona
   User: preferences + top 12 wines as context
   Tool: recommend_wines(narrative: str, picks: list[WinePick])
     │
     ▼
4. Save recommendation_sessions row
   conversation_history = [{user msg}, {assistant response}]
   recommendations = picks array
   session_id = new UUID
     │
     ▼
5. Return RecommendResponse(narrative, picks, session_id)
```

---

## Components

### `backend/api/routers/recommend.py`
The endpoint. Orchestrates retrieval → scoring → Claude call → session save. Registered in `main.py`.

### `backend/recommendation/scorer.py`
Pure Python scoring function. No I/O — fully unit-testable. Takes candidate wine dicts + user preferences, returns sorted list.

**Scoring weights:**
- Wine type match: +3
- Each style preference keyword found in `flavor_profile`, `varietal`, `region`, or `tasting_notes`: +1 per hit
- Avoid list match: exclude entirely
- Price proximity to budget midpoint: +0 to +1 (normalized)

### `backend/recommendation/claude_client.py`
Anthropic SDK call. Takes scored candidates + preferences, builds prompt, calls Haiku with tool use, returns `(narrative, picks)`. Uses `tool_choice={"type": "tool", "name": "recommend_wines"}` to force structured output.

**Model:** `claude-haiku-4-5-20251001`

---

## Schemas

```python
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

`RecommendRequest` (already in `schemas.py`) is unchanged — `zip_code`, `budget_min`, `budget_max`, `style_preferences`, `avoid`, `wine_type`, `message` are all used.

---

## Prompt Design

**System:**
```
You are a knowledgeable sommelier helping someone find wines available at local shops near them.
Be warm, specific, and practical. Reference the wine's actual characteristics when explaining your picks.
```

**User message:**
```
Budget: $15–$35. Looking for: bold reds, earthy. Avoiding: sweet wines.
Here are the wines currently available:

1. Bodegas Muga Rioja Reserva — Tempranillo, Rioja, Spain — $28
   Tasting notes: dark cherry, cedar, tobacco. Structure: body 8, tannins 7, acidity 6.

2. ...up to 12 wines...

Recommend 3–5 wines that best match my preferences.
When explaining each pick, reference the wine's region and what makes it characteristic of that area.
```

When fewer than 3 candidates are available, the instruction changes to: `"Recommend as many as you can from the list below."`

**Tool definition** enforces structured output:
```json
{
  "name": "recommend_wines",
  "input_schema": {
    "type": "object",
    "properties": {
      "narrative": { "type": "string" },
      "picks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "wine_id":  { "type": "string" },
            "name":     { "type": "string" },
            "price":    { "type": "number" },
            "retailer": { "type": "string" },
            "why":      { "type": "string" }
          },
          "required": ["wine_id", "name", "price", "retailer", "why"]
        }
      }
    },
    "required": ["narrative", "picks"]
  }
}
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| No enriched wines match zip + budget | `400` — "No enriched wines found matching your criteria. Try widening your budget or style preferences." No Claude call. |
| Fewer than 3 candidates after scoring | Call Claude with adjusted instruction ("recommend as many as you can"). No hard failure. |
| Claude API error / no tool use block returned | `500` — "Recommendation service unavailable." Fail clean, no freeform text fallback. |
| Session save fails | Log error, still return recommendation. DB write is best-effort. |

---

## Session Persistence

Every successful recommendation creates a `recommendation_sessions` row using `get_service_client()` (RLS on this table blocks anon writes; service role bypasses it):
- `session_id`: new UUID (returned to client)
- `conversation_history`: `[{role: user, content: <user message>}, {role: assistant, content: <narrative + picks JSON>}]`
- `recommendations`: picks array
- `preference_snapshot`: full `RecommendRequest` dict
- `user_id`: `null` (no auth yet — multi-turn extension will populate this)

This design makes multi-turn a non-breaking extension: add optional `session_id` to `RecommendRequest`, load history if present, append and save.

---

## Testing

### `tests/test_recommend_api.py`
- `test_recommend_returns_200` — mock Supabase + Anthropic, happy path returns narrative + picks + session_id
- `test_recommend_no_enriched_wines_returns_400` — empty candidate list returns 400
- `test_recommend_missing_zip_returns_422` — missing required field caught by FastAPI validation
- `test_recommend_picks_have_required_fields` — each pick has all required fields

### `tests/test_scorer.py`
- `test_wine_type_match_scores_higher` — red preference ranks red wines above white
- `test_avoid_list_excludes_wines` — avoided style removes wine from candidates
- `test_price_proximity_scores_midrange_higher` — $25 wine scores higher than $10 when budget is $20–$30

---

## Files Changed

```
backend/
  api/
    main.py                          — register recommend router
    routers/recommend.py             — NEW: endpoint
    schemas.py                       — add WinePick, update RecommendResponse
  recommendation/
    __init__.py                      — NEW: empty
    scorer.py                        — NEW: rule-based candidate scorer
    claude_client.py                 — NEW: Haiku tool-use call
  tests/
    test_recommend_api.py            — NEW: 4 tests
    test_scorer.py                   — NEW: 3 tests
```
