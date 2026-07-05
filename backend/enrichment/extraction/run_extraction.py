"""
Extract facts (region, varietal, grapes, abv, body) for wines and write back to wines table.

Usage:
    cd backend
    python3 -m enrichment.extraction.run_extraction            # all wines
    python3 -m enrichment.extraction.run_extraction --null-only  # only wines with null region
"""
import sys
from db import get_service_client
from enrichment.extraction.extractor import extract_facts

BATCH_SIZE = 15
WRITE_FIELDS = ["region", "sub_region", "country", "vintage_year", "varietal", "grapes", "abv", "body"]


def fetch_wines(db, null_only: bool = False):
    wines, details = [], {}
    page, limit = 0, 1000
    while True:
        q = db.table("wines").select("id,name,wine_type")
        if null_only:
            q = q.is_("region", "null")
        rows = q.range(page * limit, (page + 1) * limit - 1).execute()
        if not rows.data:
            break
        wines.extend(rows.data)
        page += 1
        if len(rows.data) < limit:
            break

    wine_ids = [w["id"] for w in wines]
    for i in range(0, len(wine_ids), 200):
        chunk = wine_ids[i:i + 200]
        desc_rows = db.table("wine_details").select("wine_id,description,description_long").in_("wine_id", chunk).execute()
        for d in desc_rows.data:
            details[d["wine_id"]] = d

    rows_for_extraction = []
    for w in wines:
        d = details.get(w["id"], {})
        rows_for_extraction.append({
            "id": w["id"],
            "name": w["name"],
            "wine_type": w["wine_type"],
            "description": d.get("description") or "",
            "description_long": d.get("description_long") or "",
        })
    return rows_for_extraction


def write_batch(db, results):
    for r in results:
        payload = {f: r.get(f) for f in WRITE_FIELDS}
        try:
            db.table("wines").update(payload).eq("id", r["wine_id"]).execute()
        except Exception as e:
            print(f"  write failed for {r['wine_id']}: {e}", flush=True)


def _arg_limit() -> int:
    """--limit N caps how many wines a run processes (bounds the Haiku spend
    when the catalog is large). 0/absent = no cap."""
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                return 0
        if a.startswith("--limit="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def main():
    null_only = "--null-only" in sys.argv
    limit = _arg_limit()
    db = get_service_client()

    mode = "null-region wines only" if null_only else "all wines"
    print(f"Fetching wines + descriptions ({mode})...", flush=True)
    wines = fetch_wines(db, null_only=null_only)
    if limit and len(wines) > limit:
        print(f"  capping to {limit} of {len(wines)} (--limit)", flush=True)
        wines = wines[:limit]
    total = len(wines)
    print(f"  {total} wines loaded", flush=True)

    written = 0
    for i in range(0, total, BATCH_SIZE):
        batch = wines[i:i + BATCH_SIZE]
        results = extract_facts(batch, batch_size=BATCH_SIZE)
        write_batch(db, results)
        written += len(results)
        pct = (i + len(batch)) / total * 100
        print(f"  {i + len(batch)}/{total} ({pct:.0f}%) — {written} written", flush=True)

    print(f"Done — {written} wines updated", flush=True)


if __name__ == "__main__":
    main()
