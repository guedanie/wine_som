import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.extraction.reference import (
    parent_region_for, APPELLATIONS, CORE_GRAPES, FEW_SHOT,
)


def test_parent_region_for_bordeaux_appellation():
    assert parent_region_for("Saint-Émilion") == "Bordeaux"
    assert parent_region_for("Pomerol") == "Bordeaux"


def test_parent_region_for_is_case_and_accent_insensitive():
    assert parent_region_for("saint-emilion") == "Bordeaux"
    assert parent_region_for("SAINT-ÉMILION") == "Bordeaux"
    assert parent_region_for("  margaux ") == "Bordeaux"


def test_parent_region_for_napa_and_other_regions():
    assert parent_region_for("Oakville") == "Napa Valley"
    assert parent_region_for("Russian River Valley") == "Sonoma"
    assert parent_region_for("Barolo") == "Piedmont"
    assert parent_region_for("Uco Valley") == "Mendoza"


def test_parent_region_for_unknown_returns_none():
    assert parent_region_for("Nowhere Valley") is None
    assert parent_region_for("") is None
    assert parent_region_for(None) is None


def test_cheat_sheets_are_populated():
    assert len(APPELLATIONS) >= 20          # many regions
    assert "Cabernet Sauvignon" in CORE_GRAPES["red"]
    assert "Chardonnay" in CORE_GRAPES["white"]
    assert len(FEW_SHOT) >= 4
