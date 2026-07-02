# Vivino API Findings

**Probed:** 2026-07-01  
**Method:** curl, no auth, standard browser headers

---

## Endpoint Status

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/explore/explore` | ✅ 200 | The one that works — all data flows through here |
| `GET /api/wines/search` | ❌ 404 | Blocked |
| `GET /api/wines/{id}` | ❌ 404 | Blocked |
| `GET /api/vintages/{id}` | ❌ 404 | Blocked |
| `GET /api/wines/{id}/prices` | ❌ 404 | Blocked |

Only `/api/explore/explore` responds. Everything else is dead.

---

## Working Endpoint: `/api/explore/explore`

```
GET https://www.vivino.com/api/explore/explore
  ?q=<search term>
  &country_codes[]=us          # optional country filter
  &min_rating=3.5              # optional floor
  &price_range_min=15          # optional
  &price_range_max=50          # optional
  &order_by=ratings_count      # ratings_count | ratings_average | price
  &order=desc
  &records_per_page=24         # max 24
  &page=1
```

No auth required. Standard browser headers sufficient (`User-Agent`, `Referer: https://www.vivino.com/`).

**Pagination:** `page` + `records_per_page`. Response includes `records_matched` (e.g. 32,449 for Cab Sauv US). Max 24 per page.

---

## Data Shape (per match)

```json
{
  "vintage": {
    "id": 176907205,
    "year": 2024,
    "name": "El Enemigo Chardonnay 2024",
    "seo_name": "el-enemigo-chardonnay-2024",
    "statistics": {
      "ratings_average": 4.2,
      "ratings_count": 40966,
      "labels_count": 207
    },
    "image": {
      "variations": {
        "bottle_large": "//images.vivino.com/thumbs/...pb_x960.png",
        "bottle_medium": "//images.vivino.com/thumbs/...pb_x600.png",
        "label": "//images.vivino.com/thumbs/...pl_480x640.png"
      }
    },
    "wine": {
      "id": 1272950,
      "name": "Chardonnay",
      "type_id": 2,
      "is_natural": false,
      "winery": { "name": "El Enemigo" },
      "region": {
        "name": "Mendoza",
        "country": { "code": "ar", "name": "Argentina" }
      },
      "taste": {
        "structure": {
          "acidity": 3.33,
          "sweetness": 1.83,
          "tannin": 3.2,
          "intensity": 4.53,
          "fizziness": null
        },
        "flavor": [
          { "group": "black_fruit", "primary_keywords": [{"name": "blackberry"}, {"name": "cassis"}] },
          { "group": "oak",         "primary_keywords": [{"name": "oak"}, {"name": "vanilla"}] },
          { "group": "spices",      "primary_keywords": [{"name": "mint"}, {"name": "licorice"}] },
          { "group": "earth",       "primary_keywords": [{"name": "cocoa"}, {"name": "graphite"}] }
        ]
      }
    }
  },
  "price": {
    "amount": 29.99,
    "currency": { "code": "USD" },
    "url": "https://...",
    "merchant_id": 34781
  },
  "prices": [ /* array of merchant prices */ ]
}
```

### Structure field scale
Values appear to be 1–5 (crowd-sourced). Different scale from GrapeMinds (1–10) — needs normalization to our 0–1 internal scale: `vivino_val / 5`.

### Flavor groups available
`black_fruit`, `oak`, `non_oak`, `spices`, `earth`, `red_fruit`, `microbio`, `dried_fruit`, `floral`, `vegetal`, `mineral`, `citrus`, `tree_fruit`, `tropical_fruit` — maps well onto our existing flavor tag vocabulary.

### Type IDs (inferred)
`type_id: 1` = Red, `2` = White, `3` = Rosé, `7` = Sparkling, `24` = Fortified, `3` = ? — need to verify full mapping.

---

## Critical Problem: Search Quality

**The `q=` param does NOT do fuzzy name matching.** It sorts by rating, not relevance:

```
q=esprit+de+tablas  →  returns Schrader CCS Beckstoffer 4.9, Hundred Acre Wraith 4.9
                        (highest-rated US wines, not Tablas Creek)
```

