from typing import List, Dict, Any, Optional


def score_candidates(
    candidates: List[Dict[str, Any]],
    wine_type: Optional[str],
    style_preferences: List[str],
    avoid: List[str],
    budget_min: float,
    budget_max: float,
) -> List[Dict[str, Any]]:
    budget_mid = (budget_min + budget_max) / 2.0
    avoid_lower = [a.lower() for a in avoid]
    pref_lower = [p.lower() for p in style_preferences]
    scored = []

    for wine in candidates:
        searchable = " ".join(filter(None, [
            wine.get("varietal") or "",
            wine.get("wine_type") or "",
            wine.get("region") or "",
            wine.get("country") or "",
            wine.get("tasting_notes") or "",
            " ".join(wine.get("flavor_profile") or []),
        ])).lower()

        if any(a in searchable for a in avoid_lower):
            continue

        score = 0.0

        if wine_type and wine.get("wine_type") == wine_type:
            score += 3.0

        for pref in pref_lower:
            if pref in searchable:
                score += 1.0

        price = float(wine.get("price") or 0.0)
        if budget_max > budget_min:
            distance = abs(price - budget_mid) / (budget_max - budget_min)
            score += max(0.0, 1.0 - distance)

        scored.append({**wine, "_score": score})

    scored.sort(key=lambda w: w["_score"], reverse=True)
    return scored
