"""Vivino enrichment client.

Vivino's JSON API endpoints for name lookup are dead (404) and the explore
endpoint's q= param is popularity-ranked, not relevance-ranked. The HTML
search page (/search/wines?q=) does true name search, and the wine page
embeds full JSON stats — so this client works in two HTML requests:

  1. search_wine(query, client)   -> top /w/{id} hit + slug-similarity score
  2. fetch_ratings(match, client) -> wine-level ratings parsed from the page JSON

Both functions are async. Callers should share a single httpx.AsyncClient
across concurrent enrichment tasks to reuse connections.

See data/exploration/vivino_findings.md for the probe history.
"""

import asyncio
import re
import urllib.parse
from typing import Any, Dict, Optional

import httpx

BASE = "https://www.vivino.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}

# Match /w/{id} links; slug segment precedes /w/
_WINE_LINK_RE = re.compile(r'href="(/[^"]*?/w/(\d+)[^"]*)"')
_SLUG_RE = re.compile(r"/([^/]+)/w/\d+")
_YEAR_PARAM_RE = re.compile(r"[?&]year=(\d{4})")
_VOLUME_RE = re.compile(r"\b\d+(\.\d+)?\s*(ml|ltr|l|liter|litre)s?\b", re.I)
_STATS_PAIR_RE = re.compile(r'"ratings_count":\s*(\d+)\s*,\s*"ratings_average":\s*([\d.]+)')
_BOTTLE_MEDIUM_RE = re.compile(r'"bottle_medium":"(//[^"]+)"')

# Wine-object attribute regexes — anchored on the wine id, applied to a bounded
# window so we read this wine's data, not the recommended-wines carousel's.
_REGION_RE = re.compile(r'"region":\{"id":\d+,"name":"([^"]+)"')
_COUNTRY_RE = re.compile(r'"country":\{"code":"[^"]*","name":"([^"]+)"')
_ALCOHOL_RE = re.compile(r'"alcohol":([\d.]+)')
_BASELINE_RE = re.compile(
    r'"baseline_structure":\{'
    r'"acidity":(null|[\d.]+),'
    r'"fizziness":(null|[\d.]+),'
    r'"intensity":(null|[\d.]+),'
    r'"sweetness":(null|[\d.]+),'
    r'"tannin":(null|[\d.]+)\}'
)
_NAME_RE = re.compile(r'"name":"([^"]+)"')

# On the real page the wine object spans ~33KB (region blob is huge) and the
# recommended-wines carousel starts ~55KB past the anchor — 40KB covers ours
# and excludes theirs.
_ATTR_WINDOW = 40000

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


class VivinoFetchError(Exception):
    """The HTTP fetch itself failed (rate-limit, network) — distinct from a
    successful fetch with no results. Callers must NOT record 'no match'."""


async def _get(url: str, client: httpx.AsyncClient, timeout: int = 25) -> Optional[str]:
    """Return the page text, or None when the fetch failed (non-200 / network).

    A 429 block page parses as 'no wine links' — indistinguishable from a
    genuine empty result — so status must be checked here, not downstream.
    """
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=timeout)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return resp.text


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


async def search_wine(
    query: str,
    client: httpx.AsyncClient,
    delay: float = 0.3,
) -> Optional[Dict[str, Any]]:
    """Search Vivino by name; return the top hit with a slug-similarity score.

    Returns {"wine_id", "href", "slug", "year", "score"} or None if the
    search page yields no wine links. Raises VivinoFetchError when the fetch
    itself fails (rate-limit/network) — the caller must not treat that as a miss.

    delay: seconds to sleep before the HTTP request (rate-limiting).
    """
    if delay:
        await asyncio.sleep(delay)
    url = BASE + "/search/wines?q=" + urllib.parse.quote(query)
    html = await _get(url, client)
    if html is None:
        raise VivinoFetchError(f"search fetch failed: {query!r}")
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
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def parse_wine_stats(page: str, wine_id: int) -> Optional[Dict[str, Any]]:
    """Extract wine-level ratings and bottle image from a wine page's embedded JSON.

    Anchors on the wine object ("id":{wine_id}) for ratings. The bottle image
    sits at the vintage level (before the wine id in the JSON), so it's read
    from the first "bottle_medium" occurrence on the page — which is always the
    hero wine on a /w/{id} detail page, not a carousel recommendation.

    Returns {"ratings_count", "ratings_average", "image_url"} or None if no
    ratings found for wine_id.
    """
    # Image: first bottle_medium on page (vintage wraps the wine — appears before wine id)
    img_m = _BOTTLE_MEDIUM_RE.search(page)
    image_url = ("https:" + img_m.group(1)) if img_m else None

    anchor = page.find('"id":%d' % wine_id)
    while anchor != -1:
        stats_idx = page.find('"statistics"', anchor)
        if stats_idx != -1 and stats_idx - anchor < 5000:
            m = _STATS_PAIR_RE.search(page, stats_idx, stats_idx + 800)
            if m:
                count = int(m.group(1))
                avg = float(m.group(2))
                if count > 0 and avg > 0:
                    return {"ratings_count": count, "ratings_average": avg, "image_url": image_url}
        anchor = page.find('"id":%d' % wine_id, anchor + 1)
    return None


