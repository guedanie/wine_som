import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.geraldines import (
    _parse_product, _parse_vintage, _first_paragraph, _strip_html, GeraldinesScraper,
)


def _raw_product(**kwargs):
    base = {
        "id": 12345,
        "title": "Some Cabernet 2021",
        "handle": "some-cabernet-2021",
        "vendor": "Test Producer",
        "product_type": "Red Wine",
        "body_html": "<p>Dark cherry and tobacco.</p><p>Aged in French oak.</p>",
        "tags": ["Organic", "Red", "Sustainable"],
        "variants": [{"price": "29.00", "available": True, "option1": "750 ml"}],
        "images": [{"src": "https://cdn.shopify.com/img.jpg"}],
    }
    base.update(kwargs)
    return base


def test_parse_product_wine_fields():
    product = _parse_product(_raw_product())
    assert product.title == "Some Cabernet 2021"
    assert product.vendor == "Test Producer"
    assert product.product_type == "Red Wine"
    assert product.price == 29.0
    assert product.available is True
    assert product.bottle_size == "750 ml"
    assert product.vintage_year == 2021
    assert "Organic" in product.tags


def test_parse_product_description_is_first_paragraph():
    product = _parse_product(_raw_product())
    assert product.description == "Dark cherry and tobacco."
    assert "Aged in French oak." in product.description_long


def test_parse_product_non_wine_returns_none():
    product = _parse_product(_raw_product(product_type="Event"))
    assert product is None

    product = _parse_product(_raw_product(product_type="Merchandise"))
    assert product is None


def test_parse_product_no_variants_returns_none():
    product = _parse_product(_raw_product(variants=[]))
    assert product is None


def test_parse_vintage_from_title():
    assert _parse_vintage("Chateau Montelena Cabernet 2019") == 2019
    assert _parse_vintage("NV Champagne Blanc de Blancs") is None
    assert _parse_vintage("Meiomi Pinot Noir 2022 750ml") == 2022


def test_strip_html():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert _strip_html("") == ""


def test_first_paragraph():
    html = "<p>First para.</p><p>Second para.</p>"
    assert _first_paragraph(html) == "First para."
    assert _first_paragraph("no paragraphs here") is None


def test_parse_product_rose_type():
    product = _parse_product(_raw_product(product_type="Rosé Wine", title="Rosé 2023"))
    assert product is not None
    assert product.product_type == "Rosé Wine"


def test_parse_product_image_url():
    product = _parse_product(_raw_product())
    assert product.image_url == "https://cdn.shopify.com/img.jpg"


def test_parse_product_no_image():
    product = _parse_product(_raw_product(images=[]))
    assert product.image_url is None


def test_inventory_item_carries_image_url():
    scraper = GeraldinesScraper.__new__(GeraldinesScraper)
    product = _parse_product(_raw_product())
    items = scraper._shopify_products_to_inventory_items([product])
    assert items[0].image_url == "https://cdn.shopify.com/img.jpg"
