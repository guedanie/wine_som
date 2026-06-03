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
        Upsert wine catalog records from scraper results.
        Returns a upc -> wine_id mapping for use in inventory upsert.
        """
        from utils import infer_wine_type

        seen = set()
        records = []
        for item in items:
            if not item.wine_name or (item.upc and item.upc in seen):
                continue
            if item.upc:
                seen.add(item.upc)
            record = {k: v for k, v in {
                "upc": item.upc,
                "name": item.wine_name,
                "brand": item.brand,
                "varietal": item.varietal,
                "wine_type": infer_wine_type(item.varietal or item.wine_name),
            }.items() if v is not None}
            records.append(record)

        if records:
            self.supabase.table("wines").upsert(records, on_conflict="upc").execute()

        # Return upc -> id map for inventory linking
        result = self.supabase.table("wines").select("id,upc").execute()
        return {w["upc"]: w["id"] for w in result.data if w["upc"]}

    def _upsert_inventory(self, items: List[RetailInventoryItem], upc_to_id: dict):
        """Upsert retail inventory records, linking to wine IDs where known."""
        now = datetime.now(timezone.utc).isoformat()
        records = []
        for item in items:
            wine_id = upc_to_id.get(item.upc) if item.upc else None
            record = {k: v for k, v in {
                "wine_id": wine_id,
                "upc": item.upc,
                "retailer_name": item.retailer_name,
                "store_id": item.store_id,
                "store_name": item.store_name,
                "address": item.address,
                "city": item.city,
                "state": item.state,
                "zip_code": item.zip_code,
                "price": item.price,
                "in_stock": item.in_stock,
                "last_scraped_at": now,
            }.items() if v is not None}
            records.append(record)

        if records:
            self.supabase.table("retail_inventory").upsert(
                records, on_conflict="upc,store_id"
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
