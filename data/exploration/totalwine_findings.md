# Total Wine — re-probe findings (2026-08-26)

**Context:** `CLAUDE.md` lists Total Wine under blocked retailers as "(Imperva)". Since
Imperva *is* Incapsula — the same vendor whose JS challenge we just defeated on H-E-B
with patchright (item 45) — Total Wine looked like the strongest candidate to reuse
that technique. It has the biggest Texas footprint of any blocked retailer, so it's
also the most valuable coverage gap.

**Headline: the premise was wrong, in a useful way.** The gate is not the obstacle —
plain `urllib` reads Total Wine's storefront fine today. The real blocker is
**store scoping**, which is a harder and more fundamental problem for this app.

## 1. There is no challenge on storefront HTML

A plain `urllib` GET with a normal desktop UA:

| URL | Status | Bytes | Incapsula marker |
|---|---|---|---|
| `https://www.totalwine.com/` | 200 | 375,027 | none |
| `https://www.totalwine.com/wine/c/c0020` | 200 | 1,431,642 | none |

No `_Incapsula_Resource`, no 401/502, no JS challenge. **patchright was never needed
and was never invoked** in this probe. The "blocked (Imperva)" note appears stale for
the storefront path — either the protection was relaxed, or it was only ever enforced
on a path we no longer remember testing. Worth re-checking from a datacenter IP before
concluding anything about GitHub Actions; **this probe ran from the mini's residential
IP**, which may be the whole difference.

## 2. Product data is server-rendered, with a stable URL anchor

The wine category page carries 79 price strings inline. Markup is React SSR with
**hashed CSS-module class names** (`price__ff218822`, `pricingHolder__a7fa079c`) — those
hashes change on every frontend build, so they are a brittle anchor.

The good anchor is the product URL, which is clean and semantic:

```
/wine/red-wine/cabernet-sauvignon/caymus-cabernet/p/223968750
/wine/white-wine/sauvignon-blanc/olema-sauvignon-blanc/p/231443750
/wine/red-wine/red-blend/1858-red-blend/p/232279750
```

`/{category}/{color}/{varietal}/{slug}/p/{productId}` — it encodes colour and varietal
in the path, which is exactly the taxonomy the recommender wants, and the numeric
`productId` is a natural stable key.

## 3. `/site/resourceapi/` is a CMS API, NOT a product API

The page references `https://www.totalwine.com/site/resourceapi/global/header?cacheStoreId=1108&cacheState=US-CA&cacheShoppingMethod=INSTORE_PICKUP&cacheApiVersion=1.0`,
which looks promising but isn't. It's **Bloomreach Experience Manager** (`"product":"brxm"`)
page-delivery: it returns page components and `$ref` graphs, not catalog data.

Probed endpoint names under `/site/resourceapi/` — everything except `global/header`
and `search` returns an identical 2,009-byte not-found shape:

| endpoint | bytes |
|---|---|
| `global/header` | 161,725 |
| `search` | 2,948 (CMS page model for the search *page*, no products) |
| `products` / `product` / `browse` / `catalog` / `productsearch` / `store/1108` | 2,009 (not found) |

Fetching the category path through the resourceapi (`/site/resourceapi/wine/c/c0020`)
returns 9,184 bytes with **zero** occurrences of `price`, `productId`, `sku`, `brand`,
or `inventory`. So there is no clean JSON catalog behind this route — products reach
the browser via SSR HTML.

## 4. THE BLOCKER — store scoping was not cracked

Scoping demonstrably exists. Embedded in the page:

```json
{"shoppingMethod":"INSTORE_PICKUP","storeId":"1108","state":"US-CA"}
```

and the CMS URLs carry `cacheStoreId` / `cacheState` / `cacheShoppingMethod`. But:

- The default is **store 1108, US-CA** — a California store.
- `/store-finder?state=TX` returns 854KB with **zero** mentions of San Antonio, Austin,
  Dallas or Houston and only storeId `1108` — the finder loads its store list
  client-side, so the ids aren't in the HTML.
- Guessed cookie names (`wineStoreId` / `state` / `shoppingMethod`) had **no effect** —
  `US-CA` and `US-TX` returned byte-identical responses (1,431,627 both) with identical
  prices, so those are not the real cookie names.

**Why this is disqualifying rather than annoying:** this app's entire premise is
"available near you." California prices and California availability are worse than no
data — they'd feed the recommender confident, wrong inventory, which is exactly the
false-availability class items 39/40/44 exist to prevent. A Total Wine scraper that
can't scope to a Texas store should not be built.

## Verdict

**Not blocked — but not yet scrapable either.** The reusable insight from item 45
(patchright beats Incapsula) turned out to be irrelevant here; nothing needed solving.
What stands in the way is a plain product-engineering problem: discovering how the site
selects a store, and getting real Texas store ids.

## If picked up again — next steps, cheapest first

1. **Find how the store is actually set.** Open totalwine.com in the browser session we
   already have, select a San Antonio store by hand, and diff the cookies/localStorage
   before and after. That names the real mechanism in one shot — far faster than the
   guessing this probe did.
2. **Get TX store ids** from whatever XHR the store-finder fires (visible in the same
   browser session), since they're not in the HTML.
3. **Only then** assess scraping cost: SSR HTML parsing anchored on the `/p/{productId}`
   URL pattern, with pagination over category pages. Avoid the hashed CSS classes.
4. **Re-probe the gate from a datacenter IP** before assuming GitHub Actions can run it —
   this probe was residential-IP only, and that may be exactly why it saw no challenge.

## Not assessed

ToS posture. H-E-B's GraphQL was open and got fenced later; Total Wine's storefront being
readable today says nothing about whether scraping it is permitted. That's a business
decision to make deliberately, not by default.
