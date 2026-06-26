# Terroir Frontend — Design Spec

**Date:** 2026-06-25
**Status:** Approved

---

## Overview

A React SPA that wraps the existing FastAPI recommendation backend in the Terroir editorial design system. Users enter zip code, budget, and style preferences to get Claude-powered sommelier recommendations for wines available at local retailers near them.

**Goals:**
- Ship all 4 screens in one pass
- Capacitor-ready from day one (web → iOS path, no code changes required)
- No auth in v1 — session-based, no account needed

---

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Build | Vite 5 | Fast dev server, minimal config, Capacitor-compatible SPA output |
| UI | React 18 | Prototype is already React; direct port |
| Routing | React Router v6 | Simple 4-route app, router state for prefs passing |
| Styling | Tailwind v3 + CSS custom properties | Brand tokens from `colors_and_type.css`; Tailwind extends theme with same values |
| Data fetching | Native `fetch` | Single POST + one GET — no library needed yet |
| iOS path | Capacitor | Wraps the Vite SPA build with zero code changes |

---

## Project Structure

```
frontend/
  public/
    assets/
      poster-tuscany.png          ← moved from design-system/assets/
      poster-paso-robles.png      ← moved from design-system/assets/
      mark-terroir.svg
      mark-terroir-reversed.svg
      contours-hero.svg
      # more region posters added here as designed
  src/
    main.jsx                      ← ReactDOM.createRoot + BrowserRouter
    App.jsx                       ← route table
    index.css                     ← @import colors_and_type.css + Tailwind base/components/utilities
    components/
      WineCard.jsx
      StructureBars.jsx
      Poster.jsx
      Contours.jsx
      Tag.jsx
      Btn.jsx
      Eyebrow.jsx
      Stamp.jsx
    screens/
      PreferenceCapture.jsx
      ChatRecommend.jsx
      RegionDossier.jsx
      Discovery.jsx
    lib/
      api.js                      ← recommend(), getWine()
      regions.js                  ← REGION_POSTERS map + DISCOVERY_REGIONS list
  index.html                      ← Google Fonts link tag
  vite.config.js
  tailwind.config.js
  .env                            ← VITE_API_URL=http://localhost:8000
  .env.example
```

The existing `design-system/` directory stays in place as a living reference prototype — open `design-system/ui_kits/wine-app/index.html` in a browser to compare visuals while building.

---

## Design System Integration

CSS custom properties are the source of truth. `index.css` imports `../design-system/colors_and_type.css` directly (no duplication). Tailwind `tailwind.config.js` extends `theme` with the same values so both `className="text-bordeaux"` and `style={{ color: 'var(--bordeaux)' }}` work:

```js
// tailwind.config.js
theme: {
  extend: {
    colors: {
      ink: '#1A1A1A',
      body: '#33312C',
      faded: '#6B6453',
      bordeaux: '#6E1023',
      'bordeaux-deep': '#560B1B',
      'bordeaux-tint': '#F4E6E2',
      brass: '#B08D57',
      sage: '#7C8A5A',
      paper: '#EFE6D4',
      cream: '#F5EFE6',
      'cream-raised': '#FBF8F2',
    },
    fontFamily: {
      serif: ['"DM Serif Display"', 'Georgia', 'serif'],
      sans: ['Archivo', 'system-ui', 'sans-serif'],
    },
  },
},
```

---

## Shared Components

All ports of `design-system/ui_kits/wine-app/shared.jsx`. Inline styles are preserved (prototype is pixel-precise; rewriting in Tailwind classes would risk drift).

| Component | Props | Notes |
|---|---|---|
| `WineCard` | `wine`, `onClick` | Adds router `navigate` to `/wine/:id` via `onClick`. `wine` shape: `{ wine_id, name, price, retailer, why, varietal, region, tagline?, coord?, flavors? }`. `tagline` is derived as `${region?.toUpperCase() ?? varietal?.toUpperCase() ?? 'AVAILABLE NEAR YOU'}`. `coord` is looked up from `DISCOVERY_REGIONS` by region name, or omitted if not found. Both are computed in ChatRecommend before passing to WineCard. |
| `StructureBars` | `items`, `compact?` | Items: `[key, label, value 0–1][]`. Skipped when `structure_profile` is null/empty |
| `Poster` | `region`, `className?` | Looks up `REGION_POSTERS[region]`; falls back to striped diagonal placeholder |
| `Contours` | `w?`, `h?`, `color?`, `cfg?` | Used only on RegionDossier (section divider). Never on card grids |
| `Tag` | `children` | Brass keyline chip. Uppercase 10.5px |
| `Btn` | `children`, `variant?`, `onClick?` | `variant="ghost"` for secondary actions |
| `Eyebrow` | `children` | Uppercase tracked label |
| `Stamp` | `size?`, `reversed?` | SVG wordmark; reversed (cream on bordeaux) for the chat avatar |

