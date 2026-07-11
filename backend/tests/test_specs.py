import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.specs import _parse_product, SpecsProduct, _fetch_wine_page, SpecsScraper
from scrapers.base import RetailInventoryItem


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
            "unitPrice": 1578,
            "unitPricePromoDiscount": 318,   # DISCOUNT AMOUNT ($3.18 off), not the sale price
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
    # sale = shelf - discount = (1578 - 318)/100 = 12.60 (NOT the 3.18 discount amount)
    assert p.price == 12.60
    assert p.sale_price == 12.60
    assert p.shelf_price == 15.78
    assert p.in_stock is True
    assert p.image_url == "https://cdn.specsonline.com/images/products/081883800770.jpg"


def test_parse_product_no_promo_uses_shelf_price():
    raw = _raw_product()
    raw["pricing"]["unitPricePromoDiscount"] = None
    p = _parse_product(raw)
    assert p.price == 15.78
    assert p.sale_price is None
    assert p.shelf_price == 15.78


def test_parse_product_promo_is_discount_amount_not_price():
    """Regression: unitPricePromoDiscount is $ OFF, not the sale price.
    A $15.78 wine with a $3.18 discount must show $12.60, never $3.18."""
    raw = _raw_product()
    raw["pricing"]["unitPrice"] = 1578
    raw["pricing"]["unitPricePromoDiscount"] = 318
    p = _parse_product(raw)
    assert p.price == 12.60
    assert p.price > 5      # never the bare discount amount


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


def _make_scraper():
    s = SpecsScraper.__new__(SpecsScraper)
    s.supabase = MagicMock()
    return s


def test_products_to_inventory_items_maps_correctly():
    scraper = _make_scraper()
    product = _parse_product(_raw_product())
    items = scraper._products_to_inventory_items(
        [product], store_number=100, store_name="San Antonio - De Zavala"
    )
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RetailInventoryItem)
    assert item.wine_name == "Stonegate Sauvignon Blanc"
    assert item.upc == "081883800770"
    assert item.price == 12.60      # shelf 15.78 − 3.18 discount
    assert item.retailer_name == "Spec's"
    assert item.store_id == "100"
    assert item.store_name == "San Antonio - De Zavala"
    assert item.in_stock is True
    assert item.zip_code == "78209"
    assert item.image_url == "https://cdn.specsonline.com/images/products/081883800770.jpg"


def test_products_to_inventory_items_skips_no_price():
    scraper = _make_scraper()
    raw = _raw_product()
    raw["pricing"]["unitPrice"] = None
    raw["pricing"]["unitPricePromoDiscount"] = None
    product = _parse_product(raw)
    items = scraper._products_to_inventory_items(
        [product], store_number=100, store_name="De Zavala"
    )
    assert len(items) == 0


def test_upsert_wine_details_writes_non_empty_descriptions():
    scraper = _make_scraper()
    scraper.supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    product_with_desc = _parse_product(_raw_product())
    raw_no_desc = _raw_product()
    raw_no_desc["details"]["description"] = ""
    product_no_desc = _parse_product(raw_no_desc)

    upc_to_id = {"081883800770": "wine-uuid-1"}
    scraper._upsert_wine_details([product_with_desc, product_no_desc], upc_to_id)

    scraper.supabase.table.assert_called_with("wine_details")
    call_args = scraper.supabase.table.return_value.upsert.call_args
    records = call_args[0][0]
    assert len(records) == 1
    assert records[0]["wine_id"] == "wine-uuid-1"
    assert records[0]["description"] == "Crisp and dry with notes of green apple and citrus."
    assert records[0]["source"] == "scraped_specs"


def test_upsert_wine_details_skips_when_all_empty():
    scraper = _make_scraper()
    raw = _raw_product()
    raw["details"]["description"] = ""
    product = _parse_product(raw)
    upc_to_id = {"081883800770": "wine-uuid-1"}
    scraper._upsert_wine_details([product], upc_to_id)
    scraper.supabase.table.assert_not_called()


# ── multi-metro store expansion ──────────────────────────────────

def test_parse_store_detail_extracts_city_zip():
    from scrapers.specs import _parse_store_detail
    data = {"name": "Northwest Highway",
            "address": {"city": "Dallas", "postcode": "75220", "provinceCode": "US-TX",
                        "street": "9500 N Central Expy"}}
    d = _parse_store_detail(data, 115)
    assert d == {"name": "Northwest Highway", "city": "Dallas", "zip": "75220",
                 "address": "9500 N Central Expy"}


def test_parse_store_detail_joins_street2():
    from scrapers.specs import _parse_store_detail
    data = {"name": "X",
            "address": {"city": "Dallas", "postcode": "75220",
                        "street": "9500 N Central Expy", "street2": "Ste 100"}}
    assert _parse_store_detail(data, 115)["address"] == "9500 N Central Expy, Ste 100"


def test_parse_store_detail_falls_back_on_missing_address():
    from scrapers.specs import _parse_store_detail
    d = _parse_store_detail({"name": "X"}, 999)
    assert d["city"] == "San Antonio" and d["zip"] == "78209"
    assert d["address"] is None


def test_inventory_item_uses_per_store_city_zip():
    """Austin/Dallas stores must carry their own zip/city, not SA's — else
    they geocode to San Antonio and a local tester's radius misses them."""
    from scrapers.specs import SpecsScraper
    scraper = SpecsScraper.__new__(SpecsScraper)
    product = _parse_product(_raw_product())
    items = SpecsScraper._products_to_inventory_items(
        scraper, [product], store_number=115, store_name="Northwest Highway",
        store_zip="75220", store_city="Dallas", store_address="9500 N Central Expy")
    assert items[0].zip_code == "75220"
    assert items[0].city == "Dallas"
    assert items[0].state == "TX"
    assert items[0].address == "9500 N Central Expy"


def test_inventory_item_defaults_to_sa():
    from scrapers.specs import SpecsScraper
    scraper = SpecsScraper.__new__(SpecsScraper)
    product = _parse_product(_raw_product())
    items = SpecsScraper._products_to_inventory_items(
        scraper, [product], store_number=100, store_name="De Zavala")
    assert items[0].zip_code == "78209" and items[0].city == "San Antonio"
