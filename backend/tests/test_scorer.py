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


def test_region_match_uses_containment():
    # intent "Rhône" should match a wine whose stored region is "Côtes du Rhône"
    match = _wine("Cotes du Rhone Wine", varietal="Grenache", grapes=["Grenache"],
                  region="Côtes du Rhône")
    other = _wine("Napa Cab", varietal="Cabernet Sauvignon",
                  grapes=["Cabernet Sauvignon"], region="Napa Valley")
    result = score_candidates(_intent(region="Rhône"), [match, other])
    assert result[0]["name"] == "Cotes du Rhone Wine"


def test_vivino_rating_boosts_score():
    """A well-rated wine (with enough ratings to trust) outranks an identical unrated one."""
    rated = _wine("Crowd Favorite")
    rated["vivino_rating"] = 4.5
    rated["vivino_ratings_count"] = 12000
    unrated = _wine("Unknown Wine")
    result = score_candidates(_intent(), [unrated, rated])
    assert result[0]["name"] == "Crowd Favorite"


def test_vivino_rating_low_count_ignored():
    """A rating backed by too few reviews must not move the score."""
    thin = _wine("Thin Rating")
    thin["vivino_rating"] = 5.0
    thin["vivino_ratings_count"] = 3
    plain = _wine("Plain Wine")
    result = score_candidates(_intent(), [thin, plain])
    assert result[0]["_score"] == result[1]["_score"]


def test_vivino_mediocre_rating_no_boost():
    """Ratings at or below the 3.5 baseline add nothing (boost-only, no penalty)."""
    meh = _wine("Mediocre Wine")
    meh["vivino_rating"] = 3.2
    meh["vivino_ratings_count"] = 50000
    plain = _wine("Plain Wine")
    result = score_candidates(_intent(), [meh, plain])
    assert result[0]["_score"] == result[1]["_score"]


def test_body_from_structure_profile():
    """Numeric body in structure_profile (GrapeMinds/Vivino) must satisfy a body intent
    even when the text body field is null and grapes imply nothing."""
    structured = _wine("Structured Full", varietal=None, grapes=[], region=None,
                       tasting_notes="")
    structured["structure_profile"] = {"body": 8.0, "tannins": 7.0, "source": "vivino"}
    flat = _wine("No Signal", varietal=None, grapes=[], region=None, tasting_notes="")
    result = score_candidates(_intent(body="full"), [flat, structured])
    assert result[0]["name"] == "Structured Full"


def test_body_from_structure_light():
    structured = _wine("Structured Light", varietal=None, grapes=[], region=None,
                       tasting_notes="")
    structured["structure_profile"] = {"body": 2.5}
    flat = _wine("No Signal", varietal=None, grapes=[], region=None, tasting_notes="")
    result = score_candidates(_intent(body="light"), [flat, structured])
    assert result[0]["name"] == "Structured Light"


def test_table_fills_medium_body_where_tags_cannot():
    """infer_body only knows light/full (from tags); a medium grape like Merlot
    has no such tag, so ONLY the grape+region table can satisfy a 'medium' intent."""
    from recommendation.flavor_profiles import flavor_tags_for
    from recommendation.scorer import infer_body
    # confirm the tag path genuinely can't produce 'medium' for Merlot
    tags = flavor_tags_for("Merlot", ["Merlot"], "Bordeaux")
    assert infer_body(tags) != "medium"

    merlot = _wine("Table Merlot", varietal="Merlot", grapes=["Merlot"],
                   region="Bordeaux", body=None)
    merlot["structure_profile"] = {}   # Vivino never matched it
    cab = _wine("Table Cab", varietal="Cabernet Sauvignon", grapes=["Cabernet Sauvignon"],
                region="Napa Valley", body=None)
    cab["structure_profile"] = {}
    result = score_candidates(_intent(wine_type="red", body="medium"), [cab, merlot])
    assert result[0]["name"] == "Table Merlot"   # only the table gives it medium body


# ── personalization: similarity to wines the user liked ──────────

def test_similarity_boosts_and_tags_a_wine_close_to_a_liked_one():
    intent = _intent()
    intent["liked_wines"] = [{
        "name": "Esprit de Tablas", "wine_id": "liked1",
        "varietal": "Grenache", "region": "Paso Robles", "flavors": ["earthy", "garrigue"],
    }]
    similar   = _wine("Rhône Blend", varietal="Grenache", grapes=["Grenache"], region="Paso Robles")
    unrelated = _wine("Cava Brut", wine_type="sparkling", varietal="Macabeo", grapes=["Macabeo"], region="Penedès")
    result = score_candidates(intent, [unrelated, similar])
    top = next(w for w in result if w["name"] == "Rhône Blend")
    other = next(w for w in result if w["name"] == "Cava Brut")
    assert top["_score"] > other["_score"]              # similar ranks higher
    assert top["_similar_to"] == "Esprit de Tablas"     # cites the liked wine
    assert other.get("_similar_to") is None


def test_no_self_similarity_citation():
    intent = _intent()
    intent["liked_wines"] = [{"name": "My Malbec", "wine_id": "w1", "varietal": "Malbec", "region": "Mendoza"}]
    cand = _wine("My Malbec", varietal="Malbec", grapes=["Malbec"], region="Mendoza")
    cand["wine_id"] = "w1"
    result = score_candidates(intent, [cand])
    assert result[0].get("_similar_to") is None          # don't cite a wine as similar to itself


def test_no_liked_wines_leaves_scoring_unchanged():
    cand = _wine("Plain", varietal="Merlot", grapes=["Merlot"], region="Bordeaux")
    result = score_candidates(_intent(), [cand])
    assert result[0].get("_similar_to") is None


def test_disliked_wine_penalizes_similar_candidates():
    intent = _intent()
    intent["disliked_wines"] = [{"name": "Oaky Chard", "wine_id": "d1", "varietal": "Chardonnay", "region": "Napa"}]
    similar   = _wine("Napa Chardonnay", wine_type="white", varietal="Chardonnay", grapes=["Chardonnay"], region="Napa")
    unrelated = _wine("Chianti", varietal="Sangiovese", grapes=["Sangiovese"], region="Tuscany")
    result = score_candidates(intent, [similar, unrelated])
    assert result[0]["name"] == "Chianti"                 # the disliked-resembling wine is pushed down
    assert next(w for w in result if w["name"] == "Napa Chardonnay")["_score"] < \
           next(w for w in result if w["name"] == "Chianti")["_score"]
