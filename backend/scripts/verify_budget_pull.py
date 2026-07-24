"""Acceptance: an 'up to $50' bold-red request now clusters picks in the upper band
(vs the ~$16-20 the user saw), while a standout value wine can still surface.
Run from backend/: /usr/bin/python3 -m scripts.verify_budget_pull"""
from statistics import median
from db import get_supabase_client
from recommendation.scorer import score_candidates
from utils.geo import find_nearby_store_ids

ZIP = "78209"
SEL = ("price, wine_id, wines!inner(id, name, varietal, region, country, wine_type, "
       "grapes, vivino_rating, vivino_ratings_count)")


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    rows = (sb.table("retail_inventory").select(SEL).in_("store_ref", nearby)
            .eq("in_stock", True).gte("price", 10).lte("price", 50)
            .eq("wines.wine_type", "red").limit(1000).execute().data or [])
    cands = []
    for r in rows:
        w = r["wines"]
        cands.append({"wine_id": w["id"], "store_ref": "s", "name": w["name"],
                      "varietal": w.get("varietal"), "region": w.get("region"),
                      "country": w.get("country"), "wine_type": "red",
                      "grapes": w.get("grapes") or [], "price": float(r["price"] or 0),
                      "vivino_rating": w.get("vivino_rating"),
                      "vivino_ratings_count": w.get("vivino_ratings_count")})
    intent = {"wine_type": "red", "flavors": ["bold"], "grapes": [], "regions": [],
              "region": None, "avoid": [], "budget_min": 10.0, "budget_max": 50.0}
    scored = score_candidates(intent, cands)
    top = scored[:8]
    prices = [c["price"] for c in top]
    print(f"scored {len(cands)} red candidates under $50")
    print(f"top-8 prices: {[round(p) for p in prices]}")
    print(f"median top-8 price: ${median(prices):.0f}")
    assert median(prices) >= 30, f"expected upper-band clustering, got median ${median(prices):.0f}"
    print("OK — budget pull clusters picks in the upper band")


if __name__ == "__main__":
    main()
