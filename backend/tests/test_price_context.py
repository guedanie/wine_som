import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from datetime import datetime, timezone
from utils.price_context import derive_price_context

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _h(store, price, at):
    return {"store_ref": store, "price": price, "recorded_at": at}


def _avail(store, retailer, price, address="123 Main St"):
    return {"store_ref": store, "retailer": retailer, "address": address, "price": price}


def test_fresh_drop_is_the_headline():
    history = [
        _h("s1", 24.99, "2026-06-07T10:00:00+00:00"),   # initial
        _h("s1", 19.99, "2026-07-12T10:00:00+00:00"),   # dropped yesterday
    ]
    avail = [_avail("s1", "H-E-B", 19.99)]
    ctx, rows = derive_price_context(history, avail, now=NOW)
    assert ctx["variant"] == "drop"
    assert ctx["amount"] == 5.0
    assert ctx["from_price"] == 24.99 and ctx["to_price"] == 19.99
    assert ctx["store"] == "H-E-B"
    assert ctx["since_label"] == "this week"


def test_old_drop_reads_as_steady():
    """A drop from a month ago isn't news — the chip rule is 'no fresh
    movement, no chip', so the context is steady."""
    history = [
        _h("s1", 24.99, "2026-06-07T10:00:00+00:00"),
        _h("s1", 19.99, "2026-06-14T10:00:00+00:00"),   # dropped a month ago
    ]
    ctx, _ = derive_price_context(history, [_avail("s1", "H-E-B", 19.99)], now=NOW)
    assert ctx["variant"] == "steady"


def test_price_rise_reads_as_steady():
    """Design has no 'rise' marker — a raised price renders no movement."""
    history = [
        _h("s1", 19.99, "2026-06-07T10:00:00+00:00"),
        _h("s1", 24.99, "2026-07-12T10:00:00+00:00"),
    ]
    ctx, _ = derive_price_context(history, [_avail("s1", "H-E-B", 24.99)], now=NOW)
    assert ctx["variant"] == "steady"


def test_single_row_is_steady_since_first_tracked():
    history = [_h("s1", 28.0, "2026-06-07T10:00:00+00:00")]
    ctx, _ = derive_price_context(history, [_avail("s1", "Spec's", 28.0)], now=NOW)
    assert ctx["variant"] == "steady"
    assert ctx["since_label"] == "since June"
    assert ctx["weeks_tracked"] >= 5


def test_biggest_fresh_drop_wins_across_stores():
    history = [
        _h("s1", 22.0, "2026-06-07T10:00:00+00:00"),
        _h("s1", 20.0, "2026-07-12T10:00:00+00:00"),    # -$2
        _h("s2", 30.0, "2026-06-07T10:00:00+00:00"),
        _h("s2", 24.0, "2026-07-12T10:00:00+00:00"),    # -$6 ← headline
    ]
    avail = [_avail("s1", "H-E-B", 20.0), _avail("s2", "Twin Liquors", 24.0)]
    ctx, _ = derive_price_context(history, avail, now=NOW)
    assert ctx["store"] == "Twin Liquors"
    assert ctx["amount"] == 6.0


def test_cheapest_nearby_flagged_once_with_delta():
    history = [_h("s1", 20.0, "2026-06-07T10:00:00+00:00"),
               _h("s2", 23.0, "2026-06-07T10:00:00+00:00")]
    avail = [_avail("s2", "Spec's", 23.0), _avail("s1", "H-E-B", 20.0)]
    ctx, rows = derive_price_context(history, avail, now=NOW)
    assert ctx["cheapest"] == {"retailer": "H-E-B", "price": 20.0, "delta_vs_next": 3.0}
    flags = {r["retailer"]: r["is_cheapest"] for r in rows}
    assert flags == {"H-E-B": True, "Spec's": False}


def test_dropped_store_row_carries_was_price():
    history = [
        _h("s1", 24.99, "2026-06-07T10:00:00+00:00"),
        _h("s1", 19.99, "2026-07-12T10:00:00+00:00"),
    ]
    _, rows = derive_price_context(history, [_avail("s1", "H-E-B", 19.99)], now=NOW)
    assert rows[0]["was_price"] == 24.99


