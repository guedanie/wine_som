# HEB Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `backend/scrapers/heb.py` — a pure-curl HEB wine scraper using the cracked `productSearch` GraphQL API, following the `BaseScraper`/`geraldines.py` pattern.

**Architecture:** HEB's `POST /graphql` is reachable server-side with no auth/cookies/browser (Imperva is path-based and doesn't cover `/graphql`). The scraper paginates `productSearch(query:"wine", storeId:567)` via `offset`, parses each record into an `HEBProduct`, filters to records that map to a known wine type, and upserts to `wines` + `retail_inventory` + `wine_details`. Price uses the ONLINE context (in-store, lower) as canonical with CURBSIDE kept as a secondary column.

**Tech Stack:** Python 3.9 (use `Optional[...]`, not `X | None`), `urllib.request` for GraphQL POST, supabase-py, pytest. No Playwright.

**Design decisions (confirmed with user):**
- Store: **hardcode store 567** (Lincoln Heights, San Antonio) for MVP.
- Price: keep both contexts; **canonical = ONLINE-context price (in-store, lower)**; CURBSIDE stored in a new `retail_inventory.curbside_price` column.
- Filter: **keep only records where `infer_wine_type()` returns a type.**

---

## The cracked GraphQL request (reference)

`POST https://www.heb.com/graphql`, headers:
```
Content-Type: application/json
User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148
Apollographql-Client-Name: heb-com
Origin: https://www.heb.com
Referer: https://www.heb.com/
```
Body (ad-hoc full query; no persisted hash needed):
```graphql
{ productSearch(shoppingContext: CURBSIDE_PICKUP, query: "wine", storeId: 567, limit: 60, offset: 0) {
    total
    records {
      id
      displayName
      brand { name }
      productPageURL
      productDescription
      inventory { quantity }
      SKUs { twelveDigitUPC customerFriendlySize
        contextPrices { context isOnSale
          listPrice { amount } salePrice { amount } } }
    }
} }
```
`query:"wine"` at store 567 → `total` ~1993; `offset` paginates.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260611000001_heb_curbside_price.sql` | Create | Add nullable `curbside_price` to `retail_inventory` |
| `backend/scrapers/heb.py` | Create | GraphQL client + `_parse_record` + `HebScraper` |
| `backend/tests/test_heb.py` | Create | Unit tests for parsing/filtering/price selection |
| `CLAUDE.md` | Modify | Mark HEB unblocked, document the recipe |

All commands run from `backend/` unless noted.

---

### Task 1: Migration — curbside_price column

**Files:**
- Create: `supabase/migrations/20260611000001_heb_curbside_price.sql`

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/20260611000001_heb_curbside_price.sql`:

```sql
-- HEB exposes two price contexts per item: ONLINE (in-store shelf price, lower)
-- and CURBSIDE (pickup price, higher). retail_inventory.price holds the canonical
-- in-store price; this column keeps the curbside price alongside it.
ALTER TABLE retail_inventory ADD COLUMN IF NOT EXISTS curbside_price NUMERIC(8,2);
```

- [ ] **Step 2: Apply to the cloud DB**

This migration must be applied to the live Supabase project before running the scraper. Apply via the Supabase SQL editor or CLI. (The scraper code in Task 3 writes `curbside_price`; until the column exists, a full run would error on upsert.)

