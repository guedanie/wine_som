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
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parents[1]))

from db import get_service_client
from enrichment.vivino import (VivinoFetchError, build_query, fetch_ratings,
                               search_wine, strip_query_noise,
                               structure_to_profile)
from enrichment.extraction.reference import is_default_blend

MATCH_THRESHOLD = 0.6   # ratings + image: cosmetic, tolerate borderline matches
FACTS_THRESHOLD = 0.7   # grapes/region/abv/structure: canonical facts need a stronger match

# Rate profile. GitHub runner IPs are datacenter addresses that Vivino
# throttles far harder than residential ones — pause-and-resume at 2 req/s
# still aborted after ~34 wines/run. In CI we crawl: 1 worker, ~0.4 req/s,
# long pauses. Locally the faster profile has proven safe.
_IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
CONCURRENCY   = 1 if _IN_CI else 2      # parallel workers
REQ_DELAY     = 2.5 if _IN_CI else 1.0  # seconds before each HTTP request per worker
ABORT_AFTER   = 10                      # consecutive fetch failures → pause / abort
PAUSE_SECONDS = 300 if _IN_CI else 90   # wait out the throttle window
MAX_PAUSES    = 5 if _IN_CI else 3      # pause cycles before conceding the block is real


async def handle_fetch_failure(state, abort):
    """Failure-streak policy: pause and resume up to MAX_PAUSES times, then abort.

    GitHub runner IPs get intermittently throttled by Vivino; a hard abort at
    the first streak wasted the rest of the run. Single-threaded event loop —
    the increment/check below is atomic between awaits.
    """
    state["consecutive_fails"] += 1
    if state["consecutive_fails"] < ABORT_AFTER:
        return
    if state["pauses"] >= MAX_PAUSES:
        if not abort.is_set():
            print(f"  !! still rate-limited after {MAX_PAUSES} pauses — aborting run", flush=True)
        abort.set()
        return
    state["pauses"] += 1
    state["consecutive_fails"] = 0
    print(f"  .. {ABORT_AFTER} consecutive fetch failures — pausing {PAUSE_SECONDS}s "
          f"(pause {state['pauses']}/{MAX_PAUSES})", flush=True)
    await asyncio.sleep(PAUSE_SECONDS)


_SAMPLE_COLS = "id,name,brand,vintage_year,varietal,region,country,wine_type,grapes,abv"

# Non-wine catalog noise that will never match on Vivino
_JUNK_NAMES = ("%sake%", "%cocktail%", "%margarita%", "%daiquiri%",
               "%pina colada%", "%spiked%", "%lemonade%")


def _junk_filter(q):
    for junk in _JUNK_NAMES:
        q = q.not_.ilike("name", junk)
    return q


def _tier_queries(db):
    """Priority tiers, all un-enriched + junk-filtered: (1) both-null wines are
    fully invisible to the recommender (item 13 — the Pogo's residue);
    (2) Bordeaux/Rhône rows need ratings + real blends (item 27); (3) the rest."""
    def base():
        return _junk_filter(db.table("wines").select(_SAMPLE_COLS)
                            .is_("vivino_enriched_at", "null"))
    return [
        base().is_("varietal", "null").is_("region", "null"),
        base().in_("region", ["Bordeaux", "Rhône"]),
        base(),
    ]


def fetch_sample(db, limit, missing_images_only=False):
    if missing_images_only:
        # Only HEB/CM wines lack images (all other scrapers capture CDN URLs),
        # so this flag effectively targets the HEB catalog — the mainstream
        # brands with the best Vivino match rates.
        q = (db.table("wines").select(_SAMPLE_COLS)
             .is_("vivino_enriched_at", "null").is_("image_url", "null"))
        return _junk_filter(q).limit(limit).execute().data
    picked, seen = [], set()
    for q in _tier_queries(db):
        if len(picked) >= limit:
            break
        for r in q.limit(limit).execute().data:
            if r["id"] not in seen and len(picked) < limit:
                seen.add(r["id"])
                picked.append(r)
    return picked


