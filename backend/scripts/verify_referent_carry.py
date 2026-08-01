"""Acceptance replay for item 41 (referent carry across turns).
Run from backend/: python3 -m scripts.verify_referent_carry
Replays the 37210 repro deterministically (no Sonnet call): turn-1 picks ride
history, the referential turn-2 fetches them BY ID budget-free and pins them."""
from db import get_supabase_client
from recommendation.candidate_filters import (is_referential, pin_prior_picks,
                                              prior_picks_from_history)
from utils.geo import find_nearby_store_ids

ZIP = "37210"
NAMES = ["Avaline%Sauvignon%", "Starborough%"]


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    assert nearby, "no nearby stores for 37210"

    # Stand-ins for turn-1 picks: the two bug-report wines, found by name.
    picks = []
    for pat in NAMES:
        row = (sb.table("retail_inventory")
               .select("wine_id, wines!inner(id, name)")
               .in_("store_ref", nearby).eq("in_stock", True)
               .ilike("wines.name", pat).limit(1).execute().data or [])
        assert row, f"expected {pat} in stock near {ZIP}"
        picks.append({"wine_id": row[0]["wine_id"], "name": row[0]["wines"]["name"]})

    history = [{"role": "user", "content": "sauvignon blanc, maybe sancerre?"},
               {"role": "sommelier", "content": "Two I like.", "picks": picks}]
    followup = "Can we compare these two? Which do you recommend?"

    prior = prior_picks_from_history(history)
    assert [p["wine_id"] for p in prior] == [p["wine_id"] for p in picks]
    assert is_referential(followup), "follow-up must read as referential"

    # Budget-free by-id fetch (mirrors recommend.py's _prior_rows)
    ids = [p["wine_id"] for p in prior]
    rows = (sb.table("retail_inventory")
            .select("price, wine_id, wines!inner(id, name)")
            .in_("store_ref", nearby).eq("in_stock", True)
            .in_("wine_id", ids).limit(60).execute().data or [])
    cands = [{"wine_id": r["wine_id"], "name": r["wines"]["name"], "price": r["price"]}
             for r in rows]
    print(f"FETCH | {len(ids)} prior ids -> {len(cands)} in-stock rows near {ZIP}")
    assert {c["wine_id"] for c in cands} == set(ids), "both prior picks must be fetchable"

    filler = [{"wine_id": "filler", "name": "Some Other White", "price": 12.0}]
    top = pin_prior_picks(filler, cands, ids, cap=4)
    head_ids = [w["wine_id"] for w in top[:2]]
    assert head_ids == ids, f"prior picks must lead the shortlist, got {head_ids}"
    for w in top[:2]:
        print(f"PINNED | {w['name'][:50]:50s} ${w['price']}")
    print("OK — 'compare these two' keeps its subjects")


if __name__ == "__main__":
    main()
