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


def test_ambiguous_appellation_words_in_name_do_not_type():
    # 'fino'/'marsala'/'jerez'/'gavi' as name homonyms must not force a type
    assert plan_change(_row(name="Fino House Cuvee Red 2020")) == {"wine_type": "red"}
    assert plan_change(_row(name="Marsala Family Estate 2021")) == {}
    # explicit region path still works for a real Jerez sherry
    assert plan_change(_row(name="Bodega X", region="Other Spain", sub_region="Jerez")) == {"wine_type": "fortified"}


def test_non_wine_products_are_not_typed():
    """Grocery/beverage catalog noise (sake, cocktails, food) must stay NULL —
    they have color/style words but aren't grape wine."""
    for junk in [
        "Hiro Sake Red Junmai", "Ninki-ichi Junmai Daiginjo Sparkling Sake",
        "Stella Rosa Naturals Peach Non-alcoholic Wine",
        "Coral Sparkling Cocktail Cucumber & Watermelon",
        "Simple Truth Organic Dark Color Maple Syrup",
        "Sunrise Flour Mill Heritage Pancake Mix",
        "Kroger Red Grapefruit Cup in Extra Light Syrup",
        "Rama Caida Sidra Demi Sec Sparkling Apple Wine",
        "Country Crush Fruit Wine Co Peach Fruit Wine",
        "Ozeki Hana Awaka Sparkling Sake",
    ]:
        assert plan_change(_row(name=junk, varietal="Red Blend")) == {}, junk


def test_non_wine_guard_does_not_over_reach_real_wines():
    """Real wines whose names merely contain a substring of a junk token must
    still be typed (word-boundary matching, not substring)."""
    assert plan_change(_row(name="Maple Creek Zinfandel", varietal="Zinfandel")) == {"wine_type": "red"}
    assert plan_change(_row(name="Sakonnet Vineyards Chardonnay", varietal="Chardonnay")) == {"wine_type": "white"}
    assert plan_change(_row(name="Duplin Sweet Muscadine Red", varietal=None)) == {"wine_type": "red"}  # muscadine IS a grape


def test_plural_cocktails_are_skipped():
    for junk in ["Dailys Wine Cocktails Tea Lemon",
                 "Coral Agave Based Cocktails Variety Pack"]:
        assert plan_change(_row(name=junk, varietal="Red Blend")) == {}, junk
