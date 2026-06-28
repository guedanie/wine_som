"""
Central Market wine scraper — same HEB GraphQL endpoint, different client name.

Central Market is HEB-owned and shares the same Apollo GraphQL backend at
heb.com/graphql. The only differences are:
  - Apollographql-Client-Name: central-market
  - Origin/Referer: centralmarket.com
  - retailer_name: "Central Market"

Parsing, pagination, and upsert logic are identical to the HEB scraper.
"""
from typing import Optional, List, Dict

from scrapers.heb import (
    GRAPHQL_URL,
    HEBProduct,
    _parse_record,
    _PRODUCT_FIELDS,
    fetch_wine_page as _heb_fetch_wine_page,
    HebScraper,
)
from scrapers.base import BaseScraper, RetailInventoryItem

RETAILER_NAME = "Central Market"

# Austin CM stores confirmed working via GraphQL probe (store 191 SA returns []).
CM_STORES: Dict[str, Dict[str, str]] = {
    "61":  {"name": "Central Market North Lamar", "address": "4001 North Lamar",   "zip": "78756", "city": "Austin", "state": "TX"},
    "420": {"name": "Central Market Westgate",    "address": "4477 S. Lamar Blvd", "zip": "78745", "city": "Austin", "state": "TX"},
}

# Override headers for the Central Market client
_CM_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 Mobile/15E148",
    "Apollographql-Client-Name": "central-market",
    "Origin": "https://www.centralmarket.com",
    "Referer": "https://www.centralmarket.com/",
}


def fetch_cm_wine_page(offset: int = 0, limit: int = 60, store_id: str = "61"):
    """Fetch one page of CM wine products using the central-market client name."""
    import json
    import urllib.request
    import urllib.error
    import time

    query = (
        "{ productSearch(shoppingContext: CURBSIDE_PICKUP, query: \"wine\", "
        f"storeId: {store_id}, limit: {limit}, offset: {offset}) "
        f"{{ total records {{ {_PRODUCT_FIELDS} }} }} }}"
    )
    body = json.dumps({"query": query}).encode("utf-8")
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(GRAPHQL_URL, data=body, headers=_CM_HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            ps = (data.get("data") or {}).get("productSearch") or {}
            total = ps.get("total") or 0
            products = [p for raw in (ps.get("records") or []) if (p := _parse_record(raw))]
            return total, products
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise last_err


class CentralMarketScraper(HebScraper):
    """Central Market scraper — inherits HEB upsert/parsing, uses CM store list."""

    async def run_full(self, city: Optional[str] = None, store_ids: Optional[List[str]] = None) -> dict:
        import uuid
        import time
        from datetime import datetime, timezone

        stores = {
            k: v for k, v in CM_STORES.items()
            if (city is None or v["city"] == city)
            and (store_ids is None or k in store_ids)
        }

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total_committed = 0
        page_size = 60

        try:
            for store_id, store_info in stores.items():
                store_name    = store_info["name"]
                store_zip     = store_info["zip"]
                store_address = store_info["address"]
                store_city    = store_info["city"]
                store_state   = store_info["state"]
                print(f"\n  Store {store_id} — {store_name} ({store_city})")

                offset = 0
                server_total = None

                for _ in range(60):
                    page_total, products = fetch_cm_wine_page(offset=offset, limit=page_size, store_id=store_id)
                    if server_total is None:
                        server_total = page_total
                    if products:
                        upc_to_id = self._upsert_inventory_with_curbside(
                            products, store_id, store_name, store_zip, store_address,
                            city=store_city, state=store_state,
                            retailer_name=RETAILER_NAME,
                        )
                        self._upsert_wine_details(products, upc_to_id)
                        total_committed += len(products)
                        print(f"    offset {offset}: {len(products)} wines (total: {total_committed})")
                    offset += page_size
                    if server_total is not None and offset >= server_total:
                        break
                    time.sleep(0.3)

            self.supabase.table("scraper_runs").update({
                "status": "success",
                "records_updated": total_committed,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

            return {"wines_committed": total_committed, "stores": len(stores)}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