---

## Routing

```
/              → PreferenceCapture
/recommend     → ChatRecommend    (requires location.state.prefs; redirects to / if missing)
/wine/:id      → RegionDossier
/discover      → Discovery
```

Navigation bar appears on all screens: wordmark left → `/`, "Recommend" and "Discover" links right.

---

## Data Flow

### Preference → Recommendation

PreferenceCapture collects:
```js
{ zip: "78209", budget: 60, styles: ["Bold & Tannic"], occasion: "Tonight" }
```

Before navigating to `/recommend`, maps to API shape:
```js
{
  zip_code: prefs.zip,
  budget_min: 10,
  budget_max: prefs.budget,
  // Union tags across all selected styles: ["Bold & Tannic", "Earthy & Savory"] →
  //   ["dark fruit", "grip", "structure", "full body", "earthy", "herbal", "leather", "mineral"]
  style_preferences: [...new Set(prefs.styles.flatMap(s => STYLE_TAG_MAP[s] ?? []))],
  // wine_type from first style that has one; null if ambiguous (e.g. "Earthy & Savory" alone)
  wine_type: prefs.styles.map(s => STYLE_WINE_TYPE[s]).find(Boolean) ?? null,
  message: occasionMessage(prefs.occasion),  // "Tonight" → "I want something to open tonight."
}
```

ChatRecommend mounts → `POST /api/recommend` → renders `narrative` as sommelier bubble + `picks[]` as WineCards.

Follow-up messages: new `POST /api/recommend` with same prefs + `message` set to user text. Response replaces the picks panel.

### Wine detail

Clicking a WineCard → `navigate('/wine/' + wine_id, { state: { pick } })`. RegionDossier receives the `pick` object via router state (for immediate price/retailer display) + fetches `GET /api/wines/:id` for full detail (tasting notes, structure profile).

### Discovery

Static region list in `lib/regions.js`. Clicking a region card → `navigate('/recommend', { state: { prefs: regionPrefs(region) } })` which pre-populates a recommend request for that region. No extra API call.

---

## API Client (`lib/api.js`)

```js
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function recommend(req) {
  const res = await fetch(`${BASE}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const { detail } = await res.json().catch(() => ({}));
    throw new Error(detail ?? `HTTP ${res.status}`);
  }
  return res.json(); // { narrative, picks, session_id }
}

