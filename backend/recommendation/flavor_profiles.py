"""
Curated grape/region -> flavor-tag knowledge for the recommendation scorer.
Lets the deterministic scorer infer flavor as a fact about the wine (e.g. a
Grenache/Syrah/Mourvèdre Rhône blend is 'earthy/savory') without embeddings.

Follows the cheat-sheet pattern of enrichment/extraction/reference.py.
Flavor tags are a small controlled vocabulary shared with recommendation.intent.
"""
import re
import unicodedata
from typing import Optional, List, Set

# Controlled flavor vocabulary (keep in sync with recommendation.intent prompt).
FLAVOR_VOCAB = {
    "earthy", "bold", "savory", "light", "peppery", "structured", "herbal",
    "red-fruit", "black-fruit", "dark-fruit", "tart-cherry", "spice", "gamey",
    "garrigue", "ripe",
}

GRAPE_FLAVORS = {
    "Cabernet Sauvignon": {"bold", "structured", "black-fruit"},
    "Merlot": {"red-fruit", "ripe", "herbal"},
    "Pinot Noir": {"light", "red-fruit", "earthy"},
    "Syrah": {"peppery", "savory", "dark-fruit"},
    "Shiraz": {"bold", "ripe", "dark-fruit", "spice"},
    "Malbec": {"bold", "dark-fruit", "ripe"},
    "Grenache": {"earthy", "red-fruit", "spice"},
    "Garnacha": {"earthy", "red-fruit", "spice"},
    "Tempranillo": {"savory", "red-fruit", "earthy"},
    "Sangiovese": {"earthy", "savory", "tart-cherry", "herbal"},
    "Nebbiolo": {"structured", "earthy", "tart-cherry"},
    "Zinfandel": {"bold", "ripe", "spice"},
    "Primitivo": {"bold", "ripe", "spice"},
    "Cabernet Franc": {"herbal", "red-fruit", "earthy"},
    "Petite Sirah": {"bold", "structured", "dark-fruit"},
    "Mourvèdre": {"earthy", "savory", "gamey"},
    "Monastrell": {"earthy", "savory", "gamey"},
    "Carmenère": {"herbal", "dark-fruit", "peppery"},
    "Gamay": {"light", "red-fruit"},
    "Barbera": {"savory", "tart-cherry", "red-fruit"},
    "Montepulciano": {"savory", "dark-fruit", "earthy"},
    "Tannat": {"bold", "structured", "dark-fruit"},
    "Touriga Nacional": {"bold", "dark-fruit", "structured"},
    "Chardonnay": {"ripe", "structured"},
    "Sauvignon Blanc": {"herbal", "light"},
    "Riesling": {"light", "spice"},
    "Pinot Grigio": {"light"},
    "Pinot Gris": {"light"},
    "Chenin Blanc": {"light", "ripe"},
    "Viognier": {"ripe", "spice"},
    "Albariño": {"light", "savory"},
    "Grüner Veltliner": {"herbal", "spice", "savory"},
}

REGION_FLAVORS = {
    "Rhône": {"earthy", "garrigue", "savory", "peppery"},
    "Burgundy": {"earthy", "red-fruit"},
    "Bordeaux": {"structured", "black-fruit", "herbal"},
    "Beaujolais": {"light", "red-fruit"},
    "Tuscany": {"earthy", "savory", "tart-cherry"},
    "Piedmont": {"structured", "earthy", "tart-cherry"},
    "Rioja": {"savory", "red-fruit", "earthy"},
    "Napa Valley": {"bold", "ripe", "black-fruit"},
    "Sonoma": {"ripe", "red-fruit"},
    "Central Coast": {"ripe", "red-fruit"},
    "Willamette Valley": {"light", "earthy", "red-fruit"},
    "Mendoza": {"bold", "dark-fruit", "ripe"},
    "Barossa Valley": {"bold", "ripe", "spice"},
    "Texas": {"bold", "ripe"},
}


def _norm(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    return re.sub(r"\s+", " ", s).strip().lower()


_GRAPE_INDEX = {_norm(k): v for k, v in GRAPE_FLAVORS.items()}
_REGION_INDEX = {_norm(k): v for k, v in REGION_FLAVORS.items()}


def flavor_tags_for(varietal: Optional[str], grapes: Optional[List[str]],
                    region: Optional[str]) -> Set[str]:
    """Union of flavor tags implied by a wine's grape(s) + region. Empty if unknown."""
    tags: Set[str] = set()
    names = list(grapes or [])
    if varietal:
        names.append(varietal)
    for name in names:
        tags |= _GRAPE_INDEX.get(_norm(name), set())
    if region:
        tags |= _REGION_INDEX.get(_norm(region), set())
    return tags


def infer_body(tags: Set[str]) -> Optional[str]:
    """Infer a body bucket from flavor tags when a wine's body column is null."""
    if "light" in tags:
        return "light"
    if "bold" in tags or "structured" in tags:
        return "full"
    return None
