# Spec's Wines, Spirits & Foods — API Findings

**Date:** 2026-06-18
**Domain:** `https://specsonline.com` (NOT `specs.com` — that's a glasses company)

---

## Summary

Spec's runs a custom Next.js App Router site. Product search is powered by an internal REST API at `/api/search/` — no auth, no cookies, no session required. Pure-curl is sufficient.

---

## Search API

**Endpoint:** `POST https://specsonline.com/api/search/`

**Required headers:**
```
Content-Type: application/json
Referer: https://specsonline.com/shop/wine/
User-Agent: Mozilla/5.0 ...
```

**Request body:**
```json
{
  "userQuery": "",
  "orderBy": "popularity",
  "storeNumber": 100,
  "page": 1,
  "pageSize": 96,
  "facets": {
    "category.keyword": "[\"Wine\"]"
  }
}
```

- `storeNumber`: integer store number (see SA stores below)
- `page`: 1-based
- `pageSize`: any value; 96 is efficient (~52 pages for ~4,983 wines per store)
- `facets.category.keyword = "[\"Wine\"]"` filters to wine only — **beer, spirits, sake excluded at API level**

**Response shape:**
```json
{
  "totalProducts": 4983,
  "currentPage": "1",
  "totalPages": 52,
  "productsPerPage": 96,
  "products": [
    {
      "code": "100-081883800770",
      "details": {
        "description": "Tasting notes here (often empty string)",
        "title": "Stonegate Rose",
        "type": "wine",
        "attributes": {
          "sku": "125681",
          "upc": "081883800770",
          "brand": "STONEGATE",
          "size": "750ML",
          "classid": 990,
          "category": "Wine",
          "categoryGroup": "Rosé / Blush",
          "subcategory": "Chile Wines"
        },
        "image": "https://cdn.specsonline.com/images/products/081883800770.jpg"
      },
      "url": "/shop/wine/stonegate-rose/",
      "pricing": {
        "unitPrice": 1262,
        "unitPricePromoDiscount": 965,
        "casePrice": null,
        "caseQuantity": null,
        "casePricePromoDiscount": null,
        "casePriceKeyclubDiscount": null,
        "unitPriceKeyclubDiscount": null
      },
      "stock": {
        "inStock": false,
        "details": null
      },
      "taxonomy": "category_wine_ros-blush_chile-wines"
    }
  ]
}
```

**Key fields:**
- `details.title` → wine name
- `details.attributes.upc` → 12-digit UPC (real barcode, enables cross-retailer deduplication)
- `details.attributes.brand` → producer/brand
- `details.attributes.size` → "750ML", "1.5L", etc.
- `details.attributes.categoryGroup` → "Cabernet Sauvignon", "Rosé / Blush", "Red Blend", etc.
- `details.description` → tasting notes (often empty — Haiku extractor fills the gap)
- `details.image` → product image CDN URL
- `pricing.unitPrice` → shelf price in **cents** (divide by 100)
- `pricing.unitPricePromoDiscount` → sale price in cents (null if no promo)
- `stock.inStock` → boolean

---

## Store API

**Endpoint:** `GET https://specsonline.com/api/store/number/{N}/`

No auth or headers required beyond User-Agent.

**Response:**
```json
{
  "id": 91,
  "name": "San Antonio - De Zavala",
  "number": 100,
  "status": "active",
  "featureFlags": {"uberdirect": true, "doordash": true}
}
```

---

## San Antonio Store Numbers

Discovered from `/liquor-stores/san-antonio/` and individual store pages:

| Store # | Name |
|---|---|
| 69 | Live Oak |
| 72 | Legacy |
| 74 | Kerrville* |
| 98 | East Southcross |
| 100 | De Zavala |
| 110 | The Vineyard |
| 113 | Bandera Road |
| 114 | Barnes Drive |
| 117 | Alamo Ranch |
| 169 | Stone Oak |
| 171 | Ingram Festival Loop |
| 194 | Boerne Stage |
| 197 | Rector Drive |
| 207 | Boerne* |

*Kerrville and Boerne are adjacent Hill Country markets, not strictly San Antonio — include or exclude based on desired coverage.

For MVP: use stores 69, 72, 98, 100, 110, 113, 114, 117, 169, 171, 194, 197 (12 true SA-area stores).

---

## Scraper Implementation Notes

1. **No session/auth needed** — pure `curl -X POST` with JSON body works without cookies
2. **Wine-only filtering** — set `facets.category.keyword = "[\"Wine\"]"` in every request; no post-processing needed
3. **Pricing is in cents** — divide `unitPrice` by 100 for dollars. Use `unitPricePromoDiscount` if non-null as the effective price
4. **Descriptions often empty** — use `details.description` when non-empty; Haiku extractor fills the gap from name+brand+categoryGroup
5. **UPCs are real barcodes** — enables cross-retailer deduplication with HEB data
6. **Pagination** — use `pageSize=96` and iterate `page` from 1 to `totalPages`
7. **Per-store scrape** — run the search for each store number; products appear in every store they're available at (inventory is store-specific per `stock.inStock`)
8. **`code` field** — format is `"{storeNumber}-{upc}"` — don't store this; UPC alone is the canonical identifier
9. **No 302 redirects on the API** — the `POST /api/search/` endpoint with trailing slash returns 200 directly; without trailing slash returns 308

---

## What We Don't Have

- **No product-level in-stock data at non-home-store** — `stock.inStock` reflects the queried store. A wine can be in stock at store 100 but out at store 113. Must query each store separately.
- **No vintage year in API** — not a field; Haiku extractor pulls it from the product name
- **ABV** — not in the API response; extractor fills from description if present
