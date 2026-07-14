import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from datetime import datetime, timezone
from recommendation.deals import deal_score, rank_deals, week_of_label


def _item(amount=5.0, from_price=25.0, rating=4.2, count=1000, **over):
    d = {"amount": amount, "from_price": from_price, "to_price": from_price - amount,
         "vivino_rating": rating, "vivino_ratings_count": count}
    d.update(over)
    return d


def test_quality_times_movement_not_percent_off():
    """A well-rated bottle with a modest drop beats a mediocre bottle with a
    huge drop — sommelier judgment, not a bargain bin."""
    good_small = _item(amount=3.0, from_price=30.0, rating=4.5, count=5000, name="good")
    meh_big = _item(amount=12.0, from_price=30.0, rating=3.6, count=5000, name="meh")
    ranked = rank_deals([meh_big, good_small])
    assert ranked[0]["name"] == "good"


def test_unrated_wines_still_rank_but_below_equally_dropped_rated():
    unrated = _item(rating=None, count=0, name="unrated")
    rated = _item(rating=4.4, count=2000, name="rated")
    ranked = rank_deals([unrated, rated])
    assert ranked[0]["name"] == "rated"
    assert deal_score(unrated) > 0        # not excluded — just below


def test_thin_rating_counts_treated_as_unrated():
    thin = _item(rating=4.9, count=5, name="thin")
    solid = _item(rating=4.2, count=500, name="solid")
    ranked = rank_deals([thin, solid])
    assert ranked[0]["name"] == "solid"


def test_relative_movement_capped():
    """A 90%-off data glitch shouldn't dominate the cut."""
    glitch = _item(amount=27.0, from_price=30.0, rating=3.8, count=100, name="glitch")
    honest = _item(amount=6.0, from_price=30.0, rating=4.5, count=5000, name="honest")
    ranked = rank_deals([glitch, honest])
    assert ranked[0]["name"] == "honest"


def test_personalization_seam_multiplies():
    a = _item(rating=4.0, count=100, name="a")
    b = _item(rating=4.0, count=100, name="b")
    ranked = rank_deals([a, b], personalization_weight=lambda d: 2.0 if d["name"] == "b" else 1.0)
    assert ranked[0]["name"] == "b"


def test_editorial_cut_drops_jug_wine_and_poor_ratings():
    """'Not a bargain bin. These are bottles I'd recommend anyway.' A $2.39
    jug wine or a 3.4-star bottle isn't a deal, whatever the drop."""
    from recommendation.deals import editorial_cut
    jug = _item(price=2.39, rating=3.9, count=900, name="jug")
    poor = _item(price=15.0, rating=3.4, count=900, name="poor")
    unrated_ok = _item(price=12.0, rating=None, count=0, name="unrated")
    rated_ok = _item(price=19.0, rating=4.2, count=900, name="rated")
    kept = [d["name"] for d in editorial_cut([jug, poor, unrated_ok, rated_ok])]
    assert kept == ["unrated", "rated"]


def test_deal_score_accepts_was_price_alias():
    a = _item(); b = dict(_item()); del b["from_price"]; b["was_price"] = 25.0
    assert deal_score(a) == deal_score(b)


def test_week_of_label_is_most_recent_sunday():
    # Monday 2026-07-13 → week of Sunday Jul 12
    assert week_of_label(datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)) == "JUL 12"
    # Sunday itself is its own week
    assert week_of_label(datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)) == "JUL 12"
    # no leading zero
    assert week_of_label(datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)) == "JUL 5"
