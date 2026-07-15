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


def test_norm_folds_hyphens_so_spelling_variants_match():
    """Prod rows write 'Lalande de Pomerol' where the table says
    'Lalande-de-Pomerol' — hyphen/space variants must resolve identically."""
    assert parent_region_for("Lalande de Pomerol") == "Bordeaux"
    assert parent_region_for("Cote Rotie") == "Rhône"
    assert parent_region_for("Saint-Émilion") == "Bordeaux"   # hyphenated still fine
    from enrichment.extraction.reference import canonical_region
    assert canonical_region("Côtes-du-Rhône") == "Rhône"


def test_default_grapes_left_and_right_bank_unchanged():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Pauillac") == ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert default_grapes_for("Saint-Émilion") == ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]
    assert default_grapes_for("Châteauneuf-du-Pape") == ["Grenache", "Syrah", "Mourvèdre"]
    assert default_grapes_for("Nowhere") is None
    assert default_grapes_for(None) is None


def test_default_grapes_gate_blocks_color_conflicts():
    """A white wine in a red appellation must NOT get a red blend — the
    extractor was stamping Cab/Merlot on white Pessac-Léognan."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Margaux", wine_type="white") is None
    assert default_grapes_for("Châteauneuf-du-Pape", wine_type="white") is None
    assert default_grapes_for("Margaux", wine_type="red") == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]


def test_multi_color_appellations_require_explicit_type():
    """Graves/Pessac-Léognan bottle both colors — unknown type must not guess."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Graves") is None
    assert default_grapes_for("Graves", wine_type="red") == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert default_grapes_for("Graves", wine_type="white") == \
        ["Sauvignon Blanc", "Sémillon"]
    assert default_grapes_for("Pessac-Léognan", wine_type="white") == \
        ["Sauvignon Blanc", "Sémillon"]


def test_single_color_appellations_fire_on_unknown_type():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Pauillac", wine_type=None) == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]


def test_sauternes_accepts_dessert_wine_type():
    """Prod Sauternes rows carry wine_type='dessert' — the white blend must fire."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Sauternes", wine_type="dessert") == \
        ["Sémillon", "Sauvignon Blanc"]
    assert default_grapes_for("Sauternes", wine_type="red") is None


def test_right_bank_satellites_and_grand_cru_get_merlot_led_blend():
    """30 uncovered Bordeaux rows in the 07-14 audit sit in these appellations."""
    from enrichment.extraction.reference import default_grapes_for
    merlot_led = ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]
    for app in ["Saint-Émilion Grand Cru", "Lussac-Saint-Émilion",
                "Montagne-Saint-Émilion", "Puisseguin-Saint-Émilion",
                "Castillon", "Castillon Côtes de Bordeaux", "Côtes de Castillon",
                "Côtes de Francs", "Blaye Côtes de Bordeaux", "Côtes de Bourg",
                "Bordeaux Supérieur"]:
        assert default_grapes_for(app) == merlot_led, app
    # Côtes de Bordeaux (whites exist) requires an explicit type
    assert default_grapes_for("Côtes de Bordeaux") is None
    assert default_grapes_for("Côtes de Bordeaux", wine_type="red") == merlot_led


def test_bordeaux_white_appellations():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Entre-Deux-Mers") == ["Sauvignon Blanc", "Sémillon"]
    assert default_grapes_for("Entre-Deux-Mers", wine_type="red") is None
    assert default_grapes_for("Loupiac", wine_type="dessert") == \
        ["Sémillon", "Sauvignon Blanc"]
    assert default_grapes_for("Cadillac") == ["Sémillon", "Sauvignon Blanc"]


def test_northern_rhone_syrah_and_whites():
    from enrichment.extraction.reference import default_grapes_for
    # red-only crus fire on unknown type
    assert default_grapes_for("Côte-Rôtie") == ["Syrah"]
    assert default_grapes_for("Cornas") == ["Syrah"]
    # dual-color crus require explicit type
    assert default_grapes_for("Hermitage") is None
    assert default_grapes_for("Hermitage", wine_type="red") == ["Syrah"]
    assert default_grapes_for("Crozes-Hermitage", wine_type="white") == \
        ["Marsanne", "Roussanne"]
    assert default_grapes_for("Saint-Joseph", wine_type="red") == ["Syrah"]
    assert default_grapes_for("Condrieu") == ["Viognier"]


def test_tavel_is_grenache_rose():
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Tavel", wine_type="rose") == ["Grenache"]
    assert default_grapes_for("Tavel", wine_type="rosé") == ["Grenache"]   # accent folds
    assert default_grapes_for("Tavel") == ["Grenache"]                     # rosé-only AOC
    assert default_grapes_for("Tavel", wine_type="red") is None


def test_southern_rhone_satellites_and_spelling_variants():
    """'Côte du Rhône' (singular) is a real prod variant — 4 rows."""
    from enrichment.extraction.reference import default_grapes_for
    gsm = ["Grenache", "Syrah", "Mourvèdre"]
    for app in ["Côtes du Rhône Villages", "Côte du Rhône", "Ventoux",
                "Cairanne", "Rasteau", "Vinsobres"]:
        assert default_grapes_for(app) == gsm, app
    assert default_grapes_for("Lalande de Pomerol") == \
        ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"]   # hyphen fold, Task 1
