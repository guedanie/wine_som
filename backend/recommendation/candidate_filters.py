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
