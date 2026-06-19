# Spec's Wine Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape wine inventory from all 12 San Antonio Spec's stores via their internal REST API and seed wines + inventory into the database.

**Architecture:** Pure-curl `POST /api/search/` with `{"facets":{"category.keyword":"[\"Wine\"]"}}` filters wine-only at the API level. `SpecsScraper(BaseScraper)` follows the same structure as `heb.py` — per-store pagination, per-page commit, `scraper_runs` logging. 77% of products include descriptions; the other 23% fall back to Haiku extraction.

**Tech Stack:** `subprocess curl` (no new deps), `BaseScraper` + `RetailInventoryItem` from `scrapers/base.py`, Supabase.

---

## Reference

- **Probe findings:** `data/exploration/specs_findings.md` — full API shape, store numbers, field docs
- **Pattern to follow:** `backend/scrapers/heb.py` + `backend/tests/test_heb.py`
- **API endpoint:** `POST https://specsonline.com/api/search/` (trailing slash required — without it returns 308)

## File Map

| Action | File | Purpose |
|---|---|---|
| Create | `backend/scrapers/specs.py` | Full scraper: constants, `SpecsProduct` dataclass, parser, HTTP fetch, `SpecsScraper` class |
| Create | `backend/tests/test_specs.py` | Unit tests with mocked HTTP responses |

---

## Task 1: SpecsProduct dataclass and parser (TDD)

**Files:**
- Create: `backend/scrapers/specs.py`
- Create: `backend/tests/test_specs.py`

- [ ] **Step 1: Create the test file with failing parser tests**

Create `backend/tests/test_specs.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.specs import _parse_product, SpecsProduct


def _raw_product(**overrides):
    base = {
        "code": "100-081883800770",
        "details": {
            "description": "Crisp and dry with notes of green apple and citrus.",
            "title": "Stonegate Sauvignon Blanc",
            "type": "wine",
            "attributes": {
                "sku": "125681",
                "upc": "081883800770",
                "brand": "STONEGATE",
                "size": "750ML",
                "classid": 990,
                "category": "Wine",
                "categoryGroup": "Sauvignon Blanc",
                "subcategory": "California Wines",
            },
            "image": "https://cdn.specsonline.com/images/products/081883800770.jpg",
        },
        "url": "/shop/wine/stonegate-sauvignon-blanc/",
        "pricing": {
            "unitPrice": 1262,
            "unitPricePromoDiscount": 965,
            "casePrice": None,
            "caseQuantity": None,
            "casePricePromoDiscount": None,
            "casePriceKeyclubDiscount": None,
            "unitPriceKeyclubDiscount": None,
        },
        "stock": {"inStock": True, "details": None},
    }
    for k, v in overrides.items():
        if "." in k:
            parts = k.split(".", 1)
            base[parts[0]][parts[1]] = v
        else:
            base[k] = v
    return base


def test_parse_product_full():
    p = _parse_product(_raw_product())
    assert isinstance(p, SpecsProduct)
    assert p.upc == "081883800770"
    assert p.name == "Stonegate Sauvignon Blanc"
    assert p.brand == "STONEGATE"
    assert p.size == "750ML"
    assert p.category_group == "Sauvignon Blanc"
    assert p.description == "Crisp and dry with notes of green apple and citrus."
    assert p.price == 9.65           # promo price used when available
    assert p.sale_price == 9.65
    assert p.shelf_price == 12.62
    assert p.in_stock is True


def test_parse_product_no_promo_uses_shelf_price():
    raw = _raw_product()
    raw["pricing"]["unitPricePromoDiscount"] = None
    p = _parse_product(raw)
    assert p.price == 12.62
    assert p.sale_price is None
    assert p.shelf_price == 12.62


def test_parse_product_empty_description_returns_none():
    raw = _raw_product()
    raw["details"]["description"] = ""
    p = _parse_product(raw)
    assert p.description is None


def test_parse_product_no_upc_returns_none():
    raw = _raw_product()
    raw["details"]["attributes"]["upc"] = None
    assert _parse_product(raw) is None


def test_parse_product_non_wine_type_returns_none():
    raw = _raw_product()
    raw["details"]["type"] = "spirits"
    assert _parse_product(raw) is None


def test_parse_product_out_of_stock():
    raw = _raw_product()
    raw["stock"]["inStock"] = False
    p = _parse_product(raw)
    assert p.in_stock is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /path/to/wine_app/backend
python3 -m pytest tests/test_specs.py -v
```

Expected: `ModuleNotFoundError: No module named 'scrapers.specs'`

- [ ] **Step 3: Create `backend/scrapers/specs.py` with dataclass and parser**