Note in your report that this step requires the user to apply the SQL.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260611000001_heb_curbside_price.sql
git commit -m "feat: add retail_inventory.curbside_price for HEB dual pricing"
```

---

### Task 2: Parse logic — TDD

**Files:**
- Create: `backend/tests/test_heb.py`
- Create: `backend/scrapers/heb.py` (parse layer only in this task)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_heb.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scrapers.heb import _parse_record, _price_for_context, HEBProduct


def _raw_record(**kwargs):
    base = {
        "id": "2210067",
        "displayName": "Decoy Cabernet Sauvignon California Red Wine",
        "brand": {"name": "Decoy"},
        "productPageURL": "/product-detail/decoy-cabernet-sauvignon-california-red-wine-750-ml/2210067",
        "productDescription": "Rich Californian red. <b>Type:</b> Red wine<br/><b>ABV:</b> 13.9%",
        "inventory": {"quantity": 181},
        "SKUs": [{
            "twelveDigitUPC": "669576019191",
            "customerFriendlySize": "750 ml",
            "contextPrices": [
                {"context": "ONLINE", "isOnSale": True,
                 "listPrice": {"amount": 19.97}, "salePrice": {"amount": 18.97}},
                {"context": "CURBSIDE", "isOnSale": True,
                 "listPrice": {"amount": 20.97}, "salePrice": {"amount": 19.92}},
            ],
        }],
    }
    base.update(kwargs)
    return base


def test_price_for_context_prefers_sale():
    prices = [
        {"context": "ONLINE", "listPrice": {"amount": 19.97}, "salePrice": {"amount": 18.97}},
    ]
    assert _price_for_context(prices, "ONLINE") == 18.97


def test_price_for_context_falls_back_to_list_when_no_sale():
    prices = [
        {"context": "ONLINE", "listPrice": {"amount": 19.97}, "salePrice": None},
    ]
    assert _price_for_context(prices, "ONLINE") == 19.97


def test_price_for_context_missing_returns_none():
    assert _price_for_context([], "ONLINE") is None


def test_parse_record_full():
    p = _parse_record(_raw_record())
    assert isinstance(p, HEBProduct)
    assert p.product_id == "2210067"
    assert p.name == "Decoy Cabernet Sauvignon California Red Wine"
    assert p.brand == "Decoy"
    assert p.upc == "669576019191"
    assert p.bottle_size == "750 ml"
    assert p.price == 18.97          # ONLINE/in-store, canonical
    assert p.curbside_price == 19.92
    assert p.in_stock is True
    assert p.wine_type == "red"
    assert "Californian red" in p.description


def test_parse_record_out_of_stock_when_zero_inventory():
    p = _parse_record(_raw_record(inventory={"quantity": 0}))
    assert p.in_stock is False


def test_parse_record_non_wine_returns_none():
    # A product whose name maps to no wine type is filtered out
    p = _parse_record(_raw_record(
        displayName="Riedel Wine Glass Set",
        brand={"name": "Riedel"},
    ))
    assert p is None


def test_parse_record_no_skus_returns_none():
    assert _parse_record(_raw_record(SKUs=[])) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python3 -m pytest tests/test_heb.py -v
```

Expected: ImportError — `scrapers.heb` does not exist yet.

- [ ] **Step 3: Implement the parse layer in `backend/scrapers/heb.py`**

Create `backend/scrapers/heb.py`:

```python
"""
HEB wine scraper — pure-curl GraphQL.

HEB's storefront HTML/REST routes are behind Imperva, but the Apollo GraphQL
endpoint (POST /graphql) is reachable server-side with no auth, cookies, or
browser. We reconstructed the productSearch query by reading Apollo validation
errors (introspection is disabled). See docs and CLAUDE.md for the recipe.

Each wine record carries:
  - id, displayName, brand.name, productPageURL
  - productDescription (embeds Type/Blend/Tasting Notes/ABV as light HTML)
  - inventory.quantity (live per-store stock)
  - SKUs[].twelveDigitUPC, customerFriendlySize
  - SKUs[].contextPrices: ONLINE (in-store, canonical) + CURBSIDE
"""
import re
import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from scrapers.base import BaseScraper, RetailInventoryItem
from utils import infer_wine_type

GRAPHQL_URL = "https://www.heb.com/graphql"
STORE_NAME = "H-E-B"
STORE_ID = "567"
STORE_ZIP = "78208"            # Lincoln Heights, San Antonio
STORE_ADDRESS = "1520 Austin Hwy, San Antonio, TX 78218"
RETAILER_NAME = "H-E-B"

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 Mobile/15E148",
    "Apollographql-Client-Name": "heb-com",
    "Origin": "https://www.heb.com",
    "Referer": "https://www.heb.com/",
}

_PRODUCT_FIELDS = """
  id
  displayName
  brand { name }
  productPageURL
  productDescription
  inventory { quantity }
  SKUs { twelveDigitUPC customerFriendlySize
    contextPrices { context isOnSale listPrice { amount } salePrice { amount } } }
"""


@dataclass
class HEBProduct:
    product_id: str
    name: str
    brand: Optional[str]
    upc: Optional[str]
    bottle_size: Optional[str]
    price: Optional[float]            # ONLINE context (in-store, canonical)
    curbside_price: Optional[float]   # CURBSIDE context
    in_stock: bool
    wine_type: Optional[str]
    description: Optional[str]


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _price_for_context(context_prices: List[Dict[str, Any]], context: str) -> Optional[float]:
    """Return the sale price for a context, falling back to list price."""
    for cp in context_prices or []:
        if cp.get("context") == context:
            sale = cp.get("salePrice") or {}
            if sale.get("amount") is not None:
                return float(sale["amount"])
            listp = cp.get("listPrice") or {}
            if listp.get("amount") is not None:
                return float(listp["amount"])
    return None


def _parse_record(raw: Dict[str, Any]) -> Optional[HEBProduct]:
    """Parse a productSearch record into an HEBProduct. Returns None for non-wine / unusable rows."""
    name = raw.get("displayName") or ""
    if not name:
        return None

    skus = raw.get("SKUs") or []
    if not skus:
        return None
    sku = skus[0]

    brand = (raw.get("brand") or {}).get("name")
    wine_type = infer_wine_type(name)
    if wine_type is None:
        # Not identifiably a wine — filter out (glasses, mixers, etc.)
        return None

    context_prices = sku.get("contextPrices") or []
    price = _price_for_context(context_prices, "ONLINE")
    curbside_price = _price_for_context(context_prices, "CURBSIDE")

    quantity = (raw.get("inventory") or {}).get("quantity") or 0

    return HEBProduct(
        product_id=str(raw.get("id", "")),
        name=name,
        brand=brand,
        upc=sku.get("twelveDigitUPC"),
        bottle_size=sku.get("customerFriendlySize"),
        price=price,
        curbside_price=curbside_price,
        in_stock=quantity > 0,
        wine_type=wine_type,
        description=_strip_html(raw.get("productDescription") or "") or None,
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_heb.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/heb.py backend/tests/test_heb.py
git commit -m "feat: HEB record parser with wine-type filter and dual pricing (TDD)"
```

