import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app


WINE_ROW = {
    "price": 22.0,
    "curbside_price": None,
    "wine_id": "abc-123",
    "stores": {"retailer_name": "Geraldine's", "store_name": "Geraldine's", "zip_code": "78209", "address": "7700 Broadway St, San Antonio, TX 78209"},
    "wines": {
        "id": "abc-123",
        "name": "Test Malbec",
        "varietal": "Malbec",
        "region": "Mendoza",
        "country": "Argentina",
        "wine_type": "red",
        "wine_details": [{
            "tasting_notes": "dark fruit, plum, chocolate",
            "flavor_profile": ["dark fruit", "plum"],
            "structure_profile": {"body": 8, "tannins": 7, "acidity": 5},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        }],
    },
}

_ENRICHED_PICK = {
    "wine_id": "abc-123",
    "name": "Test Malbec",
    "price": 22.0,
    "retailer": "Geraldine's",
    "store_address": "7700 Broadway St, San Antonio, TX 78209",
    "why": "A classic Mendoza Malbec from Argentina with bold dark fruit.",
}


def _wine_row(name="Test Malbec", wine_id="abc-123", enriched=True, varietal="Malbec",
              region="Mendoza", grapes=None, body="full", price=22.0):
    return {
        "price": price, "curbside_price": None, "wine_id": wine_id,
        "stores": {"retailer_name": "Spec's", "store_name": "Spec's", "zip_code": "78209", "address": "1000 Austin Hwy, San Antonio, TX 78209"},
        "wines": {
            "id": wine_id, "name": name, "varietal": varietal, "region": region,
            "country": "Argentina", "wine_type": "red", "grapes": grapes or ["Malbec"],
            "body": body,
            "wine_details": [{
                "tasting_notes": "dark fruit, plum",
                "flavor_profile": ["dark fruit"],
                "structure_profile": {},
                "grapeminds_enriched_at": "2026-06-03T00:00:00Z" if enriched else None,
            }],
        },
    }


def _make_db_mock(data):
    qb = MagicMock()
    qb.table.return_value = qb
    qb.select.return_value = qb
    qb.eq.return_value = qb
    qb.gte.return_value = qb
    qb.lte.return_value = qb
    qb.in_.return_value = qb
    qb.limit.return_value = qb
    qb.insert.return_value = qb
    execute_result = MagicMock()
    execute_result.data = data
    qb.execute.return_value = execute_result
    return qb


def _make_stream_mock(narrative="Here are my top picks.", picks=None):
    """Returns a generator function suitable for use as stream_recommendations side_effect."""
    _picks = picks or [{
        "wine_id": "abc-123", "name": "Test Malbec", "price": 22.0,
        "retailer": "Geraldine's", "why": "A classic Mendoza Malbec.",
    }]
    def gen(*args, **kwargs):
        yield ("token", narrative)
        yield ("picks", _picks)
    return gen


def _sse_events(text):
    """Parse SSE response text into a list of event dicts (skips [DONE])."""
    events = []
    for part in text.split("\n\n"):
        part = part.strip()
        if not part.startswith("data: "):
            continue
        data = part[6:].strip()
        if data == "[DONE]":
            continue
        events.append(json.loads(data))
    return events


def _sse_picks(text):
    return next((e["picks"] for e in _sse_events(text) if e.get("type") == "picks"), [])


def _sse_narrative(text):
    return "".join(e["text"] for e in _sse_events(text) if e.get("type") == "token")


@pytest.mark.asyncio
async def test_recommend_returns_200():
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
                "style_preferences": ["bold", "earthy"],
                "avoid": [],
            })
    assert response.status_code == 200
    events = _sse_events(response.text)
    types = {e["type"] for e in events}
    assert "token" in types
    assert "picks" in types


@pytest.mark.asyncio
async def test_recommend_passes_conversational_flag_through():
    """The conversational flag from the request must reach stream_recommendations."""
    stream = MagicMock(side_effect=_make_stream_mock())
    with patch("api.routers.recommend.stream_recommendations", stream), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "style_preferences": ["bold"], "conversational": True,
                "message": "why that one?",
                "conversation_history": [{"role": "user", "content": "bold red"}],
            })
    assert stream.call_args.args[3] is True   # 4th positional arg = conversational


@pytest.mark.asyncio
async def test_recommend_conversational_defaults_false():
    stream = MagicMock(side_effect=_make_stream_mock())
    with patch("api.routers.recommend.stream_recommendations", stream), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "style_preferences": ["bold"],
            })
    assert stream.call_args.args[3] is False


