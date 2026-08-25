"""Acceptance replay for item 44 (aisle-mode hard store filter).
Run from backend/: python3 -m scripts.verify_store_filter
Against live 78209 inventory: a store-scoped pool must contain ONLY that store's
rows, and dropping the store must widen to multiple stores."""
from db import get_supabase_client
from recommendation.candidate_filters import filter_to_store
from utils.geo import find_nearby_store_ids

ZIP = "78209"
STORE_NAME_LIKE = "Geraldine%"

INV = ("price, wine_id, stores!inner(id, retailer_name, name), wines!inner(id, name)")


def _pool(sb, nearby):
    """A breadth-style pool with EVERY nearby store represented — mirrors the real
    per-retailer fetch (`recommend.py::_fetch_rows`) rather than a flat limit, which
    would starve a small store like Geraldine's out of the sample."""
    out = []
    for sref in nearby:
        rows = (sb.table("retail_inventory").select(INV)
                .eq("store_ref", sref).eq("in_stock", True)
                .limit(120).execute().data or [])
        out += [{"wine_id": r["wine_id"], "name": r["wines"]["name"],
                 "store_ref": r["stores"]["id"], "retailer": r["stores"]["retailer_name"],
                 "store_name": r["stores"]["name"]} for r in rows]
    return out


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    assert nearby, "no nearby stores for 78209"

    store = (sb.table("stores").select("id, name")
             .in_("id", nearby).ilike("name", STORE_NAME_LIKE)
             .limit(1).execute().data or [])
    assert store, f"no nearby store matching {STORE_NAME_LIKE}"
    sid, sname = store[0]["id"], store[0]["name"]

    pool = _pool(sb, nearby)
    stores_in_pool = {c["store_ref"] for c in pool}
    print(f"POOL   | {len(pool)} rows across {len(stores_in_pool)} nearby stores")
    assert len(stores_in_pool) >= 2, "expected a multi-store breadth pool to widen from"

    scoped = filter_to_store(pool, sid)
    scoped_stores = {c["store_ref"] for c in scoped}
    print(f"SCOPED | {sname}: {len(scoped)} rows, stores in result = {scoped_stores}")
    assert scoped, f"{sname} should have in-stock rows near {ZIP}"
    assert scoped_stores == {sid}, f"HARD FILTER LEAKED: {scoped_stores} != {{{sid}}}"
    off = [c for c in scoped if c["store_ref"] != sid]
    assert not off, f"off-store rows survived: {[c['store_name'] for c in off][:3]}"

    widened = filter_to_store(pool, None)   # widen = no store_ref
    assert len(widened) == len(pool) and {c["store_ref"] for c in widened} == stores_in_pool
    print(f"WIDEN  | dropping the store restores all {len(widened)} rows "
          f"across {len(stores_in_pool)} stores")
    print(f"OK — {sname} scope yields only its shelves; widening restores nearby stores")


if __name__ == "__main__":
    main()
