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
