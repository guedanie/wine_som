"""One rule for "did the user actually state a budget?".

budget_min/budget_max are hard SQL filters on every inventory query and cannot
be omitted, so the aisle-mode Ask face — where demanding a budget is friction —
sends a deliberately wide range (0-10000) instead of dropping the field. That
sentinel must read as "no budget stated" everywhere budget shows up: the scorer
must not chase 0.85x$10,000 bottles, the prompt must not say "your budget", and
availability lines must not count things "in budget". A spoken cap ("under
$20") replaces budget_max via merge_intent, making it stated again — in either
direction, since a budget the user says out loud also has to be able to RAISE a
carried one ("actually, up to $200").
"""

from typing import Any, Dict, Optional

# The considered face's slider tops out well under this; anything at or above
# it can only be the wide-range sentinel.
WIDE_BUDGET_THRESHOLD = 1000.0


def budget_is_stated(budget_max) -> bool:
    """False when budget_max is the aisle-mode wide-range sentinel."""
    try:
        return float(budget_max) < WIDE_BUDGET_THRESHOLD
    except (TypeError, ValueError):
        return True


def effective_budget_max(resolved: Dict[str, Any], request_max: float) -> float:
    """The budget to count and render against.

    A budget spoken THIS turn lives only in `resolved` — `req.budget_max` is
    still whatever the client sent (the wide sentinel, in ASK mode). Counting
    against the request value would tell the user "12 in budget" while the
    narrative says $60.
    """
    value = resolved.get("budget_max")
    return float(value) if isinstance(value, (int, float)) else float(request_max)


def budget_widened(resolved: Dict[str, Any], request_max: float) -> bool:
    """True when the user spoke a budget HIGHER than the one the fetch ran on.

    Only widening matters: the breadth query already retrieved everything at or
    below `request_max`, so narrowing is a scoring problem, while widening means
    the newly-affordable wines are simply absent from the pool.
    """
    value = resolved.get("budget_max")
    if not isinstance(value, (int, float)):
        return False
    return float(value) > float(request_max)


def budget_frame_values(parsed: Optional[Dict[str, Any]],
                         resolved: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """{"min": ..., "max": ...} to persist client-side, or None.

    Silence is load-bearing: this must return None on every turn the user
    did not speak a budget, or the client would pin a value the user never
    said and `budget_is_stated()` would start reporting a phantom budget on
    every later turn. `parsed.max_price` is checked (not the wide sentinel
    that always lives on the request) with the same numeric/positive test
    merge_intent uses internally to decide whether a spoken budget replaces
    the carried one — kept in sync deliberately, not shared, since
    merge_intent is out of scope for this change. Values come from
    `resolved` (post-merge_intent) rather than `parsed.max_price` alone
    because merge_intent may additionally clamp budget_min against it.
    """
    if not parsed:
        return None
    max_price = parsed.get("max_price")
    if not isinstance(max_price, (int, float)) or isinstance(max_price, bool) or max_price <= 0:
        return None
    return {
        "min": float(resolved.get("budget_min", 0.0)),
        "max": float(resolved.get("budget_max", max_price)),
    }
