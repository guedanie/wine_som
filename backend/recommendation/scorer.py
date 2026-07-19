import re
import unicodedata
from typing import List, Dict, Any
from recommendation.flavor_profiles import flavor_tags_for, infer_body
from recommendation.structure_profiles import structure_for

# Axis weights
_W_TYPE = 3.0
_W_BODY = 2.0
_W_GRAPE = 2.0
_W_REGION = 1.5
_W_FLAVOR_TAG = 1.0      # per matched flavor tag, capped
_FLAVOR_CAP = 3.0
_W_BUDGET = 1.0
_W_TIER = 0.5
_W_RATING = 1.5          # max community-rating boost (never a penalty)
_MIN_RATINGS = 25        # below this, the rating is noise — ignore it
_W_SIMILAR = 2.5         # max personalization boost for resembling a wine the user liked
_W_DISLIKE = 2.0         # max penalty for resembling a wine the user disliked (thumbs-down)
_SIM_FULL = 3.0          # raw-similarity value that earns the full boost/penalty

# Taste-profile nudges — softer than an explicit request, and only fill a
# dimension the request left unspecified (the request always wins).
_W_PROFILE_REGION = 1.0
_W_PROFILE_BODY = 1.0
_W_PROFILE_LEAN = 0.75
_LEAN_TYPES = {
    "bold_red": {"red"}, "elegant_red": {"red"},
    "crisp_white": {"white"}, "rich_white": {"white"},
    "rose_sparkling": {"rosé", "rose", "sparkling"},
}

# 'Red blend' / 'white blend' asks match any wine of that type with a 2+
# grape blend — Bordeaux/GSM wines carry real grape arrays, not the literal
# label, so set-intersection alone can't see them.
_BLEND_WANTS = {"red blend": "red", "white blend": "white"}


def _blend_match(want_grapes: set, wine_type, grapes_col) -> bool:
    if len(grapes_col or []) < 2:
        return False
    return any(want in want_grapes and wine_type == wtype
               for want, wtype in _BLEND_WANTS.items())


def _norm_liked(liked_wines) -> List[Dict[str, Any]]:
    """Normalize the user's liked wines once (grapes/region/flavors as sets)."""
    out = []
    for lw in liked_wines or []:
        grapes = {_norm(g) for g in (lw.get("grapes") or [])}
        if lw.get("varietal"):
            grapes.add(_norm(lw["varietal"]))
        flavors = {_norm(f) for f in (lw.get("flavors") or [])}
        flavors |= flavor_tags_for(lw.get("varietal"), lw.get("grapes"), lw.get("region"))
        out.append({
            "name": lw.get("name"), "wine_id": lw.get("wine_id"), "source": lw.get("source"),
            "grapes": grapes, "region": _norm(lw.get("region")), "flavors": flavors,
        })
    return out


def _similarity(grapes: set, region: str, tags: set, liked: Dict[str, Any]) -> float:
    """Raw resemblance of a candidate to one liked wine: shared grape (strong),
    region (medium), flavor-tag overlap (weak)."""
    s = 0.0
    if grapes & liked["grapes"]:
        s += 2.0
    if region and liked["region"] and (region in liked["region"] or liked["region"] in region):
        s += 1.0
    s += 0.5 * len(tags & liked["flavors"])
    return s


def _body_from_structure(sp: Dict[str, Any]) -> str:
    """Map a numeric structure body (1-10, GrapeMinds/Vivino) to the text scale."""
    b = (sp or {}).get("body")
    if b is None:
        return None
    if b >= 7:
        return "full"
    if b >= 4:
        return "medium"
    return "light"


def _resolve_body(wine: Dict[str, Any], tags: set) -> str:
    """Best available body: explicit field → real numeric structure → grape+region
    table → inferred from flavor tags."""
    return (wine.get("body")
            or _body_from_structure(wine.get("structure_profile"))
            or _body_from_structure(
                structure_for(wine.get("varietal"), wine.get("grapes"), wine.get("region")))
            or infer_body(tags))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip accents
    return re.sub(r"\s+", " ", s).strip().lower()


