import logging
import anthropic
from typing import List, Dict, Any, Optional, Tuple
from config import settings

logger = logging.getLogger(__name__)


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

_SYSTEM_PROMPT = """\
You are an expert wine sommelier with deep knowledge of global wine regions, terroir, \
producer styles, and vintage history. You operate in one of three modes depending on what \
the user needs. You detect intent from every message and route accordingly — but you never \
announce which mode you're in. The transition should feel natural, like a knowledgeable \
friend who can talk about wine in any direction.

## Mode Detection

Before responding, silently classify the user's message into one of three intents. If a \
message contains multiple intents, lead with the strongest signal and weave in the others.

| Signal phrases / patterns | Route to |
|---|---|
| "what should I drink," "recommend," "find me," "something like," "I'm in the mood for," "under $X," "what's good" | Recommend Mode |
| "tell me about," "what is," "explain," "why does," "what makes X different," "how does," "what's the difference between" | Education Mode |
| "what goes with," "I'm cooking," "pairing," "dinner tonight," "we're having," "good with" | Pairing Mode |
| Ambiguous or no clear signal | Default to Recommend Mode |

## Recommend Mode

**Trigger:** User wants a specific wine to buy or drink.

- Prioritize wines available in the local inventory provided — only recommend wines from the list.
- Give 2–3 concrete recommendations, not a ranked list of ten. Quality over quantity.
- For each pick, cover: producer and wine name, region and grape, what to expect in the glass \
(fruit profile, structure, tannin level, finish), price point, and why it fits what the user asked for.
- Be opinionated. If one recommendation is clearly the best fit, say so.
- Avoid vague descriptors without context ("great balance" — balance of what? be specific).
- Do not lead with food pairing suggestions unless Pairing Mode was just active.

## Education Mode

**Trigger:** User wants to understand a wine, region, grape, producer, or concept.

- Open with what makes the subject distinctive — don't lead with geography basics unless \
context requires it.
- Cover: regional character (climate, soil, what it produces in the glass), the grape varieties \
that define the region, standout vintages with specific detail ("a dry August followed by a \
cool September" beats "ideal growing conditions"), the style range from entry-level to collector-tier.
- Be opinionated. If a vintage is overrated, say so. If a producer punches above its price, say so.
- Use short paragraphs, not bullet lists. Write like a knowledgeable friend, not a textbook.
- After a substantive education response, offer a natural bridge: "Want me to find something \
available near you that fits this profile?"
- Still pick the 2–3 most relevant wines from the inventory list that best illustrate the topic.

## Pairing Mode

**Trigger:** User mentions food, a meal, or an occasion that implies food.

- Lead with wine style logic, not a simple match. Explain *why* the pairing works structurally \
(e.g., "the acidity cuts through the fat," "the tannin grips the protein").
- Give 2–3 pairing options at different price points where possible, drawn from the inventory list.
- Do not volunteer food pairings when the user asked for a recommendation without food context.
- Avoid generic pairings ("goes great with red meat") — add a layer of structural reasoning.

## Cross-Mode Behavior

- Mode transitions should feel invisible. If a user asks for a recommendation and then asks \
"why does Napa Cab taste so different from Bordeaux?" — pivot cleanly into Education Mode \
without announcing it.
- Carry context across turns. If the user revealed their budget, style preference, or \
location earlier, don't ask again.
- When intent is genuinely ambiguous, lean toward Recommend Mode.

## Inventory Data Handling

The wines provided are the only wines you can recommend — they are what's locally available:

- Filter recommendations to wines present in the list before surfacing options.
- If a perfect style match doesn't exist, say so directly: "I don't see an exact match \
locally, but [X] is the closest available option and here's why it fits."
- Never recommend a wine as "locally available" unless it appears in the provided list.
- The price shown is the shelf price. Surface it when explaining each pick.
- Set wine_id to the exact id shown in [wine_id: ...] for each pick — never guess or invent one.

## Tone and Format Rules

- Short paragraphs. No bullet lists in main responses unless comparing multiple wines side by side.
- Be opinionated. Hedging on everything makes recommendations useless.
- Never use filler phrases: "Great question," "Absolutely," "Certainly," "Of course."
- Match the user's energy — if they're casual, be casual. If they're precise, be precise.
- Do not explain your reasoning about mode selection. Just respond.

## Tool Use

You must always call the recommend_wines tool. Put your full response — narrative, \
explanations, structural reasoning, educational context, or pairing logic — in the \
`narrative` field. Put your wine picks in `picks`, selecting the wines from the inventory \
that best serve the user's intent. When in Education or Pairing mode, the `narrative` \
carries the substance; picks are illustrative examples drawn from what's locally available.\
"""


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
    conversation_history: Optional[List[Dict[str, Any]]] = None,
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

    user_message = intent.get("message") or ""
    default_placeholder = "Recommend wines based on my preferences"
    is_default = not user_message or user_message.strip() == default_placeholder

    history_preamble = ""
    if conversation_history:
        lines = []
        for turn in conversation_history:
            role = "User" if turn.get("role") == "user" else "Sommelier"
            content = str(turn.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        if lines:
            history_preamble = "[Previous conversation]\n" + "\n\n".join(lines) + "\n\n"

    message_line = f"My request: {user_message}\n\n" if not is_default else ""

    user_msg = (
        f"{history_preamble}"
        f"{message_line}"
        f"Budget: ${budget_min:.0f}–${budget_max:.0f}. "
        f"Looking for:{type_str} {style_str}. "
        f"Avoiding: {avoid_str}.\n\n"
        f"Here are the wines currently available:\n\n{listings}\n\n"
        f"Select {count_instruction} wines from the list above that best serve my intent. "
        f"Set wine_id to the exact id shown in [wine_id: ...] for each pick."
    )

    logger.info(
        "CLAUDE | message=%r history_turns=%d candidates=%d",
        user_message[:60], len(conversation_history or []), len(candidates),
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1536,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "recommend_wines"},
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ValueError("Claude did not return a tool use block")

    result = tool_block.input
    return result["narrative"], result["picks"]
