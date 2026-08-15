"""Producer identity as a looked-up fact, not a recalled one.

Somm told a user "Epoch is a Texas Hill Country producer" — it is Paso Robles, and our
own catalog held 4 Epoch rows, three labelled Paso Robles. Same structural mistake as
the false-absence class: the model inferring what we can look up.

Self-validating by design: a token only yields a fact when the wines it matches look
like a real producer — a BOUNDED set that is REGION-CONCENTRATED. A generic word
("estate") matches thousands scattered everywhere and emits nothing, so no maintained
vocabulary is needed and it self-updates with the catalog.
"""
import logging
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PRODUCER_MAX_ROWS = 60          # a producer has a handful; "estate" has thousands
_PRODUCER_MIN_CONCENTRATION = 0.5  # top region must hold >= half the regioned rows
_PRODUCER_MIN_ROWS = 2           # one row is not evidence of a producer
_MAX_PRODUCERS = 2               # bound the prompt block


def _fold(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def summarize_producer(token: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Region summary for the wines a token matched, or None when the match doesn't
    look like a producer. PURE — `rows` come from the caller's query."""
    if not token or not rows or len(rows) > _PRODUCER_MAX_ROWS:
        return None
    regioned = [r for r in rows if (r.get("region") or "").strip()]
    if len(regioned) < _PRODUCER_MIN_ROWS:
        return None
    counts = Counter(r["region"].strip() for r in regioned)
    top_region, top_n = counts.most_common(1)[0]
    if top_n / float(len(regioned)) < _PRODUCER_MIN_CONCENTRATION:
        return None                      # scattered => not a coherent producer
    ctry = Counter((r.get("country") or "").strip()
                   for r in regioned if (r.get("country") or "").strip())
    return {
        "token": token,
        "regions": counts.most_common(2),
        "country": ctry.most_common(1)[0][0] if ctry else None,
        "total": len(rows),
    }


def format_producer_block(facts: List[Dict[str, Any]]) -> str:
    """Render producer facts for the prompt. Empty string when there are none."""
    if not facts:
        return ""
    lines = []
    for f in facts:
        regions = ", ".join(f"{r} ({n} of {f['total']} bottles we carry)"
                            for r, n in (f.get("regions") or []))
        ctry = f" — {f['country']}" if f.get("country") else ""
        lines.append(f"- {f.get('token')}: {regions}{ctry}")
    return ("\n\n[VERIFIED PRODUCER — drawn from our own catalog, not recalled. Use these "
            "regions when you describe the producer.]\n" + "\n".join(lines))


def producer_tokens(message: str, wine_name: Optional[str] = None) -> List[str]:
    """Candidate producer tokens: the parser's wine_name when present, plus the
    message's distinctive tokens. The parser is unreliable here — it returned None for
    "close to epoch in style", the case that produced the hallucination — so the token
    scan is the deterministic floor."""
    from recommendation.candidate_filters import significant_name_tokens
    toks = []
    for t in significant_name_tokens(wine_name) + significant_name_tokens(message):
        if len(t) >= 4 and t not in toks:      # 3-char tokens are too noisy
            toks.append(t)
    return toks[:6]


def fetch_producer_facts(supabase, message: str,
                         wine_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Catalog-WIDE producer lookup: no nearby-store scoping and no price filter.

    Both are load-bearing. Epoch is stocked only in Dallas at $55-$103 while the user
    was in San Antonio — a nearby-scoped or budget-clamped lookup returns nothing in
    exactly the situation where the model falls back on recall.

    Fails open to [] (logged) — never breaks a recommendation."""
    facts: List[Dict[str, Any]] = []
    try:
        for tok in producer_tokens(message, wine_name):
            if len(facts) >= _MAX_PRODUCERS:
                break
            rows = (supabase.table("wines").select("name,region,country")
                    .ilike("name", f"%{tok}%")
                    .limit(_PRODUCER_MAX_ROWS + 1).execute().data or [])
            f = summarize_producer(tok, rows)
            if f:
                facts.append(f)
    except Exception:
        logger.exception("PRODUCER | fact lookup failed — no producer facts this turn")
        return []
    return facts
