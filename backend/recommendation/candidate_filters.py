"""Pure candidate-shaping helpers for the recommend endpoint: NULL wine_type
resolution + hard type gate, fuzzy store detection, and candidate merge/dedup.
Kept free of I/O so they unit-test without a DB (the router wires them)."""
import difflib
import re
from typing import Any, Dict, List, Optional

from utils import infer_wine_type


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
    parsed message intent."""
    types = set(t for t in (chip_types or []) if t)
    if parsed_type:
        types.add(parsed_type)
    return types
