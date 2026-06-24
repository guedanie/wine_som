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
                "minItems": 1,
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
        # body/tannins/acidity/sweetness are the most sommelier-relevant for matching; alcohol/finish omitted
        if k in ("body", "tannins", "acidity", "sweetness") and v is not None
    ]

    if notes:
        line += f"\n   Tasting notes: {notes}"
    if struct_parts:
        line += f". Structure: {', '.join(struct_parts)}."
    return line


def get_recommendations(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]]]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    listings = "\n\n".join(
        f"{i + 1}. [wine_id: {w.get('wine_id')}] {_format_wine(w)}"
        for i, w in enumerate(candidates))
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
        f"For each pick, set wine_id to the exact id shown in [wine_id: ...] for that wine. "
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
