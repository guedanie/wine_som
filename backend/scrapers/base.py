"""
Base scraper interface. Every retailer scraper inherits from BaseScraper.

Each scraper is responsible for:
  1. Fetching product pages via Playwright
  2. Parsing HTML into RetailInventoryItem dataclasses
  3. Upserting results to Supabase and logging the run to scraper_runs
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from db import get_service_client
from utils.geo import zip_to_centroid


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

        seen = set()
        records = []
        for item in items:
            if not item.wine_name or (item.upc and item.upc in seen):
                continue
            if item.upc:
                seen.add(item.upc)
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
            records.append(record)

        if records:
            self.supabase.table("wines").upsert(records, on_conflict="upc_canonical").execute()

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
        self.supabase.table("stores").upsert(
            list(seen.values()), on_conflict="retailer_name,store_id"
        ).execute()
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
        records = []
        for item in items:
            store_ref = store_map.get((item.retailer_name, item.store_id))
            if not store_ref:
                continue
            records.append({k: v for k, v in {
                "wine_id": upc_to_id.get(item.upc) if item.upc else None,
                "upc": item.upc,
                "store_ref": store_ref,
                "price": item.price,
                "in_stock": item.in_stock,
                "last_scraped_at": now,
            }.items() if v is not None})
        if records:
            self.supabase.table("retail_inventory").upsert(
                records, on_conflict="upc,store_ref"
            ).execute()

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
