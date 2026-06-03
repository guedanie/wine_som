# GrapeMinds API — Data Granularity Findings

**Calls used:** ~17 (of 250/month)
**Date:** 2026-06-01

---

## TL;DR

GrapeMinds is **much richer than initial tests suggested**. First-time requests for a wine trigger async AI content generation and return nulls. Subsequent requests return fully populated data. We need a warm-up strategy: hit each wine on import, cache the response, never re-fetch unless stale.

---

## Auth & Technical Notes

- **Auth header:** `Authorization: Bearer <key>` only — `X-API-Key` does NOT work
- **Python urllib/requests:** blocked by Cloudflare TLS fingerprinting — use `curl` via `subprocess`
- **Rate limit:** 60 req/minute
- **Monthly budget:** 250 calls — cache everything aggressively
- **First-request generation:** content fields (`description`, `tasting_notes`, `flavor_profile`, `pairing`) return `null` on first fetch while content is generated async. Re-fetch after ~30–60s to get populated data.

---

## Full Data Schema — Wine Detail (`/wines/{id}`)

Confirmed from Tignanello (id: 9146) and Caymus Napa (id: 113817):

```json
{
  "id": 113817,
  "display_name": "Caymus Vineyards, Cabernet Sauvignon Napa Valley",
  "color": "red",
  "type": "wine",
  "sub_type": "still",
  "residual_sugar": null,
  "producer": {
    "id": 2519,
    "name": "Caymus Vineyards",
    "title": null,
    "display_name": "Caymus Vineyards"
  },
  "region": {
    "id": 22,
    "name": "California",
    "country": "us",
    "language": "en"
  },
  "grapes": [
    { "id": 201563, "name": "Cabernet Sauvignon" }
  ],
  "description": {
    "text": "...(~100 words, English prose description)",
    "text_long": "...(~300 words, long-form)",
    "language": "en"
  },
  "pairing": {
    "text": "...(~100 words)",
    "text_long": "...(~400 words)",
    "language": "en"
  },
  "tasting_notes": {
    "text": "...(~100 words)",
    "text_long": "...(~300 words)",
    "language": "en"
  },
  "flavor_profile": {
    "sweetness": 3,
    "acidity": 4,
    "tannins": 6,
    "alcohol": 8,
    "body": 8,
    "finish": 8
  }
}
```

### Flavor Profile Scale
All fields are integers, 1–10. Perfect for direct preference matching:
- `sweetness` — 1 (bone dry) → 10 (very sweet)
- `acidity` — 1 (flat) → 10 (very tart)
- `tannins` — 1 (silky) → 10 (grippy/astringent)
- `alcohol` — 1 (low) → 10 (high ABV)
- `body` — 1 (light) → 10 (full)
- `finish` — 1 (short) → 10 (very long)

---

## Drinking Period (`/drinking-periods/{wineId}`)

Fully populated for Tignanello after warm-up:

```json
{
  "id": 12791,
  "wine_id": 9146,
  "lang": "en",
  "from": 8,
  "to": 25,
  "statement": "Robust structure and substantial tannins require extended cellaring; optimal complexity typically develops after 8 years...",
  "young": "Vibrant cherry and dark plum, prominent cedar and warming spice, crisp acidity with firm tannins...",
  "ripe": "At maturity, layered notes of dried cherry, supple leather, tobacco leaf...",
  "storage": "Maintain consistent temperature of 12–14°C, relative humidity 60–70%, store bottles horizontally..."
}
```

Fields: `from` + `to` (years), `statement`, `young`, `ripe`, `storage`

Also returns `"generating": true` + error on first request — re-fetch after 30–60s.

---

## Region Data (`/regions`, `/region-insights/{id}`)

- **2,165 total regions** globally
- Region detail: `{ id, name, country (ISO-2), language }`
- Region insights: also async-generated on first request
- Useful for: region educational content, terroir descriptions

---

## Bulk vs. Per-Wine Requests