---

### Task 3: GraphQL client + HebScraper

**Files:**
- Modify: `backend/scrapers/heb.py` (add fetch + scraper class)
- Modify: `backend/tests/test_heb.py` (add fetch/scraper tests with mocked HTTP)

- [ ] **Step 1: Add failing tests for fetch + scraper mapping**

Append to `backend/tests/test_heb.py`:

```python
from unittest.mock import patch, MagicMock
from scrapers.heb import fetch_wine_page, HebScraper


def _fake_response(records, total=2):
    return {"data": {"productSearch": {"total": total, "records": records}}}


def test_fetch_wine_page_parses_records():
    raw = _raw_record()
    with patch("scrapers.heb._graphql_post", return_value=_fake_response([raw], total=1)):
        total, products = fetch_wine_page(offset=0, limit=60)
    assert total == 1
    assert len(products) == 1
    assert products[0].upc == "669576019191"


def test_fetch_wine_page_filters_non_wine():
    wine = _raw_record()
    glass = _raw_record(displayName="Riedel Wine Glass", brand={"name": "Riedel"})
    with patch("scrapers.heb._graphql_post", return_value=_fake_response([wine, glass], total=2)):
        total, products = fetch_wine_page(offset=0, limit=60)
    assert total == 2          # total is the server's count
    assert len(products) == 1  # only the parseable wine survives


def test_scraper_maps_to_inventory_items():
    scraper = HebScraper.__new__(HebScraper)  # skip __init__ (no Supabase client)
    p = _parse_record(_raw_record())
    items = scraper._products_to_inventory_items([p])
    assert len(items) == 1
    item = items[0]
    assert item.retailer_name == "H-E-B"
    assert item.store_id == "567"
    assert item.upc == "669576019191"
    assert item.price == 18.97
    assert item.brand == "Decoy"
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
cd backend && python3 -m pytest tests/test_heb.py -v
```

Expected: the 3 new tests fail (ImportError on `fetch_wine_page`/`HebScraper`).

- [ ] **Step 3: Implement fetch + scraper in `backend/scrapers/heb.py`**

Append to `backend/scrapers/heb.py`:

