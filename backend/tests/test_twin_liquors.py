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


# ---------------------------------------------------------------------------
# Throttle reporting (2026-08-31 incident)
# ---------------------------------------------------------------------------

def _run_full_with(monkeypatch, rate_limit_on):
    """Drive run_full over two stores, raising TwinRateLimited on the given
    search term. Returns (result_dict, scraper_runs_update_payload)."""
    import asyncio
    from unittest.mock import MagicMock
    from scrapers import twin_liquors as tl

    def fake_fetch(mid, term):
        if term == rate_limit_on:
            raise tl.TwinRateLimited()
        return [_wine_raw(id=f"p-{mid}-{term}")]

    import time as _time
    monkeypatch.setattr(tl, "_fetch", fake_fetch)
    # run_full does `import time` in its own body, so the module object itself
    # must be patched rather than a twin_liquors attribute.
    monkeypatch.setattr(_time, "sleep", lambda *_: None)
    monkeypatch.setattr(tl, "WINE_SEARCH_TERMS", ["cabernet", "merlot"])

    scraper = tl.TwinLiquorsScraper.__new__(tl.TwinLiquorsScraper)
    scraper.supabase = MagicMock()
    scraper._upsert_wines = MagicMock(return_value={})
    scraper._upsert_inventory = MagicMock()

    updates = []
    table = scraper.supabase.table.return_value
    table.insert.return_value.execute.return_value = MagicMock()
    def capture_update(payload):
        updates.append(payload)
        return table
    table.update.side_effect = capture_update
    table.eq.return_value = table

    result = asyncio.get_event_loop().run_until_complete(
        scraper.run_full(merchant_ids=[MID, "store2"]))
    return result, updates[-1]


def test_rate_limited_store_is_reported_in_result(monkeypatch):
    """Twin printed the skip to the log but returned a clean dict, so the run
    recorded success and sweep_delisted delisted the stores it never reached."""
    result, _ = _run_full_with(monkeypatch, rate_limit_on="cabernet")
    assert result["throttled"] == [MID, "store2"]


def test_rate_limited_run_marks_error_message_for_the_sweep(monkeypatch):
    from scrapers.throttle import was_throttled
    _, update = _run_full_with(monkeypatch, rate_limit_on="cabernet")
    assert was_throttled(update["error_message"])


def test_clean_run_reports_no_throttling(monkeypatch):
    from scrapers.throttle import was_throttled
    result, update = _run_full_with(monkeypatch, rate_limit_on=None)
    assert result["throttled"] == []
    assert not was_throttled(update["error_message"])
