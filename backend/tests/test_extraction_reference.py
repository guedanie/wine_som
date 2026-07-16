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


def test_region_level_defaults_fire_only_for_explicit_red():
    """68 prod rows have region but no sub_region — Bordeaux AOC rouge is
    Merlot-led by law; region-only Rhône reds are overwhelmingly southern GSM."""
    from enrichment.extraction.reference import default_grapes_for_region
    assert default_grapes_for_region("Bordeaux", "red") == \
        ["Merlot", "Cabernet Sauvignon", "Cabernet Franc"]
    assert default_grapes_for_region("Rhône", "red") == \
        ["Grenache", "Syrah", "Mourvèdre"]
    assert default_grapes_for_region("Rhone", "red") is not None   # accent variant
    assert default_grapes_for_region("Bordeaux", None) is None
    assert default_grapes_for_region("Bordeaux", "white") is None
    assert default_grapes_for_region("Napa Valley", "red") is None
    assert default_grapes_for_region(None, "red") is None


def test_all_default_blends_contains_every_law_blend():
    """Vivino's write_facts uses this to recognize (and replace) law-book
    approximations without a schema change."""
    from enrichment.extraction.reference import ALL_DEFAULT_BLENDS
    assert ("Cabernet Sauvignon", "Merlot", "Cabernet Franc") in ALL_DEFAULT_BLENDS
    assert ("Merlot", "Cabernet Franc", "Cabernet Sauvignon") in ALL_DEFAULT_BLENDS
    assert ("Merlot", "Cabernet Sauvignon", "Cabernet Franc") in ALL_DEFAULT_BLENDS
    assert ("Grenache", "Syrah", "Mourvèdre") in ALL_DEFAULT_BLENDS
    assert ("Syrah",) in ALL_DEFAULT_BLENDS
    assert ("Viognier",) in ALL_DEFAULT_BLENDS
    assert ("Zinfandel",) not in ALL_DEFAULT_BLENDS


def test_is_specific_grape_accepts_real_grapes_rejects_generics():
    """Backfill rule: a specific-grape varietal is trusted (grapes=[varietal]);
    generics fall through to the appellation blend. 'Sauternes' as a varietal
    (2 prod rows) is a place, not a grape — generic."""
    from enrichment.extraction.reference import is_specific_grape
    for real in ["Merlot", "merlot", "Shiraz", "Sémillon", "Semillon", "Viognier"]:
        assert is_specific_grape(real), real
    for generic in ["Red Blend", "White Blend", "Red Wine", "White Wine",
                    "Other", "Sauternes", None, ""]:
        assert not is_specific_grape(generic), generic


def test_gate_edge_cases_rose_conflict_and_empty_string_type():
    """Empty-string wine_type means 'unknown' (single-color rules fire);
    a known conflicting type ('rosé') never does."""
    from enrichment.extraction.reference import default_grapes_for
    assert default_grapes_for("Margaux", wine_type="rosé") is None
    assert default_grapes_for("Margaux", wine_type="") == \
        ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]


def test_is_default_blend_accepts_lists_and_tuples():
    from enrichment.extraction.reference import is_default_blend
    assert is_default_blend(["Grenache", "Syrah", "Mourvèdre"])
    assert is_default_blend(("Syrah",))
    assert not is_default_blend(["Zinfandel"])
    assert not is_default_blend([])
    assert not is_default_blend(None)


def test_region_rules_champagne_sparkling_and_rose():
    """Champagne AOC permits 7 grapes; PN/Chard/Meunier are 99.7% of
    plantings. Rosé Champagne uses the same grapes. Tier A (hard law)."""
    from enrichment.extraction.reference import default_grapes_for_region
    champagne = ["Pinot Noir", "Chardonnay", "Pinot Meunier"]
    assert default_grapes_for_region("Champagne", "sparkling") == champagne
    assert default_grapes_for_region("Champagne", "rosé") == champagne   # accent folds
    assert default_grapes_for_region("Champagne", "red") is None
    assert default_grapes_for_region("Champagne", None) is None


def test_region_rules_douro_penedes_provence():
    """Approved Tier B conventions: Port big-three (red+dessert), Penedès
    sparkling = Cava trio, Provence rosé template."""
    from enrichment.extraction.reference import default_grapes_for_region
    port = ["Touriga Nacional", "Touriga Franca", "Tinta Roriz"]
    assert default_grapes_for_region("Douro", "dessert") == port
    assert default_grapes_for_region("Douro", "red") == port
    assert default_grapes_for_region("Douro", "white") is None
    assert default_grapes_for_region("Penedès", "sparkling") == \
        ["Macabeo", "Xarel·lo", "Parellada"]
    assert default_grapes_for_region("Penedes", "sparkling") is not None  # accent variant
    assert default_grapes_for_region("Penedès", "rosé") is None
    assert default_grapes_for_region("Provence", "rosé") == \
        ["Grenache", "Cinsault", "Syrah"]
    assert default_grapes_for_region("Provence", "red") is None


def test_region_rules_never_fire_without_explicit_type():
    """Region granularity is too coarse to guess on unknown type — the
    conservative invariant from the 07-14 design, now spanning all colors."""
    from enrichment.extraction.reference import default_grapes_for_region
    for region in ("Bordeaux", "Rhône", "Champagne", "Douro", "Penedès", "Provence"):
        assert default_grapes_for_region(region, None) is None, region
        assert default_grapes_for_region(region, "") is None, region


def test_all_default_blends_gains_the_new_trios():
    from enrichment.extraction.reference import ALL_DEFAULT_BLENDS
    assert ("Pinot Noir", "Chardonnay", "Pinot Meunier") in ALL_DEFAULT_BLENDS
    assert ("Touriga Nacional", "Touriga Franca", "Tinta Roriz") in ALL_DEFAULT_BLENDS
    assert ("Macabeo", "Xarel·lo", "Parellada") in ALL_DEFAULT_BLENDS
    assert ("Grenache", "Cinsault", "Syrah") in ALL_DEFAULT_BLENDS