```python
def _graphql_post(query: str, timeout: int = 20) -> Dict[str, Any]:
    """POST a GraphQL query to HEB and return the parsed JSON."""
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=body, headers=_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_wine_page(offset: int = 0, limit: int = 60, store_id: str = STORE_ID):
    """
    Fetch one page of wine products. Returns (server_total, [HEBProduct]).
    Non-wine rows are filtered out by _parse_record.
    """
    query = (
        "{ productSearch(shoppingContext: CURBSIDE_PICKUP, query: \"wine\", "
        f"storeId: {store_id}, limit: {limit}, offset: {offset}) {{ total records {{ {_PRODUCT_FIELDS} }} }} }}"
    )
    data = _graphql_post(query)
    ps = (data.get("data") or {}).get("productSearch") or {}
    total = ps.get("total") or 0
    products = []
    for raw in ps.get("records") or []:
        product = _parse_record(raw)
        if product:
            products.append(product)
    return total, products


class HebScraper(BaseScraper):
    """HEB scraper — pure-curl GraphQL, hardcoded to store 567 (San Antonio) for MVP."""

    def _products_to_inventory_items(self, products: List[HEBProduct]) -> List[RetailInventoryItem]:
        return [
            RetailInventoryItem(
                wine_name=p.name,
                retailer_name=RETAILER_NAME,
                zip_code=STORE_ZIP,
                upc=p.upc,
                price=p.price,
                store_name=STORE_NAME,
                store_id=STORE_ID,
                address=STORE_ADDRESS,
                city="San Antonio",
                state="TX",
                in_stock=p.in_stock,
                varietal=None,
                brand=p.brand,
            )
            for p in products
        ]

    async def search_by_zip(self, zip_code: str) -> List[RetailInventoryItem]:
        """MVP: single hardcoded store. Paginate the full wine catalog."""
        products = self._fetch_all()
        return self._products_to_inventory_items(products)

    async def search_by_wine(self, wine_name: str, zip_code: str) -> List[RetailInventoryItem]:
        _total, products = fetch_wine_page(offset=0, limit=60)
        matches = [p for p in products if wine_name.lower() in p.name.lower()]
        return self._products_to_inventory_items(matches)

    def _fetch_all(self, page_size: int = 60, max_pages: int = 60) -> List[HEBProduct]:
        """Paginate productSearch via offset until all records are fetched."""
        all_products: List[HEBProduct] = []
        offset = 0
        total = None
        for _ in range(max_pages):
            page_total, products = fetch_wine_page(offset=offset, limit=page_size)
            if total is None:
                total = page_total
            all_products.extend(products)
            offset += page_size
            if total is not None and offset >= total:
                break
        return all_products
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python3 -m pytest tests/test_heb.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/scrapers/heb.py backend/tests/test_heb.py
git commit -m "feat: HEB GraphQL fetch + HebScraper with offset pagination"
```

---

### Task 4: run_full with per-page commit + wine_details

**Files:**
- Modify: `backend/scrapers/heb.py` (add `run_full` + `_upsert_wine_details`)

- [ ] **Step 1: Implement `run_full` and details upsert**

Append to `backend/scrapers/heb.py` (mirrors `GeraldinesScraper.run_full` — per-page commit so progress is never lost, plus `curbside_price` written into inventory):

```python
    def _upsert_inventory_with_curbside(self, products: List[HEBProduct]):
        """Like base._upsert_inventory but includes curbside_price and links wine ids by UPC."""
        from datetime import datetime, timezone
        items = self._products_to_inventory_items(products)
        upc_to_id = self._upsert_wines(items)
        now = datetime.now(timezone.utc).isoformat()
        curbside_by_upc = {p.upc: p.curbside_price for p in products if p.upc}
        records = []
        for item in items:
            records.append({k: v for k, v in {
                "wine_id": upc_to_id.get(item.upc) if item.upc else None,
                "upc": item.upc,
                "retailer_name": item.retailer_name,
                "store_id": item.store_id,
                "store_name": item.store_name,
                "address": item.address,
                "city": item.city,
                "state": item.state,
                "zip_code": item.zip_code,
                "price": item.price,
                "curbside_price": curbside_by_upc.get(item.upc),
                "in_stock": item.in_stock,
                "last_scraped_at": now,
            }.items() if v is not None})
        if records:
            self.supabase.table("retail_inventory").upsert(
                records, on_conflict="upc,store_id"
            ).execute()
        return upc_to_id

    def _upsert_wine_details(self, products: List[HEBProduct], upc_to_id: dict):
        """Write HEB productDescription into wine_details as scraped enrichment."""
        from datetime import datetime, timezone
        records = []
        for p in products:
            wine_id = upc_to_id.get(p.upc) if p.upc else None
            if not wine_id or not p.description:
                continue
            records.append({
                "wine_id": wine_id,
                "description": p.description,
                "source": "scraped_heb",
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            })
        if records:
            self.supabase.table("wine_details").upsert(
                records, on_conflict="wine_id"
            ).execute()

    async def run_full(self) -> dict:
        """Full scrape with per-page commit. Paginates the HEB wine catalog at store 567."""
        import uuid
        from datetime import datetime, timezone

        run_id = str(uuid.uuid4())
        self.supabase.table("scraper_runs").insert({
            "id": run_id, "retailer_name": RETAILER_NAME, "status": "running",
        }).execute()

        total_committed = 0
        offset = 0
        page_size = 60
        server_total = None

        try:
            for _ in range(60):  # safety cap
                page_total, products = fetch_wine_page(offset=offset, limit=page_size)
                if server_total is None:
                    server_total = page_total
                if products:
                    upc_to_id = self._upsert_inventory_with_curbside(products)
                    self._upsert_wine_details(products, upc_to_id)
                    total_committed += len(products)
                    print(f"   offset {offset}: {len(products)} wines committed (total: {total_committed})")
                offset += page_size
                if server_total is not None and offset >= server_total:
                    break

            self.supabase.table("scraper_runs").update({
                "status": "success",
                "records_updated": total_committed,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()

            return {"wines_committed": total_committed, "store": STORE_NAME, "store_id": STORE_ID}

        except Exception as e:
            self.supabase.table("scraper_runs").update({
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
            raise
```

