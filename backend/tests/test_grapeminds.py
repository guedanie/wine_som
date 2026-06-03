import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.grapeminds import GrapeMindsClient, GrapeMindsWine, DrinkingPeriod


def _client():
    return GrapeMindsClient.__new__(GrapeMindsClient)


def test_parse_detail_full_payload():
    client = _client()
    payload = {
        "data": {
            "id": 113817,
            "display_name": "Caymus Vineyards, Cabernet Sauvignon Napa Valley",
            "color": "red",
            "producer": {"name": "Caymus Vineyards"},
            "region": {"name": "California"},
            "grapes": [{"id": 1, "name": "Cabernet Sauvignon"}],
            "description": {"text": "A bold Napa Cab.", "text_long": "Long description here."},
            "tasting_notes": {"text": "Dark cherry, vanilla.", "text_long": "Detailed notes."},
            "pairing": {"text": "Great with steak.", "text_long": "Long pairing notes."},
            "flavor_profile": {
                "sweetness": 3, "acidity": 4, "tannins": 6,
                "alcohol": 8, "body": 8, "finish": 8,
            },
        }
    }
    wine = client._parse_detail(payload)
    assert wine.grapeminds_id == "113817"
    assert wine.description == "A bold Napa Cab."
    assert wine.description_long == "Long description here."
    assert wine.tasting_notes == "Dark cherry, vanilla."
    assert wine.pairing == "Great with steak."
    assert wine.structure_profile["body"] == 8
    assert wine.structure_profile["tannins"] == 6
    assert wine.grapes == ["Cabernet Sauvignon"]
    assert wine.is_fully_enriched is True


def test_parse_detail_null_fields_returns_partial():
    client = _client()
    payload = {
        "data": {
            "id": 999,
            "display_name": "Unknown Wine",
            "color": "red",
            "producer": {"name": "Producer"},
            "region": {"name": "Napa"},
            "grapes": [],
            "description": None,
            "tasting_notes": None,
            "pairing": None,
            "flavor_profile": None,
        }
    }
    wine = client._parse_detail(payload)
    assert wine.grapeminds_id == "999"
    assert wine.description is None
    assert wine.structure_profile == {}
    assert wine.is_fully_enriched is False


def test_parse_detail_missing_data_key_returns_none():
    client = _client()
    wine = client._parse_detail({"error": "not found"})
    assert wine is None


def test_parse_drinking_period_full():
    client = _client()
    payload = {
        "id": 12791, "wine_id": 9146, "lang": "en",
        "from": 8, "to": 25,
        "statement": "Best after 8 years.",
        "young": "Firm tannins, primary fruit.",
        "ripe": "Silky, complex, dried cherry.",
        "storage": "12-14C, horizontal.",
    }
    dp = client._parse_drinking_period(payload)
    assert dp.from_year == 8
    assert dp.to_year == 25
    assert dp.statement == "Best after 8 years."
    assert dp.storage == "12-14C, horizontal."


def test_parse_drinking_period_generating_returns_none():
    client = _client()
    dp = client._parse_drinking_period({"error": "not found", "generating": True})
    assert dp is None


def test_parse_text_field_handles_non_dict():
    client = _client()
    assert client._parse_text_field(None) == (None, None)
    assert client._parse_text_field("plain string") == (None, None)
    short, long = client._parse_text_field({"text": "Hi", "text_long": "Hello there"})
    assert short == "Hi"
    assert long == "Hello there"
