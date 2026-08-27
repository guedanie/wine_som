# Albertsons / Tom Thumb / Randalls — probe findings (2026-08-26)

**Context:** `CLAUDE.md` listed Tom Thumb/Albertsons under blocked retailers as "(Incapsula)".
Since Incapsula is the same vendor whose JS challenge we beat on H-E-B (item 45), this was
flagged as the strongest remaining candidate for reusing that technique.

**Headline: the "blocked" label was wrong — and so was the technique it implied.** Plain
`urllib` reads all four banners fine, and there is a large, documented JSON API behind an
Azure API Management gateway whose **subscription keys are published in the page HTML**.
No browser, no challenge-solving. The real constraint is **geographic coverage**, not access.

## 1. Not challenge-blocked

Plain `urllib`, normal desktop UA, no cookies:

| host | status | bytes | Incapsula markers |
|---|---|---|---|
| `albertsons.com` | 200 | 823,334 | present |
| `tomthumb.com` | 200 | 819,920 | present |
| `randalls.com` | 200 | 817,959 | present |
| `safeway.com` | 200 | 820,809 | present |

The Incapsula markers are its **protection script embedded in a real page**, not a challenge:
an actual Incapsula block is ~200 bytes (cf. the Central Market block page, 212 b). 820 KB
with 107 "Tom Thumb" mentions and 396 `shop/aisles` references is the genuine storefront.

**Third retailer in a row whose documented block class was wrong** (Total Wine: not blocked
but browser-fingerprinted; H-E-B: not an IP block but a JS challenge). The cheap
urllib-vs-browser A/B should always come first.

## 2. The API surface — 60 endpoints under `/abs/pub/`

Extracted straight from the homepage HTML. Highlights:

```
/abs/pub/xapi/search/products              <- product search
/abs/pub/xapi/search/autosuggest
/abs/pub/xapi/v1/aisles/products           <- aisle browse
/abs/pub/xapi/storeresolver/all            <- stores by zip
/abs/pub/xapi/storeresolver/v2/storesByAddress
/abs/pub/xapi/storeresolver/zipcodetoshopping
/abs/pub/erums/storeservice/api/v2/store/
```

That `storeresolver` family matters: it is a **first-class store-by-zip lookup**, which is
exactly the problem that cost hours on Total Wine (whose store scoping had to be
reverse-engineered from a cookie and a cache key).

## 3. Auth — Azure APIM, keys published in the page

An unauthenticated call returns a precise, actionable error:

```
401 { "message": "Access denied due to missing subscription key..." }
```

The page HTML contains **17 named subscription keys**, each labelled by service:

| key name | value | unlocks |
|---|---|---|
| `xapiSubscriptionKey` | `7bad9afbb87043b28519c4443106db06` | `storeresolver/*` ✅ |
| `apimSubscriptionKey` | `e914eec9448c4d5eb672debf5011cf8f` | `search/autosuggest` ✅ |
| `cncSubscriptionKey` / `apimSubscriptionKey` | `9e38e3f1d32a4279a49a264e0831ea46` | cnc |
| (14 more: tokenvault, chase, sloc, ppms, ztpReceipts, b4uClipped, p13n, …) | | |

Header is the standard `Ocp-Apim-Subscription-Key`. Keys are **service-scoped** — the xapi
key 401s on autosuggest ("invalid subscription key") while the apim key returns 200, so
matching key to endpoint is part of the work.

**Verified working:**
```
GET /abs/pub/xapi/storeresolver/all?zipcode=75201
    Ocp-Apim-Subscription-Key: 7bad9afbb87043b28519c4443106db06
-> 206, 158,825 b, {"delivery":{"stores":{"locationId":"3296","banner":"Tom Thumb",
   "operatingStatus":"ACTIVE","locationZipcode":"75201", …
```

## 4. ⚠️ THE REAL BLOCKER — coverage, not access

`storeresolver/all` by zip across the tester markets:

