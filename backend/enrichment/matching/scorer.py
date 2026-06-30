"""
Rule-based GrapeMinds match scorer.

Scores a GrapeMinds search hit against one of our wines using only fields the
SEARCH response carries (display_name, producer_name, color) — grapes/region
are not available until the detail fetch. Pure functions, no I/O.

    confidence = producer_score * 0.45 + color_score * 0.25 + name_score * 0.30
"""
import re
from typing import Optional, List, Dict, Any

PRODUCER_WEIGHT = 0.45
COLOR_WEIGHT = 0.25
NAME_WEIGHT = 0.30

# Maps a GrapeMinds `color` to our wines.wine_type vocabulary.
_COLOR_MAP = {"red": "red", "white": "white", "rosé": "rosé", "rose": "rosé"}

# Generic wine words + geography that add no discriminating power.
_STOPWORDS = {
    "wine", "red", "white", "rosé", "rose", "sparkling", "blanc", "the", "de", "di",
    "california", "italy", "italian", "france", "french", "spain", "spanish",
    "argentina", "chile", "australia", "new", "zealand", "napa", "valley", "sonoma",
    "county", "paso", "robles", "lodi", "marlborough",
}
_SIZE_RE = re.compile(r"^(\d+(ml|l|cl|oz)?|ml|l|cl|oz)$")  # 750, 750ml, 1l, bare "ml"/"l"
_VINTAGE_RE = re.compile(r"^(19|20)\d{2}$")   # 1999, 2021


def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàáâäãåèéêëìíîïòóôöõùúûüñç]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> set:
    return {t for t in _normalize(s).split() if t}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _producer_score(brand: Optional[str], producer_name: Optional[str]) -> float:
    if not brand:
        return 0.0
    a, b = _normalize(brand), _normalize(producer_name or "")
    if not b:
        return 0.0
    if a == b:
        return 1.0
    a_tokens, b_tokens = set(a.split()), set(b.split())
    # All tokens of the shorter are in the longer (e.g. "Rombauer" ⊂ "Rombauer Vineyards")
    if a_tokens <= b_tokens or b_tokens <= a_tokens:
        return 0.85
    if a in b or b in a:
        return 0.6
    return _jaccard(a_tokens, b_tokens)


def _color_score(wine_type: Optional[str], color: Optional[str]) -> float:
    if not wine_type or not color:
        return 0.5
    mapped = _COLOR_MAP.get(_normalize(color))
    if mapped is None:
        return 0.5
    return 1.0 if mapped == _normalize(wine_type) else 0.0


def _content_tokens(s: str) -> set:
    out = set()
    for t in _tokens(s):
        if t in _STOPWORDS or _SIZE_RE.match(t) or _VINTAGE_RE.match(t):
            continue
        out.add(t)
    return out


def _name_score(our_name: Optional[str], display_name: Optional[str]) -> float:
    return _jaccard(_content_tokens(our_name or ""), _content_tokens(display_name or ""))


def _score_hit(hit: Dict[str, Any], brand, wine_type, name) -> float:
    score = (
        _producer_score(brand, hit.get("producer_name")) * PRODUCER_WEIGHT
        + _color_score(wine_type, hit.get("color")) * COLOR_WEIGHT
        + _name_score(name, hit.get("display_name")) * NAME_WEIGHT
    )
    return round(max(0.0, min(1.0, score)), 3)


def score_candidates(
    hits: List[Dict[str, Any]],
    brand: Optional[str],
    wine_type: Optional[str],
    name: Optional[str],
    keep: int = 3,
) -> List[Dict[str, Any]]:
    """
    Rank GrapeMinds search hits and return the top `keep` as candidate dicts:
      {grapeminds_id, display_name, producer_name, color, confidence, rank, is_primary}
    Dedupes by grapeminds_id, sorts by confidence desc (stable), marks rank 1 primary.
    """
    seen = set()
    scored = []
    for hit in hits:
        gid = str(hit.get("id", ""))
        if not gid or gid in seen:
            continue
        seen.add(gid)
        scored.append({
            "grapeminds_id": gid,
            "display_name": hit.get("display_name"),
            "producer_name": hit.get("producer_name"),
            "color": hit.get("color"),
            "confidence": _score_hit(hit, brand, wine_type, name),
        })

    scored.sort(key=lambda c: c["confidence"], reverse=True)
    top = scored[:keep]
    for i, c in enumerate(top):
        c["rank"] = i + 1
        c["is_primary"] = (i == 0)
    return top
