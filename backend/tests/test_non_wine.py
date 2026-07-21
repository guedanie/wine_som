import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.non_wine import is_non_wine_name, should_exclude, matched_marker


def _w(name, varietal=None, grapes=None):
    return {"name": name, "varietal": varietal, "grapes": grapes or []}


# --- name matching (whole-word) ---
def test_flags_clear_non_wine_names():
    for n in ["Del Monte Fruit Cocktail in Heavy Syrup", "Pacifico Mexican Lager",
              "Gekkeikan Sake Nigori", "Stemless Champagne Glassware Set",
              "Birch Benders Organic Pancake & Waffle Mix", "Zarbee's Cough Syrup"]:
        assert is_non_wine_name(n) is True, n


def test_whole_word_does_not_flag_real_wine_names():
    for n in ["Barbera d'Alba", "Barolo Riserva", "Bardolino Classico",
              "Herdade do Alentejo Tinto", "Aleatico Passito", "Beerenauslese Riesling"]:
        assert is_non_wine_name(n) is False, n


# --- should_exclude guards ---
def test_excludes_flagged_with_no_wine_signal():
    assert should_exclude(_w("Pacifico Mexican Lager")) is True
    assert should_exclude(_w("Del Monte Fruit Cocktail")) is True


def test_barrel_guard_keeps_barrel_aged_wine():
    assert should_exclude(_w("Bota Box Bourbon Barrel Cabernet",
                             varietal="Cabernet Sauvignon")) is False
    # even if a marker somehow matched, 'barrel' in the name protects it
    assert should_exclude(_w("Some Beer Barrel Aged Red", grapes=["Zinfandel"])) is False


def test_wine_signal_guard_keeps_varietal_or_grape():
    # 'gift set' flags the name, but a real Bordeaux carries region/varietal
    assert should_exclude(_w("Chateau Calon-Segur Bordeaux Gift Set",
                             varietal="Cabernet Sauvignon")) is False
    assert should_exclude(_w("Some Lager-named Wine", grapes=["Riesling"])) is False


def test_allowlist_keeps_known_collisions():
    # these aren't flagged by the deny-list today, but the allowlist is insurance
    assert should_exclude(_w("Hampton Water Rose")) is False


def test_matched_marker_reports_reason():
    assert matched_marker("Pacifico Mexican Lager") == "lager"
    assert matched_marker("Chateau Margaux 2015") is None
