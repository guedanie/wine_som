"""Vivino enrichment runner — concurrent edition.

Picks N un-enriched wines, resolves each via HTML name search, validates the
match by slug similarity, parses wine-level ratings from the wine page, and
writes results back to wines.vivino_* columns.

Runs up to CONCURRENCY wines in parallel, each self-throttling with a 0.3s
delay before each HTTP request.

Run from backend/:  python3 scripts/run_vivino_sample.py [--limit 100] [--dry-run]
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parents[1]))

from db import get_service_client
from enrichment.vivino import build_query, fetch_ratings, search_wine, strip_query_noise

MATCH_THRESHOLD = 0.6
CONCURRENCY = 5      # parallel workers
REQ_DELAY = 0.3      # seconds between each HTTP request within a worker


def fetch_sample(db, limit):
    resp = (
        db.table("wines")
        .select("id,name,brand,vintage_year,varietal,region,wine_type")
        .is_("vivino_enriched_at", "null")
        .limit(limit)
        .execute()
    )
    return resp.data


async def enrich_one(w, db, client, sem, args, results):
    """Enrich a single wine. Acquires semaphore slot for the full search+fetch."""
    async with sem:
        query = build_query(w["name"], w.get("brand"))
        hit = await search_wine(query, client, delay=REQ_DELAY)

        if hit is None or hit["score"] < MATCH_THRESHOLD:
            stripped = strip_query_noise(query)
            if stripped and stripped != query:
                fallback = await search_wine(stripped, client, delay=REQ_DELAY)
                if fallback and (hit is None or fallback["score"] > hit["score"]):
                    hit = fallback

        status = ""
        if hit is None:
            status = "NO_HIT"
        elif hit["score"] < MATCH_THRESHOLD:
            status = f"LOW_SCORE {hit['score']:.2f} → {hit['slug'][:50]}"
        else:
            stats = await fetch_ratings(hit, client, delay=REQ_DELAY)
            if stats is None:
                status = f"NO_STATS (id={hit['wine_id']}, score {hit['score']:.2f})"
            else:
                status = (f"OK {stats['ratings_average']} "
                          f"({stats['ratings_count']:,}) score {hit['score']:.2f}")
                if not args.dry_run:
                    update = {
                        "vivino_wine_id": hit["wine_id"],
                        "vivino_rating": stats["ratings_average"],
                        "vivino_ratings_count": stats["ratings_count"],
                        "vivino_match_score": round(hit["score"], 3),
                        "vivino_enriched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if stats.get("image_url"):
                        update["image_url"] = stats["image_url"]
                    db.table("wines").update(update).eq("id", w["id"]).execute()

        if not args.dry_run and not status.startswith("OK"):
            db.table("wines").update({
                "vivino_enriched_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", w["id"]).execute()

        print(f"  {w['name'][:55]!r} → {status}", flush=True)
        results.append((w["name"][:55], query[:50], status))


async def main_async(args):
    db = get_service_client()
    wines = fetch_sample(db, args.limit)
    total = len(wines)
    print(f"Sample: {total} wines | concurrency={CONCURRENCY} | threshold={MATCH_THRESHOLD} | "
          f"{'DRY RUN' if args.dry_run else 'writing to DB'}", flush=True)

    results = []
    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [enrich_one(w, db, client, sem, args, results) for w in wines]
        await asyncio.gather(*tasks)

    matched = sum(1 for _, _, s in results if s.startswith("OK"))
    below   = sum(1 for _, _, s in results if s.startswith("LOW_SCORE"))
    no_hit  = sum(1 for _, _, s in results if s == "NO_HIT")
    no_stats = sum(1 for _, _, s in results if s.startswith("NO_STATS"))

    print("\n" + "=" * 64)
    print(f"  Matched + written : {matched}/{total} ({matched/total*100:.0f}%)" if total else "  No wines to process")
    print(f"  Below threshold   : {below}")
    print(f"  No search hit     : {no_hit}")
    print(f"  Hit but no stats  : {no_stats}")
    print("=" * 64)

    if below or no_hit or no_stats:
        print("\nNon-matches for review:")
        for name, query, status in results:
            if not status.startswith("OK"):
                print(f"  {name!r:58} {status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
