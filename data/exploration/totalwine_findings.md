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

## 8. SOLVED 2026-08-26 — parsing works; identity from JSON-LD, price from the tile

Prototype: `backend/scripts/probe_totalwine_parse.py`. **24/24 products with
`product_id` + `name` + `price`, on every store tested.**

**Identity comes from JSON-LD, not the DOM.** Each category page carries
`<script data-rh="true" type="application/ld+json">` holding an `ItemList` of 24 products
with a canonical `url` (→ `/p/{productId}`) and `name`. (The earlier regex missed this
because the tag has a `data-rh="true"` attribute *before* `type=` — it is not a bare
`<script type="application/ld+json">`.)

**Price comes from the tile, bounded by JSON-LD anchors.** JSON-LD carries no price. Each
product's canonical path *does* appear as an `href`, but with a `?s={storeId}&igrules=true`
query string — which is why an exact-path match found 0/24. Matching `path + r'\?s=\d+'`
finds 24/24, and those offsets bound each tile; the price is the first `price__*` inside.
The hashed CSS classes are used only *within* an already-established tile, never to find
one, so a frontend rebuild degrades a price to `None` rather than mis-pairing it.

### The scoping is real — proven on price, not on markers

Same 24 products, three stores, one run:

| product | SA (503) | CA (1108) |
|---|---|---|
| 223968750 Caymus | **$68.99** | $66.97 |
| 20095750 | **$47.99** | $54.99 |
| 231443750 Olema Sauv Blanc | **$12.99** | $15.99 |
| 110475750 | **$19.49** | $19.99 |
| 93152750 | **$22.99** | $20.99 |

**8 of 24 priced differently**, and the two San Antonio stores (503, 504) agree with each
other while both differ from California. Vintages differ too (Mina Mesa is "2023" in SA,
unlabelled in CA), i.e. genuinely different inventory, not a price overlay.

## 9. CRITICAL — the store cookie is silently ignored under load

**The single most important operational fact about this target.** Past some request rate,
Total Wine stops honouring `twm-userStoreInformation` and serves the DEFAULT California
store (1108) — with **HTTP 200, no 429, no error, no marker**. Measured in one session:

| condition | result |
|---|---|
| paced run, 8 requests ~1.5s apart | **8/8 correctly scoped to 503** |
| immediately after a burst | **4/4 returned 1108** despite asking for 503 |
| after a 120s pause | correctly scoped again (503, 97 "San Antonio" mentions) |

An unguarded scraper would therefore fill the database with **California prices labelled
as San Antonio** — silently, at 200 OK. That is precisely the false-availability class
items 39/40/44 exist to prevent, and it is worse than an outage because nothing looks wrong.

### Root cause (headers, 2026-08-26)

```
vary:         Accept-Encoding, X-UA-Device, Origin      <-- NO Cookie
x-served-by:  cache-iah17222-IAH, cache-iah17269-IAH    <-- Fastly, Houston POP
x-cache:      MISS, MISS
```

**`Cookie` is absent from `Vary`.** Total Wine is behind Fastly and the cache is told to
vary on encoding/device/origin but *not* on cookies — so nothing in the caching layer is
obliged to keep per-store responses separate, and a response rendered for one store can be
served to a request carrying a different store cookie. Store **1108 is the origin default**,
so any non-personalised path (throttled render, shared cached copy) lands on Sacramento —
at 200, because from the CDN's view nothing failed.

**It escalates to a hard block.** A run of rapid requests: 9 consecutive correct (all
`x-cache: MISS`), then request 10 → **HTTP 403 Forbidden**. So throttling has two faces —
silent default-store content, then an outright 403.

*Honest limit of this evidence:* no `x-cache: HIT` was ever caught serving California, so
"cached cross-store response" vs "origin fallback under pressure" is not distinguished. The
missing `Cookie` in `Vary` is confirmed and makes the former structurally possible; the
rate-limit escalation is confirmed directly.

**Practical ceiling: ~9-10 requests before a 403.** At 24 products/page that is ~240
products per burst, then a mandatory cooldown — the real input to the crawl-budget question.

**Mandatory guard, implemented in the prototype:** every response is checked with
`_echoed_stores(html) == {store_id}` and *refused* (`WrongStore`) otherwise, with a 120s
backoff between attempts and ~8s pacing between pages. Never trust a 200.

(This is the same lesson as the H-E-B `_w_solve` bug in item 45: a plausible-looking
success signal — a page title there, a 200 here — is not proof the thing you needed
actually happened. Validate the specific property you depend on.)

## Verdict

**Technically solved end to end** — access (plain HTTP), store scoping (forgeable cookie),
identity + price extraction (JSON-LD + tile) all work, verified against three stores with
real price deltas.

**The open question is now operational, not technical:** the silent de-scoping under load
(§9) sets a hard ceiling on crawl rate. 24 products/page at ~8s pacing plus a 120s penalty
on every de-scope, across N categories x M stores, is the number that decides whether this
is worth building. Estimate that before writing a scraper — and never relax the store
guard to go faster. The reusable insight from item 45
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