### List endpoint — `/wines?per_page=N`
- Returns up to **100 wines per request**
- **Summary fields only:** `id`, `display_name`, `color`, `type`, `sub_type`, `producer`, `region`
- No `flavor_profile`, `tasting_notes`, `description`, `pairing`, or `grapes`
- Database total: **264,737 wines** across 88,246 pages (at 100/page)
- Useful for: building a name → ID lookup table, browsing catalog

### Search endpoint — `/wines/search?q=...&limit=N`
- Returns up to **100 results per request**
- Same summary-only fields as the list endpoint
- Use this to match wine names from the CSV to GrapeMinds IDs

### Detail endpoint — `/wines/{id}`
- Always **one wine per request**
- Returns the full enriched payload (flavor profile, tasting notes, description, pairing, grapes)

### Call budget per wine (full enrichment)

| Goal | Calls |
|---|---|
| Name → ID match | 1 (`/wines/search`) |
| Full enrichment (flavor, notes, description) | 1 (`/wines/{id}`) |
| Drinking window | 1 (`/drinking-periods/{id}`) |
| **Total per wine (full)** | **3** |
| **Total per wine (no drinking window)** | **2** |

With 250 calls/month: ~83 fully enriched wines (3 calls) or ~125 wines without drinking window (2 calls).

### On-demand enrichment strategy (recommended)

Don't enrich everything on import — 250 calls won't cover a large CSV upfront.

1. Import all CSV wines to DB (zero API calls)
2. Enrich on first recommendation hit: search → detail → drinking period
3. Cache permanently in `wine_details` — never re-fetch unless `last_enriched_at` > 30 days
4. 250 calls/month easily covers organic usage as real users drive enrichment

---

## What's Actually Available vs. Missing

| Field | Available | Notes |
|---|---|---|
| Wine identity (name/producer/region) | ✅ | Reliable on first call |
| Grape varieties | ✅ | Populated after warm-up (empty on first call) |
| Description (short + long) | ✅ | After warm-up — English content |
| Tasting notes (short + long) | ✅ | After warm-up |
| Food pairing (short + long) | ✅ | After warm-up |
| Flavor profile (6-axis numeric) | ✅ | Perfect for preference matching |
| Drinking window (from/to/young/ripe) | ✅ | After warm-up |
| Vintage-level data | ❌ | Not in schema — use Wine-Searcher |
| Critic scores | ❌ | Not in schema — use Wine-Searcher |
| Retail pricing / store availability | ❌ | Not in schema — use Wine-Searcher / scrapers |

---

## Revised Role in the Stack

GrapeMinds is now the **primary wine knowledge layer** — not just identity resolution.

| Data Need | Source |
|---|---|
| Wine identity + region + producer | GrapeMinds search |
| Grape varieties | GrapeMinds detail |
| Tasting notes + description | GrapeMinds detail |
| Flavor profile (numeric, for scoring) | GrapeMinds detail |
| Drinking window | GrapeMinds drinking-periods |
| Vintage quality + critic scores | Wine-Searcher |
| Retail pricing + store locations | Wine-Searcher / scrapers |
| Community flavor tags (granular) | Apify/Vivino (still useful as supplement) |

---

## Warm-Up Strategy (Important)

Because content generates async on first request:

1. On wine import (CSV seed or scraper result): fire a GrapeMinds search → get `wine_id`
2. Fire `/wines/{id}` to trigger generation — store whatever comes back (may be null fields)
3. Queue a Celery task to re-fetch `/wines/{id}` and `/drinking-periods/{id}` after 60s
4. Persist fully populated result to `wine_details` table
5. Never re-fetch from GrapeMinds after cached — only refresh if `last_enriched_at` > 30 days

This keeps us well within 250 calls/month for the seed dataset.

---

## Python Integration (Cloudflare workaround)

```python
import subprocess, json

def grapeminds_get(path: str, api_key: str) -> dict:
    result = subprocess.run([
        "curl", "-s",
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Accept-Language: en",
        f"https://api.grapeminds.eu/public/v1{path}"
    ], capture_output=True, text=True, timeout=15)
    return json.loads(result.stdout)
```