def _extract_array(page: str, key: str) -> Optional[str]:
    """Return the text of the first `"key":[...]` array via bracket counting."""
    m = re.search(r'"%s":\[' % key, page)
    if not m:
        return None
    start = m.end() - 1
    depth = 0
    for i in range(start, min(len(page), start + 20000)):
        c = page[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return page[start:i + 1]
    return None


def _num_or_none(token: str) -> Optional[float]:
    return None if token == "null" else float(token)


def parse_wine_attributes(page: str, wine_id: int) -> Optional[Dict[str, Any]]:
    """Extract canonical wine attributes from the wine page's embedded JSON.

    Anchors on the wine object ("id":{wine_id}) and reads within a bounded
    window — this skips the localization strings earlier in the page (where
    "grapes" is a UI label, not data) and stops short of the recommended-wines
    carousel. Returns None when the wine id isn't on the page; individual
    attributes missing from the page come back as None/[].
    """
    anchor = page.find('"id":%d' % wine_id)
    if anchor == -1:
        return None
    window = page[anchor:anchor + _ATTR_WINDOW]

    region_m = _REGION_RE.search(window)
    country_m = _COUNTRY_RE.search(window)
    alcohol_m = _ALCOHOL_RE.search(window)

    grapes_arr = _extract_array(window, "grapes")
    foods_arr = _extract_array(window, "foods")
    # foods objects nest a background_image whose keys carry no "name",
    # so a flat name scan inside the array text is safe for both arrays.
    grapes = _NAME_RE.findall(grapes_arr) if grapes_arr else []
    foods = _NAME_RE.findall(foods_arr) if foods_arr else []

    structure = None
    base_m = _BASELINE_RE.search(window)
    if base_m:
        structure = {
            "acidity":   _num_or_none(base_m.group(1)),
            "fizziness": _num_or_none(base_m.group(2)),
            "intensity": _num_or_none(base_m.group(3)),
            "sweetness": _num_or_none(base_m.group(4)),
            "tannin":    _num_or_none(base_m.group(5)),
        }

    return {
        "grapes": grapes,
        "foods": foods,
        "region": region_m.group(1) if region_m else None,
        "country": country_m.group(1) if country_m else None,
        "abv": float(alcohol_m.group(1)) if alcohol_m else None,
        "structure": structure,
    }


def structure_to_profile(structure: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert Vivino baseline_structure (1-5) to the GrapeMinds structure_profile
    convention (1-10) used by the scorer and the dossier StructureBars.

    intensity maps to body; fizziness has no equivalent and is dropped. The
    "source" marker lets downstream consumers prefer GrapeMinds when both exist.
    """
    if not structure:
        return None
    mapping = {"acidity": "acidity", "tannin": "tannins",
               "sweetness": "sweetness", "intensity": "body"}
    out = {}
    for src, dst in mapping.items():
        v = structure.get(src)
        if v is not None:
            out[dst] = round(v * 2, 1)
    if not out:
        return None
    out["source"] = "vivino"
    return out


async def fetch_ratings(
    match: Dict[str, Any],
    client: httpx.AsyncClient,
    delay: float = 0.3,
) -> Optional[Dict[str, Any]]:
    """Fetch the wine page for a search match and parse wine-level ratings.

    Raises VivinoFetchError when the fetch fails (rate-limit/network).

    delay: seconds to sleep before the HTTP request (rate-limiting).
    """
    if delay:
        await asyncio.sleep(delay)
    page = await _get(BASE + match["href"], client)
    if page is None:
        raise VivinoFetchError(f"wine page fetch failed: {match['href']}")
    stats = parse_wine_stats(page, match["wine_id"])
    if stats is not None:
        stats["attributes"] = parse_wine_attributes(page, match["wine_id"])
    return stats
