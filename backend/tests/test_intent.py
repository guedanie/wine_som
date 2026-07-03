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
    assert merged["budget_max"] == 50.0           # explicit budget always wins


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
