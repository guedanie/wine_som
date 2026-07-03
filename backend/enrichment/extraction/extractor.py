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
_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
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
            resp = _anthropic_client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content":
                           "Extract facts for these wines:\n" + listing}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "extract_facts"},
                timeout=60.0,
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
