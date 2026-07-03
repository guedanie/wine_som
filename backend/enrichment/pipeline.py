"""
Enrichment pipeline orchestrator.

Flow per wine:
  1. Search GrapeMinds by wine name → get grapeminds_id
  2. Fetch /wines/{id} → may return nulls on first call (content generating async)
  3. Persist whatever we got (partial is OK — marks needs_refetch=True)
  4. If needs_refetch: sleep 60s, fetch again, persist final result
  5. Also fetch /drinking-periods/{id} after the second pass

Never re-enriches a wine with grapeminds_enriched_at already set unless forced.
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timezone

from db import get_service_client
from enrichment.grapeminds import GrapeMindsClient, GrapeMindsWine, DrinkingPeriod
from enrichment.matching.scorer import score_candidates
from config import settings

# Below this primary-match confidence we store the candidates but skip the
# (budget-spending) detail fetch — eval showed precision drops sharply under 0.80.
MIN_ENRICH_CONFIDENCE = 0.80


@dataclass
class EnrichmentResult:
    wine_id: str
    grapeminds_id: Optional[str] = None
    description: Optional[str] = None
    description_long: Optional[str] = None
    tasting_notes: Optional[str] = None
    tasting_notes_long: Optional[str] = None
    pairing: Optional[str] = None
    pairing_long: Optional[str] = None
    structure_profile: dict = field(default_factory=dict)
    flavor_profile: List[str] = field(default_factory=list)
    drinking_window_start: Optional[int] = None
    drinking_window_end: Optional[int] = None
    drinking_window_young: Optional[str] = None
    drinking_window_ripe: Optional[str] = None
    drinking_window_storage: Optional[str] = None
    source: str = "grapeminds"
    needs_refetch: bool = False
    match_confidence: Optional[float] = None
    region: Optional[str] = None
    region_country: Optional[str] = None


def _result_from_wine_data(
    wine_id: str,
    gm_wine: GrapeMindsWine,
    drinking: Optional[DrinkingPeriod] = None,
) -> EnrichmentResult:
    result = EnrichmentResult(
        wine_id=wine_id,
        grapeminds_id=gm_wine.grapeminds_id,
        description=gm_wine.description,
        description_long=gm_wine.description_long,
        tasting_notes=gm_wine.tasting_notes,
        tasting_notes_long=gm_wine.tasting_notes_long,
        pairing=gm_wine.pairing,
        pairing_long=gm_wine.pairing_long,
        structure_profile=gm_wine.structure_profile,
        flavor_profile=gm_wine.grapes,  # grapes as flavor tags until Vivino/Apify added
        needs_refetch=not gm_wine.is_fully_enriched,
        source="grapeminds",
        region=gm_wine.region_name,
        region_country=gm_wine.region_country,
    )
    if drinking:
        result.drinking_window_start = drinking.from_year
        result.drinking_window_end = drinking.to_year
        result.drinking_window_young = drinking.young
        result.drinking_window_ripe = drinking.ripe
        result.drinking_window_storage = drinking.storage
    return result


def _persist(result: EnrichmentResult, final: bool = False):
    """Upsert enrichment result to wine_details table."""
    client = get_service_client()
    now = datetime.now(timezone.utc).isoformat()
    # Retail scrapers own `description`/`description_long` (the product page text);
    # GrapeMinds contributes only the structured fields below, so its upsert must
    # NOT include the description columns or it would clobber the retailer's text.
    record = {k: v for k, v in {
        "wine_id": result.wine_id,
        "grapeminds_id": result.grapeminds_id,
        "tasting_notes": result.tasting_notes,
        "tasting_notes_long": result.tasting_notes_long,
        "pairing": result.pairing,
        "pairing_long": result.pairing_long,
        "structure_profile": result.structure_profile or None,
        "flavor_profile": result.flavor_profile or None,
        "drinking_window_start": result.drinking_window_start,
        "drinking_window_end": result.drinking_window_end,
        "drinking_window_young": result.drinking_window_young,
        "drinking_window_ripe": result.drinking_window_ripe,
        "drinking_window_storage": result.drinking_window_storage,
        "source": result.source,
        "match_confidence": result.match_confidence,
        "grapeminds_enriched_at": now if final else None,
        "enriched_at": now if final else None,
    }.items() if v is not None}

    client.table("wine_details").upsert(record, on_conflict="wine_id").execute()

    # Backfill GrapeMinds region/country onto the wines row (only where still empty —
    # don't overwrite a scraped region). Scrapers leave these null, so this fills the gap.
    if final and result.region:
        wine_update = {k: v for k, v in {
            "region": result.region,
            "country": result.region_country,
        }.items() if v is not None}
        if wine_update:
            client.table("wines").update(wine_update).eq(
                "id", result.wine_id
            ).is_("region", "null").execute()


def persist_candidates(wine_id: str, candidates: list):
    """Upsert this wine's GrapeMinds candidate rows (atomic — no DELETE+INSERT)."""
    if not candidates:
        return
    client = get_service_client()
    now = datetime.now(timezone.utc).isoformat()
    records = [{
        "wine_id": wine_id,
        "grapeminds_id": c["grapeminds_id"],
        "display_name": c.get("display_name"),
        "producer_name": c.get("producer_name"),
        "color": c.get("color"),
        "confidence": c.get("confidence"),
        "rank": c.get("rank"),
        "is_primary": c.get("is_primary", False),
        "matched_at": now,
    } for c in candidates]
    client.table("wine_grapeminds_matches").upsert(
        records, on_conflict="wine_id,grapeminds_id"
    ).execute()


