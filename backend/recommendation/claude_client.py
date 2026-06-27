import logging
from typing import List, Dict, Any, Optional, Tuple
import anthropic
from config import settings

logger = logging.getLogger(__name__)


# Picks-only tool — narrative goes in the text response, not the tool.
_TOOL = {
    "name": "recommend_wines",
    "description": "Submit structured wine picks after your text response. Do not put the narrative here.",
    "input_schema": {
        "type": "object",
        "properties": {
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
        "required": ["picks"],
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
- Give 2–3 concrete recommendations. Quality over quantity.
- For each pick: producer and wine name, what to expect in the glass (fruit, structure, finish), \
price point, and why it fits. One sentence of context, one sentence of description. Be specific.
- Be opinionated. If one recommendation is clearly the best fit, say so.
- Avoid vague descriptors ("great balance" — balance of what?).

## Education Mode

**Trigger:** User wants to understand a wine, region, grape, producer, or concept.

- Open with what makes the subject distinctive.
- Cover: regional character, defining grapes, standout vintages. Be opinionated.
- Use short paragraphs, not bullet lists.
- After a substantive education response, offer: "Want me to find something available near you?"
- Still pick 2–3 illustrative wines from the inventory list.

## Pairing Mode

**Trigger:** User mentions food, a meal, or an occasion that implies food.

- Lead with wine style logic, not a simple match. Explain *why* the pairing works structurally.
- Give 2–3 pairing options at different price points from the inventory list.

## Cross-Mode Behavior

- Mode transitions should feel invisible.
- Carry context across turns. Don't ask for budget or location a second time.
- When intent is ambiguous, lean toward Recommend Mode.

## Inventory Data Handling

The wines provided are the only wines you can recommend — they are what's locally available.
Each listing shows the retailer after the price (e.g. "@ H-E-B", "@ Spec's", "@ Geraldine's Natural Wines"):

- Only recommend wines present in the list.
- If the user specifies a retailer, only pick wines from that retailer.
- If no perfect match exists, say so and offer the closest alternative.
- Never recommend a wine as "locally available" unless it appears in the provided list.
- Set wine_id to the exact id shown in [wine_id: ...] for each pick — never guess or invent one.

## Tone and Format Rules

- Be opinionated. Hedging on everything makes recommendations useless.
- Never use filler phrases: "Great question," "Absolutely," "Certainly," "Of course."
- Match the user's energy.
- Do not explain your reasoning about mode selection.
- **Narrative structure:** 1 sentence of framing. Then each wine gets its own short paragraph \
(2 sentences max): wine name first, then why it fits + what's in the glass. Blank line between wines. \
No bullet lists. No numbered lists. Keep the entire response under 120 words.

## Tool Use

Write your complete response as text first. Then call the recommend_wines tool with your \
structured picks. Do not put the narrative in the tool.
Set wine_id to the exact id shown in [wine_id: ...] for each pick — never guess or invent one.\
"""


def _format_wine(wine: Dict[str, Any]) -> str:
    location = ", ".join(filter(None, [
        wine.get("varietal") or "",
        wine.get("region") or "",
        wine.get("country") or "",
    ]))
    price = float(wine.get("price") or 0.0)
    retailer = wine.get("retailer") or ""
    line = f"{wine.get('name', 'Unknown')} — {location} — ${price:.2f} @ {retailer}"

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


def _build_user_message(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
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

    return (
        f"{history_preamble}"
        f"{message_line}"
        f"Budget: ${budget_min:.0f}–${budget_max:.0f}. "
        f"Looking for:{type_str} {style_str}. "
        f"Avoiding: {avoid_str}.\n\n"
        f"Here are the wines currently available:\n\n{listings}\n\n"
        f"Select {count_instruction} wines from the list above that best serve my intent. "
        f"Set wine_id to the exact id shown in [wine_id: ...] for each pick."
    )


def stream_recommendations(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
):
    """
    Returns a generator that yields (type, data) tuples:
      ("token", str)          — narrative text chunk
      ("picks", list)         — raw model picks (unenriched)

    Raises if the Anthropic client cannot be initialized so the router can
    return a 500 before the StreamingResponse starts.
    """
    client_inst = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_msg = _build_user_message(candidates, intent, conversation_history)
    user_message = intent.get("message") or ""

    logger.info(
        "CLAUDE | streaming | message=%r history_turns=%d candidates=%d",
        user_message[:60], len(conversation_history or []), len(candidates),
    )

    def _gen():
        try:
            with client_inst.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                tools=[_TOOL],
                tool_choice={"type": "any"},
            ) as stream:
                for text in stream.text_stream:
                    yield ("token", text)
                final = stream.get_final_message()

            tool_block = next((b for b in final.content if b.type == "tool_use"), None)
            if tool_block is None:
                raise ValueError("Claude did not return tool picks")
            yield ("picks", tool_block.input.get("picks", []))
        except Exception as e:
            logger.exception("CLAUDE | streaming error: %s", e)
            yield ("error", str(e))

    return _gen()


def get_recommendations(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Non-streaming variant kept for tests that mock anthropic.Anthropic directly."""
    client_inst = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_msg = _build_user_message(candidates, intent, conversation_history)

    response = client_inst.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[_TOOL],
        tool_choice={"type": "any"},
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ValueError("Claude did not return a tool use block")

    # narrative may come from a text block or be absent (picks-only response)
    text_block = next((b for b in response.content if b.type == "text"), None)
    narrative = (text_block.text if text_block else "") or ""
    return narrative, tool_block.input.get("picks", [])