This means we **cannot** use the explore endpoint as a simple wine name lookup. The search is popularity-ranked, not text-matched.

### Workaround options

1. **Search by winery name + wine name separately and intersect** — e.g. `q=tablas+creek` to get winery results, then filter by wine name. Untested.
2. **Known wine ID lookup** — if we know the Vivino `wine.id`, we can use it as a filter: `?wine_id[]=1140843` (unverified — need to test).
3. **Enrich only GrapeMinds-matched wines** — GrapeMinds already has winery + wine name normalized. Use that as the canonical match, then search Vivino for the exact winery name.
4. **Accept fuzzy + rank** — search `q={wine_name}`, take top 10 results, use Haiku to pick the best match. Expensive per wine.

Option 3 is cleanest for Terroir: only ~17 GrapeMinds wines are enriched but those are the highest-quality candidates anyway.

---

## What We'd Get (If Matching Works)

| Field | Vivino | Notes |
|---|---|---|
| Rating | `statistics.ratings_average` (1–5) | High signal — crowd sourced from 10k+ reviews typically |
| Review count | `statistics.ratings_count` | Good for credibility badge ("4.2 · 40,966 reviews") |
| Structure | `taste.structure` (1–5 scale) | acidity, sweetness, tannin, intensity — normalize to 0–1 |
| Flavor keywords | `taste.flavor[].primary_keywords` | Grouped by category, maps to our tag vocabulary |
| Bottle image | `image.variations.bottle_medium` | CDN URLs — could supplement missing HEB images |
| Wine type | `wine.type_id` | Integer type code |
| Natural flag | `wine.is_natural` | Boolean |
| Merchant price | `price.amount` | Online market price — interesting but not local |

---

## Rate Limiting

No rate limiting observed in rapid sequential requests. The API is open and does not require tokens, cookies, or session state. Scraping responsibly (1–2 req/s) should be fine.

---

## Recommended Integration Path

1. **New `wines` columns**: `vivino_wine_id INT`, `vivino_rating FLOAT`, `vivino_ratings_count INT`, `vivino_enriched_at TIMESTAMPTZ`
2. **Matching strategy**: For each GrapeMinds-enriched wine, search `q={winery_name}+{wine_name}`, take best match by name similarity (Haiku or simple string distance), store `vivino_wine_id`.
3. **Enrichment call**: Use stored `vivino_wine_id` to call `explore?wine_id[]={id}` (verify this works) or pull directly from the search response.
4. **Fields to write**: `vivino_rating`, `vivino_ratings_count`, flavor keywords (merge into `wines.flavor_profile`), `vivino_enriched_at`.
5. **Display**: Show "4.2 ★ on Vivino (40k reviews)" credibility badge on wine cards and dossier. Do NOT show merchant prices (we have local prices).
6. **Budget**: No API key needed, no cost. Rate limit gently.

---

## Open Questions — Answered

- **`?wine_id[]=N`** → ❌ 400 error. Not a supported filter param.
- **`?winery_id[]=N`** → ✅ 200, works. But you need the correct Vivino winery ID. IDs are not discoverable from the explore endpoint — must be extracted from Vivino winery page URLs (e.g. `vivino.com/wineries/tablas-creek-winery` → scrape or parse the page to get the numeric ID). Once you have the winery ID, `?winery_id[]={id}` returns all vintages for that winery sorted by rating.
- **`q=` search** → confirmed popularity-ranked, not relevance-ranked. `q=tablas+creek+esprit` returns Schrader, Hundred Acre, Colgin — completely unrelated high-rated wines. Not usable for name matching without a separate winery ID discovery step.
- **Practical matching path**: (1) From winery name in our DB, scrape `vivino.com/search/wines?q={winery_name}` or `vivino.com/wineries/{seo-slug}` to get winery ID. (2) Call `explore?winery_id[]={id}` to get all wines. (3) Fuzzy-match wine name against our catalog. This is a 2–3 step pipeline per winery, not a simple 1-shot lookup.
- **Full `type_id` mapping** → needs verification. Confirmed: 1=Red, 2=White. Others (Rosé, Sparkling, Fortified, Orange) unknown.
