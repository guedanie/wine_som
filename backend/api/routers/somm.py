import json
import logging
import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from api.schemas import SommRequest
from config import settings
from api.ratelimit import RateLimiter, limit_dependency

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/somm", tags=["somm"])

# Streams Haiku per message — cap per IP per hour.
_somm_limiter = RateLimiter(limit=40, window_seconds=3600)

anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 512


def _your_wines_block(taste) -> str:
    """Compact list of the person's cellar/saved/rated wines so the Somm can
    reference them directly ("looking at your cellar…")."""
    liked = (taste or {}).get("liked_wines") or []
    if not liked:
        return ""
    src = {"saved": "saved", "cellar": "in your cellar", "upvoted": "you rated up"}
    lines = []
    for lw in liked[:10]:
        desc = ", ".join(p for p in [lw.get("varietal") or "", lw.get("region") or ""] if p)
        tag = src.get(lw.get("source"), "you liked")
        lines.append(f"- {lw.get('name')}" + (f" ({desc})" if desc else "") + f" — {tag}")
    return (
        "\n\nThe person's own wines (their cellar, saved bottles, and highly-rated picks) — "
        "you can reference these directly:\n" + "\n".join(lines)
    )


def _system_prompt(wine, taste=None) -> str:
    parts = [f"Wine: {wine.wine_name}"]
    if wine.producer:  parts.append(f"Producer: {wine.producer}")
    if wine.vintage:   parts.append(f"Vintage: {wine.vintage}")
    if wine.price:     parts.append(f"Price: ${wine.price:.0f}")
    if wine.store:     parts.append(f"Available at: {wine.store}")
    if wine.region:    parts.append(f"Region: {wine.region}")
    if wine.tags:      parts.append(f"Flavor profile: {', '.join(wine.tags)}")
    if wine.vivino_rating and wine.vivino_ratings_count:
        parts.append(
            f"Community rating: {wine.vivino_rating}/5 on Vivino ({wine.vivino_ratings_count:,} ratings)"
        )
    context = "\n".join(parts)
    return (
        "You are a sommelier assistant — knowledgeable, opinionated, direct. "
        "The user is currently viewing this wine:\n\n"
        f"{context}"
        f"{_your_wines_block(taste)}\n\n"
        "Keep responses to 2–3 sentences. Lead with the wine's most distinctive characteristic. "
        "Be specific about flavors, structure, and place. Never use filler phrases."
    )


def _build_messages(req: SommRequest) -> list:
    messages = []
    for h in (req.history or []):
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": h.get("content", "")})
    user_msg = req.message.strip() or (
        f"Introduce {req.wine.wine_name} — lead with its most distinctive characteristic "
        "in one sentence, then ask what I'd like to know."
    )
    messages.append({"role": "user", "content": user_msg})
    return messages


@router.post("", status_code=200, dependencies=[Depends(limit_dependency(_somm_limiter, "somm"))])
async def ask_somm(req: SommRequest):
    system = _system_prompt(req.wine, req.taste)
    messages = _build_messages(req)

    def event_gen():
        try:
            with anthropic_client.messages.stream(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=messages,
            ) as stream:
                for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                        and event.delta.text
                    ):
                        yield "data: " + json.dumps({"type": "token", "text": event.delta.text}) + "\n\n"
        except Exception as e:
            logger.exception("somm streaming error: %s", e)
            yield "data: " + json.dumps({"type": "error", "message": "Something went wrong"}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
