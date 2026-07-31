"""One rule for "did the user actually state a budget?".

budget_min/budget_max are hard SQL filters on every inventory query and cannot
be omitted, so the aisle-mode Ask face — where demanding a budget is friction —
sends a deliberately wide range (0-10000) instead of dropping the field. That
sentinel must read as "no budget stated" everywhere budget shows up: the scorer
must not chase 0.85x$10,000 bottles, the prompt must not say "your budget", and
availability lines must not count things "in budget". A spoken cap ("under
$20") re-tightens budget_max via merge_intent, making it stated again.
"""

# The considered face's slider tops out well under this; anything at or above
# it can only be the wide-range sentinel.
WIDE_BUDGET_THRESHOLD = 1000.0


def budget_is_stated(budget_max) -> bool:
    """False when budget_max is the aisle-mode wide-range sentinel."""
    try:
        return float(budget_max) < WIDE_BUDGET_THRESHOLD
    except (TypeError, ValueError):
        return True
