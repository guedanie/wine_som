"""Vivino enrichment client.

Vivino's JSON API endpoints for name lookup are dead (404) and the explore
endpoint's q= param is popularity-ranked, not relevance-ranked. The HTML
search page (/search/wines?q=) does true name search, and the wine page
embeds full JSON stats — so this client works in two HTML requests:

  1. search_wine(query)   -> top /w/{id} hit + slug-similarity score
  2. fetch_ratings(match) -> wine-level ratings parsed from the page JSON

See data/exploration/vivino_findings.md for the probe history.
"""

import re
import subprocess
import urllib.parse
from typing import Any, Dict, Optional

BASE = "https://www.vivino.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Match /w/{id} links; slug segment precedes /w/
_WINE_LINK_RE = re.compile(r'href="(/[^"]*?/w/(\d+)[^"]*)"')
_SLUG_RE = re.compile(r"/([^/]+)/w/\d+")
_YEAR_PARAM_RE = re.compile(r"[?&]year=(\d{4})")
_VOLUME_RE = re.compile(r"\b\d+(\.\d+)?\s*(ml|ltr|l|liter|litre)s?\b", re.I)
_STATS_PAIR_RE = re.compile(r'"ratings_count":\s*(\d+)\s*,\s*"ratings_average":\s*([\d.]+)')

# Retail-listing junk that never appears in Vivino slugs
_JUNK_TOKENS = {"bottle", "750", "375", "1.5", "ml", "wine"}

# Low-information tokens: shared varietal/style words alone must never make a
# match ("Beringer Pinot Grigio" vs "frecciarossa-pinot-grigio" share only the
# varietal — different producer). A match needs >=1 distinctive shared token.
_LOW_INFO_TOKENS = {
    "pinot", "grigio", "gris", "noir", "blanc", "cabernet", "sauvignon",
    "chardonnay", "merlot", "syrah", "shiraz", "zinfandel", "riesling",
    "malbec", "tempranillo", "sangiovese", "grenache", "garnacha", "viognier",
    "moscato", "prosecco", "chianti", "rioja", "brut", "rosso", "bianco",
    "red", "white", "rose", "rosé", "sparkling", "blend", "reserve",
    "reserva", "estate", "vineyard", "vineyards", "cellars", "winery",
}

# Tokens stripped for the fallback search query when the full name gets no
# hits — Vivino's search chokes on over-specified retail names.
_QUERY_NOISE = {"white", "red", "rose", "rosé", "sparkling", "wine", "still",
                "california", "blend"}


def _get(url: str, timeout: int = 25) -> str:
    cmd = [
        "curl", "-s", "-L", "--max-time", str(timeout),
        "-H", f"User-Agent: {_UA}",
        "-H", "Accept-Language: en-US,en;q=0.9",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def clean_wine_name(name: str) -> str:
    """Strip volume suffixes and punctuation from a retail listing name."""
    s = _VOLUME_RE.sub(" ", name)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> set:
    toks = set(re.sub(r"[^\w\s]", " ", s.lower()).split())
    return toks - _JUNK_TOKENS


def match_score(query: str, slug: str) -> float:
    """Overlap coefficient between query tokens and slug tokens.

    The slug is canonical (producer + wine name); our retail names carry junk
    (volume, type suffixes), so overlap/min is forgiving of extra tokens on
    either side while still requiring genuine name agreement.
    """
    q = _tokens(query)
    s = _tokens(slug.replace("-", " "))
    if not q or not s:
        return 0.0
    inter = q & s
    if len(inter) < 2:
        return 0.0
    if not (inter - _LOW_INFO_TOKENS):
        return 0.0
    return len(inter) / min(len(q), len(s))


def build_query(name: str, brand: Optional[str]) -> str:
    """Combine brand + name for search unless the name already contains it."""
    cleaned = clean_wine_name(name)
    if brand:
        brand_toks = _tokens(brand)
        if brand_toks and not brand_toks <= _tokens(cleaned):
            return clean_wine_name(brand) + " " + cleaned
    return cleaned


def strip_query_noise(query: str) -> str:
    """Fallback query: drop style/region noise words that break Vivino search."""
    kept = [t for t in query.split() if t.lower() not in _QUERY_NOISE]
    return " ".join(kept)


def search_wine(query: str) -> Optional[Dict[str, Any]]:
    """Search Vivino by name; return the top hit with a slug-similarity score.

    Returns {"wine_id", "href", "slug", "year", "score"} or None if the
    search page yields no wine links.
    """
    url = BASE + "/search/wines?q=" + urllib.parse.quote(query)
    html = _get(url)
    if not html:
        return None
    best = None
    seen = set()
    for href, wid in _WINE_LINK_RE.findall(html):
        if wid in seen:
            continue
        seen.add(wid)
        slug_m = _SLUG_RE.search(href)
        if not slug_m:
            continue
        slug = slug_m.group(1)
        year_m = _YEAR_PARAM_RE.search(href.replace("&amp;", "&"))
        candidate = {
            "wine_id": int(wid),
            "href": href.replace("&amp;", "&"),
            "slug": slug,
            "year": int(year_m.group(1)) if year_m else None,
            "score": match_score(query, slug),
        }
        # Vivino's own ranking puts the right wine near the top, but not
        # always first — score every hit on the page and keep the best.
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def parse_wine_stats(page: str, wine_id: int) -> Optional[Dict[str, Any]]:
    """Extract wine-level (all-vintages) ratings from a wine page's embedded JSON.

    Anchors on the wine object ("id":{wine_id}) and reads the first
    statistics pair after it — that is the wine-level scope, distinct from
    the vintage-level stats and from recommended-wine carousels elsewhere
    on the page.
    """
    anchor = page.find('"id":%d' % wine_id)
    while anchor != -1:
        stats_idx = page.find('"statistics"', anchor)
        if stats_idx != -1 and stats_idx - anchor < 5000:
            m = _STATS_PAIR_RE.search(page, stats_idx, stats_idx + 800)
            if m:
                count = int(m.group(1))
                avg = float(m.group(2))
                if count > 0 and avg > 0:
                    return {"ratings_count": count, "ratings_average": avg}
        anchor = page.find('"id":%d' % wine_id, anchor + 1)
    return None


def fetch_ratings(match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fetch the wine page for a search match and parse wine-level ratings."""
    page = _get(BASE + match["href"])
    if not page:
        return None
    return parse_wine_stats(page, match["wine_id"])