```python
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

# SA store numbers discovered via probe (see data/exploration/specs_findings.md)
# Excludes Kerrville (74) and Boerne (207) — Hill Country, not SA proper
SA_STORE_NUMBERS = [69, 72, 98, 100, 110, 113, 114, 117, 169, 171, 194, 197]

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


def _parse_product(raw: dict) -> Optional["SpecsProduct"]:
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
    promo_cents = pricing.get("unitPricePromoDiscount")

    shelf = unit_cents / 100 if unit_cents is not None else None
    sale = promo_cents / 100 if promo_cents is not None else None
    effective = sale if sale is not None else shelf

    raw_desc = details.get("description", "")
    description = raw_desc.strip() if raw_desc and raw_desc.strip() else None

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
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python3 -m pytest tests/test_specs.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/specs.py backend/tests/test_specs.py
git commit -m "feat: SpecsProduct dataclass + _parse_product (TDD)"
```

---

## Task 2: HTTP fetch layer (TDD)

**Files:**
- Modify: `backend/scrapers/specs.py`
- Modify: `backend/tests/test_specs.py`

- [ ] **Step 1: Write failing tests for _fetch_wine_page**

Append to `backend/tests/test_specs.py`:

```python
from unittest.mock import patch, MagicMock
from scrapers.specs import _fetch_wine_page


def _make_search_response(products=None, total=1, pages=1):
    return json.dumps({
        "totalProducts": total,
        "currentPage": "1",
        "totalPages": pages,
        "productsPerPage": 96,
        "products": products or [],
    })


def test_fetch_wine_page_returns_parsed_response():
    fake_response = _make_search_response(products=[_raw_product()], total=1, pages=1)
    mock_result = MagicMock()
    mock_result.stdout = fake_response
    mock_result.returncode = 0

    with patch("scrapers.specs.subprocess.run", return_value=mock_result):
        result = _fetch_wine_page(store_number=100, page=1)

    assert result["totalProducts"] == 1
    assert len(result["products"]) == 1


def test_fetch_wine_page_sends_correct_store_and_page():
    captured = {}
    fake_response = _make_search_response()
    mock_result = MagicMock(stdout=fake_response, returncode=0)

    def capture_call(cmd, **kwargs):
        captured["cmd"] = cmd
        return mock_result

    with patch("scrapers.specs.subprocess.run", side_effect=capture_call):
        _fetch_wine_page(store_number=113, page=3)

    cmd_str = " ".join(captured["cmd"])
    assert '"storeNumber": 113' in cmd_str or '"storeNumber":113' in cmd_str
    assert '"page": 3' in cmd_str or '"page":3' in cmd_str
    assert '"category.keyword"' in cmd_str
```

Add `import json` at the top of the test file (after existing imports).

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_specs.py::test_fetch_wine_page_returns_parsed_response tests/test_specs.py::test_fetch_wine_page_sends_correct_store_and_page -v
```

Expected: FAIL — `ImportError: cannot import name '_fetch_wine_page'`

- [ ] **Step 3: Add `_fetch_wine_page` to `backend/scrapers/specs.py`**

Add after the `_parse_product` function:

```python
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
```

- [ ] **Step 4: Run all specs tests**

```bash
python3 -m pytest tests/test_specs.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/specs.py backend/tests/test_specs.py
git commit -m "feat: _fetch_wine_page curl implementation (TDD)"
```

---

## Task 3: Inventory mapping and wine details upsert (TDD)

**Files:**
- Modify: `backend/scrapers/specs.py`
- Modify: `backend/tests/test_specs.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_specs.py`:

```python
from scrapers.specs import SpecsScraper
from scrapers.base import RetailInventoryItem
from unittest.mock import MagicMock


def _make_scraper():
    s = SpecsScraper.__new__(SpecsScraper)
    s.supabase = MagicMock()
    return s


def test_products_to_inventory_items_maps_correctly():
    scraper = _make_scraper()
    product = _parse_product(_raw_product())
    items = scraper._products_to_inventory_items(
        [product], store_number=100, store_name="San Antonio - De Zavala"
    )
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RetailInventoryItem)
    assert item.wine_name == "Stonegate Sauvignon Blanc"
    assert item.upc == "081883800770"
    assert item.price == 9.65
    assert item.retailer_name == "Spec's"
    assert item.store_id == "100"
    assert item.store_name == "San Antonio - De Zavala"
    assert item.in_stock is True
    assert item.zip_code == "78209"


def test_products_to_inventory_items_skips_no_price():
    scraper = _make_scraper()
    raw = _raw_product()
    raw["pricing"]["unitPrice"] = None
    raw["pricing"]["unitPricePromoDiscount"] = None
    product = _parse_product(raw)
    items = scraper._products_to_inventory_items(
        [product], store_number=100, store_name="De Zavala"
    )
    assert len(items) == 0


def test_upsert_wine_details_writes_non_empty_descriptions():
    scraper = _make_scraper()
    scraper.supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    product_with_desc = _parse_product(_raw_product())
    raw_no_desc = _raw_product()
    raw_no_desc["details"]["description"] = ""
    product_no_desc = _parse_product(raw_no_desc)

    upc_to_id = {"081883800770": "wine-uuid-1"}
    scraper._upsert_wine_details([product_with_desc, product_no_desc], upc_to_id)

    scraper.supabase.table.assert_called_with("wine_details")
    call_args = scraper.supabase.table.return_value.upsert.call_args
    records = call_args[0][0]
    assert len(records) == 1
    assert records[0]["wine_id"] == "wine-uuid-1"
    assert records[0]["description"] == "Crisp and dry with notes of green apple and citrus."
    assert records[0]["source"] == "scraped_specs"


