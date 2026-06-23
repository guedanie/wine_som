import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.scorer import score_candidates


def _intent(wine_type=None, body=None, flavors=None, grapes=None, region=None,
            avoid=None, budget_min=10.0, budget_max=50.0):
    return {
        "wine_type": wine_type,
        "body": body,
        "flavors": flavors or [],
        "grapes": grapes or [],
        "region": region,
        "avoid": avoid or [],
        "budget_min": budget_min,
        "budget_max": budget_max,
    }


def _wine(name, wine_type="red", varietal="Malbec", grapes=None, region="Mendoza",
          country="Argentina", body=None, tasting_notes="dark fruit",
          flavor_profile=None, price=25.0, tier=2):
    return {
        "wine_id": "test-id",
        "name": name,
        "wine_type": wine_type,
        "varietal": varietal,
        "grapes": grapes or [],
        "region": region,
        "country": country,
        "body": body,
        "tasting_notes": tasting_notes,
        "flavor_profile": flavor_profile or [],
        "structure_profile": {},
        "price": price,
        "retailer": "Geraldine's",
        "tier": tier,
    }


def test_wine_type_match_scores_higher():
    red = _wine("Bold Red", wine_type="red")
    white = _wine("Crisp White", wine_type="white", varietal="Chardonnay")
    result = score_candidates(_intent(wine_type="red"), [white, red])
    assert result[0]["name"] == "Bold Red"


def test_avoid_list_excludes_wines():
    sweet = _wine("Sweet Riesling", wine_type="white", varietal="Riesling",
                  tasting_notes="sweet honey peach")
    dry = _wine("Dry Chardonnay", wine_type="white", varietal="Chardonnay",
                tasting_notes="crisp citrus oak")
    result = score_candidates(_intent(avoid=["sweet"]), [sweet, dry])
    names = [w["name"] for w in result]
    assert "Sweet Riesling" not in names
    assert "Dry Chardonnay" in names


def test_price_proximity_scores_midrange_higher():
    cheap = _wine("Budget Red", price=10.0)
    mid = _wine("Mid Red", price=25.0)
    result = score_candidates(_intent(budget_min=20.0, budget_max=30.0), [cheap, mid])
    assert result[0]["name"] == "Mid Red"


def test_earthy_intent_ranks_gsm_over_fruit_bomb_via_grape_inference():
    # Neither wine's notes literally say "earthy"; the GSM wins on grape/region knowledge.
    gsm = _wine("Rhône GSM", varietal="Grenache",
                grapes=["Grenache", "Syrah", "Mourvèdre"], region="Rhône",
                tasting_notes="Mediterranean assemblage, blended for immediacy")
    jammy = _wine("Jammy Zin", varietal="Zinfandel", grapes=["Zinfandel"],
                  region="Napa Valley", tasting_notes="luscious smooth jam")
    result = score_candidates(_intent(wine_type="red", flavors=["earthy"]), [jammy, gsm])
    assert result[0]["name"] == "Rhône GSM"


def test_body_inferred_when_null():
    # full-body intent; wine body is null but grape implies 'full' (bold/structured)
    cab = _wine("Cab No Body", varietal="Cabernet Sauvignon",
                grapes=["Cabernet Sauvignon"], region="Napa Valley", body=None)
    light = _wine("Light Gamay", varietal="Gamay", grapes=["Gamay"],
                  region="Beaujolais", body=None)
    result = score_candidates(_intent(wine_type="red", body="full"), [light, cab])
    assert result[0]["name"] == "Cab No Body"


def test_tier1_outranks_equal_tier2():
    t1 = _wine("GrapeMinds Wine", tier=1)
    t2 = _wine("Extractor Wine", tier=2)
    result = score_candidates(_intent(), [t2, t1])
    assert result[0]["name"] == "GrapeMinds Wine"


def test_grape_match_scores():
    match = _wine("Malbec Match", varietal="Malbec", grapes=["Malbec"])
    other = _wine("Pinot", varietal="Pinot Noir", grapes=["Pinot Noir"], region="Burgundy")
    result = score_candidates(_intent(grapes=["Malbec"]), [other, match])
    assert result[0]["name"] == "Malbec Match"


def test_region_match_is_accent_insensitive():
    accented = _wine("Rhone Wine", varietal="Syrah", grapes=["Syrah"], region="Rhône")
    other = _wine("Other", varietal="Malbec", grapes=["Malbec"], region="Mendoza")
    # intent region without accent must still match the accented wine region
    result = score_candidates(_intent(region="Rhone"), [other, accented])
    assert result[0]["name"] == "Rhone Wine"
