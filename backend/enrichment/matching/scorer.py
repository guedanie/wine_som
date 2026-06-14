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
_SIZE_RE = re.compile(r"^\d+(ml|l)?$")        # 750, 750ml, 1l
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
    if a in b or b in a:
        return 0.6
    return _jaccard(set(a.split()), set(b.split()))


def _color_score(wine_type: Optional[str], color: Optional[str]) -> float:
    if not wine_type or not color:
        return 0.5
    mapped = _COLOR_MAP.get(_normalize(color))
    if mapped is None:
        return 0.5
    return 1.0 if mapped == _normalize(wine_type) else 0.0
