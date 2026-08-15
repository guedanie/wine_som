import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.producer_facts import (summarize_producer, format_producer_block,
                                           producer_tokens, _PRODUCER_MAX_ROWS)


def _PF_rows(*pairs):
    return [{"name": f"W{i}", "region": r, "country": c}
            for i, (r, c) in enumerate(pairs)]


def test_majority_outvotes_a_single_bad_row():
    """The Epoch shape: 3 Paso Robles + 1 mislabelled Ribeira Sacra."""
    rows = _PF_rows(("Paso Robles", "United States"), ("Paso Robles", "United States"),
                    ("Paso Robles", "United States"), ("Ribeira Sacra", "Spain"))
    f = summarize_producer("epoch", rows)
    assert f is not None
    assert f["regions"][0][0] == "Paso Robles"
    assert f["regions"][0][1] == 3
    assert f["total"] == 4


def test_scattered_token_emits_nothing():
    """A generic word matches unrelated wines everywhere — not a producer."""
    rows = _PF_rows(("Napa Valley", "US"), ("Rioja", "Spain"), ("Tuscany", "Italy"),
                    ("Mendoza", "Argentina"), ("Loire", "France"), ("Douro", "Portugal"))
    assert summarize_producer("estate", rows) is None


def test_too_many_rows_emits_nothing():
    rows = _PF_rows(*[("Napa Valley", "US")] * (_PRODUCER_MAX_ROWS + 1))
    assert summarize_producer("reserve", rows) is None


def test_needs_at_least_two_regioned_rows():
    assert summarize_producer("solo", _PF_rows(("Paso Robles", "US"))) is None
    assert summarize_producer("none", []) is None


def test_multi_region_producer_keeps_both_with_counts():
    rows = _PF_rows(*([("Napa Valley", "US")] * 9 + [("Alexander Valley", "US")] * 2))
    f = summarize_producer("silver oak", rows)
    assert f["regions"][0] == ("Napa Valley", 9)
    assert f["regions"][1] == ("Alexander Valley", 2)


def test_rows_without_a_region_do_not_break_it():
    rows = _PF_rows(("Paso Robles", "US"), ("Paso Robles", "US"), (None, None))
    f = summarize_producer("epoch", rows)
    assert f and f["regions"][0][0] == "Paso Robles"


def test_format_block_renders_counts_and_is_empty_when_none():
    assert format_producer_block([]) == ""
    block = format_producer_block([
        {"token": "epoch", "regions": [("Paso Robles", 3)], "country": "United States", "total": 4},
    ])
    assert "VERIFIED PRODUCER" in block
    assert "epoch" in block.lower() and "Paso Robles" in block and "3" in block


def test_chat_stopwords_do_not_crowd_out_the_real_producer_name():
    """Repro case: "close" (chat filler, false-matched "Closerie" in prod) and the
    6-token cap previously pushed "epoch" off the end of the token list entirely."""
    toks = producer_tokens("Looking for something from willow creek - close to epoch in style")
    assert "close" not in toks
    assert "epoch" in toks


def test_generic_chat_message_yields_no_tokens():
    """A message with no producer name should not surface a stopword as a candidate."""
    assert producer_tokens("something bold and structured please") == []
