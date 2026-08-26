# H-E-B / Central Market GraphQL — Incapsula outage (2026-08-25)

**Verdict: BLOCKED by an Imperva Incapsula JavaScript challenge on the product
query. NOT the datacenter-IP block previously assumed — fails from residential
IPs too. Cookie-priming + curl is necessary but NOT sufficient.**

## Impact (why this matters)

- **H-E-B and Central Market have failed every weekly scrape for 5 straight
  weeks** (last success 2026-07-19). H-E-B: `502 Bad Gateway`; Central Market:
  0 records — both are HEB-owned and share `heb.com/graphql`.
- **H-E-B inventory is now ~36 days old → past the 10-day staleness window →
  benched from recommendations.** San Antonio testers currently get **zero
  H-E-B wines**, and H-E-B was the single biggest SA source (~39k records, ~1,999
  wines/store).
- `verify_scrape_runs.py` correctly marked these failed (and Slack-alerted), but
  the failures went unactioned for a month.

## Correcting the earlier hypothesis

`scripts/probe_heb_graphql.py` (written ~2026-08-18) guessed this matched the
Spec's/Twin Liquors/Vivino pattern — *datacenter IPs blocked, residential fine —
so move it to the mini.* **That is wrong.** The probe fails identically from a
residential IP. The mini will not fix it.

## What's actually happening (evidence, 2026-08-25, residential IP)

HEB moved `/graphql` behind **Imperva Incapsula** (added ~2026-07-26). Three
layers, each defeating a naive fix:

1. **Cold POST is rejected.** Bare `POST {}` → **401**; the scraper's query → **502**.
2. **A storefront GET issues provisional cookies.** `GET https://www.heb.com/`
   sets `incap_ses_*` + `visid_incap_*`. A **light** query (`{ productSearch(... ){ total records { id displayName } } }`) sent WITH that jar returns **200, total=1999** — so cookie-priming helps.
3. **The real query trips a JS challenge.** The actual scraper query (full
   `_PRODUCT_FIELDS`: SKUs, contextPrices, inventory, …, limit 60) returns
   **502 with an Incapsula JavaScript challenge page** (`_Incapsula_Resource`
   `<script>`), **consistently (4/4)**. The provisional cookie is not enough;
   Incapsula demands the client execute its obfuscated JS to earn the real
   access token (`reese84`/`___utmvc`-class cookie). curl and Python's urllib
   have no JS engine, so they cannot pass.

Also: **Incapsula fingerprints the HTTP client** — the priming GET returns a
clean 200 to `curl` but a **403 JS challenge to Python urllib**. So any real fix
must at minimum use curl (the repo's WAF pattern), not urllib.

## What was tried

- **urllib cookie-jar priming** — urllib itself gets 403-challenged on the prime;
  the challenge cookies then make the POST 502. Dead end.
- **curl-subprocess prime + POST** — reliable for the *light* probe query (3/3
  200s), but the *real* full-fields query is JS-challenged 4/4. Architecturally
  right (client fingerprint + cookie jar, matching Spec's/Twin Liquors), and it's
  the foundation any real fix builds on — but on its own it does not restore the
  scrape. **Not committed** (would masquerade as a fix).

## Fix options (a decision, not a quick patch)

1. **Headless browser + stealth** (Playwright/Camoufox + `playwright-stealth`):
   load heb.com, let it solve the Incapsula JS challenge, harvest the earned
   cookie, then hand it to the existing curl GraphQL calls (which work with a
   *real* cookie). The repo's stated stack is explicitly **"no Playwright"**, so
   this is a deliberate reversal. Runs on the mini (residential IP). Brittle to
   Incapsula updates.
2. **Anti-bot / residential-proxy service** (Bright Data / Oxylabs / ScraperAPI
   "Incapsula unblocker"): ~$0.01–0.05/request solves the challenge for us.
   ~39k records ≈ a few dollars/week. Lowest engineering effort, ongoing cost.
3. **Accept the loss** and lean on the other SA sources (Central Market shares
   this fate; Spec's ~63k, Twin Liquors, and the indies still work). Weakest for
   testers — H-E-B is the dominant SA grocer.

**Recommendation:** option 1 or 2 (H-E-B is too big an SA source to drop). Both
reuse the working curl GraphQL path — the only missing piece is a *JS-solved*
Incapsula cookie.

## Secondary finding (independent of the block)

The configured Central Market store `61` returns `total=0` even when the API is
reachable — store 61 appears no longer e-commerce-enabled. Store `51` returns
`total=157`. When CM scraping is restored, revisit the `CM_STORES` IDs.
