"""Tests for the grapes backfill (scripts/backfill_grapes.py).

plan_change(row) decides, per grapes-empty Bordeaux/Rhône wine, what to write:
a trusted specific varietal ([varietal]), the appellation-law blend (color-
gated), or the red-only region-level blend — in that precedence. varietal is
set to the blend's lead grape only when NULL. Returns (changes, rule).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.backfill_grapes import plan_change


def _row(**kw):
    base = {
        "id": "w1", "name": "Château Test", "region": "Bordeaux",
        "sub_region": None, "varietal": None, "wine_type": "red", "grapes": [],
    }
    base.update(kw)
    return base


def test_specific_varietal_is_trusted_over_the_appellation_blend():
    """varietal='Merlot' on a left-bank row: the label gave us the grape —
    appellation law must not contradict it."""
    changes, rule = plan_change(_row(varietal="Merlot", sub_region="Margaux"))
    assert changes == {"grapes": ["Merlot"]}          # varietal untouched
    assert rule == "specific-varietal"


def test_generic_varietal_gets_blend_and_keeps_its_label():
    changes, rule = plan_change(_row(varietal="Red Blend", sub_region="Pauillac"))
    assert changes == {"grapes": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]}
    assert rule == "appellation"


def test_null_varietal_gets_blend_plus_lead_grape():
    changes, _ = plan_change(_row(sub_region="Saint-Émilion"))
    assert changes["grapes"] == ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]
    assert changes["varietal"] == "Merlot"


def test_white_wine_in_red_appellation_left_for_vivino():
    changes, rule = plan_change(_row(sub_region="Margaux", wine_type="white"))
    assert changes == {}
    assert rule is None


def test_sauternes_dessert_rows_get_the_semillon_blend():
    changes, _ = plan_change(_row(sub_region="Sauternes", wine_type="dessert"))
    assert changes["grapes"] == ["Sémillon", "Sauvignon Blanc"]
    assert changes["varietal"] == "Sémillon"


def test_region_only_red_gets_region_default():
    changes, rule = plan_change(_row(region="Rhône"))
    assert changes == {"grapes": ["Grenache", "Syrah", "Mourvèdre"],
                       "varietal": "Grenache"}
    assert rule == "region"


def test_region_only_unknown_type_left_for_vivino():
    changes, rule = plan_change(_row(wine_type=None))
    assert changes == {}
    assert rule is None


def test_specific_varietal_synonyms_are_canonicalized_into_grapes():
    """'Shiraz' folds to 'Syrah' in grapes; the varietal column itself stays
    untouched (set-only-when-NULL policy) — an intended cross-field mismatch."""
    changes, rule = plan_change(_row(region="Rhône", varietal="Shiraz"))
    assert changes == {"grapes": ["Syrah"]}
    assert rule == "specific-varietal"


def test_rows_with_grapes_or_foreign_regions_are_untouched():
    assert plan_change(_row(grapes=["Zinfandel"]))[0] == {}
    assert plan_change(_row(region="Napa Valley", sub_region="Oakville"))[0] == {}
    assert plan_change(_row(region=None))[0] == {}


def test_champagne_sparkling_gets_pn_led_blend():
    changes, rule = plan_change(_row(region="Champagne", wine_type="sparkling"))
    assert changes == {"grapes": ["Pinot Noir", "Chardonnay", "Pinot Meunier"],
                       "varietal": "Pinot Noir"}
    assert rule == "region"


def test_generic_port_varietal_keeps_label_gains_blend():
    """varietal='Port' is a place-word, not a grape — is_specific_grape says
    generic, so the blend fills and the label survives."""
    changes, rule = plan_change(_row(region="Douro", wine_type="dessert",
                                     varietal="Port"))
    assert changes == {"grapes": ["Touriga Nacional", "Touriga Franca",
                                  "Tinta Roriz"]}
    assert rule == "region"


def test_chianti_classico_fills_on_unknown_type():
    changes, rule = plan_change(_row(region="Tuscany", wine_type=None,
                                     sub_region="Chianti Classico"))
    assert changes == {"grapes": ["Sangiovese"], "varietal": "Sangiovese"}
    assert rule == "appellation"


def test_tuscany_region_only_rows_left_for_vivino():
    """No Tuscany region rule (Super Tuscans) — typed red or not."""
    assert plan_change(_row(region="Tuscany", wine_type="red"))[0] == {}
    assert plan_change(_row(region="Tuscany", wine_type=None))[0] == {}


def test_iberian_single_varietal_is_trusted_not_trioed():
    changes, rule = plan_change(_row(region="Douro", wine_type="red",
                                     varietal="Tinta Roriz"))
    assert changes == {"grapes": ["Tinta Roriz"]}
    assert rule == "specific-varietal"


def test_provence_rose_fills_white_does_not():
    changes, rule = plan_change(_row(region="Provence", wine_type="rosé"))
    assert changes["grapes"] == ["Grenache", "Cinsault", "Syrah"]
    assert rule == "region"
    assert plan_change(_row(region="Provence", wine_type="white"))[0] == {}
