"""
Base scraper interface. Every retailer scraper inherits from BaseScraper.

Each scraper is responsible for:
  1. Fetching product pages via Playwright
  2. Parsing HTML into RetailInventoryItem dataclasses
  3. Upserting results to Supabase and logging the run to scraper_runs
"""
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from postgrest.exceptions import APIError

from db import get_service_client
from utils.geo import zip_to_centroid

# Transient Postgres errors from two writers touching the same rows at once —
# 40P01 deadlock_detected, 40001 serialization_failure. Retryable: the loser
# aborts, the winner commits, and a retry almost always clears. This surfaced
# when Spec's moved to the mini (Sun 10:00 UTC) and overlapped the still-running
# GitHub weekly scrape, both upserting overlapping wines on `upc_canonical`.
_RETRYABLE_PG_CODES = {"40P01", "40001"}


def _execute_with_retry(query, retries: int = 4, base_delay: float = 0.5):
    """Execute a supabase query, retrying transient deadlock/serialization
    failures with exponential backoff. Non-retryable errors propagate at once."""
    for attempt in range(retries):
        try:
            return query.execute()
        except APIError as e:
            if getattr(e, "code", None) in _RETRYABLE_PG_CODES and attempt < retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise


@dataclass
class RetailInventoryItem:
    wine_name: str
    retailer_name: str
    zip_code: str
    upc: Optional[str] = None
    price: Optional[float] = None
    store_name: Optional[str] = None
    store_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    in_stock: bool = True
    varietal: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None


class BaseScraper(ABC):
    def __init__(self):
        self.supabase = get_service_client()

    @abstractmethod
    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """Return all available wines at stores near zip_code."""
        ...

    @abstractmethod
    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        """Search for a specific wine at stores near zip_code."""
        ...

    def _upsert_wines(self, items: List[RetailInventoryItem]) -> dict:
        """
        Upsert wine catalog records, deduplicated by canonical UPC so the same
        physical wine from different retailers collapses to one row.
        Returns a {raw_upc -> wine_id} mapping for inventory linking.
        """
        from utils import infer_wine_type
        from utils.upc import canonical_upc

        # Dedup by the CONFLICT KEY (upc_canonical), not raw upc — two different
        # raw UPCs can normalize to the same canonical and would otherwise raise
        # 'ON CONFLICT DO UPDATE command cannot affect row a second time'.
        # Keep-last: the later occurrence's fields win.
        by_canon = {}
        for item in items:
            if not item.wine_name:
                continue
            canon = canonical_upc(item.upc)
            record = {k: v for k, v in {
                "upc": item.upc,
                "upc_canonical": canon,
                "name": item.wine_name,
                "brand": item.brand,
                "varietal": item.varietal,
                "wine_type": infer_wine_type(item.varietal or item.wine_name),
                "avg_price": item.price,
                "image_url": item.image_url,
            }.items() if v is not None}
            by_canon[canon] = record
        records = list(by_canon.values())

        if records:
            _execute_with_retry(self.supabase.table("wines").upsert(records, on_conflict="upc_canonical"))

        # Build {raw_upc -> wine_id}. retail_inventory stores the RAW upc, so we map
        # each item's raw upc through its canonical to the resulting wine_id.
        canons = [r["upc_canonical"] for r in records if r.get("upc_canonical")]
        if not canons:
            return {}
        result = self.supabase.table("wines").select("id,upc_canonical").in_("upc_canonical", canons).execute()
        canon_to_id = {w["upc_canonical"]: w["id"] for w in result.data if w.get("upc_canonical")}
        mapping = {}
        for item in items:
            if not item.upc:
                continue
            wid = canon_to_id.get(canonical_upc(item.upc))
            if wid:
                mapping[item.upc] = wid
        return mapping

    def _upsert_stores(self, items: List[RetailInventoryItem]) -> dict:
        """Upsert the distinct stores in this batch; return {(retailer_name, store_id): store_uuid}."""
        seen = {}
        for item in items:
            key = (item.retailer_name, item.store_id)
            if item.retailer_name and item.store_id and key not in seen:
                coords = zip_to_centroid(item.zip_code) if item.zip_code else None
                seen[key] = {k: v for k, v in {
                    "retailer_name": item.retailer_name,
                    "store_id": item.store_id,
                    "name": item.store_name,
                    "address": item.address,
                    "city": item.city,
                    "state": item.state,
                    "zip_code": item.zip_code,
                    "latitude": coords[0] if coords else None,
                    "longitude": coords[1] if coords else None,
                }.items() if v is not None}
        if not seen:
            return {}
        _execute_with_retry(self.supabase.table("stores").upsert(
            list(seen.values()), on_conflict="retailer_name,store_id"
        ))
        store_ids = [k[1] for k in seen]
        result = (
            self.supabase.table("stores")
            .select("id,retailer_name,store_id")
            .in_("store_id", store_ids)
            .execute()
        )
        return {(s["retailer_name"], s["store_id"]): s["id"] for s in result.data}

    def _upsert_inventory(self, items: List[RetailInventoryItem], upc_to_id: dict):
        """Upsert slim retail inventory rows referencing a store_ref."""
        store_map = self._upsert_stores(items)
        now = datetime.now(timezone.utc).isoformat()
        # Dedup by CONFLICT KEY (upc, store_ref) — same raw UPC listed twice for
        # one store would otherwise raise 'affect row a second time'. Keep-last.
        by_key = {}
        for item in items:
            store_ref = store_map.get((item.retailer_name, item.store_id))
            if not store_ref or not item.upc:
                continue
            record = {k: v for k, v in {
                "wine_id": upc_to_id.get(item.upc),
                "upc": item.upc,
                "store_ref": store_ref,
                "price": item.price,
                "in_stock": item.in_stock,
                "last_scraped_at": now,
            }.items() if v is not None}
            by_key[(item.upc, store_ref)] = record
        records = list(by_key.values())
        if records:
            _execute_with_retry(self.supabase.table("retail_inventory").upsert(
                records, on_conflict="upc,store_ref"
            ))

    async def run(self, zip_codes: List[str]) -> int:
        """
        Run the scraper across all zip codes, upsert results, log to scraper_runs.
        Returns total inventory records written.
        """
        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id,
            "retailer_name": self.__class__.__name__,
            "status": "running",
        }).execute()

        total = 0
        try:
            for zip_code in zip_codes:
                items = await self.search_by_zip(zip_code)
                upc_to_id = self._upsert_wines(items)
                self._upsert_inventory(items, upc_to_id)
                total += len(items)

            self.supabase.table("scraper_runs").update({
                "status": "success",
                "records_updated": total,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise

        return total
