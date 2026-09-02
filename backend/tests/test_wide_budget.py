"""Aisle-mode delta 2: a wide-range budget (the aisle face sends 0-10000 because
budget_min/max are hard SQL filters that can't be omitted) must read as "no
budget stated" — scorer budget axis silent, prompt budget-silent, availability
lines dropping "in budget" phrasing. A spoken "under $20" re-tightens via
merge_intent, making the budget stated again."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.budget import budget_is_stated, effective_budget_max, budget_widened, WIDE_BUDGET_THRESHOLD
from recommendation.scorer import score_candidates
from recommendation.claude_client import _build_user_message
from recommendation.availability import availability_lines, PRESENT_NOT_SHORTLISTED


def test_budget_is_stated_thresholds():
    assert budget_is_stated(50.0)
    assert budget_is_stated(WIDE_BUDGET_THRESHOLD - 1)
    assert not budget_is_stated(10000.0)
    assert not budget_is_stated(WIDE_BUDGET_THRESHOLD)


def _wine(i, price):
    return {"wine_id": str(i), "name": "Same Wine", "price": price,
            "wine_type": "red", "grapes": [], "tier": 2}


def _intent(bmax):
    return {"budget_min": 0.0, "budget_max": bmax,
            "flavors": [], "grapes": [], "avoid": []}


def test_scorer_budget_axis_silent_when_wide():
    # identical wines apart from price: wide budget must not prefer the pricier one
    scored = score_candidates(_intent(10000.0), [_wine(1, 12.0), _wine(2, 8400.0)])
    scores = {w["wine_id"]: w["_score"] for w in scored}
    assert scores["1"] == scores["2"]


def test_scorer_budget_axis_active_when_stated():
    scored = score_candidates(_intent(50.0), [_wine(1, 42.0), _wine(2, 12.0)])
    scores = {w["wine_id"]: w["_score"] for w in scored}
    assert scores["1"] > scores["2"]      # 0.85×max target favors the upper band


def _prompt_intent(bmax):
    return {"flavors": [], "avoid": [], "grapes": [],
            "budget_min": 0.0, "budget_max": bmax, "message": "a good red"}


def test_prompt_omits_budget_line_when_wide():
    msg = _build_user_message([], _prompt_intent(10000.0))
    assert "Budget:" not in msg
    assert "No budget was given" in msg


def test_prompt_keeps_budget_line_when_stated():
    msg = _build_user_message([], _prompt_intent(50.0))
    assert "Budget: $0–$50" in msg
    assert "No budget was given" not in msg


def _fact():
    return {"label": "Barolo", "state": PRESENT_NOT_SHORTLISTED,
            "total": 5, "in_budget": 5, "min_price": 20.0, "max_price": 90.0,
            "axis": {"value": "Barolo", "scope": None}}


def test_availability_line_drops_in_budget_wording_when_wide():
    lines = availability_lines([_fact()], [], 10000.0)
    assert lines and "in budget" not in lines[0]
    assert "5 Barolo" in lines[0]


def test_availability_line_keeps_in_budget_wording_when_stated():
    lines = availability_lines([_fact()], [], 50.0)
    assert lines and "in budget" in lines[0]


def test_effective_budget_prefers_the_resolved_value():
    """On the turn a budget is spoken, req.budget_max is still the wide
    sentinel. Counting 'in budget' against 10000 while the prompt says $60
    makes the oracle and the narrative disagree."""
    assert effective_budget_max({"budget_max": 60.0}, 10000.0) == 60.0


def test_effective_budget_falls_back_to_the_request():
    assert effective_budget_max({}, 50.0) == 50.0
    assert effective_budget_max({"budget_max": None}, 50.0) == 50.0


def test_budget_widened_detects_only_upward_moves():
    """Narrowing needs no re-fetch — the pool already holds everything under
    the lower ceiling. Only widening exposes wines the breadth query never
    retrieved."""
    assert budget_widened({"budget_max": 200.0}, 60.0) is True
    assert budget_widened({"budget_max": 20.0}, 60.0) is False
    assert budget_widened({"budget_max": 60.0}, 60.0) is False
    assert budget_widened({}, 60.0) is False
