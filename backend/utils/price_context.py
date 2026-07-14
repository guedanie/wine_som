"""Derive the dossier's price context from price_history + current availability.

price_history is a delta-only append log (first row on insert, then a row only
when the price changes — see supabase/migrations/20260707000001_price_history.sql).
So per (wine × store): the last two rows are the latest movement, and a single
row means the price has held since tracking began.

Design contract (frontend/design-system/handoffs/price-intelligence/README.md):
- a "drop" is only news while fresh (within FRESH_DAYS); an old drop reads as
  steady — the chip rule is "no fresh movement, no chip"
- rises render no movement (there is no "rise" marker)
- every claim is anchored to a named store and a week ("this week", never today)
- restock is NOT derivable yet: the trigger fires on price changes only, so
  in_stock-only flips write no history row (needs a trigger extension later)
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

FRESH_DAYS = 8      # weekly cadence + grace: a drop older than this isn't news
STRIP_WEEKS = 6     # week-marker glyph length


import re

_FRAC = re.compile(r"\.(\d+)")


def _parse_ts(raw: str) -> datetime:
    # Py3.9 fromisoformat needs exactly 3 or 6 fractional digits; Supabase
    # emits variable precision (.5, .25511, …) — normalize to 6.
    raw = _FRAC.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), raw.replace("Z", "+00:00"), count=1)
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def derive_price_context(
    history: List[Dict[str, Any]],
    availability: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return (price_context, availability_rows_annotated).

    history: price_history rows for one wine — {store_ref, price, recorded_at}.
    availability: current nearby in-stock rows — {store_ref, retailer, address, price}.
    Rows for stores outside `availability` are ignored (not nearby → not a claim
    we can anchor).
    """
    now = now or datetime.now(timezone.utc)
    nearby_refs = {a["store_ref"] for a in availability}

    by_store: Dict[str, List[Dict[str, Any]]] = {}
    for row in history:
        if row.get("store_ref") in nearby_refs and row.get("price") is not None:
            by_store.setdefault(row["store_ref"], []).append(row)
    for rows in by_store.values():
        rows.sort(key=lambda r: r["recorded_at"])

    # Latest fresh drop per store; the biggest one is the headline.
    headline = None   # (amount, store_ref, prev_row, last_row)
    fresh_drops: Dict[str, float] = {}   # store_ref -> was_price, for row annotation
    for store_ref, rows in by_store.items():
        if len(rows) < 2:
            continue
        prev, last = rows[-2], rows[-1]
        amount = round(float(prev["price"]) - float(last["price"]), 2)
        is_fresh = (now - _parse_ts(last["recorded_at"])) <= timedelta(days=FRESH_DAYS)
        if amount > 0 and is_fresh:
            fresh_drops[store_ref] = float(prev["price"])
            if headline is None or amount > headline[0]:
                headline = (amount, store_ref, prev, last)

    retailer_of = {a["store_ref"]: a["retailer"] for a in availability}
    first_ts = min((_parse_ts(r["recorded_at"]) for rows in by_store.values() for r in rows),
                   default=None)

    if headline:
        amount, store_ref, prev, last = headline
        context: Dict[str, Any] = {
            "variant": "drop",
            "amount": amount,
            "from_price": float(prev["price"]),
            "to_price": float(last["price"]),
            "store": retailer_of.get(store_ref),
            "since_label": "this week",
        }
        strip_store = store_ref
    else:
        context = {
            "variant": "steady",
            "amount": None,
            "from_price": None,
            "to_price": None,
            "store": None,
            "since_label": f"since {first_ts.strftime('%B')}" if first_ts else None,
        }
        # glyph follows the cheapest store when nothing moved
        strip_store = min(availability, key=lambda a: a["price"])["store_ref"] if availability else None

    context["weeks_tracked"] = (
        max(1, ((now - first_ts).days // 7) + 1) if first_ts else 0
    )
    context["strip"] = _weekly_strip(by_store.get(strip_store) or [], now)

    cheapest = None
    if availability:
        by_price = sorted(availability, key=lambda a: a["price"])
        cheapest = {
            "retailer": by_price[0]["retailer"],
            "price": float(by_price[0]["price"]),
            "delta_vs_next": round(float(by_price[1]["price"]) - float(by_price[0]["price"]), 2)
            if len(by_price) > 1 else None,
        }
    context["cheapest"] = cheapest

    cheapest_ref = min(availability, key=lambda a: a["price"])["store_ref"] if availability else None
    annotated = []
    for a in availability:
        annotated.append({
            **a,
            "is_cheapest": a["store_ref"] == cheapest_ref,
            "was_price": fresh_drops.get(a["store_ref"]),
        })
    return context, annotated


def fresh_drops_for(
    history: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """Map (wine_id, store_ref) -> fresh drop {amount, from_price, to_price}.

    Used to annotate the recommendation shortlist: one price_history fetch for
    the top candidates, then this picks out the pairs whose latest change is a
    drop within FRESH_DAYS. Rises, old drops, and rows missing ids are ignored.
    """
    now = now or datetime.now(timezone.utc)
    by_pair: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in history:
        if row.get("wine_id") and row.get("store_ref") and row.get("price") is not None:
            by_pair.setdefault((row["wine_id"], row["store_ref"]), []).append(row)
    drops: Dict[Tuple[str, str], Dict[str, float]] = {}
    for pair, rows in by_pair.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r["recorded_at"])
        prev, last = rows[-2], rows[-1]
        amount = round(float(prev["price"]) - float(last["price"]), 2)
        if amount <= 0:
            continue
        if (now - _parse_ts(last["recorded_at"])) > timedelta(days=FRESH_DAYS):
            continue
        drops[pair] = {
            "amount": amount,
            "from_price": float(prev["price"]),
            "to_price": float(last["price"]),
        }
    return drops


def _weekly_strip(rows: List[Dict[str, Any]], now: datetime) -> List[float]:
    """Carried-forward price per week for the last STRIP_WEEKS weeks — the
    week-marker glyph's data. Oldest first, current week last."""
    if not rows:
        return []
    points = [(_parse_ts(r["recorded_at"]), float(r["price"])) for r in rows]
    strip = []
    for weeks_back in range(STRIP_WEEKS - 1, -1, -1):
        week_end = now - timedelta(weeks=weeks_back)
        known = [p for ts, p in points if ts <= week_end]
        if known:
            strip.append(known[-1])
    return strip
