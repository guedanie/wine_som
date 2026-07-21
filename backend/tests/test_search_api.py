import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app

# ── fixtures ─────────────────────────────────────────────────────────────────

_STORES = [
    {"id": "store-1", "retailer_name": "Spec's", "latitude": 29.50, "longitude": -98.45},
    {"id": "store-2", "retailer_name": "H-E-B", "latitude": 29.40, "longitude": -98.50},
]

_WINES = [
    {"id": "w1", "name": "Brunello di Montalcino", "brand": "Altesino",
     "vintage_year": 2018, "varietal": "Sangiovese", "region": "Tuscany",
     "country": "Italy", "wine_type": "red", "image_url": "https://x/b.png",
     "vivino_rating": 4.3, "vivino_ratings_count": 12000},
    {"id": "w2", "name": "Chianti Classico Riserva", "brand": "Fèlsina",
     "vintage_year": 2020, "varietal": "Sangiovese", "region": "Tuscany",
     "country": "Italy", "wine_type": "red", "image_url": None,
     "vivino_rating": None, "vivino_ratings_count": None},
]

_INVENTORY = [
    {"price": 72.0, "wine_id": "w1", "store_ref": "store-1"},
    {"price": 76.0, "wine_id": "w1", "store_ref": "store-2"},   # dearer duplicate
    {"price": 38.0, "wine_id": "w2", "store_ref": "store-2"},
]


def _make_db(stores=None, wines=None, inventory=None):
    db = MagicMock()
    q = db.table.return_value.select.return_value

    stores_resp = MagicMock()
    stores_resp.data = stores if stores is not None else _STORES
    q.in_.return_value.execute.return_value = stores_resp

    wines_resp = MagicMock()
    wines_resp.data = wines if wines is not None else _WINES
    q.or_.return_value.is_.return_value.limit.return_value.execute.return_value = wines_resp

    inv_resp = MagicMock()
    inv_resp.data = inventory if inventory is not None else _INVENTORY
    (q.in_.return_value.in_.return_value.eq.return_value
     .lte.return_value.limit.return_value.execute.return_value) = inv_resp
    return db


def _patches(db):
    return (
        patch("api.routers.search.get_supabase_client", return_value=db),
        patch("api.routers.search.zip_to_centroid", return_value=(29.48, -98.42)),
        patch("api.routers.search.find_nearby_store_ids", return_value=["store-1", "store-2"]),
    )


async def _get(url):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.get(url)


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_wines_with_price_and_retailer():
    db = _make_db()
    p1, p2, p3 = _patches(db)
    with p1, p2, p3:
        resp = await _get("/api/search?q=tuscany&zip=78209")
    assert resp.status_code == 200
    wines = resp.json()["wines"]
    assert len(wines) == 2
    by_id = {w["wine_id"]: w for w in wines}
    assert by_id["w1"]["price"] == 72.0            # lowest price kept
    assert by_id["w1"]["retailer"] == "Spec's"
    assert by_id["w1"]["image_url"] == "https://x/b.png"
    assert by_id["w1"]["vivino_rating"] == 4.3
    assert by_id["w2"]["retailer"] == "H-E-B"


@pytest.mark.asyncio
async def test_search_includes_distance():
    db = _make_db()
    p1, p2, p3 = _patches(db)
    with p1, p2, p3:
        resp = await _get("/api/search?q=tuscany&zip=78209")
    wines = resp.json()["wines"]
    for w in wines:
        assert w["distance_miles"] is not None
        assert 0 < w["distance_miles"] < 30


@pytest.mark.asyncio
async def test_search_retailer_filter():
    """Filtering to a retailer restricts offers to it — and re-picks the best
    price within that retailer (w1 shows its H-E-B $76 offer, not Spec's $72)."""
    db = _make_db()
    p1, p2, p3 = _patches(db)
    with p1, p2, p3:
        resp = await _get("/api/search?q=tuscany&zip=78209&retailers=H-E-B")
    wines = resp.json()["wines"]
    assert len(wines) == 2
    assert all(w["retailer"] == "H-E-B" for w in wines)
    by_id = {w["wine_id"]: w for w in wines}
    assert by_id["w1"]["price"] == 76.0


@pytest.mark.asyncio
async def test_search_400_on_unknown_zip():
    with patch("api.routers.search.zip_to_centroid", return_value=None):
        resp = await _get("/api/search?q=x&zip=00000")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_search_empty_results_ok():
    db = _make_db(wines=[], inventory=[])
    p1, p2, p3 = _patches(db)
    with p1, p2, p3:
        resp = await _get("/api/search?q=zzzz&zip=78209")
    assert resp.status_code == 200
    assert resp.json()["wines"] == []


@pytest.mark.asyncio
async def test_search_out_of_stock_wines_excluded():
    """Wines with no nearby in-stock inventory don't appear in results."""
    db = _make_db(inventory=[{"price": 72.0, "wine_id": "w1", "store_ref": "store-1"}])
    p1, p2, p3 = _patches(db)
    with p1, p2, p3:
        resp = await _get("/api/search?q=tuscany&zip=78209")
    wines = resp.json()["wines"]
    assert [w["wine_id"] for w in wines] == ["w1"]


@pytest.mark.asyncio
async def test_search_matches_sub_region():
    """A sub-region search (e.g. 'Chianti Classico') must include sub_region in
    the OR clause so region-detail deep-links resolve to the right wines."""
    db = _make_db()
    captured = {}
    orig_or = db.table.return_value.select.return_value.or_
    def capture_or(clause):
        captured["clause"] = clause
        return orig_or.return_value
    db.table.return_value.select.return_value.or_ = capture_or
    p1, p2, p3 = _patches(db)
    with p1, p2, p3:
        await _get("/api/search?q=Chianti%20Classico&zip=78209")
    assert "sub_region.ilike" in captured["clause"]


def test_group_key_merges_vintage_variants():
    from api.routers.search import _group_key
    # same wine, different vintages/UPCs → same group key
    assert _group_key("The Prisoner Red Blend") == _group_key("The Prisoner Red Blend 2021")
    assert _group_key("The Prisoner Red Blend 2020") == _group_key("the prisoner red blend")
    # genuinely different wines → different keys
    assert _group_key("The Prisoner Red Blend") != _group_key("The Prisoner Cabernet Sauvignon")
