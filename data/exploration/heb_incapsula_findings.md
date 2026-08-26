# H-E-B / Central Market GraphQL — Incapsula outage (2026-08-25)

**Verdict: Imperva Incapsula JavaScript challenge on the product query — NOT the
datacenter-IP block previously assumed (fails from residential too), and curl/
urllib CANNOT solve it. SOLVED in a spike (2026-08-25) with `patchright` (patched
Playwright, headed) — see "SOLVED" below. Build + mini deployment pending
(item 45).**

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

## SOLVED — patchright (patched Playwright), headed (spike 2026-08-25)

Vanilla Playwright Chromium is hard-blocked by Incapsula (`errorCode 15`,
`incidentId`) headless AND headed — it fingerprints the CDP/automation tells.
**`patchright`** (drop-in patched Playwright that strips `Runtime.enable`/CDP
tells; reuses the cached Chromium) clears it with this exact recipe:

  - `launch_persistent_context(profile_dir, headless=False, no_viewport=True)`
    — headed, persistent profile, no viewport (patchright's max-stealth config;
    headless still gets errorCode-15 blocked).
  - `page.goto(home, wait_until="domcontentloaded")` — NOT `networkidle` (the SPA
    never idles → 60s timeout).
  - wait ~6s for the challenge JS to run + auto-reload; `title != ""` == cleared
    (the real "H-E-B | Curbside Pickup…" title appears).
  - POST `/graphql` from `page.evaluate` (in-browser `fetch` carries the solved
    `reese84`+`incap_ses` cookies AND the real browser fingerprint) → **200**.

Result (`scripts/spike_heb_playwright.py`): HEB store 567 → total=1999; CM store
51 → total=157, both from one solved session.

### Build path (item 45)
1. Add `patchright` to backend deps; browser already cached on the mini.
2. Rewrite HEB/CM fetch to run through one solved persistent browser session:
   solve once, then paginate the productSearch POSTs via `page.evaluate` (all
   in-browser). Re-solve (reload home) if a page starts 401ing mid-scrape.
3. **Deployment risk (unverified from dev):** it must run HEADED, which needs a
   GUI/Aqua session on the mini — a launchd *daemon* has no display. Run it from
   a launchd *agent* in the logged-in GUI session (the mini already runs GUI
   LaunchAgents for Vivino/extraction), or via `caffeinate`/an always-logged-in
   session. Confirm on the mini before committing the cron.
4. Slower + heavier than the old urllib path (a browser per run) — fine at weekly
   cadence. Fix CM store IDs (61→0, 51→157) when wiring CM back up.
