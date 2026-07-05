import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.harvest_wine import (
    _parse_product_harvest, _normalize_type, HarvestWineScraper,
    RETAILER_NAME, STORE_ZIP, CITY, STATE,
)


def _raw(**kwargs):
    base = {
        "id": 999,
        "title": "Domaine Tempier Bandol Rouge 2021",
        "handle": "tempier-bandol-2021",
        "vendor": "Domaine Tempier",
        "product_type": "Red Wine",
        "body_html": "<p>Mourvèdre from Provence.</p>",
        "tags": ["France", "Provence"],
        "variants": [{"price": "62.00", "available": True, "option1": "750ml"}],
        "images": [{"src": "https://cdn.shopify.com/harvest.jpg"}],
    }
    base.update(kwargs)
    return base


# ── type normalization (the inconsistent-casing problem) ─────────

def test_normalize_canonicalizes_casing():
    assert _normalize_type("Red Wine") == "Red Wine"
    assert _normalize_type("White wine") == "White Wine"
    assert _normalize_type("rose") == "Rosé Wine"
    assert _normalize_type("Rosé") == "Rosé Wine"
    assert _normalize_type("Rose wine") == "Rosé Wine"
    assert _normalize_type("Champagne") == "Sparkling Wine"


def test_normalize_drops_non_wine():
    for t in ("Bourbon", "Gin", "Tequila", "Whiskey", "Non Alcoholic",
              "Ready to Drink", "Event", "Gift Card", "Liqueur"):
        assert _normalize_type(t) is None


def test_normalize_unknown_type_is_dropped():
    assert _normalize_type("Mystery Category") is None
    assert _normalize_type("") is None


# ── product parsing ──────────────────────────────────────────────

def test_parse_wine_product():
    p = _parse_product_harvest(_raw())
    assert p.title == "Domaine Tempier Bandol Rouge 2021"
    assert p.vendor == "Domaine Tempier"
    assert p.product_type == "Red Wine"
    assert p.price == 62.0
    assert p.available is True
    assert p.vintage_year == 2021
    assert p.image_url == "https://cdn.shopify.com/harvest.jpg"


def test_parse_non_wine_returns_none():
    assert _parse_product_harvest(_raw(product_type="Bourbon")) is None
    assert _parse_product_harvest(_raw(product_type="Event")) is None


def test_parse_no_variants_returns_none():
    assert _parse_product_harvest(_raw(variants=[])) is None


def test_parse_rose_casing_variants_all_map():
    for t in ("rose", "Rosé", "Rose wine"):
        p = _parse_product_harvest(_raw(product_type=t))
        assert p.product_type == "Rosé Wine"


# ── inventory item mapping ───────────────────────────────────────

def test_inventory_item_shape():
    scraper = HarvestWineScraper.__new__(HarvestWineScraper)
    p = _parse_product_harvest(_raw())
    items = HarvestWineScraper._products_to_inventory_items(scraper, [p])
    it = items[0]
    assert it.retailer_name == RETAILER_NAME
    assert it.zip_code == STORE_ZIP == "37205"
    assert it.city == CITY == "Nashville"
    assert it.state == STATE == "TN"
    assert it.upc == "shopify-harvest-tempier-bandol-2021"
    assert it.brand == "Domaine Tempier"
    assert it.varietal is None   # extractor/Vivino fills varietal
    assert it.price == 62.0
