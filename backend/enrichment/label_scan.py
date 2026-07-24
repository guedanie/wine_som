"""Bottle-scan vision read: photo of a wine label -> structured fields.

Claude vision reads only what is printed on the label (same evidence-gate
philosophy as the extraction gazetteer — no producer-knowledge guessing).
Matching against the catalog lives in recommendation/label_match.py.
"""
import base64
import json
import mimetypes
import re
import time
from typing import Any, Dict, Optional, Tuple

# Same models the app already runs (overlay chat / recommendations).
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

LABEL_PROMPT = """Look at this photo of a beverage bottle label and transcribe ONLY what is printed on it.

Return a single JSON object, nothing else:
{"producer": string|null, "wine_name": string|null, "vintage": string|null, "appellation": string|null, "varietal": string|null, "confidence": number, "is_wine": boolean}

Rules:
- producer: the winery/brand name as printed. wine_name: the bottling/cuvee name as printed (may equal the varietal if that's all the label says). Do NOT repeat the producer inside wine_name.
- Transcribe only text visible in the photo. If a field is not printed or not legible, use null. Never guess from wine knowledge.
- vintage: the 4-digit year printed, as a string, else null.
- is_wine: false if the bottle is clearly not wine (beer, sake, spirits, soda...).
- confidence: 0-1, how confident you are in the transcription overall (0.2 = barely legible, 0.9 = clearly read)."""


def parse_label_read(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Tolerant parse of the model's JSON reply. Returns a normalized dict
    (vintage coerced to string, is_wine defaulting True) or None when no
    usable JSON object is present."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None

    def _s(key):
        v = raw.get(key)
        v = str(v).strip() if v is not None else None
        return v or None

    vintage = raw.get("vintage")
    vintage = str(vintage).strip() if vintage not in (None, "") else None
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (ValueError, TypeError):
        confidence = 0.0
    return {
        "producer": _s("producer"),
        "wine_name": _s("wine_name"),
        "vintage": vintage,
        "appellation": _s("appellation"),
        "varietal": _s("varietal"),
        "confidence": confidence,
        "is_wine": bool(raw.get("is_wine", True)),
    }


def read_label(image_bytes: bytes, media_type: str,
               model: str = HAIKU) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """One vision round-trip: label photo bytes -> (parsed read, call meta).
    Meta carries latency + token usage for the spike's cost/latency table."""
    import anthropic
    from config import settings

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    data = base64.standard_b64encode(image_bytes).decode("utf-8")
    t0 = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": LABEL_PROMPT},
            ],
        }],
    )
    meta = {
        "latency_s": round(time.time() - t0, 2),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": model,
    }
    text = next((b.text for b in response.content if b.type == "text"), "")
    return parse_label_read(text), meta


def media_type_for(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "image/jpeg"
