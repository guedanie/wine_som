import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import time
from unittest.mock import MagicMock, patch
from scrapers.kroger import (
    parse_product, _front_image, KrogerClient, KrogerScraper, MARKETS,
)


def _product(**kw):
    base = {
        "productId": "0001234",
        "upc": "0008500001668",
        "description": "Kim Crawford Sauvignon Blanc Marlborough 750ml",
        "brand": "Kim Crawford",
        "categories": ["Adult Beverage"],
        "items": [{
            "price": {"regular": 15.99, "promo": 14.99},
            "size": "750ml",
            "fulfillment": {"inStore": True, "curbside": True, "delivery": True, "shipToHome": False},
        }],
        "images": [{
            "perspective": "front",
            "sizes": [
                {"size": "xlarge", "url": "https://www.kroger.com/product/images/xlarge/front/x.jpg"},
                {"size": "medium", "url": "https://www.kroger.com/product/images/medium/front/x.jpg"},
            ],
        }],
    }
    base.update(kw)
    return base


# ── parse_product ────────────────────────────────────────────────

def test_parse_uses_promo_price_over_regular():
    p = parse_product(_product())
    assert p.price == 14.99
    assert p.upc == "0008500001668"
    assert p.brand == "Kim Crawford"
    assert p.in_stock is True


def test_parse_falls_back_to_regular_when_no_promo():
    p = parse_product(_product(items=[{"price": {"regular": 22.0}, "fulfillment": {"inStore": True}}]))
    assert p.price == 22.0


def test_parse_out_of_stock():
    p = parse_product(_product(items=[{
        "price": {"regular": 10.0},
        "fulfillment": {"inStore": False, "curbside": False, "delivery": False},
    }]))
    assert p.in_stock is False


def test_parse_drops_non_wine():
    for desc in ("Bud Light Beer 12pk", "Tito's Vodka 750ml",
                 "Holland House Cooking Wine", "Red Wine Vinegar"):
        assert parse_product(_product(description=desc)) is None


def test_parse_missing_upc_or_desc_returns_none():
    assert parse_product(_product(upc=None)) is None
    assert parse_product(_product(description="")) is None


def test_front_image_prefers_largest():
    assert _front_image(_product()).endswith("/xlarge/front/x.jpg")


def test_front_image_none_when_absent():
    assert _front_image(_product(images=[])) is None


# ── KrogerClient token caching ───────────────────────────────────

def test_client_caches_token_until_expiry():
    c = KrogerClient(client_id="id", client_secret="sec")
    with patch.object(c, "_fetch_token", wraps=lambda: setattr(c, "_token", "T") or setattr(c, "_token_exp", time.monotonic() + 1000) or "T") as fetch:
        c._token_value()
        c._token_value()
    assert fetch.call_count == 1   # second call served from cache


def test_client_refetches_after_expiry():
    c = KrogerClient(client_id="id", client_secret="sec")
    c._token = "old"
    c._token_exp = time.monotonic() - 1   # already expired
    with patch.object(c, "_fetch_token", return_value="new") as fetch:
        c._token_value()
    fetch.assert_called_once()


# ── scraper inventory mapping ────────────────────────────────────

def test_inventory_item_uses_real_upc_and_market_meta():
    scraper = KrogerScraper.__new__(KrogerScraper)
    p = parse_product(_product())
    market = MARKETS["nashville"]
    store = market["stores"][0]
    items = KrogerScraper._to_inventory_items(scraper, [p], store, market)
    it = items[0]
    assert it.retailer_name == "Kroger"
    assert it.city == "Nashville"
    assert it.state == "TN"
    assert it.upc == "0008500001668"      # real barcode, not synthetic
    assert it.store_id == store["id"]
    assert it.price == 14.99
    assert it.brand == "Kim Crawford"


def test_harris_teeter_market_uses_banner_name():
    """NC markets display as 'Harris Teeter', not 'Kroger'."""
    scraper = KrogerScraper.__new__(KrogerScraper)
    p = parse_product(_product())
    market = MARKETS["charlotte"]
    items = KrogerScraper._to_inventory_items(scraper, [p], market["stores"][0], market)
    assert items[0].retailer_name == "Harris Teeter"
    assert items[0].state == "NC"


def test_markets_registry_shape():
    for key, m in MARKETS.items():
        assert {"city", "state", "retailer", "stores"} <= set(m)
        assert m["stores"] and all("id" in s and "zip" in s for s in m["stores"])


def test_fetch_store_wines_dedups_by_upc():
    """Same UPC surfaced by two search terms is stored once."""
    scraper = KrogerScraper.__new__(KrogerScraper)
    dupe = _product()
    client = MagicMock()
    # every term returns the same single product, then empty
    client.search.side_effect = lambda term, loc, start=0, limit=50: [dupe] if start == 0 else []
    scraper.client = client
    out = scraper._fetch_store_wines("02600567")
    assert len(out) == 1
    assert out[0].upc == "0008500001668"


def test_fetch_store_wines_dedups_by_canonical_upc():
    """Two distinct raw UPCs that normalize to the same canonical UPC must
    collapse to one — else the upsert batch violates the unique constraint
    ('ON CONFLICT DO UPDATE cannot affect row a second time')."""
    scraper = KrogerScraper.__new__(KrogerScraper)
    # both normalize to canonical core 08500001668
    a = _product(upc="0008500001668", description="Same Wine A 750ml")
    b = _product(upc="008500001668",  description="Same Wine B 750ml")
    client = MagicMock()
    client.search.side_effect = lambda term, loc, start=0, limit=50: ([a, b] if start == 0 else [])
    scraper.client = client
    out = scraper._fetch_store_wines("02600567")
    from utils.upc import canonical_upc
    canons = {canonical_upc(p.upc) for p in out}
    assert len(canons) == len(out)
    assert len(out) == 1
