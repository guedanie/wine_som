"""Canonical non-wine detection for the catalog (CLAUDE.md item 32).

Grocery scrapers pull non-wine products into `wines` (fruit cocktail, sake, beer,
cough syrup, glassware). This module is the single source of truth for detecting
them. `is_non_wine_name` is a whole-word deny-list match (shared with the wine_type
backfill). `should_exclude` is the conservative PURGE gate — it adds guards so a real
wine is never dropped.
"""
import re
from typing import Any, Dict, List, Optional

# Whole-word markers of clearly non-wine products. Deliberately EXCLUDES tokens that
# collide with real wines: bourbon/rum/brandy (barrel-aged wines), water/soda
# (Hampton Water rosé, Soda Canyon), martini (Martini Asti), stout (Stout Family),
# opener ("Road Opener"), punch. Wine-adjacent products (vermouth, sangria,
# wine-cocktails) are intentionally NOT here — they're kept.
NON_WINE_MARKERS = (
    # fermented non-grape / rice
    "sake", "junmai", "daiginjo", "ginjo", "nigori", "mead",
    # beer
    "beer", "ale", "lager", "ipa", "pilsner", "kombucha",
    # non-alcoholic / soft
    "non-alcoholic", "non alcoholic", "nonalcoholic", "alcohol removed",
    "alcohol-removed", "zero proof", "seltzer", "hard cider", "cider",
    "lemonade", "limeade", "iced tea", "sweet tea", "sparkling water",
    "tonic water", "energy drink",
    # cocktails / RTD noise (fruit cocktail is food; wine-cocktails carry a varietal
    # and are protected by the wine-signal guard)
    "cocktail", "cocktails",
    # food / grocery
    "maple syrup", "pancake", "waffle", "grapefruit", "fruit cup", "oatmeal",
    "grits", "fruit wine", "apple wine", "peach wine", "plum wine", "syrup",
    "cookies and cream", "cookies & cream", "cough syrup", "cough",
    # merchandise / accessories
    "gift set", "gift basket", "glassware", "corkscrew", "decanter", "tumbler",
    "wine opener",
)

# Insurance for un-enriched real wines that collide with a marker. Normalized
# (lowercase) name fragments — if present, never exclude.
_ALLOWLIST = (
    "hampton water", "summer water", "road opener",
)


def matched_marker(name: Optional[str]) -> Optional[str]:
    """The first non-wine marker that whole-word matches `name`, else None."""
    low = (name or "").lower()
    for m in NON_WINE_MARKERS:
        if re.search(rf"\b{re.escape(m)}\b", low):
            return m
    return None


def is_non_wine_name(name: Optional[str]) -> bool:
    """True when the name whole-word matches a non-wine marker."""
    return matched_marker(name) is not None


def should_exclude(wine: Dict[str, Any]) -> bool:
    """Conservative purge gate: True only when the name is flagged AND every guard
    passes — barrel guard (barrel-aged wines), wine-signal guard (a real varietal or
    grape), and the allowlist. Errs toward keeping."""
    name = wine.get("name") or ""
    if not is_non_wine_name(name):
        return False
    low = name.lower()
    if "barrel" in low:
        return False
    if wine.get("varietal") or (wine.get("grapes") or []):
        return False
    if any(frag in low for frag in _ALLOWLIST):
        return False
    return True