- [ ] **Step 2: Add a test for wine_details mapping**

Append to `backend/tests/test_heb.py`:

```python
def test_upsert_wine_details_builds_records():
    scraper = HebScraper.__new__(HebScraper)
    captured = {}

    class FakeTable:
        def upsert(self, records, on_conflict=None):
            captured["records"] = records
            captured["on_conflict"] = on_conflict
            return self
        def execute(self):
            return MagicMock(data=[])

    scraper.supabase = MagicMock()
    scraper.supabase.table.return_value = FakeTable()

    p = _parse_record(_raw_record())
    scraper._upsert_wine_details([p], {"669576019191": "wine-uuid-1"})

    assert captured["on_conflict"] == "wine_id"
    assert captured["records"][0]["wine_id"] == "wine-uuid-1"
    assert captured["records"][0]["source"] == "scraped_heb"
    assert "Californian red" in captured["records"][0]["description"]
```

- [ ] **Step 3: Run tests**

```bash
cd backend && python3 -m pytest tests/test_heb.py -v
```

Expected: 11 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/scrapers/heb.py backend/tests/test_heb.py
git commit -m "feat: HEB run_full with per-page commit, curbside price, wine_details"
```

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the HEB status and add the recipe**

In `CLAUDE.md`:

1. In the **In Progress / Blocked** table, remove the HEB "Blocked" row.
2. In the **Done** table, add:
   `| HEB scraper | backend/scrapers/heb.py | Pure-curl GraphQL, store 567, ~1993 wines, dual pricing |`
3. Add a new section after the Geraldine's notes:

```markdown
### HEB (GraphQL — pure curl, no browser)
- Endpoint: `POST https://www.heb.com/graphql` — no auth/cookies/browser needed
- Imperva protects HTML/REST routes but NOT `/graphql` (WAF is path-based; `/_next/static/` also bypasses)
- Introspection + Apollo suggestions are disabled, but **validation errors leak the schema** — that's how the query was reconstructed
- HEB accepts ad-hoc full queries (no persisted hash required)
- Required headers: `Apollographql-Client-Name: heb-com`, `Origin`, `Referer: https://www.heb.com/`
- `productSearch(shoppingContext: CURBSIDE_PICKUP, query: "wine", storeId: N, limit, offset)` → paginate via `offset`
- Price lives at `records.SKUs[].contextPrices[]`: ONLINE (in-store, lower, canonical) + CURBSIDE
- UPC at `SKUs[].twelveDigitUPC`; `productDescription` embeds Type/Blend/Tasting Notes/ABV
- MVP hardcodes store 567 (San Antonio); zip→store lookup is a future enhancement
```

4. Update the **What's Next** list: replace the HEB Proxyman item with "Add HEB zip→store lookup for multi-market coverage."

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: mark HEB unblocked, document pure-curl GraphQL recipe"
```

---

### Task 6: Full Suite Verification

- [ ] **Step 1: Run the whole suite**

```bash
cd backend && python3 -m pytest tests/ -v
```

Expected: **45 tests passing** (34 from before + 11 HEB). If any pre-existing test fails, stop and investigate — do not skip.

- [ ] **Step 2: Report** the pass count and confirm git status is clean.
