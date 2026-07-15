"""Tests for the region revalidation backfill (scripts/revalidate_regions.py).

plan_change(row) decides, per wine, which place fields (region/sub_region/
country) to rewrite after running the gazetteer + evidence gate. Safe-subset
policy: only POSITIVE changes (gazetteer fixes, canonicalization renames,
country fills) are applied; null-assignments are deferred and reported — the
evidence gate's appellation coverage is too thin to bulk-null at rest
(it would null correct producer-knowledge regions like Grgich Hills → Napa).
Returns (changes, deferred_nulls).
"""
from scripts.revalidate_regions import plan_change


def _row(**kw):
    base = {
        "id": "w1",
        "name": "",
        "description": "",
        "description_long": "",
        "region": None,
        "sub_region": None,
        "country": None,
    }
    base.update(kw)
    return base


def test_unevidenced_region_null_is_deferred_not_applied():
    changes, deferred = plan_change(_row(
        name="La Cave Prosecco Extra Dry", region="Rhône", country="France"))
    assert changes == {}
    assert set(deferred) == {"region", "country"}


def test_evidenced_region_untouched():
    changes, deferred = plan_change(_row(
        name="Ruffino Chianti Classico", region="Tuscany", country="Italy"))
    assert changes == {}
    assert deferred == {}


def test_gazetteer_producer_fixes_misattribution():
    changes, _ = plan_change(_row(
        name="Puerto Viejo Merlot", region="Bordeaux", country="France"))
    assert changes["region"] == "Curicó Valley"
    assert changes["country"] == "Chile"


def test_canonicalization_rename_applied():
    changes, deferred = plan_change(_row(
        name="Antinori Toscana IGT", region="Toscana", country="Italy"))
    assert changes == {"region": "Tuscany"}
    assert deferred == {}


def test_country_fill_for_evidenced_region():
    changes, _ = plan_change(_row(
        name="Duckhorn Vineyards Napa Valley Cabernet Sauvignon",
        region="Napa Valley"))
    assert changes == {"country": "United States"}


def test_no_country_fill_when_region_unevidenced():
    # A hallucinated Bordeaux must not gain country=France; both nulls deferred.
    changes, deferred = plan_change(_row(
        name="Rusty Gate Red Blend", region="Bordeaux"))
    assert changes == {}
    assert set(deferred) == {"region"}


def test_no_region_means_no_change():
    changes, deferred = plan_change(_row(name="Mystery Red"))
    assert changes == {}
    assert deferred == {}


def test_description_chateau_mentions_are_ignored():
    # Descriptions compare wines to famous estates ("in the style of Pétrus");
    # the backfill matches on the name only.
    changes, _ = plan_change(_row(
        name="Les Noyers Vin de France",
        description="Made by a winemaker trained at Petrus in Pomerol.",
        region="Bordeaux", country="France"))
    assert changes == {}
