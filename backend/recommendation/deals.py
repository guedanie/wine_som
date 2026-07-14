"""Deals — the weekly editorial cut of "good wine whose price just moved".

Ranking is quality × movement, sommelier judgment rather than percent-off
(design: frontend/design-system/handoffs/price-intelligence/README.md,
Surface 3): a well-rated bottle with a modest drop outranks a mediocre bottle
with a huge one, and relative movement is capped so data glitches can't
dominate the cut. `personalization_weight` is the seam for taste-biasing
later — a callable multiplier, defaulting to neutral.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

_MIN_RATINGS = 25        # below this a rating is noise (matches the scorer)
_UNRATED_QUALITY = 0.25  # unrated wines stay in the cut, just below rated ones
_MOVEMENT_CAP = 0.20     # relative drop beyond ~20% is a glitch, not a deal


def deal_score(item: Dict[str, Any]) -> float:
    rating = item.get("vivino_rating")
    count = item.get("vivino_ratings_count") or 0
    if rating and count >= _MIN_RATINGS:
        quality = max(0.0, min(1.0, (float(rating) - 3.5) / 1.5))
    else:
        quality = _UNRATED_QUALITY
    # endpoint items name it was_price (the API-facing field); raw drop dicts
    # say from_price — same number
    from_price = float(item.get("from_price") or item["was_price"])
    movement = min(_MOVEMENT_CAP, float(item["amount"]) / from_price)
    # Quality leads (0.3–1.0 factor): a 4.5★ bottle down 10% must outrank a
    # 3.6★ bottle down 40% — this is a sommelier's cut, not a bargain bin.
    return (0.3 + 0.7 * quality) * movement


_MIN_PRICE = 7.0        # below this it's jug territory, not a somm's pick
_MIN_RATING_BAR = 3.7   # a rated wine below this isn't "recommend anyway"


def editorial_cut(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The quality bar before ranking: 'bottles I'd recommend anyway — they
    just happen to be cheaper this week.' Unrated wines pass (obscure natural
    bottles aren't punished); rated-but-poor and jug-priced ones don't."""
    kept = []
    for d in items:
        if float(d.get("price") or 0) < _MIN_PRICE:
            continue
        rating = d.get("vivino_rating")
        if rating and (d.get("vivino_ratings_count") or 0) >= _MIN_RATINGS and float(rating) < _MIN_RATING_BAR:
            continue
        kept.append(d)
    return kept


def rank_deals(
    items: List[Dict[str, Any]],
    personalization_weight: Optional[Callable[[Dict[str, Any]], float]] = None,
) -> List[Dict[str, Any]]:
    weight = personalization_weight or (lambda d: 1.0)
    return sorted(items, key=lambda d: deal_score(d) * weight(d), reverse=True)


def week_of_label(now: Optional[datetime] = None) -> str:
    """The most recent Sunday, as the header's week label ('JUL 12')."""
    now = now or datetime.now(timezone.utc)
    sunday = now - timedelta(days=(now.weekday() + 1) % 7)
    return f"{sunday.strftime('%b').upper()} {sunday.day}"
