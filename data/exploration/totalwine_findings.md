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

## 5. ROUND 2 — the block profile is INVERTED vs H-E-B

Follow-up probe (`backend/scripts/probe_totalwine_store.py`) tried to watch a store
selection in a patchright browser and diff cookies/localStorage. It couldn't:

```
Loading the store finder…
  baseline: 3 cookies, 4 localStorage keys
Network calls captured (1):
  403 GET https://www.totalwine.com/store-finder
```

**The automated browser gets 403 on a page plain `urllib` reads fine.** Control test run
immediately after, same machine, same minute: `urllib` → **200**, 854,808 bytes. So we
are not rate-limited or IP-banned; Total Wine fingerprints and rejects the
automation-driven Chromium specifically.

| | H-E-B | Total Wine |
|---|---|---|
| Plain HTTP (urllib) | ❌ blocked — Incapsula JS challenge | ✅ **200** |
| Automated browser | ✅ works (patchright) | ❌ **403, fingerprinted** |

**Consequence: for Total Wine the browser is a liability, not an asset.** The item-45
technique is not just unnecessary here, it is actively counterproductive — and the
"open a browser and diff the cookies" plan from §"next steps" **cannot work**. Any
scraper here must be HTTP-only.

## 6. Store ids ARE enumerable — via `/store-info/`

The store-finder HTML exposes a clean, semantic store URL pattern:

```
/store-info/california-sacramento-arden/1108     <- the default store
/store-info/california-roseville/1101
/store-info/california-folsom/1111
/store-info/california-elk-grove/1114
```

`/store-info/{state}-{city}[-{suffix}]/{storeId}`. The finder only rendered *California*
stores (it geo-defaults, and shows no Texas cities — 0 mentions of San Antonio/Austin/
Dallas/Houston), but the pattern means Texas ids are discoverable rather than guessable.

`robots.txt` lists three sitemaps (`sitemap.xml` → 34 sub-sitemaps including
`wine-dynamic-sitemap.xml`; plus `site/sitemap-index.xml`). **Probing stopped here** —
`site/sitemap-index.xml` returned **503**, and after a sustained probe run the right move
was to stop hammering rather than push through it. Re-try later, gently.

### robots.txt — relevant to the ToS question

Total Wine's `robots.txt` **disallows `/search/`**, `/cart/`, `/checkout/`, `/my-account/`,
`/session`, `/app/` — but does **not** disallow `/wine/...` category pages, `/p/{id}`
product pages, or `/store-info/`. So the paths a catalog scraper would want are the ones
the site owner explicitly leaves crawlable, and the one obvious path to avoid is
`/search/`. That is not legal advice and does not settle the ToS question, but it is a
clearer signal than we had, and it points at a design constraint: **browse categories and
store-info; never drive `/search/`.**

## 7. SOLVED 2026-08-26 — store selection is a forgeable cookie

The binding is a single cookie, `twm-userStoreInformation`, in a flat `~`/`@` encoding:

```
twm-userStoreInformation=ispStore~{id}:ifcStore~{id}@ifcStoreState~{US-XX}@method~INSTORE_PICKUP
```

Sending it on a plain `urllib` GET re-scopes the page. **No session, no handshake, no
browser** — visiting a store-info page does NOT rebind it (the cookie stays 1108/US-CA),
so forging the cookie directly is both necessary and sufficient.

Verified against `/wine/c/c0020`:

| store | `storeId` echoed in page | bytes | prices (first 8) |
|---|---|---|---|
| 1108 CA Sacramento | 1108 | 1,430,774 | 29.99, 13.49, **10.99**, 11.99, 14.99, 13.99, **12.49**, 19.99 |
| 503 TX SA Del Norte | 503 | 1,463,627 | 29.99, 13.49, **12.99**, 11.99, 14.99, 13.99, **12.99**, 19.99 |
| 504 TX SA The Rim | 504 | 1,464,253 | 29.99, 13.49, **12.99**, 11.99, 14.99, 13.99, **12.99**, 19.99 |

Prices move, byte counts move, the echoed `storeId` matches what was asked for, and the
two SA stores agree with each other while differing from CA — the signature of real
regional pricing, not a cosmetic swap. **The go/no-go gate in §"next steps" PASSES.**

### San Antonio store ids

| id | store |
|---|---|
| 503 | San Antonio Del Norte |
| 504 | San Antonio The Rim |
| 520 | Forum |

Harvest route (repeatable for any market): `local_delivery_pages_sitemap.xml` (205 urls,
34 Texas) → `alcohol-delivery-near-me-{City}-{State}` page → scrape
`/store-info/{state-city}/{id}` links. Austin/Dallas/Houston come the same way.

## 8. REMAINING before a scraper is worth writing

**Product identity extraction is not solved.** Prices parse cleanly, but the `href` regex
used in the gate test returned **no** `/p/{productId}` matches, and an earlier attempt
pulled only 51 links out of 613 `href=` occurrences. Prices without a product key are
useless — this is the next thing to nail, and it is a parsing problem, not an access one.
Anchor on `/p/{digits}` and treat the hashed CSS classes as unusable.

## Verdict

**UNLOCKED for access and scoping; blocked only on HTML parsing.** The reusable insight from item 45
(patchright beats Incapsula) is not merely irrelevant here; the browser is the one thing
that reliably gets refused. What remains is ordinary product engineering: find how the
site binds a store to a session over HTTP, and confirm prices actually move when it does.

## If picked up again — next steps, cheapest first

**Constraint learned the hard way: HTTP only. Do not reach for a browser** — §5 shows it
is the one client that gets refused.

1. **Harvest TX store ids from the sitemaps** (gently — one returned 503 after this
   probe's run). `sitemap.xml` indexes 34 sub-sitemaps; find the one carrying
   `/store-info/` URLs and filter `texas-*`. That replaces guessing entirely.
2. **Fetch a Texas `/store-info/{…}/{id}` page** and diff it against the California one.
   Whatever binds a store to a session — a `Set-Cookie` on that response, a form POST, a
   query param that sticks — should be visible in the headers of a plain request.
3. **Prove prices actually move.** Fetch the same category page under a CA store and a TX
   store and compare a known product (e.g. `caymus-cabernet/p/223968750`). If the price
   doesn't change, the scoping isn't real and the whole effort stops there. This is the
   go/no-go gate — do it before writing any scraper.
4. **Only then** assess scraping cost: SSR HTML parsing anchored on the `/p/{productId}`
   URL pattern, paginating category pages. Avoid the hashed CSS classes, and never touch
   `/search/` (robots.txt disallows it).
5. **Re-probe from a datacenter IP** before assuming GitHub Actions can run it — this was
   residential-IP only. If CI is refused, this lands on the mini like everything else,
   but as an HTTP job, not a browser one.

## Not assessed

ToS posture. H-E-B's GraphQL was open and got fenced later; Total Wine's storefront being
readable today says nothing about whether scraping it is permitted. That's a business
decision to make deliberately, not by default.