def test_upsert_wine_details_skips_when_all_empty():
    scraper = _make_scraper()
    raw = _raw_product()
    raw["details"]["description"] = ""
    product = _parse_product(raw)
    upc_to_id = {"081883800770": "wine-uuid-1"}
    scraper._upsert_wine_details([product], upc_to_id)
    scraper.supabase.table.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_specs.py::test_products_to_inventory_items_maps_correctly tests/test_specs.py::test_upsert_wine_details_writes_non_empty_descriptions -v
```

Expected: FAIL — `ImportError: cannot import name 'SpecsScraper'`

- [ ] **Step 3: Add `SpecsScraper` class to `backend/scrapers/specs.py`**

Append to `backend/scrapers/specs.py`:

```python
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
                zip_code="78209",   # San Antonio; geocoded by BaseScraper._upsert_stores
                city="San Antonio",
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

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """Not used for full scraping — exists to satisfy BaseScraper ABC."""
        return []

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        """Not used for full scraping — exists to satisfy BaseScraper ABC."""
        return []
```

- [ ] **Step 4: Run all specs tests**

```bash
python3 -m pytest tests/test_specs.py -v
```

Expected: 12 tests PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all 98+ tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/scrapers/specs.py backend/tests/test_specs.py
git commit -m "feat: SpecsScraper with inventory mapping + wine details upsert (TDD)"
```

---

## Task 4: `run_full()` + live run

**Files:**
- Modify: `backend/scrapers/specs.py`

- [ ] **Step 1: Add `run_full()` to `SpecsScraper` in `backend/scrapers/specs.py`**

Add this method to the `SpecsScraper` class:

```python
    def _fetch_store_name(self, store_number: int) -> str:
        """GET /api/store/number/N/ → store name string."""
        cmd = [
            "curl", "-s", "--max-time", "10",
            "-H", "User-Agent: Mozilla/5.0",
            "-H", "Accept: application/json",
            STORE_API_URL.format(store_number),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(result.stdout)
            return data.get("name") or f"Spec's Store {store_number}"
        except Exception:
            return f"Spec's Store {store_number}"

    async def run_full(self) -> dict:
        """
        Full scrape: iterate all 12 SA stores × all pages.
        Commits each page immediately so progress is never lost on failure.
        """
        import time

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id,
            "retailer_name": RETAILER_NAME,
            "status": "running",
        }).execute()

        total_committed = 0

        try:
            for store_number in SA_STORE_NUMBERS:
                store_name = self._fetch_store_name(store_number)
                print(f"\n  Store {store_number} — {store_name}")

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
                            products, store_number=store_number, store_name=store_name
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

            return {"wines_committed": total_committed, "stores": len(SA_STORE_NUMBERS)}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
```

- [ ] **Step 2: Run the test suite to confirm nothing broke**

```bash
cd backend
python3 -m pytest tests/ -v
```

Expected: all 98+ tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/scrapers/specs.py
git commit -m "feat: SpecsScraper.run_full() — 12 SA stores, paginated, per-page commit"
```

- [ ] **Step 4: Dry-run on one store to validate live API**

```bash
cd backend
python3 - << 'EOF'
import asyncio
from scrapers.specs import _fetch_wine_page, _parse_product

# Fetch first page of store 100 (De Zavala)
resp = _fetch_wine_page(store_number=100, page=1)
print(f"Total wines: {resp['totalProducts']}")
print(f"Pages: {resp['totalPages']}")
products = [p for raw in resp['products'] if (p := _parse_product(raw))]
print(f"Parsed {len(products)} products from page 1")
for p in products[:5]:
    print(f"  [{p.upc}] {p.name} — ${p.price} ({'in stock' if p.in_stock else 'out of stock'})")
    if p.description:
        print(f"    desc: {p.description[:80]}")
EOF
```

Expected: 96 products, sensible names/prices, some with descriptions.

- [ ] **Step 5: Run the full scrape against live DB**

This will take ~15–20 minutes (12 stores × ~52 pages each × 0.5s delay).

```bash
cd backend
python3 -c "
import asyncio
from scrapers.specs import SpecsScraper
asyncio.run(SpecsScraper().run_full())
"
```

Monitor output: should print store names and page progress. On completion, verify:

```bash
python3 - << 'EOF'
from db import get_service_client
db = get_service_client()

stores = db.table("stores").select("retailer_name,name,zip_code,latitude,longitude").eq("retailer_name", "Spec's").execute()
print(f"Spec's stores seeded: {len(stores.data)}")
for s in stores.data:
    print(f"  {s['name']} — zip={s['zip_code']} lat={s['latitude']}")
EOF
```

Expected: 12 Spec's store rows, all with lat/lon populated (auto-geocoded from zip 78209).

- [ ] **Step 6: Push to remote**

```bash
git push origin main
```