def fetch_backfill(db, limit):
    """Already-matched wines eligible for a facts/image backfill.

    These were enriched before attribute extraction existed (or before image
    capture). We stored vivino_wine_id, so no search request is needed —
    one page fetch per wine.
    """
    return (
        db.table("wines")
        .select("id,name,brand,vintage_year,varietal,region,country,wine_type,"
                "grapes,abv,image_url,vivino_wine_id,vivino_match_score")
        .not_.is_("vivino_wine_id", "null")
        .gte("vivino_match_score", FACTS_THRESHOLD)
        .limit(limit)
        .execute()
        .data
    )


def write_facts(db, w, attrs):
    """Fill NULL canonical fields from a high-confidence Vivino match.

    Precedence: scraped/extracted data always wins — Vivino only fills gaps.
    Returns the list of fields written (for the status line).
    """
    if not attrs:
        return []
    filled = []

    wine_update = {}
    # Grapes: fill when empty, and REPLACE when the current value is a
    # law-book default blend (backfill/extraction approximation) — real
    # per-wine data wins. Scraped/extracted grapes are never overwritten.
    current_grapes = w.get("grapes") or []
    if attrs.get("grapes") and attrs["grapes"] != current_grapes and (
            not current_grapes or is_default_blend(current_grapes)):
        wine_update["grapes"] = attrs["grapes"]
    if attrs.get("abv") is not None and w.get("abv") is None:
        wine_update["abv"] = attrs["abv"]
    if attrs.get("region") and not w.get("region"):
        wine_update["region"] = attrs["region"]
    if attrs.get("country") and not w.get("country"):
        wine_update["country"] = attrs["country"]
    if wine_update:
        db.table("wines").update(wine_update).eq("id", w["id"]).execute()
        filled += list(wine_update.keys())

    profile = structure_to_profile(attrs.get("structure"))
    pairing = ", ".join(attrs.get("foods") or []) or None
    if profile or pairing:
        existing = (
            db.table("wine_details")
            .select("wine_id,structure_profile,pairing")
            .eq("wine_id", w["id"]).limit(1).execute().data
        )
        if existing:
            detail_update = {}
            if profile and not existing[0].get("structure_profile"):
                detail_update["structure_profile"] = profile
            if pairing and not existing[0].get("pairing"):
                detail_update["pairing"] = pairing
            if detail_update:
                db.table("wine_details").update(detail_update).eq("wine_id", w["id"]).execute()
                filled += list(detail_update.keys())
        else:
            record = {"wine_id": w["id"], "source": "vivino"}
            if profile:
                record["structure_profile"] = profile
            if pairing:
                record["pairing"] = pairing
            db.table("wine_details").insert(record).execute()
            filled += [k for k in record if k not in ("wine_id", "source")]
    return filled


