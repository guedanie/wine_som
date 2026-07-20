"""Acceptance replay for item 31 (name-directed full-inventory fallback).
Run from backend/: python3 scripts/verify_name_fallback.py
Uses a live zip with known inventory (78209 San Antonio)."""
from db import get_supabase_client
from recommendation.candidate_filters import significant_name_tokens, rank_name_matches
from utils.geo import find_nearby_store_ids

ZIP = "78209"


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    assert nearby, "no nearby stores for 78209"

    # 1. A named bottle known to be stocked surfaces via name search.
    tokens = significant_name_tokens("Caymus Cabernet Sauvignon")
    cond = ",".join(f"name.ilike.%{t}%" for t in tokens)
    rows = (sb.table("retail_inventory")
            .select("price, wine_id, wines!inner(id, name, grapes, region)")
            .in_("store_ref", nearby).eq("in_stock", True)
            .or_(cond, reference_table="wines").limit(80).execute().data or [])
    cands = [{"wine_id": r["wine_id"], "name": r["wines"]["name"], "price": r["price"]} for r in rows]
    ranked = rank_name_matches(cands, tokens)
    print(f"NAMED  | 'Caymus' → {len(ranked)} matches; top={ranked[0]['name'] if ranked else None}")
    assert ranked, "expected Caymus in 78209 inventory"

    # 2. A grape constraint fetch returns rows via jsonb containment.
    grp = (sb.table("retail_inventory")
           .select("wine_id, wines!inner(id, name, grapes)")
           .in_("store_ref", nearby).eq("in_stock", True)
           .or_('grapes.cs.["Chenin Blanc"]', reference_table="wines").limit(50).execute().data or [])
    print(f"WEAK   | Chenin Blanc containment → {len(grp)} rows")
    assert grp, "expected Chenin Blanc rows via jsonb containment"
    print("OK — name search + grape containment both surface inventory")


if __name__ == "__main__":
    main()
