import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from utils import infer_wine_type


def test_accent_folded_varietals_resolve():
    assert infer_wine_type("Mourvèdre") == "red"
    assert infer_wine_type("Gewürztraminer") == "white"
    assert infer_wine_type("Sémillon") == "white"


def test_pet_nat_and_col_fondo_are_sparkling_not_red():
    assert infer_wine_type("Zinfandel Pet Nat") == "sparkling"
    assert infer_wine_type("Pétillant Naturel Rosé") == "sparkling"
    assert infer_wine_type("Col Fondo") == "sparkling"


def test_existing_behavior_preserved():
    assert infer_wine_type("Cabernet Sauvignon") == "red"
    assert infer_wine_type("Red Wine") == "red"
    assert infer_wine_type("Sauvignon Blanc") == "white"
    assert infer_wine_type("Rosé") == "rosé"
    assert infer_wine_type("Sparkling Wine") == "sparkling"
    assert infer_wine_type("Portuguese") is None
    assert infer_wine_type("Fruit Cocktail") is None


def test_newly_added_grapes_resolve():
    for red in ["Nero d'Avola", "Gamay", "Corvina", "Cinsault", "Carignan",
                "Aglianico", "Pinotage", "Monastrell", "Cabernet Franc"]:
        assert infer_wine_type(red) == "red", red
    for white in ["Grüner Veltliner", "Sémillon", "Furmint", "Melon de Bourgogne",
                  "Garganega", "Trebbiano", "Cortese", "Fiano", "Greco",
                  "Assyrtiko", "Vermentino"]:
        assert infer_wine_type(white) == "white", white


def test_ancestral_brand_word_does_not_force_sparkling():
    """'Ancestral' is a common English brand word — it must not override a real
    varietal signal (méthode ancestrale is still caught by its own phrase)."""
    assert infer_wine_type("Ancestral Vines Cabernet") == "red"
    assert infer_wine_type("Domaine X Méthode Ancestrale") == "sparkling"


def test_port_sherry_madeira_are_fortified_not_dessert():
    assert infer_wine_type("Taylor Fladgate 10 Year Tawny Port") == "fortified"
    assert infer_wine_type("Lustau Fino Sherry") == "fortified"
    assert infer_wine_type("Blandy's Madeira") == "fortified"
    # true dessert wines unchanged
    assert infer_wine_type("Château d'Yquem Sauternes") == "dessert"
    assert infer_wine_type("Inniskillin Ice Wine") == "dessert"


def test_infer_covers_core_grapes():
    from enrichment.extraction.reference import CORE_GRAPES
    for g in CORE_GRAPES["red"]:
        assert infer_wine_type(g) == "red", g
    for g in CORE_GRAPES["white"]:
        assert infer_wine_type(g) == "white", g
