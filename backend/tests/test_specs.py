import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.specs import _parse_product, SpecsProduct


def _raw_product(**overrides):
    base = {
        "code": "100-081883800770",
        "details": {
            "description": "Crisp and dry with notes of green apple and citrus.",
            "title": "Stonegate Sauvignon Blanc",
            "type": "wine",
            "attributes": {
                "sku": "125681",
                "upc": "081883800770",
                "brand": "STONEGATE",
                "size": "750ML",
                "classid": 990,
                "category": "Wine",
                "categoryGroup": "Sauvignon Blanc",
                "subcategory": "California Wines",
            },
            "image": "https://cdn.specsonline.com/images/products/081883800770.jpg",
        },
        "url": "/shop/wine/stonegate-sauvignon-blanc/",
        "pricing": {
            "unitPrice": 1262,
            "unitPricePromoDiscount": 965,
            "casePrice": None,
            "caseQuantity": None,
            "casePricePromoDiscount": None,
            "casePriceKeyclubDiscount": None,
            "unitPriceKeyclubDiscount": None,
        },
        "stock": {"inStock": True, "details": None},
    }
    for k, v in overrides.items():
        if "." in k:
            parts = k.split(".", 1)
            base[parts[0]][parts[1]] = v
        else:
            base[k] = v
    return base


def test_parse_product_full():
    p = _parse_product(_raw_product())
    assert isinstance(p, SpecsProduct)
    assert p.upc == "081883800770"
    assert p.name == "Stonegate Sauvignon Blanc"
    assert p.brand == "STONEGATE"
    assert p.size == "750ML"
    assert p.category_group == "Sauvignon Blanc"
    assert p.description == "Crisp and dry with notes of green apple and citrus."
    assert p.price == 9.65           # promo price used when available
    assert p.sale_price == 9.65
    assert p.shelf_price == 12.62
    assert p.in_stock is True


def test_parse_product_no_promo_uses_shelf_price():
    raw = _raw_product()
    raw["pricing"]["unitPricePromoDiscount"] = None
    p = _parse_product(raw)
    assert p.price == 12.62
    assert p.sale_price is None
    assert p.shelf_price == 12.62


def test_parse_product_empty_description_returns_none():
    raw = _raw_product()
    raw["details"]["description"] = ""
    p = _parse_product(raw)
    assert p.description is None


def test_parse_product_no_upc_returns_none():
    raw = _raw_product()
    raw["details"]["attributes"]["upc"] = None
    assert _parse_product(raw) is None


def test_parse_product_non_wine_type_returns_none():
    raw = _raw_product()
    raw["details"]["type"] = "spirits"
    assert _parse_product(raw) is None


def test_parse_product_out_of_stock():
    raw = _raw_product()
    raw["stock"]["inStock"] = False
    p = _parse_product(raw)
    assert p.in_stock is False
