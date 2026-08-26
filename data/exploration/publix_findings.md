# Publix — probe findings (2026-08-26)

**Context:** `CLAUDE.md` lists Publix under blocked retailers as "(Akamai)". Re-probed
because the previous three retailers' block labels all turned out to be wrong (H-E-B was a
JS challenge not an IP block; Total Wine is browser-fingerprinted not blocked; Albertsons
isn't blocked at all). **Strategic interest: Publix is Southeast and reaches Nashville —
the one tester market Total Wine misses entirely.**

**Headline: this label is CORRECT.** Publix is genuinely Akamai-blocked where the data
lives. It is the first of the four re-probes to hold up.

## 1. `www.publix.com` reads fine — but that's the shell, not the data

| URL | status | bytes | note |
|---|---|---|---|
| `www.publix.com/` | 200 | 588,289 | real homepage, Next.js |
| `www.publix.com/robots.txt` | 200 | 259 | see below |
| `www.publix.com/sitemap.xml` | 200 | 904 | 7 product sitemaps + a pages sitemap |
| `sitemap_products1.xml` | 200 | — | **10,000 product URLs** (29 wine-ish in the first file alone) |

The homepage carries a `__NEXT_DATA__` blob (284 KB) but it is layout/config only —
`storeNumber` appears 3×, `productId` **0×**. No catalog.

## 2. Product pages are a bot-challenge stub

Fetching a real wine product URL from the sitemap
(`/pd/livingston-cellars-cabernet-sauvignon-red-wine/RIO-PCI-105666`) returns **HTTP 200 —
and 2,378 bytes of Akamai Bot Manager challenge**:

```html
<meta http-equiv="refresh" content="5; URL='/pd/…?bm-verify=AAQAAAAN_____2XCiK70JWq…'" />
<script> var i = 1787785646; var j = i + Number("4370" + "93075"); </script>
```

`bm-verify` + the arithmetic-JS shim is Akamai Bot Manager's interstitial: it wants the
client to execute JS and re-request with the token. No `__NEXT_DATA__`, no price, no
product name. **A 200 that contains nothing** — the same "convincing success" shape seen
three times today (H-E-B's page title, Total Wine's default store, Total Wine's stripped
page), and the reason a naive scraper would have recorded thousands of empty rows.

## 3. The API subdomain is hard-blocked

The homepage config names the catalog API:

```
graphQlApiUrl: https://services.publix.com/search/api/search/storeproductssavings
```

Every attempt returns **403 Access Denied** (Akamai's HTML, not a JSON error):

| attempt | result |
|---|---|
| `GET  /search/api/search/storeproductssavings?q=wine` | **403** |
| `POST` with a REST-shaped body | **403** |
| `POST` with a GraphQL-shaped body | **403** |

For contrast, a wrong path on the same host (`/storelocator/api/v1/storesearch`) returns a
clean JSON `404` — so the host is up and routing; the catalog endpoint specifically is
denied. That is a deliberate block, not a missing parameter.

## 4. robots.txt

```
Disallow: /account?  /account/  /b2clogout  /login-callback  /mfa
Disallow: /search?*
Disallow: /feature-down
Sitemap:  https://www.publix.com/sitemap.xml
```

Product (`/pd/…`) and shop paths are **not** disallowed, and the product sitemaps are
advertised — but that is moot while the pages themselves serve a bot challenge.

## Verdict

**Genuinely blocked — do not pursue with HTTP.** Unlike H-E-B (JS challenge, solvable with
a headed patchright browser), Publix blocks at *both* layers we would need:

- product pages → Akamai Bot Manager `bm-verify` interstitial
- catalog API → 403 at the edge

Akamai Bot Manager is a materially harder target than Incapsula: it fingerprints via
collected sensor telemetry (`_abck`), not a one-time JS solve, so the item-45 patchright
recipe is not a drop-in. Untested here, and not worth testing before the cheaper work is
done.

## Recommendation

**Don't.** The value case doesn't justify the difficulty:

- Publix's draw was **Nashville**, and Nashville is already the best-covered market —
  35 Kroger stores + Harvest (item 20), deliberately deepened 2026-08-01.
- Wine selection at a grocery banner is shallow next to Total Wine (5,947 wines/store) or
  even H-E-B (~2,000/store).
- Total Wine (item 46) already covers 5 of 6 tester markets and is built but unfinished;
  Albertsons (item 47) is unblocked and needs only a param fix for Dallas + Austin depth.

Both of those are strictly cheaper per wine gained. Revisit Publix only if Nashville
coverage ever becomes a real gap — and then price the Akamai work honestly first.

## Not assessed

Whether patchright/stealth clears Akamai Bot Manager here (deliberately untested); whether
Publix even merchandises wine online in TN (state law permits grocery wine since 2016, but
online availability was never reached); rate limits (only ~12 requests made).
