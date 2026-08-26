import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.nashville_cityhive import (
    CH_STORES, RETAILER_NAME, _search_url, _cityhive_upc, _to_items, _wine_records,
)
from scrapers.twin_liquors import _parse_product


def _raw(pid="p1", name="Caymus Cabernet", price=68.99, qty=3, typ="wine",
         varietal="Cabernet Sauvignon", region="Napa Valley", country="US"):
    return {
        "id": pid, "name": name,
        "additional_properties": {"type": typ, "varietal": varietal, "subtype": varietal,
                                  "region": region, "country": country,
                                  "brands": "Caymus", "content": "14.5% alc/vol"},
        "images": {"primary": {"large": "https://img/x.jpg"}},
        "merchants": [{"merchant_id": "M1", "merchant_name": "Corkdorks - Midtown",
                       "full_address": "1610 Church St, Nashville, TN 37203",
                       "product_options": [{"merchant_id": "M1", "price": price,
                                            "quantity": qty,
                                            "merchant_name": "Corkdorks - Midtown",
                                            "full_address": "1610 Church St, Nashville, TN 37203"}]}],
    }


# --- store registry -----------------------------------------------------------

def test_all_three_nashville_stores_are_configured():
    assert len(CH_STORES) == 3
    names = {s["name"] for s in CH_STORES.values()}
    assert any("Frugal" in n for n in names)
    assert sum(1 for n in names if "Corkdorks" in n) == 2


def test_the_two_corkdorks_share_an_origin_but_frugal_does_not():
    """client_origin differs per SITE, not per store — Corkdorks' two branches share
    one, Frugal has its own. Reusing the wrong origin silently returns nothing."""
    by_name = {s["name"]: s for s in CH_STORES.values()}
    corkdorks = [s["client_origin"] for n, s in by_name.items() if "Corkdorks" in n]
    frugal = [s["client_origin"] for n, s in by_name.items() if "Frugal" in n]
    assert len(set(corkdorks)) == 1
    assert frugal[0] not in corkdorks


def test_every_store_is_nashville_tn():
    for s in CH_STORES.values():
        assert s["state"] == "TN" and s["city"] == "Nashville"
        assert s["zip"].startswith("37")


# --- the search URL must carry the per-store origin ---------------------------

def test_search_url_uses_the_stores_own_client_origin():
    u = _search_url("MID123", "app://sites.corkdorks", "cabernet")
    assert "merchant_id=MID123" in u
    assert "client_origin=app://sites.corkdorks" in u
    assert "text=cabernet" in u


def test_search_url_encodes_multi_word_terms():
    u = _search_url("M", "app://o", "pinot noir")
    assert "pinot%20noir" in u or "pinot+noir" in u


# --- identity -----------------------------------------------------------------

def test_upc_is_the_shared_cityhive_namespace():
    """Boutique wines carry no barcode; City Hive product ids are the identity."""
    assert _cityhive_upc("abc123") == "cityhive-abc123"


# --- parsing + mapping --------------------------------------------------------

def test_wine_products_map_to_inventory_items_with_store_metadata():
    p = _parse_product(_raw(), "M1")
    store = CH_STORES["5c2a8cae7309395802faf15d"]
    items = _to_items([p], "5c2a8cae7309395802faf15d", store)
    assert len(items) == 1
    it = items[0]
    assert it.retailer_name == RETAILER_NAME
    assert it.upc == "cityhive-p1"
    assert it.price == 68.99
    assert it.city == "Nashville" and it.state == "TN"
    assert it.varietal == "Cabernet Sauvignon"


def test_non_wine_is_dropped_by_the_shared_parser():
    """City Hive merchants sell spirits and beer too — the type gate keeps them out."""
    assert _parse_product(_raw(typ="spirits"), "M1") is None


def test_wine_records_keep_the_pre_enriched_region_and_country():
    """City Hive hands us varietal/region/country/ABV already — persist them rather
    than making the enrichment pipeline rediscover it later."""
    p = _parse_product(_raw(), "M1")
    rec = _wine_records([p])[0]
    assert rec["varietal"] == "Cabernet Sauvignon"
    assert rec["region"] == "Napa Valley"
    assert rec["country"] == "US"
    assert rec["grapes"] == ["Cabernet Sauvignon"]
    assert rec["upc_canonical"].startswith("cityhive-")


def test_wine_records_dedup_by_upc():
    p = _parse_product(_raw(), "M1")
    assert len(_wine_records([p, p])) == 1


def test_out_of_stock_is_recorded_not_dropped():
    """Price still matters for a wine that's temporarily out — don't discard it."""
    p = _parse_product(_raw(qty=0), "M1")
    items = _to_items([p], "5c2a8cae7309395802faf15d", CH_STORES["5c2a8cae7309395802faf15d"])
    assert items[0].in_stock is False


def test_db_chunk_is_small_enough_for_a_full_term_sweep():
    """A 42-term sweep yields ~760 wines/store; an unchunked upsert or IN-clause
    that size returns 400 Bad Request on URL length (hit live 2026-08-26)."""
    from scrapers.nashville_cityhive import _DB_CHUNK
    assert _DB_CHUNK <= 200