---

## 10. RESOLVED 2026-08-26 — `?storeId=` + `pageSize` retire the problem

Two findings that together turn this from "slow and dangerous" into "ordinary".

**Scope via the URL, not the cookie.** `?storeId={id}` on the category URL scopes the same
24 products and reproduces every known price delta — Olema $12.99 vs $15.99, Caymus $68.99
vs $66.97, Mina Mesa $12.99 vs $10.99, 8 of 24 differing, identical to the cookie method.
Because the store is now part of the URL it is part of the **cache key**, so a
`?storeId=503` request structurally cannot be served the Sacramento default. This retires
the silent-wrong-data failure rather than guarding against it.

Also settled while getting there:
- **The CA default is hard-coded, not geographic.** A San Antonio residential IP with no
  cookie still returns 1108. It is a system default, not a failed geo-lookup.
- **`?s=` scopes product DETAIL pages only** (`/p/{id}?s=503` → $12.99 vs `?s=1108` →
  $15.99, no cookie needed) — but NOT category pages. One product per request, so it is a
  fallback for spot-checks, not a crawl strategy.
- **Cache-busting was a dead end.** Every response was `x-cache: MISS` with and without a
  bust param, and a control at identical pacing was 8/8 clean without it — there was no
  cache contamination to bust. The real variable was always request *rate*.

**`pageSize` scales.** The default 24 is not a ceiling:

| pageSize | products returned | bytes |
|---|---|---|
| 24 (default) | 24 | 1.43 MB |
| 48 | 48 | 1.72 MB |
| 100 | 100 (99 priced) | 2.34 MB |
| 200 | **200** (199 priced) | 3.30 MB |

### Cost model

The wine category reports **`totalResults: 5947`**. `page=2` returns 24 entirely different
products (0 overlap with page 1), so pagination is straightforward.

| strategy | requests per store | at ~5s pacing |
|---|---|---|
| pageSize=24 | 248 | ~21 min |
| **pageSize=200** | **30** | **~2.5 min** |

At `pageSize=200`, 38 Texas stores ≈ **1,140 requests ≈ 1.6 hours** for the entire Texas
wine catalog — a normal overnight job, comparable to the existing Vivino/extraction agents,
not the multi-hour crawl feared in §9.

Caveats to carry into a build: ~1 product per large page loses its price (199/200) and
should be re-fetched individually via `/p/{id}?s={store}`; 3.3 MB per request is heavy, so
stream/parse rather than holding many in memory; and the rate limit (~10 rapid requests →
403) still applies, so pacing remains mandatory even though the request count is now small.


---

## 11. ⚠️ CORRECTION 2026-08-27 — it is PerimeterX, and we are IP-blocked

The rested crawl test (the measurement §10 said would decide the crawl budget) never got a
page: **HTTP 403 in 0.2 s on the first request**, after ~14 hours of no traffic.

Scope check — every path is blocked, not just deep pagination:

| request | result |
|---|---|
| `/` (homepage) | **403** |
| `/wine/c/c0020` | **403** |
| `?storeId=503` / `&pageSize=200` | **403** |
| `/robots.txt` | 200 |

The 403 body identifies the vendor:

```html
<meta name="description" content="px-captcha">
window._pxAppId  = 'PXFF0j69T5';
window._pxHostUrl = '/FF0j69T5/xhr';
Retry-After: 0
```

**PerimeterX** (now HUMAN Security), not Imperva. That changes the whole picture:

- Yesterday's "stripped page, then intermittent, then 403" was **PX escalating a risk score**,
  which I read as ordinary rate limiting. The empty pages were not flaky rendering and not a
  bandwidth throttle — they were an anti-bot system deciding about us in stages.
- An overnight rest did not clear it, so this is **IP reputation**, not a token bucket.
- The pacing work in §10 (45 s/page, 8 s seed) was tuning the wrong variable. You cannot
  pace your way out of a system that is scoring *how you behave*, not *how fast*.

### What still stands

The extraction work is sound and independently verified: `?storeId=` scoping reproduces real
per-store price deltas, JSON-LD gives clean identity, `pageSize=200` works, and **996 real
San Antonio wines** sit in the database with correct prices and varietals. If a block-free
path is ever found, the scraper is ready.

### What does not

The "~1.6 h for the full TX catalog" estimate, the seed-then-crawl schedule, and the
"UNLOCKED / SOLVED end-to-end" framing in §7 and §10. Read those sections as *what the
site permits when it isn't blocking you*, not as a delivery plan.

### Recommendation

**Stop here.** Total Wine sits closer to Publix (item 48) than to H-E-B (item 45): a
commercial anti-bot product that fingerprints continuously rather than a one-time challenge.
Re-probe occasionally — PX scores decay — but do not invest further until a request path
survives a full store without escalating. Note the 996 banked wines will hit the 10-day
staleness bench around **2026-09-05**.
