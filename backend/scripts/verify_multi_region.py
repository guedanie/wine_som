"""Acceptance: a California-vs-Mendoza comparison surfaces BOTH regions.
Run from backend/: /usr/bin/python3 -m scripts.verify_multi_region"""
from db import get_supabase_client
from recommendation.intent import parse_message, merge_intent, intent_from_request
from recommendation.scorer import score_candidates
from recommendation.candidate_filters import ensure_region_representation, _cand_in_place
from utils.geo import find_nearby_store_ids

ZIP = "78209"
SEL = ("price, wine_id, wines!inner(id, name, varietal, region, country, wine_type, "
       "grapes, image_url, vivino_rating, vivino_ratings_count)")


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    parsed = parse_message("a cab from California vs a Mendoza one, recommend two to try")
    intent = merge_intent(parsed, intent_from_request(
        wine_type="red", style_preferences=[], avoid=[], budget_min=10.0, budget_max=50.0))
    print("regions parsed:", intent.get("regions"))
    assert len(intent.get("regions") or []) >= 2, "expected 2 regions parsed"

    cands = []
    for place in intent["regions"]:
        rows = (sb.table("retail_inventory").select(SEL).in_("store_ref", nearby)
                .eq("in_stock", True).gte("price", 10).lte("price", 50)
                .or_(f"region.ilike.%{place}%,country.ilike.%{place}%", reference_table="wines")
                .limit(300).execute().data or [])
        for r in rows:
            w = r["wines"]
            cands.append({"wine_id": w["id"], "store_ref": "s", "name": w["name"],
                          "varietal": w.get("varietal"), "region": w.get("region"),
                          "country": w.get("country"), "wine_type": w.get("wine_type"),
                          "grapes": w.get("grapes") or [], "price": r["price"]})
    scored = score_candidates(intent, cands)
    top = ensure_region_representation(scored[:12], scored, intent["regions"], 12)
    for nr in [r.lower() for r in intent["regions"]]:
        n = sum(1 for c in top if _cand_in_place(c, nr))
        print(f"  top-12 candidates matching {nr!r}: {n}")
        assert n >= 1, f"no representation for {nr}"
    print("OK — both regions represented in the top-12")


if __name__ == "__main__":
    main()
