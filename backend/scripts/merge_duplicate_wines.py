"""
One-time, idempotent merge of duplicate wine rows that share a canonical UPC.

Run AFTER applying migration 20260620000002 (adds wines.upc_canonical):
    cd backend
    python3 scripts/merge_duplicate_wines.py

Steps: backfill upc_canonical -> group dupes -> merge fields onto a survivor ->
re-point retail_inventory / wine_details / wine_grapeminds_matches / user_saved_wines
-> delete losers -> create the unique index. Re-running after a partial failure is safe.

See docs/superpowers/specs/2026-06-20-upc-canonical-dedup-design.md
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from db import get_service_client
from utils.upc import canonical_upc

# Name source priority for display fields (lower index = preferred).
_NAME_PRIORITY = {"Spec's": 0, "H-E-B": 1}


def pick_survivor(group):
    """group: list of {"id", "inventory_count"}. Most inventory wins; tiebreak lowest id."""
    return sorted(group, key=lambda w: (-w["inventory_count"], w["id"]))[0]["id"]


def merge_fields(survivor, losers):
    """
    Return the dict of wine-column updates for the survivor.
    name/brand: prefer Spec's > HEB. region/sub_region/country/varietal/grapes/abv/body:
    keep survivor value if present, else fill from any loser.
    image_url: first non-null (survivor first).
    """
    out = dict(survivor)
    candidates = [survivor] + losers

    # name/brand by source priority
    for field in ("name", "brand"):
        ranked = sorted(
            [c for c in candidates if c.get(field)],
            key=lambda c: _NAME_PRIORITY.get(c.get("source"), 99),
        )
        if ranked:
            out[field] = ranked[0][field]

    # fill-if-null fields
    for field in ("region", "sub_region", "country", "varietal", "grapes", "abv", "body"):
        if out.get(field) in (None, "", [], "[]"):
            for c in candidates:
                if c.get(field) not in (None, "", [], "[]"):
                    out[field] = c[field]
                    break

    # image_url: first non-null, survivor first
    if not out.get("image_url"):
        for c in candidates:
            if c.get("image_url"):
                out["image_url"] = c["image_url"]
                break

    return out


# ─── DB orchestration ──────────────────────────────────────────────────────

_WINE_FIELDS = ("id,upc,upc_canonical,name,brand,region,sub_region,country,"
                "varietal,grapes,abv,body,image_url")


def _all_wines(db):
    rows, page, size = [], 0, 1000
    while True:
        r = db.table("wines").select(_WINE_FIELDS).range(page*size, (page+1)*size-1).execute()
        if not r.data:
            break
        rows.extend(r.data)
        if len(r.data) < size:
            break
        page += 1
    return rows


def _wine_source(db, wine_id):
    """Infer a wine's retailer from its inventory's stores (for name priority)."""
    inv = db.table("retail_inventory").select("store_ref").eq("wine_id", wine_id).execute()
    refs = [r["store_ref"] for r in inv.data if r.get("store_ref")]
    if not refs:
        return None
    st = db.table("stores").select("retailer_name").in_("id", refs[:50]).execute()
    names = {s["retailer_name"] for s in st.data}
    if "Spec's" in names:
        return "Spec's"
    if "H-E-B" in names:
        return "H-E-B"
    return next(iter(names), None)


def _inventory_count(db, wine_id):
    r = db.table("retail_inventory").select("id", count="exact").eq("wine_id", wine_id).execute()
    return r.count or 0


def _table_count(db, table):
    r = db.table(table).select("id", count="exact").execute()
    return r.count or 0


def _print_counts(db, label):
    counts = {t: _table_count(db, t) for t in ("wines", "retail_inventory", "wine_details")}
    print(f"  {label}: wines={counts['wines']} "
          f"retail_inventory={counts['retail_inventory']} "
          f"wine_details={counts['wine_details']}", flush=True)
    return counts


def main(dry_run=False):
    db = get_service_client()

    if dry_run:
        print("=== DRY RUN — no writes will be performed ===", flush=True)

    print("Count snapshot (before):", flush=True)
    _print_counts(db, "before")

    print("Backfilling upc_canonical ...", flush=True)
    wines = _all_wines(db)
    for w in wines:
        canon = canonical_upc(w.get("upc"))
        if canon and w.get("upc_canonical") != canon:
            if not dry_run:
                db.table("wines").update({"upc_canonical": canon}).eq("id", w["id"]).execute()
        w["upc_canonical"] = canon

    # group by canonical
    from collections import defaultdict
    groups = defaultdict(list)
    for w in wines:
        if w.get("upc_canonical"):
            groups[w["upc_canonical"]].append(w)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"  {len(dupes)} duplicate groups found", flush=True)

    merged = deleted = repointed = inv_dupes_deleted = 0
    failed = []
    for canon, group in dupes.items():
        try:
            enriched = [{**w, "inventory_count": _inventory_count(db, w["id"]),
                         "source": _wine_source(db, w["id"])} for w in group]
            survivor_id = pick_survivor(enriched)
            survivor = next(w for w in enriched if w["id"] == survivor_id)
            losers = [w for w in enriched if w["id"] != survivor_id]

            if dry_run:
                loser_ids = [l["id"] for l in losers]
                print(f"  [dry-run] group {canon}: survivor={survivor_id} "
                      f"losers={loser_ids} "
                      f"(inv counts: survivor={survivor['inventory_count']}, "
                      f"losers={[l['inventory_count'] for l in losers]})", flush=True)
                merged += 1
                deleted += len(losers)
                repointed += len(losers)
                continue

            # merge display fields onto survivor
            updates = merge_fields(survivor, losers)
            db.table("wines").update({
                k: updates.get(k) for k in
                ("name", "brand", "region", "sub_region", "country",
                 "varietal", "grapes", "abv", "body", "image_url")
            }).eq("id", survivor_id).execute()

            for loser in losers:
                lid = loser["id"]
                # retail_inventory -> survivor. UNIQUE(upc, store_ref) means a blanket
                # re-point can collide if the survivor already has the same key, so we
                # delete true duplicates and re-point the rest (idempotent, collision-proof).
                surv_keys = {
                    (r.get("upc"), r.get("store_ref"))
                    for r in db.table("retail_inventory")
                    .select("upc,store_ref").eq("wine_id", survivor_id).execute().data
                }
                for inv in (db.table("retail_inventory")
                            .select("id,upc,store_ref").eq("wine_id", lid).execute().data):
                    key = (inv.get("upc"), inv.get("store_ref"))
                    if key in surv_keys:
                        # survivor already has this (upc, store_ref) — true duplicate
                        db.table("retail_inventory").delete().eq("id", inv["id"]).execute()
                        inv_dupes_deleted += 1
                    else:
                        db.table("retail_inventory").update(
                            {"wine_id": survivor_id}).eq("id", inv["id"]).execute()
                        surv_keys.add(key)
                repointed += 1

                # wine_details: UNIQUE(wine_id) — keep longest description on survivor
                sd = db.table("wine_details").select("*").eq("wine_id", survivor_id).execute().data
                ld = db.table("wine_details").select("*").eq("wine_id", lid).execute().data
                if ld:
                    loser_desc = (ld[0].get("description") or "")
                    surv_desc = (sd[0].get("description") or "") if sd else ""
                    if not sd:
                        db.table("wine_details").update({"wine_id": survivor_id}).eq("wine_id", lid).execute()
                    else:
                        if len(loser_desc) > len(surv_desc) and loser_desc:
                            db.table("wine_details").update(
                                {"description": loser_desc}).eq("wine_id", survivor_id).execute()
                        db.table("wine_details").delete().eq("wine_id", lid).execute()

                # wine_grapeminds_matches: UNIQUE(wine_id, grapeminds_id) — re-point, skip collisions
                surv_gm = {m["grapeminds_id"] for m in
                           db.table("wine_grapeminds_matches").select("grapeminds_id").eq("wine_id", survivor_id).execute().data}
                for m in db.table("wine_grapeminds_matches").select("id,grapeminds_id").eq("wine_id", lid).execute().data:
                    if m["grapeminds_id"] in surv_gm:
                        db.table("wine_grapeminds_matches").delete().eq("id", m["id"]).execute()
                    else:
                        db.table("wine_grapeminds_matches").update({"wine_id": survivor_id}).eq("id", m["id"]).execute()

                # user_saved_wines: re-point (empty today; best-effort)
                try:
                    db.table("user_saved_wines").update({"wine_id": survivor_id}).eq("wine_id", lid).execute()
                except Exception:
                    pass

                # delete loser wine row
                db.table("wines").delete().eq("id", lid).execute()
                deleted += 1
            merged += 1
        except Exception as e:
            print(f"  group {canon} failed: {e}", flush=True)
            failed.append(canon)

    print(f"\nMerged {merged} groups, deleted {deleted} loser rows, "
          f"re-pointed {repointed} inventory sets, "
          f"deleted {inv_dupes_deleted} true-duplicate inventory rows", flush=True)

    if dry_run:
        print("\n=== DRY RUN complete — no writes performed ===", flush=True)
        if failed:
            print(f"FAILED groups ({len(failed)}): {failed}", flush=True)
        return

    # create the unique index now that dupes are gone (idempotent)
    print("Creating unique index on upc_canonical ...", flush=True)
    try:
        db.rpc("exec_sql", {"sql":
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wines_upc_canonical "
            "ON wines(upc_canonical) WHERE upc_canonical IS NOT NULL;"}).execute()
        print("Index created.", flush=True)
    except Exception as e:
        print(f"  Could not create index via RPC ({e}). "
              f"Add it via migration 20260620000003 instead.", flush=True)

    print("Count snapshot (after):", flush=True)
    _print_counts(db, "after")

    if failed:
        print(f"\nFAILED groups ({len(failed)}): {failed}", flush=True)
        print("WARNING: run incomplete — some groups did not merge. "
              "Fix the cause and re-run this script (it is idempotent).", flush=True)
    else:
        print("\nAll groups merged successfully.", flush=True)
    print("Done.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Read/group/decide and print what would happen, but make no writes.")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