def is_already_enriched(wine_id: str) -> bool:
    """Return True if wine already has a completed GrapeMinds enrichment.

    Uses limit(1) rather than maybe_single(): supabase-py's maybe_single returns
    None from execute() when there is no row, which crashes on `.data`. Many wines
    have no wine_details row yet (no scraped description), so this must be robust.
    """
    client = get_service_client()
    result = (
        client.table("wine_details")
        .select("grapeminds_enriched_at")
        .eq("wine_id", wine_id)
        .limit(1)
        .execute()
    )
    rows = (result.data if result else None) or []
    return bool(rows and rows[0].get("grapeminds_enriched_at"))


async def enrich_wine(wine_row: dict, force: bool = False) -> EnrichmentResult:
    """
    Enrich a single wine row from the wines table.

    wine_row must have: id, name (varietal and region are optional but help matching).
    force=True bypasses the already-enriched check.
    """
    wine_id = wine_row["id"]
    wine_name = wine_row.get("name", "")

    if not force and is_already_enriched(wine_id):
        return EnrichmentResult(wine_id=wine_id, source="cached", needs_refetch=False)

    gm = GrapeMindsClient(api_key=settings.grapeminds_api_key)

    # ── Step 1: Search, score, and persist top-3 candidates ───────────────────
    hits = gm.search(wine_name, limit=5)
    if not hits:
        return EnrichmentResult(wine_id=wine_id, source="not_found", needs_refetch=False)

    candidates = score_candidates(
        hits,
        brand=wine_row.get("brand"),
        wine_type=wine_row.get("wine_type"),
        name=wine_name,
    )
    persist_candidates(wine_id, candidates)
    primary = candidates[0]
    primary_confidence = primary["confidence"]

    # ── Confidence gate: weak match → keep candidates, skip enrichment ────────
    if primary_confidence < MIN_ENRICH_CONFIDENCE:
        return EnrichmentResult(
            wine_id=wine_id,
            source="low_confidence",
            match_confidence=primary_confidence,
            needs_refetch=False,
        )

    gm_id = int(primary["grapeminds_id"])

    # ── Step 2: First fetch — triggers async content generation ───────────────
    gm_wine = gm.get_wine(gm_id)
    if not gm_wine:
        return EnrichmentResult(wine_id=wine_id, source="error", needs_refetch=False)

    drinking = gm.get_drinking_period(gm_id)
    result = _result_from_wine_data(wine_id, gm_wine, drinking)
    result.match_confidence = primary_confidence

    if result.needs_refetch:
        # Content is generating async — persist partial, return with flag
        _persist(result, final=False)
        return result

    # ── Step 3: Content came back fully on first fetch — persist and done ─────
    _persist(result, final=True)
    return result


async def enrich_wine_with_refetch(wine_row: dict, refetch_delay: int = 60) -> EnrichmentResult:
    """
    Full two-step warm-up enrichment.
    If first fetch returns nulls, waits refetch_delay seconds and tries again.
    """
    result = await enrich_wine(wine_row)

    if not result.needs_refetch:
        return result

    # GrapeMinds is generating content — wait and re-fetch
    await asyncio.sleep(refetch_delay)

    gm = GrapeMindsClient(api_key=settings.grapeminds_api_key)
    gm_id = int(result.grapeminds_id)

    gm_wine = gm.get_wine(gm_id)
    drinking = gm.get_drinking_period(gm_id)

    if gm_wine:
        result = _result_from_wine_data(wine_row["id"], gm_wine, drinking)
        _persist(result, final=True)

    return result


async def enrich_batch(wine_rows: List[dict], refetch_delay: int = 60) -> dict:
    """
    Enrich a list of wines. Returns a summary dict.
    Processes sequentially to stay within GrapeMinds rate limits (60 req/min).
    """
    enriched, skipped, failed = 0, 0, 0

    for wine_row in wine_rows:
        try:
            result = await enrich_wine(wine_row)
            if result.source == "cached":
                skipped += 1
            elif result.source in ("not_found", "error"):
                failed += 1
            else:
                enriched += 1
                # Throttle to ~1 req/sec to respect rate limits
                await asyncio.sleep(1.5)
        except Exception as e:
            failed += 1
            print(f"  Error enriching {wine_row.get('name')}: {e}")

    # Re-fetch wines that needed a warm-up pass
    needs_refetch = (
        get_service_client()
        .table("wine_details")
        .select("wine_id, wines(id, name, varietal, region)")
        .is_("grapeminds_enriched_at", "null")
        .not_.is_("grapeminds_id", "null")
        .execute()
    )

    if needs_refetch.data:
        await asyncio.sleep(refetch_delay)
        for row in needs_refetch.data:
            wine = row.get("wines") or {}
            if wine.get("id"):
                try:
                    gm = GrapeMindsClient(api_key=settings.grapeminds_api_key)
                    gm_id = int(row.get("grapeminds_id") or 0)
                    if gm_id:
                        gm_wine = gm.get_wine(gm_id)
                        drinking = gm.get_drinking_period(gm_id)
                        if gm_wine:
                            result = _result_from_wine_data(wine["id"], gm_wine, drinking)
                            _persist(result, final=True)
                    await asyncio.sleep(1.5)
                except Exception:
                    pass

    return {
        "enriched": enriched,
        "skipped_cached": skipped,
        "failed": failed,
        "refetch_pass": len(needs_refetch.data) if needs_refetch.data else 0,
    }