@pytest.mark.asyncio
async def test_recommend_no_enriched_wines_returns_400():
    with patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "No enriched wines" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recommend_missing_zip_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/recommend", json={
            "budget_min": 15.0,
            "budget_max": 35.0,
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recommend_claude_failure_returns_500():
    with patch("api.routers.recommend.stream_recommendations", side_effect=Exception("API down")), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 500
    assert "unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_recommend_picks_have_required_fields():
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([WINE_ROW])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 200
    for pick in _sse_picks(response.text):
        assert all(k in pick for k in ["wine_id", "name", "price", "retailer", "why"])


@pytest.mark.asyncio
async def test_recommend_unknown_zip_returns_400():
    with patch("api.routers.recommend.zip_to_centroid", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "00000",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "don't recognize" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recommend_no_stores_nearby_returns_400():
    with patch("api.routers.recommend.zip_to_centroid", return_value=(29.47, -98.46)), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209",
                "budget_min": 15.0,
                "budget_max": 35.0,
            })
    assert response.status_code == 400
    assert "no stores found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recommend_includes_extractor_only_tier2_wine():
    """A wine with no GrapeMinds enrichment but with varietal/region is still a candidate."""
    row = _wine_row(enriched=False)
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock()), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([row])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommend_parses_nl_message_and_merges():
    captured = {}
    def fake_parse(msg):
        captured["msg"] = msg
        return {"wine_type": "white", "body": "light", "flavors": ["earthy"],
                "grapes": [], "region": None, "max_price": None, "avoid": []}
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock()), \
         patch("api.routers.recommend.parse_message", side_effect=fake_parse), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "wine_type": "red", "message": "something earthy"})
    assert response.status_code == 200
    assert captured["msg"] == "something earthy"


@pytest.mark.asyncio
async def test_recommend_fail_soft_when_parse_errors():
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock()), \
         patch("api.routers.recommend.parse_message", return_value=None), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0,
                "message": "anything"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommend_reattaches_retailer_from_candidate_not_model():
    """The router must re-attach authoritative name/price/retailer from candidates."""
    bad_picks = [{"wine_id": "abc-123", "name": "Hallucinated Name",
                  "price": 999.0, "retailer": "WRONG-RETAILER", "why": "because"}]
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock(picks=bad_picks)), \
         patch("api.routers.recommend.get_supabase_client", return_value=_make_db_mock([_wine_row()])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200
    pick = _sse_picks(response.text)[0]
    assert pick["retailer"] == "Spec's"
    assert pick["name"] == "Test Malbec"
    assert pick["price"] == 22.0
    assert pick["why"] == "because"


def test_recommend_request_accepts_wine_types():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209", wine_types=["red", "white"])
    assert req.wine_types == ["red", "white"]


def test_recommend_request_wine_types_defaults_empty():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209")
    assert req.wine_types == []


def test_recommend_request_accepts_grapes():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209", grapes=["Cabernet Sauvignon", "Merlot"])
    assert req.grapes == ["Cabernet Sauvignon", "Merlot"]


def test_recommend_request_grapes_defaults_empty():
    from api.schemas import RecommendRequest
    req = RecommendRequest(zip_code="78209")
    assert req.grapes == []


_WINE_ROW_WITH_ADDRESS = {
    "price": 22.0,
    "curbside_price": None,
    "wine_id": "abc-123",
    "stores": {
        "retailer_name": "Spec's",
        "zip_code": "78209",
        "address": "1000 Austin Hwy, San Antonio, TX 78209",
    },
    "wines": {
        "id": "abc-123", "name": "Test Malbec", "varietal": "Malbec",
        "region": "Mendoza", "country": "Argentina", "wine_type": "red",
        "grapes": ["Malbec"], "body": "full",
        "wine_details": {
            "tasting_notes": "dark fruit",
            "flavor_profile": ["dark fruit"],
            "structure_profile": {},
            "grapeminds_enriched_at": "2026-06-03T00:00:00Z",
        },
    },
}


@pytest.mark.asyncio
async def test_recommend_picks_include_store_address():
    """store_address should flow through from the stores join to the pick."""
    with patch("api.routers.recommend.stream_recommendations", side_effect=_make_stream_mock()), \
         patch("api.routers.recommend.get_supabase_client",
               return_value=_make_db_mock([_WINE_ROW_WITH_ADDRESS])), \
         patch("api.routers.recommend.get_service_client", return_value=_make_db_mock([])), \
         patch("api.routers.recommend.find_nearby_store_ids", return_value=["store-uuid-1"]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/recommend", json={
                "zip_code": "78209", "budget_min": 15.0, "budget_max": 35.0})
    assert response.status_code == 200
    pick = _sse_picks(response.text)[0]
    assert pick["store_address"] == "1000 Austin Hwy, San Antonio, TX 78209"


