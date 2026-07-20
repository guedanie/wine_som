"""Pure candidate-shaping helpers for the recommend endpoint: NULL wine_type
resolution + hard type gate, fuzzy store detection, and candidate merge/dedup.
Kept free of I/O so they unit-test without a DB (the router wires them)."""
import difflib
import re
from typing import Any, Dict, List, Optional

from utils import infer_wine_type

# Generic wine words that don't identify a specific bottle — dropped when
# tokenizing a wine name for name search / narrative reconcile.
_GENERIC_WINE_WORDS = {
    "cabernet", "sauvignon", "merlot", "pinot", "noir", "gris", "grigio", "chardonnay",
    "syrah", "shiraz", "zinfandel", "malbec", "tempranillo", "sangiovese", "nebbiolo",
    "grenache", "mourvedre", "carignan", "riesling", "blanc", "chenin", "viognier",
    "barbera", "tannat", "red", "white", "rose", "wine", "blend", "reserve", "reserva",
    "vineyard", "vineyards", "valley", "county", "napa", "sonoma", "paso", "robles",
    "california", "italian", "the", "and", "estate", "old", "vine", "vines", "cuvee",
}


def significant_name_tokens(name: Optional[str]) -> List[str]:
    """Lowercased 3+ char tokens of a wine name, minus generic varietal/geo words —
    the distinctive producer/bottle tokens to search or reconcile on."""
    return [t for t in re.findall(r"[a-z0-9é]{3,}", (name or "").lower())
            if t not in _GENERIC_WINE_WORDS]


def rank_name_matches(candidates: List[Dict[str, Any]],
                      tokens: List[str]) -> List[Dict[str, Any]]:
    """Keep candidates whose name contains at least one search token, ordered by
    how many tokens matched (all-token matches first). Empty tokens → []."""
    if not tokens:
        return []
    scored = []
    for c in candidates:
        name = (c.get("name") or "").lower()
        hits = sum(1 for t in tokens if t in name)
        if hits:
            scored.append((hits, c))
    scored.sort(key=lambda hc: hc[0], reverse=True)
    return [c for _, c in scored]


def resolve_wine_type(wine: Dict[str, Any]) -> Optional[str]:
    """Return the wine's type, inferring from varietal -> name -> first grape
    when the stored wine_type is NULL. None only when nothing resolves."""
    if wine.get("wine_type"):
        return wine["wine_type"]
    for text in (wine.get("varietal"), wine.get("name"),
                 (wine.get("grapes") or [None])[0]):
        if text:
            t = infer_wine_type(text)
            if t:
                return t
    return None


def apply_type_gate(candidates: List[Dict[str, Any]],
                    requested_types: set) -> List[Dict[str, Any]]:
    """Resolve each candidate's NULL wine_type (written back in place), then, when
    the user requested one or more types, drop candidates whose resolved type is
    KNOWN and not requested. Unresolvable (None) types are kept — benefit of the
    doubt. Fails open (returns the input) if the gate would empty the pool."""
    for c in candidates:
        if not c.get("wine_type"):
            c["wine_type"] = resolve_wine_type(c)
    if not requested_types:
        return candidates
    kept = [c for c in candidates
            if c.get("wine_type") is None or c["wine_type"] in requested_types]
    return kept or candidates


def requested_types_from(chip_types: Optional[List[str]],
                         parsed_type: Optional[str]) -> set:
    """The set of wine types the user explicitly asked for — UI chips plus the
    parsed message intent. 'dessert' also accepts 'fortified' (the intent enum
    has no fortified value, so Port/Sherry — typed fortified — surface under a
    dessert/after-dinner ask). One-directional."""
    types = set(t for t in (chip_types or []) if t)
    if parsed_type:
        types.add(parsed_type)
    if "dessert" in types:
        types.add("fortified")
    return types


# Generic tokens that don't distinguish one store from another.
_STORE_STOPWORDS = {
    "the", "and", "wine", "wines", "market", "shop", "store", "plus",
    "natural", "heb", "h-e-b", "heb's", "central",
    # geographic / descriptor words that also appear in wine names & regions —
    # too generic to distinguish a store, and prone to false fuzzy matches
    "heights", "oak", "oaks", "valley", "park", "hill", "hills", "creek",
    "ridge", "coast", "river", "springs", "grove", "lake", "mountain",
    "village", "canyon", "vista", "view",
}


def _store_tokens(s: str) -> List[str]:
    words = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
    return [w for w in words if len(w) > 2 and w not in _STORE_STOPWORDS]


def detect_store(message: str, nearby_stores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Fuzzy-match a store named in the message against the nearby stores.
    Tolerates typos ('lincon'); returns None when no distinctive store token
    matches (e.g. only the retailer word 'heb' appears)."""
    msg = _store_tokens(message)
    if not msg:
        return None
    best, best_score = None, 0
    for st in nearby_stores:
        name_toks = _store_tokens(st.get("name", ""))
        score = sum(1 for nt in name_toks
                    if difflib.get_close_matches(nt, msg, n=1, cutoff=0.8))
        # strict > keeps the first (nearest, since nearby_stores is distance-ordered) on ties
        if score > best_score:
            best, best_score = st, score
    return best if best_score >= 1 else None


def merge_candidates(breadth: List[Dict[str, Any]],
                     targeted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Union breadth + targeted candidate dicts, deduped by (wine_id, store_ref)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in list(breadth) + list(targeted):
        key = (c.get("wine_id"), c.get("store_ref"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
