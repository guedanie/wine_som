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


def write_results(db, results):
    written = 0
    for r in results:
        payload = {f: r.get(f) for f in WRITE_FIELDS}
        db.table("wines").update(payload).eq("id", r["wine_id"]).execute()
        written += 1
    return written


def main():
    null_only = "--null-only" in sys.argv
    db = get_service_client()

    mode = "null-region wines only" if null_only else "all wines"
    print(f"Fetching wines + descriptions ({mode})...", flush=True)
    wines = fetch_wines(db, null_only=null_only)
    print(f"  {len(wines)} wines loaded", flush=True)

    print("Running extractor...", flush=True)
    results = extract_facts(wines, batch_size=BATCH_SIZE)
    print(f"  {len(results)} records extracted", flush=True)

    print("Writing to DB...", flush=True)
    written = write_results(db, results)
    print(f"  Done — {written} wines updated", flush=True)


if __name__ == "__main__":
    main()
