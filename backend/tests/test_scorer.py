import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.scorer import score_candidates


def _wine(name, wine_type="red", varietal="Malbec", region="Mendoza",
          country="Argentina", tasting_notes="dark fruit", flavor_profile=None, price=25.0):
    return {
        "wine_id": "test-id",
        "name": name,
        "wine_type": wine_type,
        "varietal": varietal,
        "region": region,
        "country": country,
        "tasting_notes": tasting_notes,
        "flavor_profile": flavor_profile or [],
        "structure_profile": {},
        "price": price,
        "retailer": "Geraldine's",
    }


def test_wine_type_match_scores_higher():
    red = _wine("Bold Red", wine_type="red")
    white = _wine("Crisp White", wine_type="white")
    result = score_candidates(
        candidates=[white, red],
        wine_type="red",
        style_preferences=[],
        avoid=[],
        budget_min=10.0,
        budget_max=50.0,
    )
    assert result[0]["name"] == "Bold Red"


def test_avoid_list_excludes_wines():
    sweet = _wine("Sweet Riesling", wine_type="white", varietal="Riesling",
                  tasting_notes="sweet honey peach")
    dry = _wine("Dry Chardonnay", wine_type="white", varietal="Chardonnay",
                tasting_notes="crisp citrus oak")
    result = score_candidates(
        candidates=[sweet, dry],
        wine_type=None,
        style_preferences=[],
        avoid=["sweet"],
        budget_min=10.0,
        budget_max=50.0,
    )
    names = [w["name"] for w in result]
    assert "Sweet Riesling" not in names
    assert "Dry Chardonnay" in names


def test_price_proximity_scores_midrange_higher():
    cheap = _wine("Budget Red", price=10.0)
    mid = _wine("Mid Red", price=25.0)
    result = score_candidates(
        candidates=[cheap, mid],
        wine_type=None,
        style_preferences=[],
        avoid=[],
        budget_min=20.0,
        budget_max=30.0,
    )
    assert result[0]["name"] == "Mid Red"
