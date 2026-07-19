"""
Deterministic (grape, region) -> structure profile, for wines Vivino can't
match. Structure is mostly grape-determined; region is a modifier (a Napa
Cabernet is bolder / softer-acid than a Bordeaux one). The grape is extracted
reliably (~80%) upstream; quantifying structure from a curated table beats
asking a small local LLM to guess 1-10 numbers (benchmark: tannin/acidity
inference is unreliable — see enrichment/extraction/structure_benchmark.py).

Output matches the structure_profile convention used by Vivino/GrapeMinds and
the scorer/StructureBars: {body, tannins, acidity} on a 1-10 scale, tagged
source='table'. Sweetness is NOT set here (almost everything is dry; off-dry/
sweet styles come from the LLM/Vivino). Precedence: Vivino's real measured
structure always wins — this only fills the unmatched gap.
"""
import re
import unicodedata
from typing import Optional, List, Dict, Any

# Base structure per grape (body / tannins / acidity, 1-10). Whites/rosé = tannins 1.
GRAPE_STRUCTURE: Dict[str, Dict[str, int]] = {
    # reds
    "Cabernet Sauvignon": {"body": 8, "tannins": 8, "acidity": 6},
    "Merlot":             {"body": 6, "tannins": 5, "acidity": 5},
    "Pinot Noir":         {"body": 4, "tannins": 4, "acidity": 7},
    "Syrah":              {"body": 8, "tannins": 7, "acidity": 6},
    "Shiraz":             {"body": 8, "tannins": 7, "acidity": 5},
    "Malbec":             {"body": 8, "tannins": 6, "acidity": 5},
    "Grenache":           {"body": 6, "tannins": 4, "acidity": 5},
    "Garnacha":           {"body": 6, "tannins": 4, "acidity": 5},
    "Tempranillo":        {"body": 6, "tannins": 6, "acidity": 6},
    "Sangiovese":         {"body": 6, "tannins": 7, "acidity": 8},
    "Nebbiolo":           {"body": 7, "tannins": 9, "acidity": 8},
    "Zinfandel":          {"body": 8, "tannins": 5, "acidity": 5},
    "Primitivo":          {"body": 8, "tannins": 5, "acidity": 5},
    "Cabernet Franc":     {"body": 6, "tannins": 6, "acidity": 6},
    "Petite Sirah":       {"body": 9, "tannins": 9, "acidity": 5},
    "Mourvèdre":          {"body": 7, "tannins": 7, "acidity": 5},
    "Monastrell":         {"body": 7, "tannins": 7, "acidity": 5},
    "Carmenère":          {"body": 7, "tannins": 6, "acidity": 5},
    "Gamay":              {"body": 3, "tannins": 3, "acidity": 7},
    "Barbera":            {"body": 5, "tannins": 4, "acidity": 8},
    "Dolcetto":           {"body": 5, "tannins": 5, "acidity": 5},
    "Montepulciano":      {"body": 7, "tannins": 6, "acidity": 6},
    "Nero d'Avola":       {"body": 7, "tannins": 6, "acidity": 5},
    "Tannat":             {"body": 8, "tannins": 10, "acidity": 6},
    "Touriga Nacional":   {"body": 8, "tannins": 8, "acidity": 6},
    "Aglianico":          {"body": 8, "tannins": 9, "acidity": 7},
    "Pinotage":           {"body": 7, "tannins": 6, "acidity": 5},
    "Corvina":            {"body": 5, "tannins": 4, "acidity": 6},
    "Carignan":           {"body": 6, "tannins": 6, "acidity": 6},
    "Cinsault":           {"body": 4, "tannins": 3, "acidity": 5},
    # whites (tannins always 1)
    "Chardonnay":         {"body": 6, "tannins": 1, "acidity": 5},
    "Sauvignon Blanc":    {"body": 3, "tannins": 1, "acidity": 8},
    "Riesling":           {"body": 3, "tannins": 1, "acidity": 8},
    "Pinot Grigio":       {"body": 3, "tannins": 1, "acidity": 6},
    "Pinot Gris":         {"body": 4, "tannins": 1, "acidity": 6},
    "Chenin Blanc":       {"body": 4, "tannins": 1, "acidity": 7},
    "Viognier":           {"body": 6, "tannins": 1, "acidity": 4},
    "Gewürztraminer":     {"body": 5, "tannins": 1, "acidity": 4},
    "Albariño":           {"body": 3, "tannins": 1, "acidity": 7},
    "Grüner Veltliner":   {"body": 4, "tannins": 1, "acidity": 7},
    "Sémillon":           {"body": 5, "tannins": 1, "acidity": 5},
    "Vermentino":         {"body": 3, "tannins": 1, "acidity": 7},
    "Torrontés":          {"body": 4, "tannins": 1, "acidity": 5},
    "Moscato":            {"body": 3, "tannins": 1, "acidity": 5},
    "Muscat":             {"body": 3, "tannins": 1, "acidity": 5},
    "Marsanne":           {"body": 6, "tannins": 1, "acidity": 4},
    "Roussanne":          {"body": 6, "tannins": 1, "acidity": 5},
    "Verdejo":            {"body": 4, "tannins": 1, "acidity": 7},
    "Garganega":          {"body": 4, "tannins": 1, "acidity": 6},
    "Melon de Bourgogne": {"body": 3, "tannins": 1, "acidity": 8},
    "Fiano":              {"body": 5, "tannins": 1, "acidity": 6},
    "Assyrtiko":          {"body": 5, "tannins": 1, "acidity": 8},
    "Grenache Blanc":     {"body": 5, "tannins": 1, "acidity": 4},
}

