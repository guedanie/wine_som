import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch, MagicMock
from recommendation.intent import merge_intent, intent_from_request, parse_message


def test_intent_from_request_maps_explicit_fields():
    intent = intent_from_request(
        wine_type="red", style_preferences=["bold", "earthy"], avoid=["sweet"],
        budget_min=15.0, budget_max=35.0)
    assert intent["wine_type"] == "red"
    assert intent["flavors"] == ["bold", "earthy"]
    assert intent["avoid"] == ["sweet"]
    assert intent["budget_min"] == 15.0
    assert intent["region"] is None
    assert intent["grapes"] == []


def test_merge_intent_explicit_wine_type_wins():
    parsed = {"wine_type": "white", "body": "light", "flavors": ["crisp"],
              "grapes": ["Chardonnay"], "region": "Burgundy", "max_price": 20.0,
              "avoid": []}
    explicit = intent_from_request(wine_type="red", style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    merged = merge_intent(parsed, explicit)
    assert merged["wine_type"] == "red"           # explicit wins
    assert merged["body"] == "light"              # filled from parsed
    assert merged["grapes"] == ["Chardonnay"]     # filled from parsed
    assert merged["region"] == "Burgundy"         # filled from parsed
    assert merged["budget_max"] == 20.0           # spoken "under $20" tightens the window


def _explicit(bmin=10.0, bmax=50.0):
    return intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                               budget_min=bmin, budget_max=bmax)


def _parsed(max_price):
    return {"wine_type": None, "body": None, "flavors": [], "grapes": [],
            "region": None, "max_price": max_price, "avoid": []}


def test_max_price_tightens_scoring_window():
    merged = merge_intent(_parsed(20.0), _explicit(10.0, 60.0))
    assert merged["budget_max"] == 20.0
    assert merged["budget_min"] == 10.0


def test_max_price_never_widens_the_window():
    """The fetch already capped candidates at the slider max — a spoken price
    above it must not pretend the window is wider than the pool."""
    merged = merge_intent(_parsed(80.0), _explicit(10.0, 50.0))
    assert merged["budget_max"] == 50.0


def test_max_price_below_floor_clamps_min_too():
    merged = merge_intent(_parsed(8.0), _explicit(10.0, 50.0))
    assert merged["budget_max"] == 8.0
    assert merged["budget_min"] == 8.0    # window stays valid (min <= max)


def test_max_price_absent_or_invalid_leaves_budget_alone():
    assert merge_intent(_parsed(None), _explicit())["budget_max"] == 50.0
    assert merge_intent(_parsed(0), _explicit())["budget_max"] == 50.0
    assert merge_intent(_parsed(-5), _explicit())["budget_max"] == 50.0
    assert merge_intent(_parsed("cheap"), _explicit())["budget_max"] == 50.0


def test_scorer_recenters_on_spoken_max_price():
    """With slider 10-60 but a spoken 'under $20', the budget pull re-centers on
    $15 — a $15 bottle must now outscore an otherwise-identical $35 one. The $35
    wine comes FIRST so a stable-sort tie can't fake a pass."""
    from recommendation.scorer import score_candidates
    wines = [
        {"wine_id": "w-35", "name": "A", "price": 35.0, "wine_type": "red", "grapes": [],
         "flavor_profile": [], "structure_profile": {}, "tier": 2},
        {"wine_id": "w-15", "name": "B", "price": 15.0, "wine_type": "red", "grapes": [],
         "flavor_profile": [], "structure_profile": {}, "tier": 2},
    ]
    merged = merge_intent(_parsed(20.0), _explicit(10.0, 60.0))
    scored = sorted(score_candidates(merged, wines), key=lambda w: w["_score"], reverse=True)
    assert scored[0]["wine_id"] == "w-15"


def test_merge_intent_unions_flavors_and_avoid():
    parsed = {"wine_type": None, "body": None, "flavors": ["earthy"], "grapes": [],
              "region": None, "max_price": None, "avoid": ["oaky"]}
    explicit = intent_from_request(wine_type=None, style_preferences=["bold"],
                                   avoid=["sweet"], budget_min=10.0, budget_max=50.0)
    merged = merge_intent(parsed, explicit)
    assert set(merged["flavors"]) == {"earthy", "bold"}
    assert set(merged["avoid"]) == {"oaky", "sweet"}


def test_parse_message_returns_structured_intent():
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"wine_type": "red", "body": "full", "flavors": ["earthy", "bold"],
                   "grapes": ["Syrah"], "region": "Rhône", "max_price": 25.0, "avoid": []}
    resp = MagicMock()
    resp.content = [block]
    with patch("recommendation.intent._anthropic_client") as mock_client:
        mock_client.messages.create.return_value = resp
        out = parse_message("a bold earthy red for steak around $25")
    assert out["wine_type"] == "red"
    assert out["body"] == "full"
    assert "earthy" in out["flavors"]
    assert out["region"] == "Rhône"


def test_parse_message_fails_soft_on_no_tool_block():
    resp = MagicMock()
    resp.content = []   # no tool_use block
    with patch("recommendation.intent._anthropic_client") as mock_client:
        mock_client.messages.create.return_value = resp
        out = parse_message("gibberish")
    assert out is None


def test_intent_from_request_sets_wine_name_none():
    out = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                              budget_min=10.0, budget_max=50.0)
    assert out["wine_name"] is None


def test_merge_takes_parsed_wine_name():
    explicit = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    merged = merge_intent({"wine_name": "Opus One", "flavors": [], "grapes": [], "avoid": []}, explicit)
    assert merged["wine_name"] == "Opus One"


def test_merge_no_parsed_leaves_wine_name_none():
    explicit = intent_from_request(wine_type=None, style_preferences=[], avoid=[],
                                   budget_min=10.0, budget_max=50.0)
    assert merge_intent(None, explicit)["wine_name"] is None
