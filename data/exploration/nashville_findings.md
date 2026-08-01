# Nashville Wine Retailers — Discovery (2026-07-05)

Prompted by a beta tester in Nashville (zip 37210). Geo stack is city-agnostic
(pgeocode radius lookup), so any Nashville store seeded just works.

## Verdict

| Shop | Platform | Scrapable? | Notes |
|---|---|---|---|
| **Harvest Wine Market** | Shopify | ✅ **BUILT** | 1,032 wines, open `/products.json`, prices + images |
| Corkdorks (Midtown/Green Hills) | City Hive | ❌ | product/inventory endpoints require login ("You must be logged in") |
| Frugal MacDoogal | City Hive | ❌ | same auth gate |
| Woodland Wine Merchant | Squarespace | ❌ | no clean product JSON API |
| Grand Cru | Squarespace | ❌ | same |
| West Nashville Wine & Liquors | unknown | ❌ | products.json 404 |
| Publix | Akamai Bot Manager | ❌ | main site 403s; `services.publix.com` API endpoints 404; delivery subdomain is Instacart-gated (re-confirmed 2026-07-05) |

## Harvest Wine Market — the win

- **Domain**: harvestwinemarket.com (Shopify, public `/products.json`, page-param pagination)
- **Address**: 6043 TN-100, Nashville TN 37205 (Belle Meade / Westgate Center) — 7.4 mi from tester zip 37210, inside the 10-mi radius
- **Catalog**: 1,518 raw products → **1,032 wines** after non-wine filter
  (Red 477, White 346, Sparkling 109, Rosé 45, Fortified 37, Dessert 11, Sake 5, Orange 2)
- **Data quality**: 99.9% priced, 85% imaged, vendor = producer
- **Casing quirk**: product_type is inconsistent (`Rosé` / `Rose wine` / `rose`,
  `White Wine` / `White wine`) — `_normalize_type()` lowercases + maps; non-wine
  types (Bourbon/Gin/Tequila/Event/Gift Card) dropped
- **UPCs**: synthetic (`shopify-harvest-{handle}`) — boutique wines rarely list barcodes

Scraper: `backend/scrapers/harvest_wine.py` (US Natural Wine pattern).
Registered in the weekly scrape workflow between Antonelli's and Spec's.

## City Hive note (for future Nashville/other-city expansion)

Corkdorks + Frugal MacDoogal run on City Hive (api.cityhive.net). Merchant IDs
are embedded in the storefront HTML (e.g. Corkdorks Midtown = `5c2a8cae7309395802faf15d`),
and the config blob leaks store addresses + coords + delivery polygons. But the
`/products` and `/inventory` endpoints return "You must be logged in" without a
session. A logged-in-session or headless-browser path would be needed — parked
unless Nashville coverage becomes a priority.

### UPDATE 2026-08-01 — the Twin Liquors bypass unblocks Frugal MacDoogal ✅

The `nashville_findings.md` City Hive verdict above predates the Twin Liquors
scraper, which cracked City Hive's anonymous gate: the **top-level search route**
`GET api.cityhive.net/api/v1/products/search.json?merchant_id={id}&new_style=true&api_key={k}&client_origin={co}&text={term}`
works WITHOUT a login (the auth wall is only on the per-merchant `/products`
route the original probe hit). Values lifted from the storefront HTML
(`window.cityHiveWidgetLoaderConfig`):

- **Frugal MacDoogal** (`frugalmacdoogal.com`): `merchant_id=6599a3f98893882b7f30798d`,
  `api_key=7508df878a8c7566a880e4d3f7fa7972` (a shared City Hive widget key — SAME
  as Twin Liquors), `client_origin=app://sites.frugalmab9bcea1a`. **Probe confirmed
  2026-08-01**: `text=cabernet` → 30 real products with prices (`Bota Box $18.99`,
  `J Lohr Seven Oaks $17.99`, …). Warehouse-scale store, likely the biggest single
  Nashville inventory win. Response shape identical to Twin Liquors
  (`data.products[]`, `basic_category`, `merchants[].product_options[].price`).
- **Corkdorks** — **ALSO SCRAPABLE** (initially misjudged). The storefront
  `corkdorks.com` has a **dead HTTPS server** (port 443 refuses; `corkdork.com`
  singular is an unrelated parked/lander domain) — but we scrape the City Hive
  API, not the website, and **the merchant backend is fully live**. Hitting the
  same `products/search.json` route with the known Midtown merchant ID +
  the shared widget key returns real priced products (confirmed 2026-08-01: 5
  terms → 149 unique wines, every term hits the 30-cap → a full sweep yields
  several hundred+). Merchant blob leaks everything needed for the `stores` row:
  `Corkdorks Wine Spirits Beer - Midtown`, **1610 Church St, Nashville TN 37203**,
  coords `36.1570489, -86.7943734`, merchant_id `5c2a8cae7309395802faf15d`,
  `api_key=7508df878a8c7566a880e4d3f7fa7972`, `client_origin=app://sites.corkdorks`.
  **Two-store chain** — the parent merchant `5c54fed1cfac4e1bcadf2525`
  ("Corkdorks (Multi)") lists both branches in `aggregated_merchant_ids`
  (enumerate the PARENT, not the branch, with the same anonymous key):
  **Midtown** `5c2a8cae7309395802faf15d` (1610 Church St, 37203) + **Green Hills**
  `5b52b2903ff14a3c5d9cdd19` (4009 Hillsboro Pike, 37215) — both confirmed live.
  So Frugal (1) + Corkdorks (2) = 3 new Nashville stores. Lesson: a dead
  storefront ≠ a dead City Hive backend — probe the API before writing a store
  off.

**Build path = clone `scrapers/twin_liquors.py`** (same route, same parse, same
30/term cap → sweep terms, same synthetic `cityhive-{id}` UPC). **Runs on the
residential-IP mini only** — City Hive Cloudflare-1015s datacenter IPs on
sustained sweeps, exactly like Twin Liquors (one-off probe from a datacenter IP
succeeded, but a full sweep will throttle). Queued: `docs/mini-agent-tasks.md`.
