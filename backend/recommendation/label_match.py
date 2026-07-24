"""Bottle-scan catalog match: vision label read -> five-state scan result.

Pure logic (no I/O) so it unit-tests without a DB. Reuses the item-31 name
tokenizer; scores candidates by what fraction of the read's distinctive tokens
appear in the candidate's name+brand, then classifies into the design
handoff's scanResult states (plus 'not_wine', which the UI renders as a
decline). Thresholds are the spike's tuning surface.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from recommendation.candidate_filters import significant_name_tokens

# A candidate must match at least this fraction of the read's tokens to count.
MATCH_FLOOR = 0.5
# Candidates within this margin of the top score disambiguate together.
CLOSE_MARGIN = 0.2
MAX_CANDIDATES = 4

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _read_tokens(read: Dict[str, Any]) -> List[str]:
    text = " ".join(filter(None, [read.get("producer"), read.get("wine_name")]))
    return significant_name_tokens(text)


def _cand_vintage(cand: Dict[str, Any]) -> Optional[str]:
    if cand.get("vintage_year"):
        return str(cand["vintage_year"])
    m = _YEAR_RE.search(cand.get("name") or "")
    return m.group(0) if m else None


def score_candidates(read: Dict[str, Any],
                     candidates: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any]]]:
    """(score, candidate) desc, deduped by wine id (first row kept — inventory
    joins repeat a wine per store). Score = fraction of read tokens present in
    the candidate's name+brand text."""
    tokens = _read_tokens(read)
    if not tokens:
        return []
    seen = set()
    scored = []
    for c in candidates:
        cid = c.get("id") or c.get("wine_id")
        if cid in seen:
            continue
        seen.add(cid)
        hay = " ".join(filter(None, [c.get("name"), c.get("brand")])).lower()
        hits = sum(1 for t in tokens if t in hay)
        scored.append((hits / len(tokens), c))
    scored.sort(key=lambda sc: sc[0], reverse=True)
    return scored


def classify_scan(read: Optional[Dict[str, Any]],
                  candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Vision read + catalog candidates -> scanResult dict:
    {status, wine?, candidates?, read_vintage?, confidence?}."""
    if read is None:
        return {"status": "unreadable"}
    if not read.get("is_wine", True):
        return {"status": "not_wine"}
    if not _read_tokens(read):
        return {"status": "unreadable"}

    result: Dict[str, Any] = {"read_vintage": read.get("vintage"),
                              "confidence": read.get("confidence")}
    scored = score_candidates(read, candidates)
    strong = [(s, c) for s, c in scored if s >= MATCH_FLOOR]
    if not strong:
        result["status"] = "unstocked"
        return result

    top_score = strong[0][0]
    close = [c for s, c in strong if top_score - s <= CLOSE_MARGIN]
    if len(close) == 1:
        wine = close[0]
        result["wine"] = wine
        cand_vintage = _cand_vintage(wine)
        rv = read.get("vintage")
        if rv and cand_vintage and rv != cand_vintage:
            result["status"] = "vintage_mismatch"
        else:
            result["status"] = "exact"
        return result

    result["status"] = "candidates"
    result["candidates"] = close[:MAX_CANDIDATES]
    return result
