"""
Natural-language intent parsing for the recommender, plus merge with explicit
request fields. Explicit fields win on conflict; lists are unioned.
"""
import logging
import re
import unicodedata

import anthropic
from typing import Optional, List, Dict, Any, Tuple
from config import settings

logger = logging.getLogger(__name__)

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
            "regions": {"type": "array", "items": {"type": "string"}},
            "wine_name": {"type": ["string", "null"]},
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
                "Use null/empty when a field is not implied. Do not invent grapes or regions. "
                "`wine_name`: set ONLY when the user names a specific bottle or producer to look up "
                "(e.g. 'Caymus Special Selection', 'Opus One', 'do you have Silver Oak?'); "
                "leave null for generic style requests. "
                "`regions`: list EVERY wine region or country the user names, in the order "
                "mentioned (e.g. 'California vs Mendoza' -> ['California','Mendoza']); keep "
                "`region` as the single primary place. "
                "Extract the named entity EVEN WHEN the user is asserting or questioning its "
                "absence — \"nothing from Mendoza right?\", \"surely you have no Barolo\", "
                "\"I assume there's no rosé\" all still NAME Mendoza / Barolo / rosé, and each "
                "must be captured in `regions`/`grapes`/`wine_type` as appropriate. "
                "A shop or retailer name (H-E-B, Spec's, Central Market, Total Wine) is NOT a "
                "`wine_name` — leave `wine_name` null for \"anything from HEB?\". "
                "`avoid` means the user wants something EXCLUDED (\"no oak\", \"I don't like "
                "Chardonnay\", \"avoid sweet wines\", \"nothing too tannic\"). An availability "
                "QUESTION is NOT an avoid: \"nothing from Mendoza right?\", \"is there really no "
                "Chablis?\", \"you probably have zero Nebbiolo\" are asking ABOUT that wine — put "
                "the subject in `regions`/`grapes`/`wine_type` and leave it OUT of `avoid`. "
                "Never put the same term in both `avoid` and a positive field."
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



def _fold_term(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def drop_bogus_avoid(avoid: List[str], regions: List[str], grapes: List[str],
                     wine_type: Optional[str]) -> Tuple[List[str], List[str]]:
    """Remove `avoid` terms that also appear as a POSITIVE constraint — you cannot ask
    for X and to exclude X. Returns (kept, dropped).

    Why this exists: "nothing from Mendoza right?" (an availability QUESTION) parsed to
    avoid=['Mendoza'] AND regions=['Mendoza']. Since `avoid` is a hard exclusion in the
    scorer, 275 of 300 fetched Mendoza wines were deleted and the narrative then
    truthfully reported "No Mendoza in sight" — we destroyed exactly what the user asked
    about and reported it absent.

    Resolution is "trust the positive" because the harms are asymmetric: a false
    exclusion is invisible and catastrophic, a missed exclusion is visible and mild.
    Measured on 6 genuine preference avoids (Chardonnay, Merlot, oak, sweet, tannic,
    "can you avoid Chardonnay?") — none populate the positive fields, so none are
    dropped."""
    positives = [_fold_term(x) for x in (list(regions or []) + list(grapes or []))]
    if wine_type:
        positives.append(_fold_term(wine_type))
    positives = [p for p in positives if p]
    kept, dropped = [], []
    for a in (avoid or []):
        fa = _fold_term(a)
        if fa and any(fa == p or fa in p or p in fa for p in positives):
            dropped.append(a)
        else:
            kept.append(a)
    return kept, dropped


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
        "regions": [],
        "wine_name": None,
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
    out["regions"] = list(parsed.get("regions") or [])
    if not out["regions"] and out.get("region"):
        out["regions"] = [out["region"]]
    if not out.get("region") and out["regions"]:
        out["region"] = out["regions"][0]
    out["wine_name"] = out.get("wine_name") or parsed.get("wine_name")
    if not out.get("grapes"):
        out["grapes"] = list(parsed.get("grapes") or [])
    # list unions
    out["flavors"] = list({*(out.get("flavors") or []), *(parsed.get("flavors") or [])})
    out["avoid"] = list({*(out.get("avoid") or []), *(parsed.get("avoid") or [])})
    # An availability QUESTION ("nothing from Mendoza right?") can parse the subject into
    # BOTH avoid and regions; since avoid is a hard exclusion the scorer then deletes the
    # very wines the user asked about. Applied here so every consumer — fetch, scorer,
    # oracle, prompt — sees the corrected intent.
    out["avoid"], _dropped = drop_bogus_avoid(
        out.get("avoid"), out.get("regions"), out.get("grapes"), out.get("wine_type"))
    if _dropped:
        logger.info("INTENT | dropped contradicted avoid term(s): %s", _dropped)
    max_price = parsed.get("max_price")
    if isinstance(max_price, (int, float)) and max_price > 0:
        if max_price < float(out.get("budget_max", 50.0)):
            out["budget_max"] = float(max_price)
            out["budget_min"] = min(float(out.get("budget_min", 10.0)), float(max_price))
    return out
