import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.extraction.extractor import _post_process, _system_prompt
from enrichment.extraction.reference import gazetteer_hit


# ── gazetteer: producer/château name → place, deterministically ─────────────

def test_chateau_name_fixes_appellation_region_country():
    hit = gazetteer_hit("Chateau Greysac Medoc Cru Bourgeois 2019")
    assert hit["sub_region"] == "Médoc"
    assert hit["region"] == "Bordeaux"
    assert hit["country"] == "France"


def test_chateau_match_is_accent_and_case_insensitive():
    assert gazetteer_hit("CHÂTEAU LYNCH-BAGES")["sub_region"] == "Pauillac"
    assert gazetteer_hit("chateau lynch bages")["sub_region"] == "Pauillac"


def test_longest_match_wins():
    """'Latour-Martillac' must land in Pessac-Léognan, not match 'Latour' (Pauillac)."""
    assert gazetteer_hit("Chateau Latour-Martillac Blanc")["sub_region"] == "Pessac-Léognan"
    assert gazetteer_hit("Chateau Latour 2010")["sub_region"] == "Pauillac"


def test_producer_gazetteer_fixes_the_requingua_class():
    hit = gazetteer_hit("Vina Requingua Puerto Viejo Reserve Estate Bottled Single Vineyard Merlot")
    assert hit["region"] == "Curicó Valley"
    assert hit["country"] == "Chile"
    assert hit["sub_region"] is None


def test_no_hit_returns_none():
    assert gazetteer_hit("Rusty Gate Merlot California") is None


# ── post-process with source text: gazetteer override + blend defaults ──────

def _rec(**over):
    base = {"wine_id": "w1", "region": None, "sub_region": None, "country": None,
            "vintage_year": None, "varietal": None, "grapes": [], "abv": None, "body": None}
    base.update(over)
    return base


def test_gazetteer_overrides_hallucinated_region():
    rec = _rec(region="Bordeaux", country="France", varietal="Merlot", grapes=["Merlot"])
    out = _post_process(rec, source_text="Vina Requingua Puerto Viejo Merlot")
    assert out["region"] == "Curicó Valley"
    assert out["country"] == "Chile"


def test_left_bank_chateau_fills_the_legal_blend():
    rec = _rec(varietal=None, grapes=[])
    out = _post_process(rec, source_text="Chateau Greysac 2019")
    assert out["grapes"] == ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert out["varietal"] == "Cabernet Sauvignon"


def test_right_bank_appellation_fills_merlot_led_blend():
    rec = _rec(sub_region="Pomerol", grapes=[])
    out = _post_process(rec, source_text="Clos de la Vieille Eglise Pomerol 2018")
    assert out["region"] == "Bordeaux"
    assert out["grapes"][0] == "Merlot"


def test_model_grapes_are_never_overwritten_by_blend_default():
    rec = _rec(sub_region="Pauillac", grapes=["Cabernet Sauvignon", "Petit Verdot"])
    out = _post_process(rec, source_text="Chateau Pontet-Canet Pauillac")
    assert out["grapes"] == ["Cabernet Sauvignon", "Petit Verdot"]


# ── evidence gate: unsupported region/country → NULL, not confident-wrong ───

def test_unevidenced_region_is_nulled():
    """The Requingua failure class: model free-associates Merlot → Bordeaux.
    Nothing in the source says Bordeaux → honest NULL."""
    rec = _rec(region="Bordeaux", country="France", varietal="Merlot", grapes=["Merlot"])
    out = _post_process(rec, source_text="Rusty Gate Merlot")
    assert out["region"] is None
    assert out["country"] is None


def test_region_evidenced_by_its_own_name_is_kept():
    rec = _rec(region="Bordeaux", country="France")
    out = _post_process(rec, source_text="Mouton Cadet Bordeaux Rouge")
    assert out["region"] == "Bordeaux"
    assert out["country"] == "France"


def test_region_evidenced_by_an_appellation_is_kept():
    rec = _rec(region="Tuscany", sub_region="Chianti Classico", country="Italy")
    out = _post_process(rec, source_text="Ruffino Chianti Classico DOCG")
    assert out["region"] == "Tuscany"


def test_region_evidenced_by_distinctive_token_is_kept():
    rec = _rec(region="Willamette Valley", country="United States")
    out = _post_process(rec, source_text="Cloudline Willamette Pinot Noir")
    assert out["region"] == "Willamette Valley"


def test_invented_sub_region_is_nulled():
    rec = _rec(region="Bordeaux", sub_region="Pauillac", country="France")
    out = _post_process(rec, source_text="Rusty Gate Red Blend")
    assert out["sub_region"] is None
    assert out["region"] is None


def test_evidenced_country_survives_region_null():
    rec = _rec(region="Bordeaux", country="France")
    out = _post_process(rec, source_text="Rusty Gate Rouge — Product of France")
    assert out["region"] is None
    assert out["country"] == "France"


def test_no_source_text_keeps_legacy_behavior():
    rec = _rec(region="Bordeaux", country="France")
    out = _post_process(rec)
    assert out["region"] == "Bordeaux"


# ── prompt carries the new guardrails ────────────────────────────────────────

def test_prompt_names_the_traps():
    p = _system_prompt()
    assert "grape name alone" in p.lower() or "never determines" in p.lower()
    assert "CHÂTEAU" in p.upper()


