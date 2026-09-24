"""Web search for a named bottle confirmed absent from the catalog.

The gate is computed here from data recommendation/availability.py already
produces every turn (the availability oracle's fact list) -- never left to
model discretion, matching the architecture's existing rule that absence and
identity are counted facts, not recalled ones (see items 39-42 of the build
log). Design: docs/superpowers/specs/2026-09-23-web-search-off-catalog-bottle-design.md
"""
from typing import Any, Dict, List

from recommendation.availability import NOT_IN_CATALOG

# Anthropic's server-side web search tool. Attached to the API call ONLY when
# off_catalog_bottles() below returns something -- never on an ordinary turn.
# max_uses=1 caps one gated turn to a single search (cost/safety control).
# allowed_domains is deliberately small: fewer, trustworthy wine sources over
# broad recall, matching the app's conservative-enrichment stance. Revisit only
# if a real query comes back empty because a legitimate source was excluded --
# don't pre-expand speculatively.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 1,
    "allowed_domains": [
        "wine-searcher.com",
        "vivino.com",
        "winespectator.com",
        "decanter.com",
        "jancisrobinson.com",
        "wine.com",
    ],
}


def off_catalog_bottles(facts: List[Dict[str, Any]]) -> List[str]:
    """Named bottles (availability axis kind 'name') that resolved NOT_IN_CATALOG
    this turn. Empty in the common case -- nothing to search for."""
    out = []
    for f in facts:
        axis = f.get("axis") or {}
        if axis.get("kind") == "name" and f.get("state") == NOT_IN_CATALOG:
            value = axis.get("value")
            if value:
                out.append(value)
    return out


def should_offer_web_search(facts: List[Dict[str, Any]]) -> bool:
    """True when at least one named bottle this turn is confirmed off-catalog."""
    return bool(off_catalog_bottles(facts))


def off_catalog_directive(bottles: List[str]) -> str:
    """Per-turn user-message directive naming exactly the off-catalog bottle(s) a
    search may cover -- never the whole catalog, never a bottle already resolved
    PRESENT_*. Empty string when there's nothing to license."""
    if not bottles:
        return ""
    joined = ", ".join(f'"{b}"' for b in bottles)
    subject = "this bottle" if len(bottles) == 1 else "these bottles"
    return (
        f"\n\n[OFF-CATALOG BOTTLE]\n{joined} -- not in the local catalog. A web "
        f"search tool is available this turn if it would help answer the "
        f"user's question about {subject}. If you use it, you must still call "
        f"recommend_wines with your narrative and picks -- never end the turn "
        f"on a search alone."
    )
