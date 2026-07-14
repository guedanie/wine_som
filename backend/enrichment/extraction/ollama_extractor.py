"""
Ollama wine-fact extractor — local-LLM alternative to the Haiku extractor.

Same task, prompt, and post-processing as extractor.py, but calls a local
Ollama model (JSON output instead of Anthropic tool-use). Free per call.
Set OLLAMA_MODEL / OLLAMA_URL to override the defaults.
"""
import os
import json
import socket
import time
import urllib.request
import urllib.error
from typing import List, Dict, Any

from enrichment.extraction.reference import APPELLATIONS, CORE_GRAPES, FEW_SHOT
from enrichment.extraction.extractor import _post_process, _system_prompt

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# JSON schema hint appended to the shared system prompt (Ollama has no tool-use;
# we ask for a strict JSON object and parse it).
_JSON_INSTRUCTION = (
    "\n\nRespond ONLY with a JSON object of this exact shape, no prose:\n"
    '{"wines": [{"wine_id": "...", "region": null, "sub_region": null, '
    '"country": null, "vintage_year": null, "varietal": null, "grapes": [], '
    '"abv": null, "body": null}]}\n'
    "Every input wine_id must appear exactly once. Use null (not \"null\") for "
    "unknown scalar fields and [] for unknown grapes."
)


def _call_ollama(system: str, user: str, model: str, timeout: int = 120,
                 retries: int = 3) -> dict:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode()
    # Each attempt opens a fresh connection with a fresh Request, so a transient
    # slow/stalled window (e.g. after a sleep/wake) self-heals instead of the
    # whole run silently skipping wines. Re-raise only after exhausting retries.
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(OLLAMA_URL, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            content = (data.get("message") or {}).get("content") or "{}"
            return json.loads(content)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))   # 2s, 4s backoff
    raise last


def extract_facts_ollama(wines: List[Dict[str, Any]], batch_size: int = 10,
                         model: str = None) -> List[Dict[str, Any]]:
    """Extract structured facts with a local Ollama model. Same output shape
    and post-processing as the Haiku extractor."""
    model = model or OLLAMA_MODEL
    system = _system_prompt() + _JSON_INSTRUCTION
    results = []
    for i in range(0, len(wines), batch_size):
        batch = wines[i:i + batch_size]
        listing = "\n".join(
            f'- wine_id={w["id"]} | name="{w.get("name","")}" | type={w.get("wine_type")} '
            f'| desc="{(w.get("description") or w.get("description_long") or "")[:400]}"'
            for w in batch
        )
        sources = {w["id"]: f'{w.get("name","")} {w.get("description") or w.get("description_long") or ""}'
                   for w in batch}
        try:
            out = _call_ollama(system, "Extract facts for these wines:\n" + listing, model)
            for rec in out.get("wines", []):
                if rec.get("wine_id"):
                    results.append(_post_process(rec, source_text=sources.get(rec["wine_id"])))
        except Exception as e:
            print(f"  ollama batch {i // batch_size} failed: {e}")
    return results
