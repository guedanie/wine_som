import sys
import urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import patch

from scrapers.heb import _parse_record, _price_for_context, HEBProduct, _graphql_post


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


from unittest.mock import patch, MagicMock
from scrapers.heb import fetch_wine_page, HebScraper


def _fake_response(records, total=2):
    return {"data": {"productSearch": {"total": total, "records": records}}}


def test_fetch_wine_page_parses_records():
    raw = _raw_record()
    with patch("scrapers.heb._graphql_post", return_value=_fake_response([raw], total=1)):
        total, products = fetch_wine_page(offset=0, limit=60)
    assert total == 1
    assert len(products) == 1
    assert products[0].upc == "669576019191"


def test_fetch_wine_page_filters_non_wine():
    wine = _raw_record()
    glass = _raw_record(displayName="Riedel Wine Glass", brand={"name": "Riedel"})
    with patch("scrapers.heb._graphql_post", return_value=_fake_response([wine, glass], total=2)):
        total, products = fetch_wine_page(offset=0, limit=60)
    assert total == 2          # total is the server's count
    assert len(products) == 1  # only the parseable wine survives


def test_scraper_maps_to_inventory_items():
    scraper = HebScraper.__new__(HebScraper)  # skip __init__ (no Supabase client)
    p = _parse_record(_raw_record())
    items = scraper._products_to_inventory_items([p])
    assert len(items) == 1
    item = items[0]
    assert item.retailer_name == "H-E-B"
    assert item.store_id == "567"
    assert item.upc == "669576019191"
    assert item.price == 18.97
    assert item.brand == "Decoy"


def test_upsert_wine_details_builds_records():
    scraper = HebScraper.__new__(HebScraper)
    captured = {}

    class FakeTable:
        def upsert(self, records, on_conflict=None):
            captured["records"] = records
            captured["on_conflict"] = on_conflict
            return self
        def execute(self):
            return MagicMock(data=[])

    scraper.supabase = MagicMock()
    scraper.supabase.table.return_value = FakeTable()

    p = _parse_record(_raw_record())
    scraper._upsert_wine_details([p], {"669576019191": "wine-uuid-1"})

    assert captured["on_conflict"] == "wine_id"
    assert captured["records"][0]["wine_id"] == "wine-uuid-1"
    assert captured["records"][0]["source"] == "scraped_heb"
    assert "Californian red" in captured["records"][0]["description"]


def test_upsert_inventory_with_curbside_uses_store_ref():
    scraper = HebScraper.__new__(HebScraper)
    captured = {}

    class FakeTable:
        def upsert(self, records, on_conflict=None):
            captured["records"] = records
            captured["on_conflict"] = on_conflict
            return self
        def execute(self):
            return MagicMock(data=[])

    scraper.supabase = MagicMock()
    scraper.supabase.table.return_value = FakeTable()
    scraper._upsert_wines = lambda items: {"669576019191": "wine-1"}
    scraper._upsert_stores = lambda items: {("H-E-B", "567"): "store-1"}

    p = _parse_record(_raw_record())  # Decoy, upc 669576019191, curbside 19.92
    scraper._upsert_inventory_with_curbside([p])

    rec = captured["records"][0]
    assert captured["on_conflict"] == "upc,store_ref"
    assert rec["store_ref"] == "store-1"
    assert rec["wine_id"] == "wine-1"
    assert rec["curbside_price"] == 19.92
    assert "retailer_name" not in rec and "zip_code" not in rec and "store_id" not in rec


# --- browser-session re-solve/retry (item 45) ---------------------------------
# HEB moved /graphql behind Incapsula; the network path is now a patchright
# browser session. The retry logic (a challenged POST re-solves and retries)
# lives in _BrowserSession._w_post and is exercised here with a FAKE page — no
# real browser — by injecting a page whose .evaluate returns scripted responses.

from scrapers.heb import _BrowserSession


class _FakePage:
    """.evaluate returns the next scripted {status, body} each call."""
    def __init__(self, responses): self._responses = list(responses); self.calls = 0
    def evaluate(self, _js, _args):
        r = self._responses[self.calls]; self.calls += 1; return r


def _session_with(responses):
    s = _BrowserSession.__new__(_BrowserSession)   # skip __init__ (no thread/browser)
    s._page = _FakePage(responses)
    s._solves = 0
    s._w_solve = lambda *a, **k: setattr(s, "_solves", s._solves + 1)
    return s


def test_session_post_returns_parsed_json_on_200():
    s = _session_with([{"status": 200, "body": '{"data": {"productSearch": {"total": 3}}}'}])
    out = s._w_post("{ productSearch { total } }", "heb-com")
    assert out == {"data": {"productSearch": {"total": 3}}}
    assert s._solves == 0                # no re-solve needed


def test_session_post_resolves_and_retries_on_challenge_then_succeeds():
    s = _session_with([
        {"status": 502, "body": "<html>_Incapsula_Resource</html>"},   # challenged
        {"status": 200, "body": '{"data": {"productSearch": {"total": 0}}}'},
    ])
    out = s._w_post("{ productSearch { total } }", "heb-com")
    assert out == {"data": {"productSearch": {"total": 0}}}
    assert s._page.calls == 2 and s._solves == 1   # re-solved once, then succeeded


def test_session_post_raises_after_exhausting_retries():
    s = _session_with([{"status": 502, "body": "blocked"}] * 3)
    try:
        s._w_post("{ productSearch { total } }", "heb-com", retries=3)
        assert False, "should have raised"
    except RuntimeError:
        pass
    assert s._solves == 2               # re-solved between the 3 attempts (not after the last)