def test_enrich_picks_carries_image_and_rating():
    """Picks must carry image_url + vivino fields so WineCards can render them."""
    from api.routers.recommend import _enrich_picks
    by_id = {"w1": {
        "wine_id": "w1", "name": "Jordan Cab", "price": 60.0,
        "retailer": "Spec's", "store_address": "123 Main St",
        "image_url": "https://images.vivino.com/x.png",
        "vivino_rating": 4.3, "vivino_ratings_count": 57491,
    }}
    picks = _enrich_picks([{"wine_id": "w1", "why": "structured"}], by_id)
    assert picks[0]["image_url"] == "https://images.vivino.com/x.png"
    assert picks[0]["vivino_rating"] == 4.3
    assert picks[0]["vivino_ratings_count"] == 57491


def test_enrich_picks_rating_fields_none_when_absent():
    from api.routers.recommend import _enrich_picks
    by_id = {"w1": {"wine_id": "w1", "name": "X", "price": 10.0,
                    "retailer": "H-E-B", "store_address": None}}
    picks = _enrich_picks([{"wine_id": "w1", "why": "y"}], by_id)
    assert picks[0]["image_url"] is None
    assert picks[0]["vivino_rating"] is None


def test_select_diverse_top_caps_per_retailer():
    """No retailer may fill more than _RETAILER_CAP of the Claude candidate list —
    prevents one retailer's price/rating distribution from shutting others out."""
    from api.routers.recommend import _select_diverse_top
    scored = (
        [{"wine_id": f"s{i}", "retailer": "Spec's", "_score": 10 - i * 0.1} for i in range(12)]
        + [{"wine_id": f"a{i}", "retailer": "AOC Selections", "_score": 5 - i * 0.1} for i in range(6)]
    )
    top = _select_diverse_top(scored, max_candidates=12, per_retailer_cap=5)
    assert len(top) == 12
    from collections import Counter
    mix = Counter(w["retailer"] for w in top)
    # 5 capped slots each; the 2 leftover slots backfill from next-best (Spec's)
    assert mix["AOC Selections"] == 5
    assert mix["Spec's"] == 7


def test_select_diverse_top_keeps_score_order():
    from api.routers.recommend import _select_diverse_top
    scored = (
        [{"wine_id": f"s{i}", "retailer": "Spec's", "_score": 10 - i} for i in range(3)]
        + [{"wine_id": "h0", "retailer": "H-E-B", "_score": 5}]
    )
    top = _select_diverse_top(scored, max_candidates=4, per_retailer_cap=5)
    assert [w["wine_id"] for w in top] == ["s0", "s1", "s2", "h0"]


def test_select_diverse_top_single_retailer_backfills():
    """With only one retailer available, the cap must not starve the list."""
    from api.routers.recommend import _select_diverse_top
    scored = [{"wine_id": f"s{i}", "retailer": "Spec's", "_score": 10 - i} for i in range(12)]
    top = _select_diverse_top(scored, max_candidates=12, per_retailer_cap=5)
    assert len(top) == 12


def test_select_diverse_top_caps_per_varietal():
    """No single grape may fill more than per_varietal_cap of the list — spreads
    grocery-heavy markets that over-index on Cabernet/Chardonnay."""
    from collections import Counter
    from api.routers.recommend import _select_diverse_top
    # 10 Cabernets (top scores) + 4 Malbec + 4 Syrah, one retailer
    scored = (
        [{"wine_id": f"c{i}", "retailer": "Kroger", "varietal": "Cabernet Sauvignon", "_score": 10 - i * 0.1} for i in range(10)]
        + [{"wine_id": f"m{i}", "retailer": "Kroger", "varietal": "Malbec", "_score": 6 - i * 0.1} for i in range(4)]
        + [{"wine_id": f"y{i}", "retailer": "Kroger", "varietal": "Syrah", "_score": 5 - i * 0.1} for i in range(4)]
    )
    top = _select_diverse_top(scored, max_candidates=12, per_retailer_cap=12, per_varietal_cap=4)
    mix = Counter(w["varietal"] for w in top)
    assert mix["Cabernet Sauvignon"] == 4      # capped, not 10
    assert mix["Malbec"] == 4
    assert mix["Syrah"] == 4
    assert len(top) == 12