# Region modifier: delta applied to the base profile (clamped 1-10 after).
# Warm New World = riper/bolder/softer acid; cool climate = fresher/lighter;
# structured Old World = a touch more grip.
REGION_MODIFIERS: Dict[str, Dict[str, int]] = {
    # warm New World
    "Napa Valley":       {"body": 1, "tannins": 1, "acidity": -1},
    "Sonoma":            {"body": 0, "tannins": 0, "acidity": 1},   # cooler coast, fresher
    "Central Coast":     {"body": 1, "tannins": 0, "acidity": -1},
    "Paso Robles":       {"body": 1, "tannins": 1, "acidity": -1},
    "Other California":  {"body": 1, "tannins": 0, "acidity": -1},
    "California":        {"body": 1, "tannins": 0, "acidity": -1},
    "Mendoza":           {"body": 1, "tannins": 1, "acidity": -1},
    "Other Argentina":   {"body": 1, "tannins": 1, "acidity": -1},
    "Barossa Valley":    {"body": 1, "tannins": 1, "acidity": -1},
    "Other Australia":   {"body": 1, "tannins": 0, "acidity": -1},
    "Texas":             {"body": 1, "tannins": 0, "acidity": -1},
    "South Africa":      {"body": 0, "tannins": 0, "acidity": 0},
    # cool climate — fresher, lighter, higher acid
    "Willamette Valley": {"body": -1, "tannins": 0, "acidity": 1},
    "Burgundy":          {"body": -1, "tannins": 0, "acidity": 1},
    "Marlborough":       {"body": 0, "tannins": 0, "acidity": 1},
    "Other New Zealand": {"body": 0, "tannins": 0, "acidity": 1},
    "Germany":           {"body": -1, "tannins": 0, "acidity": 2},
    "Mosel":             {"body": -1, "tannins": 0, "acidity": 2},
    "Loire":             {"body": -1, "tannins": 0, "acidity": 1},
    "Chile":             {"body": 0, "tannins": 0, "acidity": 1},
    "Columbia Valley":   {"body": 0, "tannins": 0, "acidity": 1},
    # structured Old World
    "Bordeaux":          {"body": 0, "tannins": 1, "acidity": 0},
    "Piedmont":          {"body": 0, "tannins": 1, "acidity": 1},
    "Rhône":             {"body": 1, "tannins": 0, "acidity": -1},
    "Tuscany":           {"body": 0, "tannins": 1, "acidity": 1},
    "Rioja":             {"body": 0, "tannins": 0, "acidity": 0},
}


def _norm(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    return re.sub(r"\s+", " ", s).strip().lower()


_GRAPE_INDEX = {_norm(k): v for k, v in GRAPE_STRUCTURE.items()}
_REGION_INDEX = {_norm(k): v for k, v in REGION_MODIFIERS.items()}


def _clamp(v: int) -> int:
    return max(1, min(10, v))


def structure_for(varietal: Optional[str], grapes: Optional[List[str]],
                  region: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return a {body, tannins, acidity, source:'table'} structure profile for
    the wine's primary grape adjusted by its region, or None if the grape is
    unknown (region alone can't anchor a profile)."""
    names = [varietal] if varietal else []
    names += list(grapes or [])
    base = None
    for name in names:
        base = _GRAPE_INDEX.get(_norm(name))
        if base:
            break
    if base is None:
        return None

    mod = _REGION_INDEX.get(_norm(region)) if region else None
    out = {
        "body":    _clamp(base["body"]    + (mod or {}).get("body", 0)),
        "tannins": _clamp(base["tannins"] + (mod or {}).get("tannins", 0)),
        "acidity": _clamp(base["acidity"] + (mod or {}).get("acidity", 0)),
        "source":  "table",
    }
    return out


def structure_to_persist(varietal: Optional[str], grapes: Optional[List[str]],
                         region: Optional[str],
                         existing: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the table structure to WRITE for a wine, or None to skip.

    Precedence: vivino/grapeminds > table > llm. An existing profile is
    refreshable only if its source is explicitly 'table' or 'llm' (both are
    safe to overwrite with the table, which beats an LLM guess on body/
    tannins/acidity). Vivino (source 'vivino') and GrapeMinds (real data, no
    source key) are both preserved. When refreshing an 'llm' profile, its
    sweetness (which the table doesn't provide) is carried over. Returns None
    when there's no grape to anchor on.
    """
    if existing:
        src = existing.get("source")
        if src not in ("table", "llm"):   # None (grapeminds), 'vivino', etc. -> preserve
            return None
    base = structure_for(varietal, grapes, region)
    if base is None:
        return None   # no grape to anchor — leave any existing profile as-is
    if existing and existing.get("source") == "llm" and existing.get("sweetness") is not None:
        base = dict(base)
        base["sweetness"] = existing["sweetness"]
        if existing.get("sweetness_source"):
            base["sweetness_source"] = existing["sweetness_source"]
    return base
