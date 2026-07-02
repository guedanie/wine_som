import json
import anthropic
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from api.schemas import SommRequest

router = APIRouter(prefix="/api/somm", tags=["somm"])

anthropic_client = anthropic.Anthropic()

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 512


def _system_prompt(wine) -> str:
    parts = [f"Wine: {wine.wine_name}"]
    if wine.producer:  parts.append(f"Producer: {wine.producer}")
    if wine.vintage:   parts.append(f"Vintage: {wine.vintage}")
    if wine.price:     parts.append(f"Price: ${wine.price:.0f}")
    if wine.store:     parts.append(f"Available at: {wine.store}")
    if wine.region:    parts.append(f"Region: {wine.region}")
    if wine.tags:      parts.append(f"Flavor profile: {', '.join(wine.tags)}")
    context = "\n".join(parts)
    return (
        "You are a sommelier assistant — knowledgeable, opinionated, direct. "
        "The user is currently viewing this wine:\n\n"
        f"{context}\n\n"
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


@router.post("", status_code=200)
async def ask_somm(req: SommRequest):
    system = _system_prompt(req.wine)
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
            yield "data: " + json.dumps({"type": "error", "message": str(e)}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
