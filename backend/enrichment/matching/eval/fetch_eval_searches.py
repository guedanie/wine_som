"""
Effectiveness eval — step 1: sample a stratified gold set, fetch + cache GrapeMinds
search hits, and emit a labeling CSV.

Run ONCE (spends ~50 GrapeMinds search calls):
  cd backend && python3 -m enrichment.matching.eval.fetch_eval_searches

Outputs (git-ignored):
  enrichment/matching/eval/eval_searches.json   — raw cached hits per wine
  enrichment/matching/eval/eval_candidates.csv  — open in Excel/Sheets, fill `correct`
"""
import csv
import json
import random
from pathlib import Path

from db import get_service_client
from config import settings
from enrichment.grapeminds import GrapeMindsClient
from enrichment.matching.scorer import score_candidates

OUT_DIR = Path(__file__).parent
SEED = 42
PER_RETAILER = 25  # ~50 total


def _sample_wines():
    """Stratified sample: PER_RETAILER wines each from H-E-B and Geraldine's."""
    c = get_service_client()
    rng = random.Random(SEED)
    sample = []
    for retailer in ("H-E-B", "Geraldine's Natural Wines"):
        rows = (
            c.table("retail_inventory")
            .select("wines(id,name,brand,wine_type)")
            .eq("retailer_name", retailer)
            .limit(1000)
            .execute()
        )
        wines, seen = [], set()
        for r in (rows.data or []):
            w = r.get("wines") or {}
            if w.get("id") and w["id"] not in seen and w.get("name"):
                seen.add(w["id"])
                w["source"] = retailer
                wines.append(w)
        rng.shuffle(wines)
        sample.extend(wines[:PER_RETAILER])
    return sample


def main():
    gm = GrapeMindsClient(api_key=settings.grapeminds_api_key)
    wines = _sample_wines()
    print(f"Sampled {len(wines)} wines. Fetching GrapeMinds searches...")

    cache = {}
    csv_rows = []
    for i, w in enumerate(wines, 1):
        hits = gm.search(w["name"], limit=5)
        cache[w["id"]] = {"wine": w, "source": w.get("source"), "hits": hits}
        candidates = score_candidates(hits, w.get("brand"), w.get("wine_type"), w["name"])
        if not candidates:
            csv_rows.append({
                "wine_id": w["id"], "wine_name": w["name"], "brand": w.get("brand"),
                "wine_type": w.get("wine_type"), "source": w.get("source"), "rank": "",
                "grapeminds_id": "", "gm_display_name": "NO_HITS", "gm_producer": "",
                "gm_color": "", "confidence": "", "is_primary": "", "correct": "",
            })
        for cand in candidates:
            csv_rows.append({
                "wine_id": w["id"], "wine_name": w["name"], "brand": w.get("brand"),
                "wine_type": w.get("wine_type"), "source": w.get("source"),
                "rank": cand["rank"], "grapeminds_id": cand["grapeminds_id"],
                "gm_display_name": cand["display_name"], "gm_producer": cand["producer_name"],
                "gm_color": cand["color"], "confidence": cand["confidence"],
                "is_primary": cand["is_primary"], "correct": "",
            })
        print(f"  [{i}/{len(wines)}] {w['name'][:50]} -> {len(hits)} hits")

    (OUT_DIR / "eval_searches.json").write_text(json.dumps(cache, indent=2, ensure_ascii=False))

    fields = ["wine_id", "wine_name", "brand", "wine_type", "source", "rank", "grapeminds_id",
              "gm_display_name", "gm_producer", "gm_color", "confidence", "is_primary", "correct"]
    with open(OUT_DIR / "eval_candidates.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\nWrote {OUT_DIR/'eval_searches.json'} and {OUT_DIR/'eval_candidates.csv'}")
    print("Now open eval_candidates.csv and put 1 in `correct` on each wine's true match (blank = none).")


if __name__ == "__main__":
    main()
