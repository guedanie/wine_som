"""
Persist deterministic grape+region structure to wine_details.structure_profile
for wines Vivino hasn't matched — so the dossier StructureBars, the Somm, and
the recommendation scorer get structure signal catalog-wide.

Precedence (structure_to_persist): never overwrites Vivino ('source':'vivino')
or GrapeMinds (real data, no source) structure; fills empty profiles and
refreshes prior table entries (idempotent). Wines with no anchoring grape are
skipped. Table-only — the ~3% of blends the table can't anchor are left for a
separate LLM-anchored pass.

  cd backend && python3 scripts/persist_structure.py [--limit N] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from db import get_service_client
from recommendation.structure_profiles import structure_to_persist

PAGE = 1000
UPSERT_BATCH = 200


def _existing_profile(wine_details) -> dict:
    d = wine_details
    if isinstance(d, list):
        d = d[0] if d else {}
    return (d or {}).get("structure_profile") or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max wines to process (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_service_client()
    written = skipped_auth = no_grape = 0
    pending = []
    page = 0
    processed = 0

    while True:
        rows = (db.table("wines")
                .select("id,varietal,region,grapes,wine_details(structure_profile)")
                .range(page * PAGE, (page + 1) * PAGE - 1)
                .execute().data)
        if not rows:
            break

        for w in rows:
            processed += 1
            existing = _existing_profile(w.get("wine_details"))
            profile = structure_to_persist(w.get("varietal"), w.get("grapes"),
                                           w.get("region"), existing)
            if profile is None:
                if existing:
                    skipped_auth += 1
                else:
                    no_grape += 1
                continue
            pending.append({"wine_id": w["id"], "structure_profile": profile})

            if len(pending) >= UPSERT_BATCH:
                if not args.dry_run:
                    db.table("wine_details").upsert(pending, on_conflict="wine_id").execute()
                written += len(pending)
                pending = []
                print(f"  processed {processed} | written {written} "
                      f"| skipped(auth) {skipped_auth} | no-grape {no_grape}", flush=True)

            if args.limit and processed >= args.limit:
                break

        if args.limit and processed >= args.limit:
            break
        if len(rows) < PAGE:
            break
        page += 1

    if pending:
        if not args.dry_run:
            db.table("wine_details").upsert(pending, on_conflict="wine_id").execute()
        written += len(pending)

    print("\n" + "=" * 56)
    print(f"  processed        : {processed}")
    print(f"  table structure  : {written}{'  (DRY RUN — not written)' if args.dry_run else ''}")
    print(f"  skipped (Vivino/GrapeMinds authoritative): {skipped_auth}")
    print(f"  no anchoring grape (blends etc.): {no_grape}")
    print("=" * 56)


if __name__ == "__main__":
    main()
