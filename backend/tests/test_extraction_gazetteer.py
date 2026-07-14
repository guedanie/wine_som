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
