import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch, MagicMock
from enrichment.extraction.extractor import _post_process, extract_facts


def test_post_process_maps_appellation_to_parent_region():
    rec = {"wine_id": "w1", "region": "wrong", "sub_region": "Saint-Émilion",
           "country": "France", "vintage_year": 2019, "varietal": "Merlot",
           "grapes": ["Merlot"], "abv": None, "body": "FULL"}
    out = _post_process(rec)
    assert out["region"] == "Bordeaux"          # overridden via cheat sheet
    assert out["sub_region"] == "Saint-Émilion"
    assert out["body"] == "full"                 # normalized


def test_post_process_coerces_ranges_and_defaults_varietal():
    rec = {"wine_id": "w1", "region": "California", "sub_region": None,
           "country": "US", "vintage_year": 1850, "varietal": None,
           "grapes": ["Zinfandel"], "abv": 99.0, "body": "rich"}
    out = _post_process(rec)
    assert out["vintage_year"] is None           # out of range -> null
    assert out["abv"] is None                    # out of range -> null
    assert out["varietal"] == "Zinfandel"        # defaults to grapes[0]
    assert out["body"] is None                   # unrecognized -> null


def test_post_process_keeps_long_tail_region_when_not_in_cheatsheet():
    rec = {"wine_id": "w1", "region": "Swartland", "sub_region": None,
           "country": "South Africa", "vintage_year": 2020, "varietal": "Syrah",
           "grapes": ["Syrah"], "abv": 13.5, "body": "medium"}
    out = _post_process(rec)
    assert out["region"] == "Swartland"


def _mock_anthropic(records):
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"wines": records}
    resp = MagicMock()
    resp.content = [block]
    cls = MagicMock()
    cls.return_value.messages.create.return_value = resp
    return cls


def test_extract_facts_returns_postprocessed_records():
    wines = [{"id": "w1", "name": "Château du Cauze Saint-Émilion Grand Cru 2019",
              "brand": "", "wine_type": "red", "description": ""}]
    model_out = [{"wine_id": "w1", "region": "France", "sub_region": "Saint-Émilion",
                  "country": "France", "vintage_year": 2019, "varietal": "Merlot",
                  "grapes": ["Merlot"], "abv": None, "body": "full"}]
    cls = _mock_anthropic(model_out)
    with patch("enrichment.extraction.extractor._anthropic_client", cls.return_value):
        out = extract_facts(wines, batch_size=15)
    assert len(out) == 1
    assert out[0]["region"] == "Bordeaux"


def test_extract_facts_batches_calls():
    wines = [{"id": f"w{i}", "name": f"Wine {i}", "brand": "", "wine_type": "red",
              "description": ""} for i in range(32)]
    cls = _mock_anthropic([])   # each call returns no wines; we only count calls
    with patch("enrichment.extraction.extractor._anthropic_client", cls.return_value):
        extract_facts(wines, batch_size=15)
    # 32 wines / 15 per batch = 3 calls
    assert cls.return_value.messages.create.call_count == 3


def test_infer_wine_type_uses_word_boundaries():
    """'Portuguese' is not Port (28 prod wines were dessert-typed by this
    substring), and 'Primrose' is not rosé."""
    from utils import infer_wine_type
    assert infer_wine_type('Portuguese Red Wine') == 'red'
    assert infer_wine_type('Patio Pounder Vino Verde Portuguese White Wine') == 'white'
    assert infer_wine_type('Primrose Hill Chardonnay') == 'white'
    assert infer_wine_type('Ruby Port') == 'fortified'
    assert infer_wine_type('Rosé of Pinot Noir') == 'rosé'


def test_infer_wine_type_knows_portuguese_terms():
    from utils import infer_wine_type
    assert infer_wine_type('Fitapreta, Alentejano, Portugal, Touriga Nacional, 2023') == 'red'
    assert infer_wine_type('Ameal, Vinho Verde, Portugal, Loureiro, 2023') == 'white'
    assert infer_wine_type('Xisto Ilimitado Branco, Douro, Rabigato Blend') == 'white'
    assert infer_wine_type('Espumante Bruto Natural, Bairrada') == 'sparkling'
    assert infer_wine_type('Quinta do Infantado, Tawny-Medium Dry, Porto') == 'fortified'
    assert infer_wine_type('Vinho Tinto Reserva') == 'red'


def test_post_process_wine_type_gates_default_blend():
    """A white wine in a red appellation must not get the red default blend."""
    rec = {"wine_id": "w1", "sub_region": "Margaux", "grapes": [], "varietal": None}
    out = _post_process(rec, wine_type="white")
    assert out["grapes"] == []
    out_red = _post_process(rec, wine_type="red")
    assert out_red["grapes"] == ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"]
    assert out_red["varietal"] == "Cabernet Sauvignon"


def test_post_process_region_fallback_for_red_without_appellation():
    rec = {"wine_id": "w1", "region": "Bordeaux", "sub_region": None,
           "grapes": [], "varietal": None}
    out = _post_process(rec, wine_type="red")
    assert out["grapes"] == ["Merlot", "Cabernet Sauvignon", "Cabernet Franc"]
    out_unknown = _post_process(rec)
    assert out_unknown["grapes"] == []


def test_post_process_region_fallback_sees_the_canonicalized_region():
    """Step 2 canonicalizes 'Rhone Valley' -> 'Rhône' before step 3b's
    fallback runs — the GSM blend must fire off the canonical name."""
    rec = {"wine_id": "w1", "region": "Rhone Valley", "sub_region": None,
           "grapes": [], "varietal": None}
    out = _post_process(rec, wine_type="red")
    assert out["region"] == "Rhône"
    assert out["grapes"] == ["Grenache", "Syrah", "Mourvèdre"]
    assert out["varietal"] == "Grenache"


def test_post_process_white_port_never_gets_the_red_trio():
    """Weekly-extraction twin of the backfill's White Port guard — the name
    is the only color signal at region granularity."""
    rec = {"wine_id": "w1", "region": "Douro", "sub_region": None,
           "grapes": [], "varietal": None}
    out = _post_process(rec, wine_type="dessert", name="Dow's White Port")
    assert out["grapes"] == []
    out_red = _post_process(rec, wine_type="dessert",
                            name="Graham's Six Grapes Reserve Port")
    assert out_red["grapes"] == ["Touriga Nacional", "Touriga Franca", "Tinta Roriz"]
