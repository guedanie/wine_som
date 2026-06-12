import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.heb import _parse_record, _price_for_context, HEBProduct


def _raw_record(**kwargs):
    base = {
        "id": "2210067",
        "displayName": "Decoy Cabernet Sauvignon California Red Wine",
        "brand": {"name": "Decoy"},
        "productPageURL": "/product-detail/decoy-cabernet-sauvignon-california-red-wine-750-ml/2210067",
        "productDescription": "Rich Californian red. <b>Type:</b> Red wine<br/><b>ABV:</b> 13.9%",
        "inventory": {"quantity": 181},
        "SKUs": [{
            "twelveDigitUPC": "669576019191",
            "customerFriendlySize": "750 ml",
            "contextPrices": [
                {"context": "ONLINE", "isOnSale": True,
                 "listPrice": {"amount": 19.97}, "salePrice": {"amount": 18.97}},
                {"context": "CURBSIDE", "isOnSale": True,
                 "listPrice": {"amount": 20.97}, "salePrice": {"amount": 19.92}},
            ],
        }],
    }
    base.update(kwargs)
    return base


def test_price_for_context_prefers_sale():
    prices = [
        {"context": "ONLINE", "listPrice": {"amount": 19.97}, "salePrice": {"amount": 18.97}},
    ]
    assert _price_for_context(prices, "ONLINE") == 18.97


def test_price_for_context_falls_back_to_list_when_no_sale():
    prices = [
        {"context": "ONLINE", "listPrice": {"amount": 19.97}, "salePrice": None},
    ]
    assert _price_for_context(prices, "ONLINE") == 19.97


def test_price_for_context_missing_returns_none():
    assert _price_for_context([], "ONLINE") is None


def test_parse_record_full():
    p = _parse_record(_raw_record())
    assert isinstance(p, HEBProduct)
    assert p.product_id == "2210067"
    assert p.name == "Decoy Cabernet Sauvignon California Red Wine"
    assert p.brand == "Decoy"
    assert p.upc == "669576019191"
    assert p.bottle_size == "750 ml"
    assert p.price == 18.97          # ONLINE/in-store, canonical
    assert p.curbside_price == 19.92
    assert p.in_stock is True
    assert p.wine_type == "red"
    assert "Californian red" in p.description


def test_parse_record_out_of_stock_when_zero_inventory():
    p = _parse_record(_raw_record(inventory={"quantity": 0}))
    assert p.in_stock is False


def test_parse_record_non_wine_returns_none():
    # A product whose name maps to no wine type is filtered out
    p = _parse_record(_raw_record(
        displayName="Riedel Wine Glass Set",
        brand={"name": "Riedel"},
    ))
    assert p is None


def test_parse_record_no_skus_returns_none():
    assert _parse_record(_raw_record(SKUs=[])) is None
