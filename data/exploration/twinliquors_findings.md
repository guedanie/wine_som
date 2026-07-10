# Twin Liquors — API findings (2026-07-09)

**Verdict: VIABLE — build it.** City Hive platform, but the anonymous auth that
blocked the Nashville City Hive shops (Corkdorks, Frugal MacDoogal) is now
cracked: `products/search.json` works anonymously with an **api_key +
client_origin** lifted from the storefront HTML. Returns price + stock quantity +
per-store data. Same scraper shape as Spec's/Kroger (store-list × search-terms).

## Platform
- `twinliquors.com` — Cloudflare-fronted, but plain `curl` gets clean 200s (no JS
  challenge on the storefront or the City Hive API). TX chain (Austin/SA heavy).
- **City Hive** (`api.cityhive.net`) — same SaaS as the blocked Nashville shops.
- Angular browsing widget: `widget.cityhive.net/city-hive-elements-browsing-module.js`.

## The working endpoint
```
GET https://api.cityhive.net/api/v1/products/search.json
  ?merchant_id={STORE_MERCHANT_ID}
  &new_style=true
  &api_key={API_KEY}
  &client_origin=app://sites.twinliquors
  &text={search term}          # THE search param (NOT q / free_text)
Headers: Origin: https://twinliquors.com, Referer: https://twinliquors.com/shop/,
         any real User-Agent. A GET to .../prospective_customer.json first mints a
         _HiveNet_uuid cookie (belt-and-suspenders; search works without it too).
```
- **api_key** is in the shop-page HTML: `window.cityHiveWidgetLoaderConfig.apiKey`
  (McCreless Corner store: `7508df878a8c7566a880e4d3f7fa7972`). Also present:
  `currentMerchantId`, `clientOrigin: "app://sites.twinliquors"`.
- Without `api_key` → `{"result":2,"Api key is required}`. Without it the plain
  `.../merchants/{id}/products.json` route returns the classic City Hive
  `"You must be logged in"` — which is what the Nashville probe hit and gave up on.
  **The api_key + client_origin on the top-level search route is the bypass.**

## Response shape (`data.products[]`)
- Product: `id, name, basic_category[] (red/white/sparkling/rose/...), size
  {measure,quantity,pack}, description, images[], tags, product_rating,
  number_of_product_ratings, is_enriched`.
- **Price + stock + store** under `merchants[].product_options[]`:
  - `price` (float, e.g. 1.99), `quantity` (units in stock, e.g. 92),
    `original_price`, `discount_value/discount_style` (promos),
  - `merchant_id, merchant_name` (e.g. "Twin Liquors - McCreless Corner"),
    `coordinates, full_address` (per-store geo — free geocoding),
  - `option_id, option_params.size, product_url, staff_pick, product_badges`.

## Per-store model (like Spec's)
- Each **store = its own merchant_id**. The shop defaults to one store
  (McCreless Corner = `5af17c10c8852b44f5995fdc`); `portfolioMode: false`.
- The homepage references a different id `5b58f0b2388cd66fbac2e4e6` — likely the
  **portfolio/parent** merchant. Twin Liquors has ~90 TX stores → each needs its
  merchant_id (TODO: enumerate via a store-locator/portfolio endpoint, or scrape
  the store-switcher). Same "store registry" chore as Spec's `SA_STORE_NUMBERS`.

## Pagination — hard-capped at 30/term
- `offset`, `page`, `per_page`, `limit` all **ignored** — every query returns a
  fixed top-30 relevance list. Same limitation as Kroger.
- **Workaround (proven): multi-term search.** `text=` DOES filter (text=cabernet →
  29 reds). Loop ~20 wine terms (varietals + regions + "red/white/rosé/sparkling
  wine") and **dedupe by product `id`**, exactly like Kroger's 17-term approach.
- Open question for build: does the category-browse grid (homepage
  `/shop/?category=cabernet_sauvignon_name`) hit a different, paginated endpoint?
  Worth one probe before settling on multi-term.

## Build plan (mirror specs.py / kroger.py)
1. Enumerate Twin Liquors store merchant_ids (store-locator probe) → registry.
2. Per store × ~20 wine terms → `products/search.json&text=…`, dedupe by id.
3. Filter to wine `basic_category` (red/white/rose/sparkling/... — exclude
   spirits/beer). Map price + quantity→in_stock + per-store to `retail_inventory`.
4. Real barcodes? check `additional_properties`/product for UPC → cross-retailer
   dedup with HEB/Spec's; else synthetic `cityhive-{id}`.
5. Geo from `coordinates`/`full_address` (BaseScraper auto-geocode as fallback).

## Reusable win
This api_key + client_origin bypass likely **unblocks the parked Nashville City
Hive shops** (Corkdorks `5c2a8cae…`, Frugal MacDoogal) — their keys are in their
own storefront HTML. Revisit `nashville_findings.md` City Hive note.
