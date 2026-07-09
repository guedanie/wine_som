"""Tests for the streaming narrative parser in recommendation/claude_client.py.

All tests call _parse_narrative_fragments() directly with fixture fragment lists —
no network calls, no Anthropic API required.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.claude_client import _parse_narrative_fragments


# ── Basic token streaming ────────────────────────────────────────────────────

def test_narrative_emitted_as_tokens():
    fragments = ['{"narrative":"Hello world","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "Hello world"


def test_narrative_split_across_fragments():
    fragments = ['{"narrative":"He', 'llo ', 'world","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "Hello world"


def test_narrative_with_space_after_colon():
    """Both '"narrative":"' and '"narrative": "' are valid JSON."""
    fragments = ['{"narrative": "Hi there","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "Hi there"


# ── JSON escape sequences ────────────────────────────────────────────────────

def test_newline_escape_decoded():
    fragments = ['{"narrative":"line1\\nline2","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "line1\nline2"


def test_tab_escape_decoded():
    fragments = ['{"narrative":"col1\\tcol2","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "col1\tcol2"


def test_unicode_escape_accent_decoded():
    """\\u00e9 must stream as é, not literal 'u00e9'. (B2)"""
    fragments = ['{"narrative":"Caf\\u00e9","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "Café"


def test_unicode_escape_smart_quote_decoded():
    """\\u2019 (right single quote) must stream as ', not literal 'u2019'. (B2)"""
    fragments = ['{"narrative":"don\\u2019t","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "don’t"


def test_unicode_escape_split_across_fragments():
    """\\uXXXX split across fragment boundaries must still decode correctly."""
    # Split inside the escape sequence
    fragments = [
        '{"narrative":"r\\u00',
        'e9gion","picks":[],"followup_suggestions":[]}',
    ]
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == "région"


# ── Picks extraction ─────────────────────────────────────────────────────────

def test_picks_yielded_after_narrative():
    picks = [{"wine_id": "x1", "name": "Test Wine", "price": 20.0,
               "retailer": "Spec's", "why": "Good."}]
    import json
    frag = json.dumps({
        "narrative": "Try this.",
        "picks": picks,
        "followup_suggestions": ["Q1?", "Q2?", "Q3?"],
    })
    events = list(_parse_narrative_fragments([frag]))
    picks_events = [v for t, v in events if t == "picks"]
    assert len(picks_events) == 1
    assert picks_events[0][0]["wine_id"] == "x1"


def test_empty_picks_yielded():
    import json
    frag = json.dumps({
        "narrative": "Here is some wine education.",
        "picks": [],
        "followup_suggestions": ["Q1?", "Q2?", "Q3?"],
    })
    events = list(_parse_narrative_fragments([frag]))
    picks_events = [v for t, v in events if t == "picks"]
    assert picks_events == [[]]


def test_picks_streamed_incrementally_across_fragments():
    """Picks array arriving in multiple fragments should still be extracted."""
    import json
    full = json.dumps({
        "narrative": "Hi.",
        "picks": [{"wine_id": "w1", "name": "Wine A", "price": 15.0,
                   "retailer": "HEB", "why": "Nice."}],
        "followup_suggestions": ["Q1?", "Q2?", "Q3?"],
    })
    # Split the full JSON at an arbitrary point mid-picks
    mid = len(full) // 2
    events = list(_parse_narrative_fragments([full[:mid], full[mid:]]))
    picks_events = [v for t, v in events if t == "picks"]
    assert len(picks_events) == 1
    assert picks_events[0][0]["wine_id"] == "w1"


# ── Followup suggestions ─────────────────────────────────────────────────────

def test_followup_suggestions_not_yielded_by_parser():
    """Suggestions come from get_final_message, not the fragment parser."""
    import json
    frag = json.dumps({
        "narrative": "Try this wine.",
        "picks": [],
        "followup_suggestions": ["Q1?", "Q2?", "Q3?"],
    })
    events = list(_parse_narrative_fragments([frag]))
    types = [t for t, _ in events]
    assert "suggestions" not in types


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_narrative_yields_no_tokens():
    import json
    frag = json.dumps({"narrative": "", "picks": [], "followup_suggestions": []})
    events = list(_parse_narrative_fragments([frag]))
    tokens = [v for t, v in events if t == "token"]
    assert tokens == []


def test_narrative_with_escaped_quote_inside():
    """An escaped quote inside the narrative must not end the string early."""
    fragments = ['{"narrative":"She said \\"cheers\\"","picks":[],"followup_suggestions":[]}']
    events = list(_parse_narrative_fragments(fragments))
    tokens = [v for t, v in events if t == "token"]
    assert "".join(tokens) == 'She said "cheers"'


# ── B6: picks in same fragment as narrative closing quote ─────────────────────

def test_picks_yielded_when_narrative_and_picks_in_same_fragment():
    """When the narrative closing quote and picks[] are in the same fragment, picks must be yielded. (B6)"""
    import json
    frag = json.dumps({
        "narrative": "Bold and earthy.",
        "picks": [{"wine_id": "w1", "name": "Malbec", "price": 18.0, "retailer": "HEB", "why": "Earthy."}],
        "followup_suggestions": ["Q1?", "Q2?", "Q3?"],
    })
    events = list(_parse_narrative_fragments([frag]))
    tokens = [v for t, v in events if t == "token"]
    picks_events = [v for t, v in events if t == "picks"]
    assert "".join(tokens) == "Bold and earthy."
    assert len(picks_events) == 1
    assert picks_events[0][0]["wine_id"] == "w1"


# ── E4: stream_recommendations yields generic error, not raw exception ────────

def test_stream_recommendations_error_message_is_generic():
    """When Claude raises, the error tuple must not expose the raw exception string. (E4)"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[1]))
    from unittest.mock import patch
    from recommendation.claude_client import stream_recommendations

    candidates = [{
        "wine_id": "w1", "name": "Test Wine", "price": 20.0, "retailer": "HEB",
        "tasting_notes": None, "structure_profile": None,
        "varietal": "Malbec", "region": "Mendoza", "country": "Argentina",
    }]
    intent = {"wine_type": "red", "flavors": [], "avoid": [], "budget_min": 10, "budget_max": 50}

    with patch("recommendation.claude_client._anthropic_client") as mock_client:
        mock_client.messages.stream.side_effect = Exception(
            "credit_balance_too_low api_key=sk-ant-SECRET"
        )
        events = list(stream_recommendations(candidates, intent))

    error_events = [v for t, v in events if t == "error"]
    assert len(error_events) == 1
    assert "sk-ant" not in error_events[0]
    assert "credit_balance" not in error_events[0]


def test_format_wine_includes_vivino_rating():
    """Claude's inventory listing must show the community rating so it can cite
    credibility in picks ('a crowd favorite at 4.3 on Vivino')."""
    from recommendation.claude_client import _format_wine
    wine = {
        "name": "Jordan Cabernet Sauvignon", "varietal": "Cabernet Sauvignon",
        "region": "Alexander Valley", "country": "USA", "price": 60.0,
        "retailer": "Spec's", "vivino_rating": 4.3, "vivino_ratings_count": 57491,
    }
    line = _format_wine(wine)
    assert "4.3" in line
    assert "Vivino" in line


def test_format_wine_omits_rating_when_absent():
    from recommendation.claude_client import _format_wine
    wine = {"name": "Obscure Wine", "varietal": "Malbec", "region": "Mendoza",
            "country": "Argentina", "price": 20.0, "retailer": "H-E-B"}
    assert "Vivino" not in _format_wine(wine)


# ── conversational follow-up directive (chat naturalness) ──────────

from recommendation.claude_client import _build_user_message

_CANDS = [{"wine_id": "w1", "name": "A", "price": 20, "retailer": "Spec's",
           "varietal": "Malbec", "region": "Mendoza", "country": "Argentina"}]
_HIST = [{"role": "user", "content": "bold red under $30"},
         {"role": "assistant", "content": "Here are three."}]


def test_conversational_followup_adds_no_cards_directive():
    msg = _build_user_message(_CANDS, {"message": "why that one?"},
                              conversation_history=_HIST, conversational=True)
    assert "picks: []" in msg
    assert "already" in msg.lower()  # references existing recommendations on screen


def test_conversational_off_has_no_directive():
    msg = _build_user_message(_CANDS, {"message": "why that one?"},
                              conversation_history=_HIST, conversational=False)
    assert "picks: []" not in msg


def test_conversational_first_turn_has_no_directive():
    """First turn (no history) must still recommend — directive only on follow-ups."""
    msg = _build_user_message(_CANDS, {"message": "bold red"},
                              conversation_history=None, conversational=True)
    assert "picks: []" not in msg


# ── relevance-first card count (no padding to a quota) ─────────────

def test_user_message_has_no_hard_card_quota():
    msg = _build_user_message(_CANDS, {"message": "shiraz from HEB"}, conversational=False)
    assert "3–5" not in msg and "3-5" not in msg
    # relevance-first, anti-padding language present
    assert "genuinely fit" in msg.lower()
    assert "just" in msg.lower()  # "return just that one" style guidance


def test_format_wine_exposes_store_name_to_agent():
    from recommendation.claude_client import _format_wine
    line = _format_wine({
        "name": "Penfolds Shiraz", "price": 24.0, "retailer": "H-E-B",
        "store_name": "Lincoln Heights H-E-B", "varietal": "Shiraz",
    })
    assert "Lincoln Heights" in line


def test_format_wine_without_store_name_still_works():
    from recommendation.claude_client import _format_wine
    line = _format_wine({"name": "X", "price": 20.0, "retailer": "Spec's", "varietal": "Malbec"})
    assert "@ Spec's" in line


# ── personalization: surface "resembles a wine you liked" to Claude ──

def test_format_wine_surfaces_similarity_to_a_liked_wine():
    from recommendation.claude_client import _format_wine
    line = _format_wine({
        "name": "Coudoulet de Beaucastel", "price": 30, "retailer": "Spec's",
        "varietal": "Grenache", "region": "Rhône",
        "_similar_to": "Esprit de Tablas", "_similar_source": "saved",
    })
    assert "Esprit de Tablas" in line
    assert "saved" in line.lower()


def test_build_user_message_adds_citation_instruction_when_similarity_present():
    cands = [{"wine_id": "w1", "name": "X", "price": 30, "retailer": "Spec's",
              "varietal": "Grenache", "_similar_to": "Esprit de Tablas", "_similar_source": "saved"}]
    msg = _build_user_message(cands, {"message": "something bold"})
    assert "resembles" in msg.lower() and "why" in msg.lower()


def test_no_citation_instruction_without_similarity():
    cands = [{"wine_id": "w1", "name": "X", "price": 30, "retailer": "Spec's", "varietal": "Grenache"}]
    msg = _build_user_message(cands, {"message": "something bold"})
    assert "resembles the" not in msg.lower()
