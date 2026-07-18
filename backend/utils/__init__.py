"""Shared utilities used across scrapers and enrichment modules."""
import re
import unicodedata
from typing import Optional


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()

RED_VARIETALS = {
    "cabernet sauvignon", "cabernet", "merlot", "pinot noir", "syrah", "shiraz",
    "malbec", "zinfandel", "sangiovese", "tempranillo", "grenache", "red blend",
    "petit verdot", "petite sirah", "mourvedre", "nebbiolo", "barbera", "dolcetto",
    "montepulciano", "primitivo", "carmenere", "tannat",
    "touriga nacional", "touriga", "baga", "trincadeira", "tinto",
}
WHITE_VARIETALS = {
    "chardonnay", "sauvignon blanc", "pinot grigio", "pinot gris", "riesling",
    "albarino", "albariño", "viognier", "white blend", "moscato", "muscat",
    "gewurztraminer", "chenin blanc", "gruner veltliner", "vermentino",
    "torrontes", "torrontés", "roussanne", "marsanne", "verdejo", "semillon",
    "loureiro", "encruzado", "rabigato", "arinto", "alvarinho", "branco", "blanco",
}
SPARKLING_TERMS = {"prosecco", "champagne", "cava", "sparkling", "cremant",
                   "frizzante", "espumante", "spumante", "pet nat", "pet-nat",
                   "petnat", "petillant", "col fondo", "methode ancestrale",
                   "ancestral", "lambrusco", "franciacorta"}
ROSE_TERMS = {"rosé", "rose", "rosado", "rosato"}
DESSERT_TERMS = {"port", "porto", "tawny", "sherry", "madeira", "sauternes", "ice wine", "icewine", "late harvest"}


def infer_wine_type(text: str) -> Optional[str]:
    """Infer wine type (red/white/rosé/sparkling/dessert) from varietal or category text.
    Handles both Shopify product_type strings ('Red Wine') and varietal names ('Cabernet Sauvignon').
    """
    s = _fold(text)
    # Direct product type strings (e.g. from Shopify product_type field)
    if s in ("red wine", "red"):
        return "red"
    if s in ("white wine", "white"):
        return "white"
    if s in ("rose wine", "rose"):
        return "rosé"
    if s in ("sparkling wine", "sparkling", "champagne"):
        return "sparkling"
    if s in ("orange wine", "orange"):
        return "orange"
    if s in ("fortified wine", "vermouth"):
        return "fortified"
    if s in ("dessert wine",):
        return "dessert"
    # Varietal / keyword matching — WORD boundaries, not substrings: 'port' in
    # 'Portuguese' classified 28 Portuguese table wines as dessert, and 'rose'
    # in 'Primrose' made a Chardonnay rosé.
    def _has(term: str) -> bool:
        return bool(re.search(rf"\b{re.escape(term)}\b", s))

    if any(_has(t) for t in SPARKLING_TERMS):
        return "sparkling"
    if any(_has(t) for t in ROSE_TERMS):
        return "rosé"
    if any(_has(t) for t in DESSERT_TERMS):
        return "dessert"
    if any(_has(t) for t in RED_VARIETALS):
        return "red"
    if any(_has(t) for t in WHITE_VARIETALS):
        return "white"
    # generic color words as a last resort ('Portuguese Red Wine')
    if _has("red"):
        return "red"
    if _has("white"):
        return "white"
    return None
