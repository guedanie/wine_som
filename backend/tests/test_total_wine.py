import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.total_wine import (
    _varietal_from_url, _parse_products, _scoped_url, TotalWineProduct,
    WrongStore, _assert_store, TW_STORES,
)


# --- varietal from the URL taxonomy ------------------------------------------
# Total Wine encodes colour + varietal in the product path, which is free
# structure the recommender otherwise has to infer (items 13/34: varietal-null
# wines are invisible to the scorer).

def test_varietal_from_a_standard_three_segment_path():
    v = _varietal_from_url("/wine/red-wine/cabernet-sauvignon/caymus-cabernet/p/223968750")
    assert v == "Cabernet Sauvignon"


def test_varietal_from_a_white_wine_path():
    v = _varietal_from_url("/wine/white-wine/sauvignon-blanc/olema-sauvignon-blanc/p/231443750")
    assert v == "Sauvignon Blanc"


def test_varietal_from_a_deeper_sparkling_path():
    """champagne-sparkling-wine/prosecco/brut/<slug> — varietal is still segment 2."""
    v = _varietal_from_url("/wine/champagne-sparkling-wine/prosecco/brut/la-vostra-prosecco/p/172976750")
    assert v == "Prosecco"


def test_varietal_is_none_when_the_path_is_too_shallow():
    assert _varietal_from_url("/wine/red-wine/p/1") is None
    assert _varietal_from_url("") is None


def test_varietal_does_not_return_the_colour_segment():
    """A 2-segment path has no varietal — must not mistake 'red-wine' for one."""
    assert _varietal_from_url("/wine/red-wine/some-slug/p/9") is None


# --- store scoping ------------------------------------------------------------

def test_scoped_url_puts_the_store_in_the_query_string():
    u = _scoped_url("https://x/wine/c/c0020", "503", 200)
    assert "storeId=503" in u and "pageSize=200" in u


def test_scoped_url_appends_to_an_existing_query():
    u = _scoped_url("https://x/wine/c/c0020?page=2", "503", 200)
    assert u.count("?") == 1 and "&storeId=503" in u


def test_assert_store_accepts_when_the_requested_store_is_present():
    _assert_store('{"storeId":"503"} … {"storeId":"1108"}', "503")   # chrome may carry 1108


def test_assert_store_raises_when_only_the_default_came_back():
    """The silent failure: a 200 with clean, parseable, WRONG-CITY data."""
    try:
        _assert_store('{"storeId":"1108"}', "503")
        assert False, "must refuse a response scoped to another store"
    except WrongStore:
        pass


# --- product parsing ----------------------------------------------------------

_LD = '''<script data-rh="true" type="application/ld+json">
{"@type":"ItemList","itemListElement":[
 {"@type":"ListItem","position":1,"url":"https://www.totalwine.com/wine/red-wine/cabernet-sauvignon/caymus-cabernet/p/223968750","name":"Caymus Cabernet Sauvignon"},
 {"@type":"ListItem","position":2,"url":"https://www.totalwine.com/wine/white-wine/sauvignon-blanc/olema-sauvignon-blanc/p/231443750","name":"Olema Sauvignon Blanc"}]}
</script>'''

_BODY = (
    '<a href="/wine/red-wine/cabernet-sauvignon/caymus-cabernet/p/223968750?s=503">x</a>'
    '<div class="price__ff218822">$68.99</div>'
    '<a href="/wine/white-wine/sauvignon-blanc/olema-sauvignon-blanc/p/231443750?s=503">y</a>'
    '<div class="price__ff218822">$12.99</div>'
)


def test_parse_pairs_identity_with_the_price_in_its_own_tile():
    rows = _parse_products(_LD + _BODY)
    assert len(rows) == 2
    assert rows[0].product_id == "223968750"
    assert rows[0].name == "Caymus Cabernet Sauvignon"
    assert rows[0].price == 68.99
    assert rows[0].varietal == "Cabernet Sauvignon"
    assert rows[1].product_id == "231443750"
    assert rows[1].price == 12.99


def test_parse_gives_a_synthetic_upc_since_total_wine_exposes_no_barcode():
    rows = _parse_products(_LD + _BODY)
    assert rows[0].upc == "totalwine-223968750"


def test_parse_leaves_price_none_rather_than_stealing_the_next_tiles_price():
    """A tile whose price markup changed must degrade to None, NEVER mis-pair —
    a wrong price is worse than a missing one."""
    body = (
        '<a href="/wine/red-wine/cabernet-sauvignon/caymus-cabernet/p/223968750?s=503">x</a>'
        '<a href="/wine/white-wine/sauvignon-blanc/olema-sauvignon-blanc/p/231443750?s=503">y</a>'
        '<div class="price__ff218822">$12.99</div>'
    )
    rows = _parse_products(_LD + body)
    assert rows[0].price is None          # its own tile had no price
    assert rows[1].price == 12.99         # the price belongs to the second


def test_parse_returns_empty_without_a_json_ld_itemlist():
    assert _parse_products("<html>no structured data</html>") == []


def test_store_registry_has_the_verified_san_antonio_store():
    s = TW_STORES["503"]
    assert s["zip"] == "78216" and s["city"] == "San Antonio" and s["state"] == "TX"


# --- resumable crawl cursor ---------------------------------------------------
# A single run CANNOT finish a store: Total Wine throttles to a stripped page and
# then a 403 around page ~11 of 30. So progress is a bookmark, and "throttled" is
# an expected outcome rather than a failure.

from scrapers.total_wine import _next_page


def test_crawl_resumes_after_the_last_completed_page():
    cur = {"503": {"last_page": 11, "total_pages": 30}}
    assert _next_page(cur, "503", 30) == 12


def test_crawl_starts_at_page_one_for_an_unseen_store():
    assert _next_page({}, "999", 30) == 1


def test_crawl_wraps_to_page_one_once_the_store_is_exhausted():
    """A finished store must re-crawl for fresh prices, not stall forever."""
    cur = {"503": {"last_page": 30, "total_pages": 30}}
    assert _next_page(cur, "503", 30) == 1


def test_crawl_wraps_when_the_cursor_overshoots_a_shrunken_catalog():
    cur = {"503": {"last_page": 42, "total_pages": 60}}
    assert _next_page(cur, "503", 30) == 1