async def enrich_one(w, db, client, sem, args, results, state, abort):
    """Enrich a single wine. Acquires semaphore slot for the full search+fetch.

    Fetch failures (429/network) do NOT stamp vivino_enriched_at — the wine
    stays eligible for the next run. ABORT_AFTER consecutive failures trips
    the abort event and the remaining queue is skipped.
    """
    if abort.is_set():
        results.append((w["name"][:55], "", "SKIPPED_ABORT"))
        return
    async with sem:
        if abort.is_set():
            results.append((w["name"][:55], "", "SKIPPED_ABORT"))
            return
        query = build_query(w["name"], w.get("brand"))
        try:
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
                        if hit["score"] >= FACTS_THRESHOLD:
                            filled = write_facts(db, w, stats.get("attributes"))
                            if filled:
                                status += f" +facts({','.join(filled)})"
        except VivinoFetchError:
            await handle_fetch_failure(state, abort)
            results.append((w["name"][:55], query[:50], "FETCH_FAIL"))
            return

        state["consecutive_fails"] = 0

        if not args.dry_run and not status.startswith("OK"):
            db.table("wines").update({
                "vivino_enriched_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", w["id"]).execute()

        print(f"  {w['name'][:55]!r} → {status}", flush=True)
        results.append((w["name"][:55], query[:50], status))


async def backfill_one(w, db, client, sem, args, results, state, abort):
    """Backfill facts + image for an already-matched wine — page fetch only,
    no search. /w/{id} redirects to the canonical slug URL."""
    if abort.is_set():
        results.append((w["name"][:55], "", "SKIPPED_ABORT"))
        return
    async with sem:
        if abort.is_set():
            results.append((w["name"][:55], "", "SKIPPED_ABORT"))
            return
        match = {"wine_id": w["vivino_wine_id"], "href": f"/w/{w['vivino_wine_id']}"}
        try:
            stats = await fetch_ratings(match, client, delay=REQ_DELAY)
        except VivinoFetchError:
            await handle_fetch_failure(state, abort)
            results.append((w["name"][:55], "", "FETCH_FAIL"))
            return

        state["consecutive_fails"] = 0
        if stats is None:
            status = "NO_STATS"
        elif args.dry_run:
            status = "OK (dry run)"
        else:
            filled = []
            if stats.get("image_url") and not w.get("image_url"):
                db.table("wines").update({"image_url": stats["image_url"]}) \
                    .eq("id", w["id"]).execute()
                filled.append("image")
            filled += write_facts(db, w, stats.get("attributes"))
            status = "OK" + (f" +{','.join(filled)}" if filled else " (nothing to fill)")

        print(f"  {w['name'][:55]!r} → {status}", flush=True)
        results.append((w["name"][:55], "", status))


async def main_async(args):
    db = get_service_client()
    if args.backfill_facts:
        wines = fetch_backfill(db, args.limit)
    else:
        wines = fetch_sample(db, args.limit, missing_images_only=args.missing_images)
    total = len(wines)
    print(f"Sample: {total} wines | concurrency={CONCURRENCY} | threshold={MATCH_THRESHOLD} | "
          f"{'DRY RUN' if args.dry_run else 'writing to DB'}", flush=True)

    results = []
    sem = asyncio.Semaphore(CONCURRENCY)
    state = {"consecutive_fails": 0, "pauses": 0}
    abort = asyncio.Event()

    worker = backfill_one if args.backfill_facts else enrich_one
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [worker(w, db, client, sem, args, results, state, abort) for w in wines]
        await asyncio.gather(*tasks)

    matched = sum(1 for _, _, s in results if s.startswith("OK"))
    below   = sum(1 for _, _, s in results if s.startswith("LOW_SCORE"))
    no_hit  = sum(1 for _, _, s in results if s == "NO_HIT")
    no_stats = sum(1 for _, _, s in results if s.startswith("NO_STATS"))
    fetch_fail = sum(1 for _, _, s in results if s == "FETCH_FAIL")
    skipped = sum(1 for _, _, s in results if s == "SKIPPED_ABORT")

    print("\n" + "=" * 64)
    print(f"  Matched + written : {matched}/{total} ({matched/total*100:.0f}%)" if total else "  No wines to process")
    print(f"  Below threshold   : {below}")
    print(f"  No search hit     : {no_hit}")
    print(f"  Hit but no stats  : {no_stats}")
    print(f"  Fetch failures    : {fetch_fail} (not stamped — will retry next run)")
    print(f"  Skipped (abort)   : {skipped}")
    print("=" * 64)
    if abort.is_set():
        print("\n!! Run aborted early — Vivino rate limit. Re-run after the block clears.")

    if below or no_hit or no_stats:
        print("\nNon-matches for review:")
        for name, query, status in results:
            if not status.startswith("OK"):
                print(f"  {name!r:58} {status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--missing-images", action="store_true",
                    help="Only wines with image_url IS NULL (targets HEB/CM catalog)")
    ap.add_argument("--backfill-facts", action="store_true",
                    help="Re-fetch pages for already-matched wines (score >= 0.7) "
                         "to fill facts/images added after their original enrichment")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