export async function getWine(id) {
  const res = await fetch(`${BASE}/api/wines/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

Error messages surface directly in the UI (the API returns human-readable `detail` strings like "No stores found near your zip code. We currently serve San Antonio, TX.").

---

## Screen Behaviours

### PreferenceCapture (`/`)
- Zip input (5-digit), budget range slider ($15–$150), style cards (multi-select), occasion toggle (Tonight / This weekend / Cellar it)
- "Find wines" button disabled until zip is 5 digits and at least one style is selected
- On submit: maps prefs → API shape → `navigate('/recommend', { state: { prefs, apiReq } })`

### ChatRecommend (`/recommend`)
- Guard: if no `location.state?.prefs` → `<Navigate to="/" />`
- Mounts → calls `recommend(apiReq)` immediately (no user action needed)
- Loading state: sommelier bubble with animated ellipsis
- Error state: sommelier bubble with the API error message + "Try different preferences" ghost button back to `/`
- Success: narrative bubble + 2-column WineCard grid (or 1-column on narrow viewport)
- Follow-up bar at bottom: pill suggestion chips + free-text input. Send → new API call, new picks replace old ones, narrative appended to chat
- Each WineCard `onClick` → `navigate('/wine/' + pick.wine_id, { state: { pick } })`

### RegionDossier (`/wine/:id`)
- Immediately shows `pick` data from router state (name, price, retailer, why) while `getWine(id)` loads
- `getWine` resolves → fills in tasting notes, structure bars, region info
- Region poster via `Poster` component (placeholder if region not in `REGION_POSTERS`)
- Contours SVG as section divider between detail and store availability
- Store availability: single row — retailer name + price from the `pick` (full multi-store lookup is a future enhancement)
- "More from this region" → links to `/discover` (Discovery screen)
- Back button → `navigate(-1)`

### Discovery (`/discover`)
- Grid of ~10 major wine regions as `Poster` cards with region name + coordinate overlay
- All show the striped placeholder until real posters are dropped into `public/assets/`
- Clicking a region → `navigate('/recommend', { state: { prefs: regionPrefs(region), apiReq: regionApiReq(region) } })`
- `regionApiReq` sets `style_preferences` to the region's known flavor tags and `message` to "Recommend wines from [region]."

---

## Style-to-API Mapping

```js
// lib/regions.js
export const STYLE_TAG_MAP = {
  "Bold & Tannic":   ["dark fruit", "grip", "structure", "full body"],
  "Light & Elegant": ["red fruit", "silky", "bright acidity", "light body"],
  "Earthy & Savory": ["earthy", "herbal", "leather", "mineral"],
  "Bright & Fruity": ["juicy", "fresh fruit", "easy drinking"],
};

export const STYLE_WINE_TYPE = {
  "Bold & Tannic":   "red",
  "Light & Elegant": "red",
  "Earthy & Savory": null,   // could be red or white
  "Bright & Fruity": null,
};

export const REGION_POSTERS = {
  "Tuscany":      "/assets/poster-tuscany.png",
  "Paso Robles":  "/assets/poster-paso-robles.png",
  // add as Daniel designs them
};

export const DISCOVERY_REGIONS = [
  { name: "Tuscany",         coord: "43.8°N · 11.2°E",  flavors: ["dark cherry", "leather", "tobacco"] },
  { name: "Paso Robles",     coord: "35.6°N · 120.7°W", flavors: ["dark fruit", "garrigue", "structure"] },
  { name: "Napa Valley",     coord: "38.5°N · 122.4°W", flavors: ["blackcurrant", "cedar", "full body"] },
  { name: "Burgundy",        coord: "47.0°N · 4.8°E",   flavors: ["red fruit", "earthy", "silky"] },
  { name: "Rioja",           coord: "42.3°N · 2.5°W",   flavors: ["cherry", "vanilla", "leather"] },
  { name: "Mendoza",         coord: "32.9°S · 68.8°W",  flavors: ["dark plum", "chocolate", "spice"] },
  { name: "Willamette Valley", coord: "45.5°N · 123.0°W", flavors: ["cherry", "earthy", "bright acidity"] },
  { name: "Rhône Valley",    coord: "45.0°N · 4.8°E",   flavors: ["dark fruit", "garrigue", "pepper"] },
  { name: "Champagne",       coord: "49.1°N · 4.0°E",   flavors: ["brioche", "citrus", "mineral"] },
  { name: "Barossa Valley",  coord: "34.5°S · 138.9°E", flavors: ["dark fruit", "chocolate", "spice"] },
];
```

---

## Region Poster Placeholders

All regions without a poster in `REGION_POSTERS` fall back to:
```css
background: repeating-linear-gradient(
  135deg,
  var(--bordeaux-deep) 0px,
  var(--bordeaux-deep) 8px,
  var(--bordeaux) 8px,
  var(--bordeaux) 16px
);
```
Drop a file into `public/assets/poster-{region-slug}.png` and add the entry to `REGION_POSTERS` to replace the placeholder.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Unrecognized zip | Sommelier bubble: API `detail` string + back button |
| No stores near zip | Sommelier bubble: "We currently serve San Antonio, TX." + back button |
| No wines match criteria | Sommelier bubble: "Try widening your budget or style preferences." + back button |
| Claude unavailable (500) | Sommelier bubble: "The sommelier is unavailable right now. Try again in a moment." |
| `/recommend` loaded without prefs | Redirect to `/` |

---

## Capacitor Path (future, no code changes)

```bash
npm run build                    # Vite outputs dist/
npx cap add ios
npx cap copy
npx cap open ios                 # Opens Xcode
```

The SPA runs in WKWebView. CSS custom properties, Google Fonts, and the FastAPI backend URL all work as-is. The only addition needed when going native is swapping `VITE_API_URL` to the production backend URL.

---

## Out of Scope (v1)

- Auth / user accounts
- Saved wines
- Multi-store availability lookup from the dossier
- Push notifications
- Offline support
