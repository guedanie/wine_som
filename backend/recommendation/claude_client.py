import logging
from typing import List, Dict, Any, Optional, Tuple
import anthropic
from config import settings

logger = logging.getLogger(__name__)


_TOOL = {
    "name": "recommend_wines",
    "description": "Return wine recommendations with narrative, structured picks, and followup suggestions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {"type": "string"},
            "picks": {
                "type": "array",
                "description": "Wine picks from the inventory. Return 2-4 wines in Recommend Mode. Return an empty array [] in Education Mode (when answering a knowledge question) or Pairing Mode (when the user asks what food goes with a wine already shown).",
                "minItems": 0,
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
            "followup_suggestions": {
                "type": "array",
                "description": "Exactly 3 short followup questions the user might ask next, grounded in what was just recommended (specific regions, price range, or styles mentioned).",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
        },
        "required": ["narrative", "picks", "followup_suggestions"],
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
| Ambiguous or no clear signal | Default to Recommend Mode, ask one clarifying question |

## Recommend Mode

**Trigger:** User wants a specific wine to buy or drink.

- Before recommending, ask 1–2 focused questions if key context is missing (budget, bold vs. \
lighter style, exploring new or familiar region). Never ask more than two questions at once.
- Default to red wines unless the user specifies otherwise.
- Prioritize wines available in the local inventory provided — only recommend wines from the list.
- Give 2–3 concrete recommendations. Quality over quantity.
- For each pick: producer and wine name, what to expect in the glass (fruit, structure, finish), \
price point, and why it fits. Be specific.
- Be opinionated. If one recommendation is clearly the best fit, say so.
- Avoid vague descriptors ("great balance" — balance of what?).

## Education Mode

**Trigger:** User wants to understand a wine, region, grape, producer, or concept.

- Open with what makes the subject distinctive — don't lead with geography basics unless context requires it.
- Cover: regional character, defining grapes, standout vintages (be specific — growing season \
detail beats "ideal conditions"). Be opinionated.
- Use short paragraphs, not bullet lists.
- After a substantive response, offer a natural bridge: "Want me to find something available \
near you that fits this profile?"
- Return `picks: []` — Education Mode answers questions, it does not push wine cards.

## Pairing Mode

**Trigger:** User explicitly raises food or a specific occasion with food context. \
Only engage Pairing Mode when food is the clear subject — do not volunteer pairings \
when the user asked for a recommendation without food context.

There are two sub-cases — handle them differently:

**Wine-for-food** ("What should I drink with steak?"): Lead with wine style logic and why the \
pairing works structurally (e.g., "the acidity cuts through the fat"). Return 2–3 picks from \
the inventory list.

**Food-for-wine** ("What food goes with this Malbec?", "What should I cook for this bottle?"): \
The user is asking what to eat, not what to drink. Respond with food pairing advice in the \
narrative. Return `picks: []` — do NOT replace the wine cards with new wines.

## Cross-Mode Behavior

- Mode transitions should feel invisible. Pivot cleanly without announcing the switch.
- Carry context across turns. If the user revealed budget, style, or location earlier, \
apply it — don't ask again.
- When intent is ambiguous, lean toward Recommend Mode and ask one question to clarify.
- If three turns pass without a clear intent signal, offer a soft prompt: "Are you looking \
for a specific bottle to grab, or more interested in learning about what you're drinking?"

## Inventory Data Handling

The wines provided are the only wines you can recommend — they are what's locally available.
Each listing shows the retailer after the price (e.g. "@ H-E-B", "@ Spec's", "@ Geraldine's Natural Wines"):

- Only recommend wines present in the list.
- If the user specifies a retailer, only pick wines from that retailer.
- If no perfect match exists, say so directly and offer the closest available alternative.
- Never recommend a wine as "locally available" unless it appears in the provided list.
- Set wine_id to the exact id shown in [wine_id: ...] for each pick — never guess or invent one.

## Tone and Format Rules

- Be opinionated. Hedging on everything makes recommendations useless.
- Never use filler phrases: "Great question," "Absolutely," "Certainly," "Of course."
- Match the user's energy — casual or precise.
- Do not explain your reasoning about mode selection.
- **Narrative structure:** 1 sentence of framing. Then each wine gets its own short paragraph \
(2 sentences max): open with **Wine Name** in bold, then why it fits + what's in the glass. \
Blank line between wines. No bullet lists. No numbered lists. Keep the entire response under 120 words.

## Tool Use

You must always call the recommend_wines tool. Put your full response in the `narrative` \
field. For `picks`:
- **Recommend Mode** or **wine-for-food Pairing**: include 2–4 wines from the inventory
- **Education Mode** or **food-for-wine Pairing** (user asks what to eat): return `picks: []`

Never return picks from memory — only wines explicitly listed in the inventory below. \
Set wine_id to the exact id shown in [wine_id: ...] — never guess or invent one.

In `followup_suggestions`, provide exactly 3 short questions the user might naturally ask \
next. Phrase them as the user would ask, like "Anything from Burgundy?" or \
"What food goes with this?". Do NOT suggest "What pairs well with pasta?" as a chip if \
you just answered a food question — vary the suggestions.\
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
      ("token", str)   — narrative character(s) extracted from input_json_delta
      ("picks", list)  — raw model picks (unenriched)

    With forced tool use the model writes everything inside the tool JSON.
    We extract the narrative string by watching input_json_delta fragments
    for the '"narrative":"' marker, then streaming chars until the closing quote.

    Raises on init failure so the router can return 500 before streaming starts.
    """
    client_inst = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_msg = _build_user_message(candidates, intent, conversation_history)
    user_message = intent.get("message") or ""

    logger.info(
        "CLAUDE | streaming | message=%r history_turns=%d candidates=%d",
        user_message[:60], len(conversation_history or []), len(candidates),
    )

    def _gen():
        # State machine for extracting the "narrative" string from streaming JSON.
        # input_json_delta fragments arrive as raw JSON text, e.g.:
        #   '{"narrative": "Here are'  →  ' three wines'  →  '...","picks":[...]}'
        # JSON escape sequence map — only the sequences Claude emits in narratives.
        _JSON_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "/": "/"}

        json_buf = ""
        in_narrative = False
        narrative_done = False
        escape_next = False
        # Both '"narrative":"' and '"narrative": "' (with space) are valid.
        MARKERS = ['"narrative":"', '"narrative": "']

        try:
            with client_inst.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "recommend_wines"},
            ) as stream:
                for event in stream:
                    # Only care about tool-input JSON deltas
                    if (getattr(event, "type", None) != "content_block_delta"):
                        continue
                    delta = getattr(event, "delta", None)
                    if delta is None or getattr(delta, "type", None) != "input_json_delta":
                        continue

                    fragment = delta.partial_json or ""

                    if narrative_done:
                        continue

                    if not in_narrative:
                        json_buf += fragment
                        # Scan for the narrative value start
                        start_idx = -1
                        for marker in MARKERS:
                            pos = json_buf.find(marker)
                            if pos != -1:
                                start_idx = pos + len(marker)
                                break
                        if start_idx == -1:
                            continue
                        in_narrative = True
                        chars = json_buf[start_idx:]
                        chunk = []
                        for ch in chars:
                            if escape_next:
                                chunk.append(_JSON_ESCAPES.get(ch, ch))
                                escape_next = False
                            elif ch == "\\":
                                escape_next = True
                            elif ch == '"':
                                narrative_done = True
                                break
                            else:
                                chunk.append(ch)
                        if chunk:
                            yield ("token", "".join(chunk))
                    else:
                        # Already inside the narrative string — stream chars directly
                        chunk = []
                        for ch in fragment:
                            if escape_next:
                                chunk.append(_JSON_ESCAPES.get(ch, ch))
                                escape_next = False
                            elif ch == "\\":
                                escape_next = True
                            elif ch == '"':
                                narrative_done = True
                                break
                            else:
                                chunk.append(ch)
                        if chunk:
                            yield ("token", "".join(chunk))

                final = stream.get_final_message()

            tool_block = next((b for b in final.content if b.type == "tool_use"), None)
            if tool_block is None:
                raise ValueError("Claude did not return tool picks")
            yield ("picks", tool_block.input.get("picks", []))
            suggestions = tool_block.input.get("followup_suggestions") or []
            if suggestions:
                yield ("suggestions", suggestions)
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
        tool_choice={"type": "tool", "name": "recommend_wines"},
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block is None:
        raise ValueError("Claude did not return a tool use block")

    result = tool_block.input
    return result.get("narrative", ""), result.get("picks", [])
