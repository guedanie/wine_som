"""
Natural-language intent parsing for the recommender, plus merge with explicit
request fields. Explicit fields win on conflict; lists are unioned.
"""
import anthropic
from typing import Optional, List, Dict, Any
from config import settings

MODEL = "claude-haiku-4-5-20251001"
_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

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
        resp = _anthropic_client.messages.create(
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
                        avoid: List[str], budget_min: float, budget_max: float,
                        grapes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build a resolved-intent dict from explicit request fields only."""
    return {
        "wine_type": wine_type,
        "body": None,
        "flavors": list(style_preferences or []),
        "grapes": list(grapes or []),
        "region": None,
        "avoid": list(avoid or []),
        "budget_min": budget_min,
        "budget_max": budget_max,
    }


def merge_intent(parsed: Optional[Dict[str, Any]], explicit: Dict[str, Any]) -> Dict[str, Any]:
    """Merge parsed NL intent into the explicit-field intent. Explicit wins on scalar
    conflicts; flavors/avoid are unioned. A spoken price cap ("under $20") TIGHTENS
    the scoring window so the budget pull re-centers on what was asked — it never
    widens it (the inventory fetch already capped candidates at the slider max)."""
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
    max_price = parsed.get("max_price")
    if isinstance(max_price, (int, float)) and max_price > 0:
        if max_price < float(out.get("budget_max", 50.0)):
            out["budget_max"] = float(max_price)
            out["budget_min"] = min(float(out.get("budget_min", 10.0)), float(max_price))
    return out
