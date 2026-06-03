"""Shared utilities used across scrapers and enrichment modules."""
from typing import Optional

RED_VARIETALS = {
    "cabernet sauvignon", "cabernet", "merlot", "pinot noir", "syrah", "shiraz",
    "malbec", "zinfandel", "sangiovese", "tempranillo", "grenache", "red blend",
    "petit verdot", "petite sirah", "mourvedre", "nebbiolo", "barbera", "dolcetto",
    "montepulciano", "primitivo", "carmenere", "tannat",
}
WHITE_VARIETALS = {
    "chardonnay", "sauvignon blanc", "pinot grigio", "pinot gris", "riesling",
    "albarino", "albariño", "viognier", "white blend", "moscato", "muscat",
    "gewurztraminer", "chenin blanc", "gruner veltliner", "vermentino",
    "torrontes", "torrontés", "roussanne", "marsanne", "verdejo",
}
SPARKLING_TERMS = {"prosecco", "champagne", "cava", "sparkling", "cremant", "crémant", "frizzante"}
ROSE_TERMS = {"rosé", "rose", "rosado", "rosato"}
DESSERT_TERMS = {"port", "sherry", "madeira", "sauternes", "ice wine", "icewine", "late harvest"}


def infer_wine_type(text: str) -> Optional[str]:
    """Infer wine type (red/white/rosé/sparkling/dessert) from varietal or category text."""
    s = text.lower()
    if any(t in s for t in SPARKLING_TERMS):
        return "sparkling"
    if any(t in s for t in ROSE_TERMS):
        return "rosé"
    if any(t in s for t in DESSERT_TERMS):
        return "dessert"
    if any(t in s for t in RED_VARIETALS):
        return "red"
    if any(t in s for t in WHITE_VARIETALS):
        return "white"
    return None
