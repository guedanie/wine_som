"""Vivino enrichment sample run — validate the pipeline before full enrichment.

Picks N un-enriched wines, resolves each via HTML name search, validates the
match by slug similarity, parses wine-level ratings from the wine page, and
writes results back to wines.vivino_* columns. Prints a match-quality report.

Run from backend/:  python3 scripts/run_vivino_sample.py [--limit 100] [--dry-run]
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from db import get_service_client
from enrichment.vivino import build_query, fetch_ratings, search_wine, strip_query_noise

MATCH_THRESHOLD = 0.6
SLEEP_BETWEEN_REQS = 0.6   # between search and wine-page fetch
SLEEP_BETWEEN_WINES = 1.0


def fetch_sample(db, limit):
    resp = (
        db.table("wines")
        .select("id,name,brand,vintage_year,varietal,region,wine_type")
        .is_("vivino_enriched_at", "null")
        .limit(limit)
        .execute()
    )
    return resp.data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_service_client()
    wines = fetch_sample(db, args.limit)
    total = len(wines)
    print(f"Sample: {total} wines (threshold {MATCH_THRESHOLD}, "
          f"{'DRY RUN' if args.dry_run else 'writing to DB'})", flush=True)

    matched, below, no_hit, no_stats, retried = 0, 0, 0, 0, 0
    rows = []

    for i, w in enumerate(wines, 1):
        query = build_query(w["name"], w.get("brand"))
        hit = search_wine(query)
        if hit is None or hit["score"] < MATCH_THRESHOLD:
            # over-specified retail names break Vivino search; retry stripped
            stripped = strip_query_noise(query)
            if stripped and stripped != query:
                retried += 1
                time.sleep(SLEEP_BETWEEN_REQS)
                fallback = search_wine(stripped)
                if fallback and (hit is None or fallback["score"] > hit["score"]):
                    hit = fallback

        status = ""
        if hit is None:
            no_hit += 1
            status = "NO_HIT"
        elif hit["score"] < MATCH_THRESHOLD:
            below += 1
            status = f"LOW_SCORE {hit['score']:.2f} → {hit['slug'][:50]}"
        else:
            time.sleep(SLEEP_BETWEEN_REQS)
            stats = fetch_ratings(hit)
            if stats is None:
                no_stats += 1
                status = f"NO_STATS (id={hit['wine_id']}, score {hit['score']:.2f})"
            else:
                matched += 1
                status = (f"OK {stats['ratings_average']} "
                          f"({stats['ratings_count']:,}) score {hit['score']:.2f}")
                if not args.dry_run:
                    db.table("wines").update({
                        "vivino_wine_id": hit["wine_id"],
                        "vivino_rating": stats["ratings_average"],
                        "vivino_ratings_count": stats["ratings_count"],
                        "vivino_match_score": round(hit["score"], 3),
                        "vivino_enriched_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", w["id"]).execute()

        rows.append((w["name"][:55], query[:50], status))
        print(f"  [{i}/{total}] {w['name'][:50]!r} → {status}", flush=True)
        time.sleep(SLEEP_BETWEEN_WINES)

    print("\n" + "=" * 64)
    print(f"  Matched + written : {matched}/{total} ({matched/total*100:.0f}%)")
    print(f"  Below threshold   : {below}")
    print(f"  No search hit     : {no_hit}")
    print(f"  Hit but no stats  : {no_stats}")
    print(f"  Retries used      : {retried}")
    print("=" * 64)

    if below or no_hit or no_stats:
        print("\nNon-matches for review:")
        for name, query, status in rows:
            if not status.startswith("OK"):
                print(f"  {name!r:58} {status}")


if __name__ == "__main__":
    main()
