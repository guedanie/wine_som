"""The throttle marker is a CONTRACT between two parties that never see each
other: a scraper writes it into scraper_runs.error_message, and sweep_delisted
reads it back hours later to decide whether the run is complete enough to
delist with. Both sides must agree on the exact string, so the round-trip is
tested here rather than the format being asserted twice independently.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.throttle import throttle_note, was_throttled


def test_no_throttled_stores_produces_no_note():
    """A clean run must leave error_message None — an empty marker string
    would make every run look throttled and stop delisting entirely."""
    assert throttle_note([]) is None


def test_note_lists_stores_sorted_and_deduped():
    note = throttle_note(["Bitters Marketplace", "Balcones Drive", "Bitters Marketplace"])
    assert "Balcones Drive" in note
    assert "Bitters Marketplace" in note
    assert note.index("Balcones Drive") < note.index("Bitters Marketplace")
    assert note.count("Bitters Marketplace") == 1


def test_note_round_trips_through_was_throttled():
    """The load-bearing test: whatever the producer writes, the consumer
    must recognise. This is the coupling that last night's incident broke."""
    assert was_throttled(throttle_note(["Frugal MacDoogal"])) is True


def test_clean_run_is_not_throttled():
    assert was_throttled(None) is False
    assert was_throttled("") is False


def test_unrelated_error_message_is_not_throttled():
    """Twin already writes 'failed stores: ...' for commit failures — that is a
    different condition and must not suppress the sweep."""
    assert was_throttled("failed stores: 5af17ad1,5af17a81") is False
    assert was_throttled("[51729 rows committed before failure] errorCode 15") is False