def test_varietal_cap_falls_back_to_grapes_field():
    """When varietal is null, the cap keys on grapes[0]."""
    from collections import Counter
    from api.routers.recommend import _select_diverse_top
    scored = (
        [{"wine_id": f"c{i}", "retailer": "Kroger", "varietal": None, "grapes": ["Cabernet Sauvignon"], "_score": 10 - i} for i in range(8)]
        + [{"wine_id": f"m{i}", "retailer": "Kroger", "varietal": None, "grapes": ["Malbec"], "_score": 3 - i} for i in range(6)]
    )
    top = _select_diverse_top(scored, max_candidates=10, per_retailer_cap=12, per_varietal_cap=5)
    mix = Counter((w.get("grapes") or [None])[0] for w in top)
    assert mix["Cabernet Sauvignon"] == 5      # capped by grapes[0]


def test_varietal_cap_backfills_when_pool_too_narrow():
    """If capping would starve the list (only one grape available), backfill."""
    from api.routers.recommend import _select_diverse_top
    scored = [{"wine_id": f"c{i}", "retailer": "Kroger", "varietal": "Cabernet Sauvignon", "_score": 10 - i} for i in range(12)]
    top = _select_diverse_top(scored, max_candidates=12, per_retailer_cap=12, per_varietal_cap=4)
    assert len(top) == 12      # cap can't be honored; fill anyway


def test_enrich_picks_warns_when_dropping_mismatched_pick(caplog):
    """A pick whose wine_id isn't a known candidate is dropped — log it so a
    narrative/card mismatch (3 wines described, 2 cards shown) is diagnosable."""
    import logging
    from api.routers.recommend import _enrich_picks
    by_id = {"good": {"wine_id": "good", "name": "Real Wine", "price": 20, "retailer": "Spec's"}}
    raw = [
        {"wine_id": "good", "name": "Real Wine", "price": 20, "retailer": "Spec's", "why": "fits"},
        {"wine_id": "ghost", "name": "Hallucinated", "price": 15, "retailer": "H-E-B", "why": "x"},
    ]
    with caplog.at_level(logging.WARNING):
        out = _enrich_picks(raw, by_id)
    assert [p["wine_id"] for p in out] == ["good"]        # ghost dropped
    assert any("ghost" in r.message for r in caplog.records)  # and logged


# ── Phantom-card fix: reconcile picks to what the narrative actually names ──

def test_reconcile_drops_picks_absent_from_narrative():
    from api.routers.recommend import _reconcile_picks_to_narrative
    narrative = "The Block 906 Merlot is stellar, and Frog's Leap sings with bright cherry."
    picks = [
        {"wine_id": "1", "name": "Block 906 Merlot Howell Mountain"},
        {"wine_id": "2", "name": "Frog's Leap Rutherford, Napa Valley Merlot"},
        {"wine_id": "3", "name": "Les Lunes Black Vineyard Napa County Merlot"},  # never named
    ]
    out = _reconcile_picks_to_narrative(picks, narrative)
    assert [p["wine_id"] for p in out] == ["1", "2"]


def test_reconcile_keeps_all_when_each_is_named():
    from api.routers.recommend import _reconcile_picks_to_narrative
    narrative = "Elk Cove Pinot, the Lieu Dit Chenin, and the Daniele Conterno Barbera all shine."
    picks = [
        {"wine_id": "1", "name": "Elk Cove Vineyards Pinot Noir"},
        {"wine_id": "2", "name": "Lieu Dit Chenin Blanc"},
        {"wine_id": "3", "name": "Daniele Conterno Barbera d'Alba"},
    ]
    assert len(_reconcile_picks_to_narrative(picks, narrative)) == 3


def test_reconcile_never_empties_and_ignores_singletons():
    from api.routers.recommend import _reconcile_picks_to_narrative
    one = [{"wine_id": "1", "name": "Silver Ghost Cabernet"}]
    assert _reconcile_picks_to_narrative(one, "no names here at all") == one   # singleton untouched
    # picks distinguishable only by generic grape/region words → keep (can't tell)
    generic = [{"wine_id": "1", "name": "Napa Cabernet"}, {"wine_id": "2", "name": "Sonoma Merlot"}]
    assert len(_reconcile_picks_to_narrative(generic, "a lovely evening pour")) == 2
