import logging
from typing import List, Dict, Any, Optional, Tuple
import anthropic
from config import settings

logger = logging.getLogger(__name__)

_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


_TOOL = {
    "name": "recommend_wines",
    "description": "Return wine recommendations with narrative, structured picks, and followup suggestions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {"type": "string"},
            "picks": {
                "type": "array",
                "description": "Wine picks from the inventory. In Recommend Mode return up to 4 wines that GENUINELY fit — fewer is better; a single standout beats padding, and one perfect match should be returned alone. Never add a weaker or off-target wine (wrong retailer/store, wrong style) to reach a number. Return an empty array [] in Education Mode (when answering a knowledge question) or Pairing Mode (when the user asks what food goes with a wine already shown).",
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
- Recommend only wines that genuinely fit — usually 2–3, but never pad to a number. \
A single standout is better than one good pick plus filler. If only one wine truly \
matches a specific request (a named grape, retailer, or store), recommend just that one.
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
- **Narrative and picks MUST match exactly (one-to-one).** Describe ONLY the wines you include \
in the `picks` array — every pick gets a paragraph, and never name or describe a wine in the \
narrative that isn't in `picks`. If you decide a wine doesn't fit and drop it from `picks`, \
drop it from the narrative too. The user sees a card for each pick, so a wine mentioned without \
a matching pick shows as text with no card.

## Tool Use

You must always call the recommend_wines tool. Put your full response in the `narrative` \
field. For `picks`:
- **Recommend Mode** or **wine-for-food Pairing**: include 2–4 wines from the inventory
- **Education Mode** or **food-for-wine Pairing** (user asks what to eat): return `picks: []`

Never return picks from memory — only wines explicitly listed in the inventory below. \
Set wine_id to the exact id shown in [wine_id: ...] — never guess or invent one. Every wine \
you name in the narrative must have a matching entry in `picks` with that exact wine_id.

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
    store_name = wine.get("store_name") or ""
    where = f"{retailer} — {store_name}" if store_name else retailer
    line = f"{wine.get('name', 'Unknown')} — {location} — ${price:.2f} @ {where}"

    rating = wine.get("vivino_rating")
    count = wine.get("vivino_ratings_count") or 0
    if rating and count:
        line += f" — {rating}★ ({count:,} ratings on Vivino)"

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

    similar_to = wine.get("_similar_to")
    if similar_to:
        verb = {"saved": "saved", "cellar": "own", "upvoted": "liked"}.get(
            wine.get("_similar_source"), "liked")
        line += f'\n   ↳ resembles the "{similar_to}" you {verb}'
    return line


# Injected on follow-up turns when the client requests conversational mode.
# Flips the ambiguous-intent default from "make cards" to "just talk" so the
# chat reads like a sommelier answering, not a slot machine spitting new picks.
_FOLLOWUP_CONVERSATIONAL_DIRECTIVE = (
    "\n\nIMPORTANT — this is a follow-up and the user already has wine "
    "recommendations on screen from earlier in this conversation. Answer "
    "conversationally in the narrative and return picks: [] UNLESS the user is "
    "clearly asking for DIFFERENT or ADDITIONAL wines (e.g. 'show me something "
    "cheaper', 'anything from Rioja instead', 'what else do you have', 'find me a "
    "white'). Treat questions about the wines already shown — 'why that one?', "
    "'tell me more about it', 'what food pairs', 'how should I serve it', 'is it "
    "worth it' — as conversation and return picks: []. Do NOT replace the existing "
    "cards with a fresh set just because the user spoke again."
)


_LEAN = {"bold_red": "bold reds", "elegant_red": "elegant reds", "crisp_white": "crisp whites",
         "rich_white": "rich whites", "rose_sparkling": "rosé & sparkling", "everything": "a bit of everything"}
_BODY = {"light": "light-bodied", "medium": "medium-bodied", "full": "full-bodied"}
_SWEET = {"dry": "bone dry", "offdry": "dry, a touch of sweetness ok", "sweet": "enjoys sweeter wines"}
_ADV = {"loyal": "loyal to familiar favorites", "open": "open to a nudge", "surprise": "wants to be surprised"}


def _taste_profile_block(profile: Optional[Dict[str, Any]]) -> str:
    """The Somm-interview palate profile, rendered as durable context to weight
    the pick toward (distinct from this turn's request)."""
    if not profile:
        return ""
    lines = []
    if profile.get("lean"):        lines.append(f"- Leans toward: {_LEAN.get(profile['lean'], profile['lean'])}")
    if profile.get("body"):        lines.append(f"- Prefers: {_BODY.get(profile['body'], profile['body'])}")
    if profile.get("sweetness"):   lines.append(f"- Sweetness: {_SWEET.get(profile['sweetness'], profile['sweetness'])}")
    if profile.get("adventurous"): lines.append(f"- Style: {_ADV.get(profile['adventurous'], profile['adventurous'])}")
    if profile.get("regions_love"): lines.append(f"- Loves regions: {', '.join(profile['regions_love'])}")
    if profile.get("avoid"):       lines.append(f"- Steers clear of: {', '.join(profile['avoid'])}")
    if not lines:
        return ""
    return (
        "\n\n[Their taste profile — a durable palate they set with me]\n"
        + "\n".join(lines)
        + "\nWeight the pick toward this profile and honor what they avoid; "
        "you may nod to it (\"tuned to your palate…\"). This turn's request still leads."
    )


def _build_user_message(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    conversational: bool = False,
) -> str:
    listings = "\n\n".join(
        f"{i + 1}. [wine_id: {w.get('wine_id')}] {_format_wine(w)}"
        for i, w in enumerate(candidates))
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

    # Explicit "your wines" context so the Somm can converse about the person's
    # cellar/saved directly ("looking at your cellar…"), not just via per-pick tags.
    your_wines = ""
    liked = intent.get("liked_wines") or []
    if liked:
        _src = {"saved": "saved", "cellar": "in your cellar", "upvoted": "you rated ↑"}
        lines = []
        for lw in liked[:10]:
            desc = ", ".join(p for p in [lw.get("varietal") or "", lw.get("region") or ""] if p)
            src = _src.get(lw.get("source"), "you liked")
            lines.append(f"- {lw.get('name')}" + (f" ({desc})" if desc else "") + f" — {src}")
        your_wines = (
            "\n\n[Your wines — the person's saved bottles, cellar, and highly-rated picks]\n"
            + "\n".join(lines)
            + "\nYou CAN reference these directly (\"looking at your cellar…\", \"since you loved the X…\"); "
            "use them to steer the pick and explain the fit."
        )

    followup_directive = (
        _FOLLOWUP_CONVERSATIONAL_DIRECTIVE
        if conversational and conversation_history else ""
    )

    # If any listing is annotated as resembling a wine the user liked, tell
    # Claude to weave that connection into the pick's why (deterministically
    # computed by the scorer, so it's accurate to cite).
    similarity_note = (
        "\n\nSome listings are annotated '↳ resembles the \"X\" you saved/own/liked'. "
        "When you pick one, work that into its why — e.g. \"right up your alley, "
        "much like the X you saved\" — so the recommendation feels personal."
        if any(w.get("_similar_to") for w in candidates) else ""
    )

    return (
        f"{history_preamble}"
        f"{message_line}"
        f"Budget: ${budget_min:.0f}–${budget_max:.0f}. "
        f"Looking for:{type_str} {style_str}. "
        f"Avoiding: {avoid_str}.{_taste_profile_block(intent.get('profile'))}{your_wines}\n\n"
        f"Here are the wines currently available:\n\n{listings}\n\n"
        f"Recommend the wines from the list that genuinely fit my intent — up to 4, but "
        f"fewer is better than padding. If only one wine truly matches, recommend just "
        f"that one; never add a weaker or off-target pick to reach a number. If I named a "
        f"retailer or store, only recommend wines shown at that retailer/store. "
        f"Set wine_id to the exact id shown in [wine_id: ...] for each pick."
        f"{similarity_note}"
        f"{followup_directive}"
    )


def _parse_narrative_fragments(fragments):
    """Parse a sequence of input_json_delta fragment strings from the streaming tool call.

    Yields (type, value) tuples:
      ("token", str)   — decoded narrative characters
      ("picks", list)  — picks array, as soon as its closing ] is seen

    Extracted from _gen() so it can be unit-tested without any Anthropic API calls.
    Handles standard JSON escape sequences including \\uXXXX (B2 fix).
    """
    _JSON_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "/": "/"}

    json_buf = ""
    in_narrative = False
    narrative_done = False
    escape_next = False
    # None = not in a \\uXXXX sequence; str = accumulating hex digits
    unicode_buf = None
    MARKERS = ['"narrative":"', '"narrative": "']

    post_buf = ""
    picks_yielded = False

    def _try_extract_picks(buf):
        import json as _json
        marker = '"picks":'
        pos = buf.find(marker)
        if pos == -1:
            return None
        rest = buf[pos + len(marker):].lstrip()
        if not rest or rest[0] != '[':
            return None
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(rest):
            if esc:
                esc = False
                continue
            if ch == '\\' and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        try:
                            return _json.loads(rest[:i + 1])
                        except _json.JSONDecodeError:
                            return None
        return None

    def _process_char(ch, chunk, escape_next, unicode_buf):
        """Process one character inside the narrative string.

        Returns (escape_next, unicode_buf, narrative_done).
        Appends decoded characters to chunk in-place.
        """
        narrative_done = False
        if unicode_buf is not None:
            # Accumulating hex digits for \\uXXXX
            unicode_buf += ch
            if len(unicode_buf) == 4:
                try:
                    chunk.append(chr(int(unicode_buf, 16)))
                except ValueError:
                    chunk.append("u" + unicode_buf)
                unicode_buf = None
            return escape_next, unicode_buf, narrative_done

        if escape_next:
            if ch == "u":
                unicode_buf = ""  # start collecting 4 hex digits
            else:
                chunk.append(_JSON_ESCAPES.get(ch, ch))
            return False, unicode_buf, narrative_done

        if ch == "\\":
            return True, unicode_buf, narrative_done
        if ch == '"':
            narrative_done = True
            return escape_next, unicode_buf, narrative_done
        chunk.append(ch)
        return escape_next, unicode_buf, narrative_done

    for fragment in fragments:
        if narrative_done:
            if not picks_yielded:
                post_buf += fragment
                early_picks = _try_extract_picks(post_buf)
                if early_picks is not None:
                    picks_yielded = True
                    yield ("picks", early_picks)
            continue

        if not in_narrative:
            json_buf += fragment
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
            post_start = None
            chunk = []
            for idx, ch in enumerate(chars):
                escape_next, unicode_buf, done = _process_char(ch, chunk, escape_next, unicode_buf)
                if done:
                    narrative_done = True
                    post_start = idx + 1
                    break
            if chunk:
                yield ("token", "".join(chunk))
            if narrative_done and post_start is not None:
                remaining = chars[post_start:]
                if remaining and not picks_yielded:
                    post_buf += remaining
                    early_picks = _try_extract_picks(post_buf)
                    if early_picks is not None:
                        picks_yielded = True
                        yield ("picks", early_picks)
        else:
            chunk = []
            post_start = None
            for idx, ch in enumerate(fragment):
                escape_next, unicode_buf, done = _process_char(ch, chunk, escape_next, unicode_buf)
                if done:
                    narrative_done = True
                    post_start = idx + 1
                    break
            if chunk:
                yield ("token", "".join(chunk))
            if narrative_done and post_start is not None:
                remaining = fragment[post_start:]
                if remaining and not picks_yielded:
                    post_buf += remaining
                    early_picks = _try_extract_picks(post_buf)
                    if early_picks is not None:
                        picks_yielded = True
                        yield ("picks", early_picks)

    # Yield empty picks if we never found a closing bracket (degenerate case)
    if not picks_yielded:
        picks = _try_extract_picks(post_buf)
        if picks is not None:
            yield ("picks", picks)


def stream_recommendations(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    conversational: bool = False,
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
    user_msg = _build_user_message(candidates, intent, conversation_history, conversational)
    user_message = intent.get("message") or ""

    logger.info(
        "CLAUDE | streaming | message=%r history_turns=%d candidates=%d",
        user_message[:60], len(conversation_history or []), len(candidates),
    )

    def _gen():
        picks_yielded = False
        try:
            with _anthropic_client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "recommend_wines"},
            ) as stream:
                def _fragments():
                    for event in stream:
                        if getattr(event, "type", None) != "content_block_delta":
                            continue
                        delta = getattr(event, "delta", None)
                        if delta is None or getattr(delta, "type", None) != "input_json_delta":
                            continue
                        yield delta.partial_json or ""

                for typ, val in _parse_narrative_fragments(_fragments()):
                    if typ == "picks":
                        picks_yielded = True
                    yield (typ, val)

                final = stream.get_final_message()

            tool_block = next((b for b in final.content if b.type == "tool_use"), None)
            if tool_block is None:
                raise ValueError("Claude did not return tool picks")
            if not picks_yielded:
                yield ("picks", tool_block.input.get("picks", []))
            suggestions = tool_block.input.get("followup_suggestions") or []
            if suggestions:
                yield ("suggestions", suggestions)
        except Exception as e:
            logger.exception("CLAUDE | streaming error: %s", e)
            yield ("error", "Recommendation service unavailable")

    return _gen()


def get_recommendations(
    candidates: List[Dict[str, Any]],
    intent: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Non-streaming variant kept for tests that mock anthropic.Anthropic directly."""
    user_msg = _build_user_message(candidates, intent, conversation_history)

    response = _anthropic_client.messages.create(
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
