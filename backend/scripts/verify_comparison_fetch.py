"""Acceptance replay for the aisle-mode multi-bottle comparison path (delta 3).
Run from backend/: python3 -m scripts.verify_comparison_fetch
Live zip with known inventory (78209): both named bottles must be fetched,
ranked, and BOTH pinned to the front of the shortlist."""
from db import get_supabase_client
from recommendation.candidate_filters import (pin_comparison_matches,
                                              rank_name_matches,
                                              significant_name_tokens)
from utils.geo import find_nearby_store_ids

ZIP = "78209"
NAMES = ["Caymus Cabernet", "Bonanza Cabernet"]


def _named_fetch(sb, nearby, wine_name):
    tokens = significant_name_tokens(wine_name)
    cond = ",".join(f"name.ilike.%{t}%" for t in tokens)
    rows = (sb.table("retail_inventory")
            .select("price, wine_id, stores!inner(id, retailer_name), wines!inner(id, name)")
            .in_("store_ref", nearby).eq("in_stock", True)
            .or_(cond, reference_table="wines").limit(80).execute().data or [])
    cands = [{"wine_id": r["wine_id"], "name": r["wines"]["name"], "price": r["price"],
              "retailer": r["stores"]["retailer_name"]} for r in rows]
    return rank_name_matches(cands, tokens)


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    assert nearby, "no nearby stores for 78209"

    named_lists = []
    for n in NAMES:
        nl = _named_fetch(sb, nearby, n)
        print(f"FETCH | {n!r} -> {len(nl)} rows; top={nl[0]['name'] if nl else None}")
        assert nl, f"expected {n} in 78209 inventory"
        named_lists.append(nl)

    filler = [{"wine_id": "filler", "name": "Some Other Red", "price": 15.0}]
    top = pin_comparison_matches(filler, named_lists, cap_per_name=2)
    print("PINNED SHORTLIST HEAD:")
    for w in top[:5]:
        print(f"  {w['name'][:60]:60s} ${w.get('price')}")
    head = " ".join(w["name"].lower() for w in top[:4])
    assert "caymus" in head and "bonanza" in head, "both bottles must lead the shortlist"
    print("OK — both compared bottles fetched and pinned to the front")


if __name__ == "__main__":
    main()
