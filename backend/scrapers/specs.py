"""
Spec's Wines, Spirits & Finer Foods — wine scraper.

Uses the internal REST API at specsonline.com/api/search/ — no auth, no cookies,
no browser needed. Wine-only filtering via facets at the API level.

API reference: data/exploration/specs_findings.md
"""
import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type

SEARCH_URL = "https://specsonline.com/api/search/"
STORE_API_URL = "https://specsonline.com/api/store/number/{}/"
RETAILER_NAME = "Spec's"
PAGE_SIZE = 96

# Store numbers discovered via probe (see data/exploration/specs_findings.md).
# Spec's is statewide (188 stores); we scrape curated per-metro sets near
# tester zips. Store address (city/zip) is fetched per store from the API,
# so no code change is needed to add a store — just its number here.
SA_STORE_NUMBERS = [69, 72, 98, 100, 110, 113, 114, 117, 169, 171, 194, 197]
# Central Austin (near 78701) — Highland, 35th St, North Lamar, Arbor Walk
AUSTIN_STORE_NUMBERS = [60, 224, 11, 62]
# Central Dallas (near 75201) — Northwest Hwy, Superstore, Preston Ctr, Marsh Ln
DALLAS_STORE_NUMBERS = [115, 150, 152, 156]

_CURL_HEADERS = [
    "-H", "Content-Type: application/json",
    "-H", "Referer: https://specsonline.com/shop/wine/",
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class SpecsProduct:
    upc: str
    name: str
    brand: Optional[str]
    size: Optional[str]
    category_group: Optional[str]
    description: Optional[str]
    shelf_price: Optional[float]        # unitPrice / 100 (always the base price)
    sale_price: Optional[float]         # unitPricePromoDiscount / 100 (None if no promo)
    price: Optional[float]              # effective price: sale_price if available else shelf_price
    in_stock: bool
    image_url: Optional[str]            # details.image CDN URL


def _parse_product(raw: dict) -> Optional[SpecsProduct]:
    """Parse one product dict from the /api/search/ response. Returns None for non-wine or missing UPC."""
    details = raw.get("details") or {}
    if details.get("type", "").lower() != "wine":
        return None

    attrs = details.get("attributes") or {}
    upc = attrs.get("upc")
    if not upc:
        return None

    pricing = raw.get("pricing") or {}
    unit_cents = pricing.get("unitPrice")
    promo_cents = pricing.get("unitPricePromoDiscount")   # DISCOUNT AMOUNT (cents off), not the sale price

    shelf = unit_cents / 100 if unit_cents is not None else None
    # sale = shelf - discount. promo_cents is how much is taken OFF, not the
    # final price (a $15.78 wine with a 318 promo sells for $12.60, not $3.18).
    sale = None
    if unit_cents is not None and promo_cents:
        sale = max(0, unit_cents - promo_cents) / 100
    effective = sale if sale is not None else shelf

    raw_desc = details.get("description", "")
    description = raw_desc.strip() if raw_desc and raw_desc.strip() else None

    raw_image = details.get("image")
    image_url = raw_image.strip() if raw_image and raw_image.strip() else None

    return SpecsProduct(
        upc=upc,
        name=details.get("title", ""),
        brand=attrs.get("brand"),
        size=attrs.get("size"),
        category_group=attrs.get("categoryGroup"),
        description=description,
        shelf_price=shelf,
        sale_price=sale,
        price=effective,
        in_stock=raw.get("stock", {}).get("inStock", False),
        image_url=image_url,
    )


def _parse_store_detail(data: dict, store_number: int) -> dict:
    """Extract {name, address, city, zip} from a /api/store/number/N/ response."""
    addr = data.get("address") or {}
    street = ", ".join(s for s in (addr.get("street"), addr.get("street2")) if s) or None
    return {
        "name": data.get("name") or f"Spec's Store {store_number}",
        "address": street,
        "city": addr.get("city") or "San Antonio",
        "zip": addr.get("postcode") or "78209",
    }


def _fetch_wine_page(store_number: int, page: int, page_size: int = PAGE_SIZE) -> dict:
    """POST to /api/search/ for one page of wines at a given store. Returns raw API response dict."""
    body = json.dumps({
        "userQuery": "",
        "orderBy": "popularity",
        "storeNumber": store_number,
        "page": page,
        "pageSize": page_size,
        "facets": {"category.keyword": "[\"Wine\"]"},
    })
    cmd = (
        ["curl", "-s", "-X", "POST", "--max-time", "30"]
        + _CURL_HEADERS
        + ["-d", body, SEARCH_URL]
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


class SpecsScraper(BaseScraper):
    """
    Scraper for Spec's Wines, Spirits & Finer Foods (specsonline.com).
    Queries the internal /api/search/ REST endpoint — no auth, no browser.
    Iterates all 12 San Antonio stores.
    """

    def _products_to_inventory_items(
        self,
        products: List[SpecsProduct],
        store_number: int,
        store_name: str,
        store_zip: str = "78209",
        store_city: str = "San Antonio",
        store_address: Optional[str] = None,
    ) -> List[RetailInventoryItem]:
        items = []
        for p in products:
            if p.price is None:
                continue
            items.append(RetailInventoryItem(
                wine_name=p.name,
                retailer_name=RETAILER_NAME,
                store_id=str(store_number),
                store_name=store_name,
                upc=p.upc,
                price=p.price,
                in_stock=p.in_stock,
                varietal=p.category_group,
                brand=p.brand,
                image_url=p.image_url,
                address=store_address,
                zip_code=store_zip,   # per-store; geocoded by BaseScraper._upsert_stores
                city=store_city,
                state="TX",
            ))
        return items

    def _upsert_wine_details(self, products: List[SpecsProduct], upc_to_id: dict):
        """Write Spec's product descriptions into wine_details for wines that have them (~77%)."""
        records = []
        for p in products:
            wine_id = upc_to_id.get(p.upc) if p.upc else None
            if not wine_id or not p.description:
                continue
            records.append({
                "wine_id": wine_id,
                "description": p.description,
                "source": "scraped_specs",
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            })
        if records:
            self.supabase.table("wine_details").upsert(
                records, on_conflict="wine_id"
            ).execute()

    def _fetch_store_detail(self, store_number: int) -> dict:
        """GET /api/store/number/N/ → {name, city, zip}. Falls back to SA on error."""
        cmd = [
            "curl", "-s", "--max-time", "10",
            "-H", "User-Agent: Mozilla/5.0",
            "-H", "Accept: application/json",
            STORE_API_URL.format(store_number),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return _parse_store_detail(json.loads(result.stdout), store_number)
        except Exception:
            return {"name": f"Spec's Store {store_number}", "address": None,
                    "city": "San Antonio", "zip": "78209"}

    async def run_full(self, store_numbers: Optional[List[int]] = None) -> dict:
        """
        Full scrape: iterate the given store numbers × all pages (default SA).
        Per-store address is fetched from the API so Austin/Dallas stores
        geocode correctly. Commits each page immediately.
        """
        import time

        stores = store_numbers if store_numbers is not None else SA_STORE_NUMBERS

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id,
            "retailer_name": RETAILER_NAME,
            "status": "running",
        }).execute()

        total_committed = 0

        try:
            for store_number in stores:
                detail = self._fetch_store_detail(store_number)
                store_name, store_zip, store_city = detail["name"], detail["zip"], detail["city"]
                store_address = detail["address"]
                print(f"\n  Store {store_number} — {store_name} ({store_city} {store_zip})")

                page = 1
                total_pages = None

                while total_pages is None or page <= total_pages:
                    try:
                        resp = _fetch_wine_page(store_number=store_number, page=page)
                    except Exception as e:
                        print(f"    page {page}: fetch error — {e}")
                        break

                    if total_pages is None:
                        try:
                            total_pages = int(resp.get("totalPages", 1))
                        except (ValueError, TypeError):
                            total_pages = 1

                    raw_products = resp.get("products") or []
                    products = [p for raw in raw_products if (p := _parse_product(raw))]

                    if products:
                        items = self._products_to_inventory_items(
                            products, store_number=store_number, store_name=store_name,
                            store_zip=store_zip, store_city=store_city,
                            store_address=store_address,
                        )
                        upc_to_id = self._upsert_wines(items)
                        self._upsert_inventory(items, upc_to_id)
                        self._upsert_wine_details(products, upc_to_id)
                        total_committed += len(products)
                        print(f"    page {page}/{total_pages}: {len(products)} wines committed (total: {total_committed})")

                    page += 1
                    time.sleep(0.5)   # polite rate limit

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

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """Not used for full scraping — exists to satisfy BaseScraper ABC."""
        return []

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        """Not used for full scraping — exists to satisfy BaseScraper ABC."""
        return []