def score_candidates(intent: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Knowledge-based deterministic scoring. `intent` is the resolved-intent dict."""
    budget_min = float(intent.get("budget_min", 10.0))
    budget_max = float(intent.get("budget_max", 50.0))
    # The budget pull targets 0.75×max, not the window midpoint — a $150 budget
    # reads as appetite to spend (~$112), not "anything under $150 is equally
    # fine". Clamped to the floor so narrow windows don't target an unreachable
    # price below budget_min.
    budget_target = max(budget_min, 0.75 * budget_max)
    want_type = intent.get("wine_type")
    want_body = intent.get("body")
    want_region = _norm(intent.get("region")) if intent.get("region") else None
    want_grapes = {_norm(g) for g in (intent.get("grapes") or [])}
    want_flavors = {_norm(f) for f in (intent.get("flavors") or [])}
    avoid = [_norm(a) for a in (intent.get("avoid") or [])]
    liked = _norm_liked(intent.get("liked_wines"))
    disliked = _norm_liked(intent.get("disliked_wines"))

    profile = intent.get("profile") or {}
    p_regions = {_norm(r) for r in (profile.get("regions_love") or [])}
    p_body = profile.get("body")
    p_lean = profile.get("lean")

    scored = []
    for wine in candidates:
        tags = flavor_tags_for(wine.get("varietal"), wine.get("grapes"), wine.get("region"))
        notes = _norm(wine.get("tasting_notes")) + " " + " ".join(
            _norm(x) for x in (wine.get("flavor_profile") or []))
        grapes = {_norm(g) for g in (wine.get("grapes") or [])}
        if wine.get("varietal"):
            grapes.add(_norm(wine["varietal"]))   # symmetric with _norm_liked
        region = _norm(wine.get("region"))
        country = _norm(wine.get("country"))

        # avoid exclusion: search grapes, region, flavor tags, and notes
        haystack = " ".join([notes, region, " ".join(grapes), " ".join(tags)])
        if any(a and a in haystack for a in avoid):
            continue

        score = 0.0

        if want_type and wine.get("wine_type") == want_type:
            score += _W_TYPE

        resolved_body = None
        if want_body:
            resolved_body = _resolve_body(wine, tags)
            if resolved_body == want_body:
                score += _W_BODY

        if want_grapes and (
                (want_grapes & grapes)
                or _blend_match(want_grapes, wine.get("wine_type"), wine.get("grapes"))):
            score += _W_GRAPE

        if want_region and (
                (region and (want_region in region or region in want_region))
                or (country and (want_region in country or country in want_region))):
            score += _W_REGION

        if want_flavors:
            tag_hits = len(want_flavors & tags)
            kw_hits = sum(1 for f in want_flavors if f in notes)
            score += min(_FLAVOR_CAP, _W_FLAVOR_TAG * (tag_hits + kw_hits))

        price = float(wine.get("price") or 0.0)
        if budget_max > budget_min:
            distance = abs(price - budget_target) / (budget_max - budget_min)
            score += _W_BUDGET * max(0.0, 1.0 - distance)

        if wine.get("tier") == 1:
            score += _W_TIER

        # Community rating: boost-only above a 3.5 baseline, scaled so 5.0 = full
        # weight. Thin rating counts are noise, not signal.
        rating = wine.get("vivino_rating")
        if rating and (wine.get("vivino_ratings_count") or 0) >= _MIN_RATINGS:
            score += _W_RATING * max(0.0, min(1.0, (rating - 3.5) / 1.5))

        # Taste profile — soft nudges that only fill a dimension the explicit
        # request left unspecified (the request always wins).
        if profile:
            if p_regions and not want_region and region and any(
                    r and (r in region or region in r) for r in p_regions):
                score += _W_PROFILE_REGION
            if p_body and not want_body:
                if resolved_body is None:
                    resolved_body = _resolve_body(wine, tags)
                if resolved_body == p_body:
                    score += _W_PROFILE_BODY
            if p_lean and not want_type and wine.get("wine_type") in _LEAN_TYPES.get(p_lean, set()):
                score += _W_PROFILE_LEAN

        # Personalization: resemblance to a wine the user liked (not itself).
        similar_to = similar_source = None
        if liked:
            best = 0.0
            for lw in liked:
                if lw["wine_id"] and lw["wine_id"] == wine.get("wine_id"):
                    continue                       # don't rate a wine similar to itself
                sim = _similarity(grapes, region, tags, lw)
                if sim > best:
                    best, similar_to, similar_source = sim, lw["name"], lw["source"]
            if best >= 1.0:                          # at least a shared grape or region
                score += _W_SIMILAR * min(1.0, best / _SIM_FULL)
            else:
                similar_to = similar_source = None

        # Resembling a wine the user thumbs-downed pushes it down.
        if disliked:
            worst = 0.0
            for dw in disliked:
                if dw["wine_id"] and dw["wine_id"] == wine.get("wine_id"):
                    continue
                worst = max(worst, _similarity(grapes, region, tags, dw))
            if worst >= 1.0:
                score -= _W_DISLIKE * min(1.0, worst / _SIM_FULL)

        scored.append({**wine, "_score": score, "_similar_to": similar_to, "_similar_source": similar_source})

    scored.sort(key=lambda w: w["_score"], reverse=True)
    return scored