# ── conflict guard: explicit place evidence beats a gazetteer needle ─────────

def test_negociant_name_containing_chateau_word_is_not_the_chateau():
    # "Latour" must not fire inside "Louis Latour" (Burgundy négociant).
    hit = gazetteer_hit("Louis Latour Bourgogne Pinot Noir")
    assert hit is not None
    assert hit["region"] == "Burgundy"


def test_explicit_conflicting_appellation_suppresses_chateau_hit():
    # There are several Château Saint-Pierre; the name says Pomerol, so the
    # Saint-Julien entry must stand down.
    assert gazetteer_hit("2019 Chateau Saint Pierre Pomerol") is None


def test_us_ava_containing_producer_name_suppresses_producer_hit():
    # "Santa Rita" (Maipo, Chile) must not fire inside "Santa Rita Hills" (CA).
    assert gazetteer_hit("Sandhi Chardonnay Santa Rita Hills 2022") is None


def test_explicit_chile_valley_beats_producer_default_region():
    # Concha y Toro defaults to Central Valley, but an explicit Maipo Valley
    # bottling must not be downgraded.
    assert gazetteer_hit("Concha y Toro Marques de Casa Concha Maipo Valley") is None


def test_agreeing_appellation_keeps_the_hit():
    assert gazetteer_hit("Chateau Latour Pauillac 2015")["sub_region"] == "Pauillac"


def test_producer_hit_with_agreeing_appellation_kept():
    hit = gazetteer_hit("Guigal Cote-Rotie Brune et Blonde")
    assert hit is not None
    assert hit["region"] == "Rhône"


def test_santa_rita_hills_spelling_evidences_central_coast():
    from enrichment.extraction.reference import region_evidenced
    assert region_evidenced("Central Coast", "Sandhi Chardonnay Santa Rita Hills 2022")


def test_explicit_region_name_suppresses_chateau_hit():
    # Château Gloria (Saint-Julien) must not fire on Gloria Ferrer (Sonoma) —
    # the producer entry now resolves it to a correct Sonoma hit.
    hit = gazetteer_hit("Gloria Ferrer Sonoma Brut Sparkling")
    assert hit is not None and hit["region"] == "Sonoma"


def test_explicit_region_name_suppresses_producer_hit():
    # "Saint-Pierre" château needle vs an explicitly Provence wine.
    assert gazetteer_hit("V Saint Pierre De Vence Rose Aix En Provence") is None


def test_comparative_chateau_mention_loses_to_region_evidence():
    # Descriptions compare New World wines to Bordeaux estates; explicit
    # Napa Valley evidence must win over the Pétrus mention.
    assert gazetteer_hit("Twomey Merlot Napa Valley made in the style of Petrus") is None


def test_umbrella_country_word_does_not_conflict_with_narrower_region():
    # 'Chile' in the text must not suppress the Requingua → Curicó fix.
    hit = gazetteer_hit("Vina Requingua Puerto Viejo Merlot from Chile")
    assert hit is not None
    assert hit["region"] == "Curicó Valley"


def test_region_alias_agreeing_with_hit_is_not_a_conflict():
    hit = gazetteer_hit("Louis Latour Bourgogne Pinot Noir")
    assert hit is not None
    assert hit["region"] == "Burgundy"


def test_burgundy_village_suppresses_bordeaux_chateau_hit():
    # Château Beauregard (Pomerol) must not fire on a Santenay (Burgundy) wine.
    assert gazetteer_hit("Domaine du Cellier Aux Moines Beauregard 1er Santenay Blanc") is None


def test_cote_de_nuits_villages_evidences_burgundy():
    from enrichment.extraction.reference import region_evidenced
    assert region_evidenced("Burgundy", "Jean Marc Millot Aux Faulques Cote de Nuits Villages")


def test_beaulieu_georges_de_latour_is_napa_not_pauillac():
    hit = gazetteer_hit("Beaulieu Vineyard Georges De Latour Cabernet Sauvignon California")
    assert hit is not None
    assert hit["region"] == "Napa Valley"


def test_gloria_ferrer_is_sonoma_not_saint_julien():
    hit = gazetteer_hit("Gloria Ferrer Blanc De Noirs Rose")
    assert hit is not None
    assert hit["region"] == "Sonoma"


def test_bare_single_word_chateau_needle_requires_chateau_prefix():
    # "Latour" without a preceding Chateau word is a brand fragment
    # (Louis Latour's Grand Ardeche), not the Pauillac first growth.
    assert gazetteer_hit("Latour Grand Ardeche Chardonnay") is None


def test_chateau_prefixed_single_word_needle_still_fires():
    assert gazetteer_hit("Chateau Latour 2010")["sub_region"] == "Pauillac"
    assert gazetteer_hit("Château Gloria Saint-Julien 2018")["sub_region"] == "Saint-Julien"


def test_producer_hit_drops_inconsistent_stale_sub_region():
    # A leftover hallucinated sub_region (Saint-Émilion) must not survive a
    # producer hit (Curicó) and drag region back to Bordeaux via parent lookup.
    rec = _rec(region="Curicó Valley", sub_region="Saint-Émilion", country="Chile")
    out = _post_process(rec, source_text="Vina Requingua Puerto Viejo Merlot")
    assert out["region"] == "Curicó Valley"
    assert out["sub_region"] is None
