import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.twin_liquors import _parse_product, _parse_address, _parse_abv, _pick_option

MID = "5af17c10c8852b44f5995fdc"


def _wine_raw(**over):
    raw = {
        "id": "prod123",
        "name": "Daou Cabernet",
        "additional_properties": {
            "type": "wine", "subtype": "red", "varietal": "Cabernet Sauvignon",
            "content": "14.5%", "country": "United States", "region": "Central Coast",
            "brands": "Daou",
        },
        "images": {"primary": {"large": "https://cdn/large.png", "original": "https://cdn/o.png"}},
        "merchants": [{
            "merchant_id": MID,
            "product_options": [{
                "merchant_id": MID, "merchant_name": "Twin Liquors - McCreless Corner",
                "full_address": "3850 S New Braunfels Ave #113, San Antonio, TX 78223, USA",
                "price": 22.99, "quantity": 8, "default_option": True,
                "option_params": {"size": {"measure": "ml", "quantity": "750"}},
            }],
        }],
    }
    raw["additional_properties"].update(over.pop("ap", {}))
    raw.update(over)
    return raw


def test_wine_is_parsed_with_enriched_facts():
    p = _parse_product(_wine_raw(), MID)
    assert p is not None
    assert p.name == "Daou Cabernet"
    assert p.varietal == "Cabernet Sauvignon"
    assert p.wine_type == "red"
    assert p.abv == 14.5
    assert p.region == "Central Coast"
    assert p.country == "United States"
    assert p.price == 22.99
    assert p.in_stock is True
    assert p.upc == "twinliquors-prod123"
    assert (p.city, p.state, p.zip_code) == ("San Antonio", "TX", "78223")
    assert p.address == "3850 S New Braunfels Ave #113"


def test_non_wine_is_rejected():
    vodka = _wine_raw(name="Tito's Vodka", ap={"type": "spirits", "subtype": "vodka"})
    assert _parse_product(vodka, MID) is None


def test_out_of_stock_flag():
    raw = _wine_raw()
    raw["merchants"][0]["product_options"][0]["quantity"] = 0
    p = _parse_product(raw, MID)
    assert p is not None and p.in_stock is False


def test_pick_option_prefers_default_750ml():
    opts = [
        {"price": 8.99, "default_option": False, "option_params": {"size": {"quantity": "375"}}},
        {"price": 12.99, "default_option": True, "option_params": {"size": {"quantity": "750"}}},
    ]
    assert _pick_option(opts)["price"] == 12.99


def test_parse_address_and_abv_helpers():
    assert _parse_address("123 Main St, Austin, TX 78701, USA") == ("123 Main St", "Austin", "TX", "78701")
    assert _parse_abv("13.5%") == 13.5
    assert _parse_abv(None) is None


def test_parse_address_unmatched_has_no_street():
    street, city, state, zip_code = _parse_address("garbage")
    assert street is None
    assert (city, state, zip_code) == ("Austin", "TX", "78701")


def test_to_items_carries_street_address():
    """stores.address stays NULL (and the UI shows no address) unless the
    street from full_address rides through to RetailInventoryItem."""
    from unittest.mock import MagicMock
    from scrapers.twin_liquors import TwinLiquorsScraper
    scraper = TwinLiquorsScraper.__new__(TwinLiquorsScraper)
    scraper.supabase = MagicMock()
    p = _parse_product(_wine_raw(), MID)
    items = scraper._to_items([p], MID)
    assert items[0].address == "3850 S New Braunfels Ave #113"