def test_steady_store_row_has_no_was_price():
    history = [_h("s1", 28.0, "2026-06-07T10:00:00+00:00")]
    _, rows = derive_price_context(history, [_avail("s1", "Spec's", 28.0)], now=NOW)
    assert rows[0]["was_price"] is None


def test_strip_carries_price_forward_weekly_capped_at_six():
    """The week-marker glyph: weekly points for the headline store, gaps
    filled with the carried-forward price, most recent last, max six."""
    history = [
        _h("s1", 24.99, "2026-05-01T10:00:00+00:00"),   # long ago
        _h("s1", 19.99, "2026-07-12T10:00:00+00:00"),   # fresh drop
    ]
    ctx, _ = derive_price_context(history, [_avail("s1", "H-E-B", 19.99)], now=NOW)
    strip = ctx["strip"]
    assert len(strip) == 6
    assert strip[-1] == 19.99          # current week reflects the drop
    assert all(p == 24.99 for p in strip[:-1])   # carried forward before it


def test_supabase_fractional_seconds_parse():
    """Py3.9 fromisoformat requires 3 or 6 fractional digits; Supabase returns
    variable precision (e.g. .25511) — must not blow up."""
    history = [
        _h("s1", 24.99, "2026-06-07T10:00:00.5+00:00"),
        _h("s1", 19.99, "2026-07-12T09:53:21.25511+00:00"),
    ]
    ctx, _ = derive_price_context(history, [_avail("s1", "H-E-B", 19.99)], now=NOW)
    assert ctx["variant"] == "drop"


def test_fresh_drops_for_maps_pairs():
    from utils.price_context import fresh_drops_for
    history = [
        _h("s1", 24.99, "2026-06-07T10:00:00+00:00"), _h("s1", 19.99, "2026-07-12T10:00:00+00:00"),
        _h("s2", 30.0, "2026-06-07T10:00:00+00:00"),                       # steady
        _h("s3", 20.0, "2026-06-07T10:00:00+00:00"), _h("s3", 18.0, "2026-06-14T10:00:00+00:00"),  # old drop
    ]
    for row in history:
        row["wine_id"] = "w1"
    drops = fresh_drops_for(history, now=NOW)
    assert drops == {("w1", "s1"): {"amount": 5.0, "from_price": 24.99, "to_price": 19.99}}


def test_fresh_drops_for_ignores_rises_and_junk():
    from utils.price_context import fresh_drops_for
    history = [
        {"wine_id": "w1", "store_ref": "s1", "price": 10.0, "recorded_at": "2026-06-07T10:00:00+00:00"},
        {"wine_id": "w1", "store_ref": "s1", "price": 14.0, "recorded_at": "2026-07-12T10:00:00+00:00"},  # rise
        {"wine_id": None, "store_ref": "s2", "price": 9.0, "recorded_at": "2026-07-12T10:00:00+00:00"},
        {"wine_id": "w2", "store_ref": None, "price": 9.0, "recorded_at": "2026-07-12T10:00:00+00:00"},
    ]
    assert fresh_drops_for(history, now=NOW) == {}


def test_no_history_is_safe():
    ctx, rows = derive_price_context([], [_avail("s1", "H-E-B", 15.0)], now=NOW)
    assert ctx["variant"] == "steady"
    assert ctx["cheapest"]["retailer"] == "H-E-B"
    assert rows[0]["was_price"] is None


def test_history_for_faraway_store_is_ignored():
    """Movement at a store outside the availability list (not nearby) must not
    become the headline."""
    history = [
        _h("far", 30.0, "2026-06-07T10:00:00+00:00"),
        _h("far", 20.0, "2026-07-12T10:00:00+00:00"),
    ]
    ctx, _ = derive_price_context(history, [_avail("s1", "H-E-B", 25.0)], now=NOW)
    assert ctx["variant"] == "steady"
