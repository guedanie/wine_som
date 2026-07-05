import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.pogos import (
    _parse_product_pogos, _normalize_type, PogosScraper,
    RETAILER_NAME, STORE_ZIP, CITY, STATE,
)


def _raw(**kw):
    base = {
        "id": 1, "title": "Occhipinti SP68 Rosso 2022", "handle": "occhipinti-sp68-2022",
        "vendor": "Some Distributor Co", "product_type": "Red",
        "body_html": "<p>Sicilian frappato blend.</p>", "tags": ["Italy", "Natural"],
        "variants": [{"price": "34.00", "available": True, "option1": "750ml"}],
        "images": [{"src": "https://cdn.shopify.com/pogos.jpg"}],
    }
    base.update(kw)
    return base


def test_normalize_maps_capitalized_types():
    assert _normalize_type("Red") == "Red Wine"
    assert _normalize_type("White") == "White Wine"
    assert _normalize_type("Sparkling") == "Sparkling Wine"
    assert _normalize_type("Rose") == "Rosé Wine"


def test_normalize_drops_non_wine():
    for t in ("Whiskey", "Beer", "Tobacco", "Tequila", "Gin", "Mezcal",
              "Ready To Drink", "Supplies", "Giftware", "Mixers & Syrups", "Vodka"):
        assert _normalize_type(t) is None


def test_parse_wine_product():
    p = _parse_product_pogos(_raw())
    assert p.title == "Occhipinti SP68 Rosso 2022"
    assert p.product_type == "Red Wine"
    assert p.price == 34.0
    assert p.vintage_year == 2022
    assert p.vendor == ""            # distributor discarded


def test_parse_non_wine_returns_none():
    assert _parse_product_pogos(_raw(product_type="Whiskey")) is None
    assert _parse_product_pogos(_raw(product_type="Tobacco")) is None


def test_inventory_item_shape():
    scraper = PogosScraper.__new__(PogosScraper)
    p = _parse_product_pogos(_raw())
    it = PogosScraper._products_to_inventory_items(scraper, [p])[0]
    assert it.retailer_name == RETAILER_NAME
    assert it.city == CITY == "Dallas"
    assert it.state == STATE == "TX"
    assert it.zip_code == STORE_ZIP == "75209"
    assert it.upc == "shopify-pogos-occhipinti-sp68-2022"
    assert it.brand is None
    assert it.varietal is None
    assert it.price == 34.0