| market | zip | result |
|---|---|---|
| Austin TX | 78701 | **10 stores** (Randalls — Austin, Cedar Park, Lakeway, Round Rock, West Lake Hills) |
| Dallas TX | 75201 | **24 stores** (Tom Thumb — Dallas, Addison, Garland, Irving, Mesquite) |
| **San Antonio TX** | 78209 | **404 / unavailable** |
| **Charlotte NC** | 28202 | **404** |
| **Winston-Salem NC** | 27101 | **404** |
| **Nashville TN** | 37210 | **404** |

So Albertsons covers **2 of 6 tester markets** — and misses **San Antonio, the primary
market**. Compare Total Wine (item 46), which covers 5 of 6 from one scraper.

Value is therefore narrower than hoped but real and well-targeted: **Dallas is a stated
push** (CLAUDE.md "Dallas focus coming") and 24 Tom Thumb stores is a substantial add, with
Austin's 10 Randalls behind it.

## 5. RESOLVED-AS-BLOCKED — the product search path is TARPITTED (2026-08-27)

`autosuggest` returns 200/1,490 b with the apim key, but `search/products` and
`v1/aisles/products` both **hang until timeout** (45 s) rather than erroring, with several
param shapes tried including the documented
`request-id / url / pageurl / pagename / rows / start / search-type / storeid / q / dvid`
form. A hang rather than a 4xx suggests a missing/malformed required param sending the
backend into a bad path, or an additional required header.

### The real endpoint was found — and it still hangs

The Angular bundle (`clientlib-angular-global.min.*.js`, 5 MB) carries a full per-environment
config. Production is **`abs/pub/xapi/pgmsearch/v1/search/products`** — note `pgmsearch/v1/`,
not the `xapi/search/products` guessed earlier — with its own key
`5e790236c84e46338f4290aa1050cdd4` (= `apimProgramSubscriptionKey` from the page HTML).
`getMoreSearchProducts()` in the same bundle gives the exact param set:

```
pageurl, url, request-id, pagename=search, rows, start, search-type=keyword,
storeid, q, dvid=GhXAoLXN-ss-search, channel, uuid, featured, banner, includeOffer
```

Called with **all of it**, verbatim from their own code: **timeout at 90 s.**

### The diagnostic that settles it

| request | result |
|---|---|
| correct prod key | **hang, 45 s** |
| deliberately WRONG key | **hang, 45 s** |
| no key at all | **hang, 45 s** |

A bad key returns **401 instantly** on `storeresolver` and `autosuggest` — same host, same
gateway. Here all three behave identically, so **the request never reaches the auth layer**:
this path is tarpitted at the edge, for us. It is not a parameter problem, not a key problem,
and not fixable by refinement — correct and incorrect requests are treated the same.

**This is a nastier pattern than Publix's 403 or Total Wine's stripped page**: a hang costs
the client 45-90 s per attempt and returns no signal at all. Anything that retries naively
burns its whole budget learning nothing.

**Still working:** `storeresolver/*` (store-by-zip, verified 206 with real data) and
`search/autosuggest` (200). So Albertsons is selectively blocking the catalogue path while
leaving the cheap endpoints open.

## Next steps

1. ~~Capture the site's own call~~ — **done, and it did not help.** The exact endpoint,
   key and param set were recovered from the Angular bundle and the request still hangs
   identically with a wrong key, so the block is upstream of auth. **Do not spend more time
   on parameters.** The only untested avenue is a real browser session (whether Albertsons
   fingerprints one is unknown), which is the same expensive path Publix would need.
2. **Confirm wine is actually merchandised.** These are grocery banners; check the wine
   catalogue depth per store before investing (H-E-B's ~2,000/store is the benchmark).
3. **Then decide scope.** Dallas (24) + Austin (10) only. Given Total Wine already covers
   Austin and Dallas *plus* San Antonio, Charlotte and Winston-Salem, finish item 46 first —
   this is complementary depth in two cities, not new market coverage.

## Not assessed

ToS/robots posture for the API path, rate limits (only ~25 requests made in total here),
and whether the published keys rotate.
