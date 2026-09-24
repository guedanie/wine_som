"""Tests for the web-search gate — recommendation/web_search.py.

The gate is a pure function over the availability oracle's already-computed
facts list (recommendation/availability.py); no network, no DB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.availability import NOT_IN_CATALOG, PRESENT_SHORTLISTED, PRESENT_OUT_OF_BUDGET
from recommendation.web_search import (
    off_catalog_bottles, should_offer_web_search, off_catalog_directive, WEB_SEARCH_TOOL,
)


def _fact(kind, value, state, scope=None):
    return {"label": value, "state": state,
            "axis": {"kind": kind, "value": value, "scope": scope}}


def test_named_bottle_not_in_catalog_is_off_catalog():
    facts = [_fact("name", "Chateau Talbot", NOT_IN_CATALOG)]
    assert off_catalog_bottles(facts) == ["Chateau Talbot"]
    assert should_offer_web_search(facts) is True


def test_named_bottle_present_is_not_off_catalog():
    facts = [_fact("name", "Chateau Talbot", PRESENT_SHORTLISTED)]
    assert off_catalog_bottles(facts) == []
    assert should_offer_web_search(facts) is False


def test_named_bottle_present_out_of_budget_is_not_off_catalog():
    """Out of budget still means it EXISTS in the catalog -- no search license."""
    facts = [_fact("name", "Chateau Talbot", PRESENT_OUT_OF_BUDGET)]
    assert off_catalog_bottles(facts) == []


def test_no_bottle_named_is_not_off_catalog():
    facts = [_fact("place", "Mendoza", NOT_IN_CATALOG)]
    assert off_catalog_bottles(facts) == []
    assert should_offer_web_search(facts) is False


def test_no_facts_at_all_is_not_off_catalog():
    assert off_catalog_bottles([]) == []
    assert should_offer_web_search([]) is False


def test_mixed_facts_only_the_off_catalog_name_axis_counts():
    facts = [
        _fact("place", "Mendoza", NOT_IN_CATALOG),
        _fact("name", "Chateau Talbot", NOT_IN_CATALOG),
        _fact("grape", "Malbec", PRESENT_SHORTLISTED),
    ]
    assert off_catalog_bottles(facts) == ["Chateau Talbot"]


def test_multiple_named_bottles_mixed_states_only_off_catalog_ones_gate():
    """axes_from_intent today only ever emits one 'name' axis per turn, but the
    gate itself is a pure function over the whole facts list -- write it to
    handle several name axes correctly now, at zero extra cost, so it needs
    no change if that ever expands."""
    facts = [
        _fact("name", "Chateau Talbot", PRESENT_SHORTLISTED),
        _fact("name", "Screaming Eagle", NOT_IN_CATALOG),
        _fact("name", "Opus One", NOT_IN_CATALOG),
    ]
    assert off_catalog_bottles(facts) == ["Screaming Eagle", "Opus One"]
    assert should_offer_web_search(facts) is True
    directive = off_catalog_directive(off_catalog_bottles(facts))
    assert "Screaming Eagle" in directive
    assert "Opus One" in directive
    assert "Chateau Talbot" not in directive


def test_directive_names_the_bottle_singular():
    directive = off_catalog_directive(["Chateau Talbot"])
    assert "Chateau Talbot" in directive
    assert "OFF-CATALOG BOTTLE" in directive
    assert "recommend_wines" in directive


def test_directive_empty_when_no_bottles():
    assert off_catalog_directive([]) == ""


def test_directive_handles_multiple_bottles_grammatically():
    directive = off_catalog_directive(["Chateau Talbot", "Screaming Eagle"])
    assert "Chateau Talbot" in directive
    assert "Screaming Eagle" in directive
    assert "these bottles" in directive


def test_web_search_tool_shape():
    assert WEB_SEARCH_TOOL["type"] == "web_search_20250305"
    assert WEB_SEARCH_TOOL["name"] == "web_search"
    assert WEB_SEARCH_TOOL["max_uses"] == 1
    assert "wine-searcher.com" in WEB_SEARCH_TOOL["allowed_domains"]
