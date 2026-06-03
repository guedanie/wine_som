# Wine App — API Stack Summary & MVP Recommendation

## API Key Status (as of 2026-06-03)

| API | Status |
|---|---|
| Anthropic Claude | ⬜ Not yet added to .env |
| GrapeMinds | ✅ Active — 250 calls/month, ~17 used |
| Wine-Searcher | 🕐 Requested — key pending |
| VineRadar | ⏳ Unreleased — on waitlist, timeline unknown |
| Apify (Vivino scraper) | ⬜ Not yet set up |
| GWDB | ⬜ Not yet emailed |
| Instacart | ❌ Not accepting new developer accounts — removed from plan |

---

## Recommended MVP Stack

For the wine recommendation app, the recommended approach is a **layered API strategy** — no single source covers all four pillars (flavor profile, vintage, region/sub-region, and local availability). The stack below covers all of them with minimal cost to start.

---

## Tier 1 — Core APIs (Build Around These)

### 1. GrapeMinds
**Site:** [grapeminds.eu/developers](https://grapeminds.eu/developers)
**Cost:** Free to start (14-day trial, no credit card required); paid tiers for scale

**What's available:**
- 260,000+ wines in the database
- Wine descriptions and tasting notes (multilingual: EN, DE, FR, IT)
- Grape variety profiles — origins, characteristics, flavor expectations
- Region and sub-region data
- Drinking windows and storage recommendations
- Full-text fuzzy search across wines, producers, and regions
- AI-powered wine label recognition (photo → matched wine)
- REST API with clean, well-documented endpoints
- Explicitly designed for AI/ML application integration

**Best for:** Primary wine knowledge layer — region, sub-region, grape variety, tasting notes, drinking window

**Gaps:** Vintage-specific quality ratings; retail pricing and availability

---

### 2. Wine-Searcher API
**Site:** [wine-searcher.com/trade/api](https://www.wine-searcher.com/trade/api)
**Cost:** 100 free calls/day trial; paid tiers for higher volume

**What's available:**
- Vintage availability and sell-out status per wine
- Retail pricing: min, max, and average per wine/vintage
- Aggregated critic score (normalized from Robert Parker, Wine Spectator, Jancis Robinson, and others onto 100-point scale)
- Store-level data: merchant name, physical address, zip code, GPS coordinates, contact details, URL
- LWIN code system: LWIN-7 (wine identity), LWIN-11 (includes vintage), LWIN-18 (includes bottle size)
- 20 million+ listings across 38,000 stores in 126 countries
- Available vintages per wine — including which are sold out vs. active

**Best for:** Vintage data, critic scores, price benchmarking, and merchant/store lookup by location

**Gaps:** Flavor profiles; tasting notes; region educational content

---

## Tier 2 — Supplementary Sources

### 3. VineRadar
**Site:** [vineradar.com](https://www.vineradar.com)
**Cost:** Free to start, no credit card required

**What's available:**
- 500+ grape variety profiles — origins, characteristics, typical flavor profiles
- Vineyard-level data including GPS coordinates and terroir descriptions
- Vintage comparison data and price trend insights
- Expert scores and user reviews
- Flexible filtering: region, grape variety, price range, ratings
- Sub-100ms response times; SOC 2 compliant
- REST API with developer-friendly endpoints

**Best for:** Grape variety depth and terroir-level detail as a supplement to GrapeMinds; good fallback if GrapeMinds misses a varietal

**Gaps:** Newer entrant — coverage breadth is still developing compared to GrapeMinds

---

### 4. Apify Vivino Scrapers
**Site:** [apify.com/mrbridge/vivino-powerful-scraper](https://apify.com/mrbridge/vivino-powerful-scraper)
**Cost:** ~$0.003 per result (pay-per-result, no subscription required)

**What's available:**
- Vivino's full taste profile: body, acidity, tannins, sweetness, fizziness
- Primary and secondary flavor keywords with mention counts (e.g. "dark cherry ×847", "tobacco ×312")
- User ratings and reviews (up to 100 per wine)
- Regional statistics from the Vivino community
- Vintage-level data
- Market-specific pricing by destination/currency
- Filter by region (Burgundy, Bordeaux, Napa, etc.), grape variety, producer
- 15+ million wines in Vivino's underlying database
- Outputs to JSON, CSV, or Excel

**Best for:** Flavor keyword enrichment — the community-sourced flavor tags are uniquely granular and useful for preference matching. Use as an enrichment layer for wines not fully covered by GrapeMinds.

**Gaps:** Not an official Vivino API — dependent on scraper infrastructure staying current with Vivino's site structure. Use with appropriate caching to minimize re-scraping.

---

## Tier 3 — Watch List (Not MVP)

### 5. Wine Folly / Global Wine Database (GWDB)
**Site:** [db.wine](https://www.db.wine) / [gwdb.io](https://gwdb.io)
**Cost:** Free for wineries; developer API access by application only (`hello@gwdb.io`)

**What's available:**
- Producer-verified wine data (wineries self-submit, keeping data accurate)
- Region and appellation data
- Vintage-specific information and tech sheets
- Winery profiles and digital assets
- Structured data designed for API integration and ML applications
- 13,000+ wineries globally; strong California coverage

**Why it's not MVP:** API access is not self-serve — requires direct application and approval. Coverage outside California is thin. North American database is strong but regional producers (e.g. Texas Hill Country) are underrepresented. Apply for access now so it's available to layer in post-launch.

**Best long-term use:** Regional educational content and producer-verified vintage tech sheets as a quality layer on top of GrapeMinds data.

---

## Data Coverage Matrix

| Data Point | GrapeMinds | Wine-Searcher | VineRadar | Apify/Vivino | GWDB |
|---|---|---|---|---|---|
| Wine name / producer | ✅ | ✅ | ✅ | ✅ | ✅ |
| Region | ✅ | ✅ (single level) | ✅ | ✅ | ✅ |
| Sub-region / appellation | ✅ | ⚠️ lowest level only | ✅ | ✅ | ✅ |
| Grape variety | ✅ | ✅ | ✅ deep | ✅ | ✅ |
| Vintage data | ⚠️ basic | ✅ strong | ✅ | ✅ | ✅ |
| Vintage quality ratings | ❌ | ✅ aggregated | ✅ | ⚠️ community | ❌ |
| Flavor profile (structured) | ✅ | ❌ | ✅ | ✅ granular tags | ⚠️ |
| Structure (tannin/acid/body) | ✅ | ❌ | ✅ | ✅ | ❌ |
| Drinking window | ✅ | ❌ | ❌ | ❌ | ⚠️ |
| Critic scores | ❌ | ✅ aggregated | ✅ | ⚠️ community | ❌ |
| Retail pricing | ❌ | ✅ strong | ✅ | ✅ market-specific | ❌ |
| Store-level availability | ❌ | ✅ + GPS | ❌ | ⚠️ | ❌ |
| Label recognition (photo) | ✅ | ⚠️ app only | ❌ | ❌ | ❌ |
| Cost to start | Free | 100 calls/day free | Free | ~$0.003/result | Apply only |

---

## Recommended MVP Integration Architecture

```
User Preference Input
        ↓
[Recommendation Engine — Claude API]
        ↓
┌─────────────────────────────────────┐
│         Data Layer                  │
│                                     │
│  GrapeMinds  →  Wine knowledge      │
│  (region, grape, tasting notes,     │
│   drinking window)                  │
│                                     │
│  Wine-Searcher →  Vintage + price   │
│  (critic score, store locations,    │
│   availability by zip)              │
│                                     │
│  Apify/Vivino  →  Flavor tags       │
│  (community taste profile,          │
│   used for preference matching)     │
│                                     │
│  H-E-B CSV / Scrapers               │
│  (local San Antonio retail data,    │
│   seeded from existing dataset)     │
└─────────────────────────────────────┘
        ↓
Matched wines ranked by:
  1. Local availability (zip proximity + in-stock)
  2. Flavor profile match to user preferences
  3. Budget fit
  4. Vintage quality score
        ↓
Sommelier-style recommendation output
```

---

## Next Steps

1. **Start with GrapeMinds** — register for free API key at [grapeminds.eu/developers](https://grapeminds.eu/developers) and test against your existing wine names from the H-E-B CSV
2. **Apply for Wine-Searcher trial** — request API key at [wine-searcher.com/trade/api](https://www.wine-searcher.com/trade/api); 100 free calls/day is enough for MVP validation
3. **Set up Apify account** — create an account at [apify.com](https://apify.com) and test the Vivino scraper actor against 20–30 wines from your dataset to validate flavor tag quality
4. **Email GWDB now** — even if it's not MVP, contact `hello@gwdb.io` to get in the access queue
5. **Seed your local DB** from the existing H-E-B CSV before touching any live APIs — validate the recommendation engine logic against real local data first