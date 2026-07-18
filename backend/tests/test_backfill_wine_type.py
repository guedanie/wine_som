import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.backfill_wine_type import plan_change


def _row(**kw):
    base = {"id": "w1", "name": "", "varietal": None, "grapes": [],
            "region": None, "sub_region": None, "wine_type": None}
    base.update(kw); return base


def test_resolves_from_varietal():
    assert plan_change(_row(varietal="Nero d'Avola")) == {"wine_type": "red"}


def test_resolves_from_name_when_varietal_missing():
    assert plan_change(_row(name="Domaine X Chablis 2022", varietal=None)) == {"wine_type": "white"}


def test_resolves_from_grape_when_varietal_and_name_miss():
    assert plan_change(_row(name="Domaine X 2022", grapes=["Furmint"])) == {"wine_type": "white"}


def test_resolves_from_appellation_last():
    assert plan_change(_row(name="Canalicchio Di Sopra 2019", region="Tuscany",
                            sub_region="Brunello di Montalcino")) == {"wine_type": "red"}


def test_fill_only_never_overwrites():
    assert plan_change(_row(varietal="Merlot", wine_type="white")) == {}


def test_noop_when_unresolvable():
    assert plan_change(_row(name="Del Monte Fruit Cocktail in Heavy Syrup")) == {}
    assert plan_change(_row(name="Domaine Lignier Morey-Saint-Denis", region="Burgundy")) == {}


def test_pet_nat_resolves_sparkling_not_red():
    assert plan_change(_row(name="Old World Winery Zinfandel Pet Nat")) == {"wine_type": "sparkling"}
