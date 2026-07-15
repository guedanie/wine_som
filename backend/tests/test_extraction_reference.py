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


def test_unaccented_rhone_canonicalizes():
    """21 prod wines sit under region 'Rhone' (no accent) fragmenting the
    catalog — plus 'Rhone Valley' variants."""
    from enrichment.extraction.reference import canonical_region
    assert canonical_region('Rhone') == 'Rhône'
    assert canonical_region('rhone valley') == 'Rhône'
    assert canonical_region('Côtes du Rhône') == 'Rhône'


def test_rhone_satellites_are_known_appellations():
    """Ventoux/Luberon/CdR-Villages crus are southern Rhône — without them the
    evidence gate false-flags legit bottles (54 in the 07-14 audit) and new
    extractions fragment into their own regions."""
    from enrichment.extraction.reference import parent_region_for
    for app in ['Ventoux', 'Luberon', 'Cairanne', 'Rasteau', 'Séguret',
                'Plan de Dieu', 'Costières de Nîmes', 'Beaumes-de-Venise',
                'Côtes du Rhône Villages', 'Saint-Péray']:
        assert parent_region_for(app) == 'Rhône', app


def test_evidence_tolerates_cotes_du_rhones_plural():
    from enrichment.extraction.reference import region_evidenced
    assert region_evidenced('Rhône', 'Chateau Pegau Setier Cotes Du Rhones Villages')


def test_cdr_shorthand_and_pegau_producer():
    from enrichment.extraction.reference import region_evidenced, gazetteer_hit
    assert region_evidenced('Rhône', "L'espigouette Vieilles Vignes Cdr")
    assert gazetteer_hit('Pink Pegau Rose')['region'] == 'Rhône'


def test_bordeaux_satellites_are_known_appellations():
    """Côtes de Francs/Castillon/Blaye/Bourg + right-bank satellites are
    Bordeaux — without them the evidence gate false-flags legit bottles
    (130+ in the 07-14 Bordeaux audit)."""
    from enrichment.extraction.reference import parent_region_for
    for app in ['Côtes de Francs', 'Francs Côtes de Bordeaux',
                'Castillon Côtes de Bordeaux', 'Côtes de Castillon',
                'Blaye Côtes de Bordeaux', 'Côtes de Bourg', 'Cadillac',
                'Loupiac', 'Lussac-Saint-Émilion', 'Montagne-Saint-Émilion',
                'Puisseguin-Saint-Émilion']:
        assert parent_region_for(app) == 'Bordeaux', app


def test_bdx_shorthand_evidences_bordeaux():
    from enrichment.extraction.reference import region_evidenced
    assert region_evidenced('Bordeaux', 'Pull Bdx Red Blend')
    assert region_evidenced('Bordeaux', 'Chateau Puygueraud Rouge Cotes De Francs')


def test_st_abbreviation_folds_to_saint():
    """Retail names abbreviate Saint → St. ('Chateau Canon St. Emilion',
    'Montagne St Emilion') — evidence and gazetteer matching must see them."""
    from enrichment.extraction.reference import region_evidenced
    assert region_evidenced('Bordeaux', 'Chateau Canon (6 / Case) St. Emilion')
    assert region_evidenced('Bordeaux', 'Clos De Bouard Montagne St Emilion 2020')


def test_listrac_without_medoc_suffix_is_bordeaux():
    from enrichment.extraction.reference import parent_region_for, region_evidenced
    assert parent_region_for('Listrac') == 'Bordeaux'
    assert region_evidenced('Bordeaux', 'Chateau Clarke Listrac 2020 (750ml)')
