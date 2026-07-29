"""Acceptance: 'anything from heb?' for a light-red profile at 78230 now surfaces
H-E-B wines (was 0). Run from backend/: /usr/bin/python3 -m scripts.verify_retailer_fetch"""
from db import get_supabase_client
from recommendation.candidate_filters import detect_retailer
from utils.geo import find_nearby_store_ids

ZIP = "78230"
SEL = "price, wine_id, wines!inner(id, name, varietal, wine_type)"


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    meta = sb.table("stores").select("id,retailer_name").in_("id", nearby).execute().data
    r2s = {}
    for s in meta:
        r2s.setdefault(s["retailer_name"], []).append(s["id"])

    for variant in ["anything from heb?", "what about HEB", "got any h-e-b picks", "show me h.e.b"]:
        got = detect_retailer(variant, list(r2s))
        print(f"  {variant!r} -> {got!r}")
        assert got == "H-E-B", f"expected H-E-B for {variant!r}"

    rows = (sb.table("retail_inventory").select(SEL).in_("store_ref", r2s["H-E-B"])
            .eq("in_stock", True).gte("price", 10).lte("price", 60)
            .eq("wines.wine_type", "red").limit(300).execute().data or [])
    print(f"H-E-B red candidates under $60 near {ZIP}: {len(rows)}")
    assert len(rows) > 0, "expected H-E-B reds to exist"
    print("sample:", [x["wines"]["name"][:40] for x in rows[:5]])
    print("OK — retailer detection + scoped fetch surface H-E-B inventory")


if __name__ == "__main__":
    main()
