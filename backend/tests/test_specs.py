import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.specs import _parse_product, SpecsProduct, _fetch_wine_page


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


def _make_search_response(products=None, total=1, pages=1):
    return json.dumps({
        "totalProducts": total,
        "currentPage": "1",
        "totalPages": pages,
        "productsPerPage": 96,
        "products": products or [],
    })


def test_fetch_wine_page_returns_parsed_response():
    fake_response = _make_search_response(products=[_raw_product()], total=1, pages=1)
    mock_result = MagicMock()
    mock_result.stdout = fake_response
    mock_result.returncode = 0

    with patch("scrapers.specs.subprocess.run", return_value=mock_result):
        result = _fetch_wine_page(store_number=100, page=1)

    assert result["totalProducts"] == 1
    assert len(result["products"]) == 1


def test_fetch_wine_page_sends_correct_store_and_page():
    captured = {}
    fake_response = _make_search_response()
    mock_result = MagicMock(stdout=fake_response, returncode=0)

    def capture_call(cmd, **kwargs):
        captured["cmd"] = cmd
        return mock_result

    with patch("scrapers.specs.subprocess.run", side_effect=capture_call):
        _fetch_wine_page(store_number=113, page=3)

    cmd_str = " ".join(captured["cmd"])
    assert '"storeNumber": 113' in cmd_str or '"storeNumber":113' in cmd_str
    assert '"page": 3' in cmd_str or '"page":3' in cmd_str
    assert '"category.keyword"' in cmd_str
