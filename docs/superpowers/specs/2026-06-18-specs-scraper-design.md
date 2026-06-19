# Specs Wine Scraper Design

**Date:** 2026-06-18
**Status:** Approved

## Goal

Scrape wine inventory from all San Antonio Spec's stores and seed it into the wine app database. Exclude liquor, beer, and sake — wines only. Include descriptions where available.

## Approach

Two-phase: probe first to discover internal APIs, then build a pure-curl scraper from findings. Same strategy that produced the HEB GraphQL scraper.

## Phase 1 — Probe

**File:** `data/exploration/specs_probe.py`

Follows `totalwine_probe.py` pattern: launch Playwright, open Specs wine pages for a San Antonio zip, intercept every non-asset network request, and log full request/response for any JSON hits.

**Targets:**
- Store locator — enumerate all SA store IDs
- Wine product search per store — pagination shape, category filter params
- Product detail page — check if descriptions are in listing or require a second call

**Output:**
- `data/exploration/specs_probe_output/` — raw captured responses
- `data/exploration/specs_findings.md` — documented endpoints, headers, field shapes

The probe is throwaway. Its only job is to produce the findings doc that drives Phase 2.

## Phase 2 — Scraper

**File:** `backend/scrapers/specs.py`

`SpecsScraper(BaseScraper)` with `run_full()`. Follows `heb.py` structure: pure-curl subprocess calls, `@dataclass` for parsed products, per-store iteration.

### Store coverage

All SA Specs locations hardcoded by store ID (discovered via probe). Same pattern as `STORE_ID = "567"` in HEB. `BaseScraper._upsert_stores` handles geocoding automatically from store zip.

### Wine filtering

Filter at the API request level using Specs' wine category ID (discovered via probe). Do not download all products and filter client-side. Explicitly excludes liquor, beer, and sake by only querying the wine department.

### Descriptions

- If descriptions are included in the listing API response → write to `wine_details` in `_upsert_wine_details()` (same pattern as Geraldine's)
- If descriptions require a separate detail-page call → cap at ~500 calls (one per unique wine SKU, not per store); skip if impractical and let the Haiku extractor fill the gap from wine name alone

### Data Model

**`RetailInventoryItem` fields:**
| Field | Source |
|---|---|
| `wine_name` | Product name from API |
| `upc` | Real UPC (Specs is a traditional retailer — UPCs expected) |
| `price` | Shelf price |
| `in_stock` | Availability flag |
| `retailer_name` | `"Spec's"` |
| `store_id` | Per-store ID from probe |
| `store_name` | Store name from locator |
| `address`, `zip_code` | From store locator |
| `brand` | Producer/brand field if available |
| `varietal` | If Specs' API includes it |

UPCs enable cross-retailer deduplication — a Specs and HEB wine with the same UPC resolve to the same `wines` row.

## Error Handling

- Exponential backoff on HTTP errors (same as HEB)
- `scraper_runs` table: log start/success/failed per run
- Per-store iteration — a failing store logs a warning and continues, doesn't abort the run
- Zero wine results for a store → skip with warning, not a crash

## Testing

Unit tests in `backend/tests/test_specs.py` with mocked HTTP responses. No Playwright in tests.

| Test | Assertion |
|---|---|
| `test_parse_product_wine_filters_out_beer_and_spirits` | Non-wine categories excluded |
| `test_parse_product_extracts_upc_price_description` | Core fields correctly parsed |
| `test_parse_product_no_upc_returns_none` | Graceful skip for products without UPC |
| `test_scraper_maps_to_inventory_items` | Correct `RetailInventoryItem` shape |
| `test_upsert_wine_details_builds_records` | Description writes to `wine_details` |

## Implementation Order

1. Write and run `specs_probe.py` → document findings
2. Build `SpecsScraper` from findings (TDD)
3. Run against live DB, verify SA stores appear in `stores` table

## Open Questions (resolved by probe)

- Exact wine category ID(s) in Specs' API
- Whether descriptions are in listing or require detail calls
- Pagination pattern (offset? cursor? page number?)
- Required headers / session cookies (if any)
