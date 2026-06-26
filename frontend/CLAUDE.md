# Terroir — Frontend Design System

Read the root `CLAUDE.md` for backend context. This file covers **how the frontend
should look and feel**. Design tokens live in `design-system/colors_and_type.css`.
Component reference (clickable prototype) is in `design-system/ui_kits/wine-app/`.

---

## The one-liner
**Every bottle is a place.** An editorial wine atlas: each wine is a destination,
rendered with illustrated travel posters, drawn contour maps, and framed,
serif-led editorial chrome. Confident, warm, opinionated — a knowledgeable friend,
never a textbook.

## Tech stack (frontend)
React + Tailwind. Port the `:root` variables from `design-system/colors_and_type.css`
into your Tailwind theme — do not hardcode hex values anywhere.

```js
// tailwind.config — theme.extend.colors
ink:'#1A1A1A', body:'#33312C', faded:'#6B6453',
bordeaux:'#6E1023', 'bordeaux-deep':'#560B1B',
brass:'#B08D57', sage:'#7C8A5A',
paper:'#EFE6D4', cream:'#F5EFE6', 'cream-raised':'#FBF8F2',
// fontFamily
serif:['"DM Serif Display"','Georgia','serif'],
sans:['Archivo','system-ui','sans-serif'],
```

Load fonts via Google Fonts CDN:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Archivo:wght@400;500;600;700&display=swap" rel="stylesheet">
```

---

## Non-negotiables (the brand's spine)

1. **Type pairing:** `DM Serif Display` for anything expressive — region names, wine
   names, hero display, ledes. `Archivo` for all UI, body, labels. Monospace only
   for coordinates/codes. Large serif + calm sans is the core visual tension.

2. **The frame:** important surfaces (wine cards, dossiers) use a `1.5px ink border`
   with a `0.75px brass inner keyline` — like a matted print. Use `border: 1.5px solid #1A1A1A` +
   a child `border: 0.75px solid #B08D57`.

3. **The contour map** is the connective motif — used sparingly. Reserve it for:
   - The wine profile / dossier page (section dividers, store markers)
   - As an imagery stand-in when no region poster exists
   - NOT on wine cards in grids (gets busy). Generate procedurally — see
     `design-system/ui_kits/wine-app/shared.jsx` `Contours` component.

4. **Region posters** are the hero imagery layer — matte vintage-lithograph style.
   See `design-system/assets/poster-tuscany.png` (sourced reference) and
   `poster-paso-robles.png` (generated) for the visual target. Fallback: striped
   diagonal placeholder (`repeating-linear-gradient(135deg, ...)`) when no poster exists.

5. **Mostly sharp corners** — `border-radius: 0` for frames, cards, buttons, tags.
   Soft radius (`8px`) + pills reserved for chat/conversational surfaces only.

6. **No emoji. No gradients** (except a subtle radial inside a dark bordeaux field).
   No glassmorphism, no drop shadows everywhere, no glows.

7. **Casing:** `UPPERCASE TRACKED` for eyebrow labels and coordinates
   (`PASO ROBLES · 35.6°N`). Serif Title Case for region/wine names. Sentence case
   for everything else.

---

## Core components to build

### WineCard
- `1.5px ink` outer frame + `0.75px brass` keyline header separator
- Header: tagline (uppercase tracked, faded) + coordinates (sage) + price (serif bordeaux)
- Body: wine name in `DM Serif Display` (23px+), producer/vintage in Archivo small, flavor tags as brass keyline chips
- **No contour map in the header** — keep it clean in grids
- Hover: lift 2px + card shadow

### WineCard header (the editorial strip)
```
┌──────────────────────────────┐  ← 1.5px ink
│ RHÔNE, BY WAY OF CALIFORNIA ··· $55 │  ← brass 0.75px bottom rule
│ PASO ROBLES · 35.6°N            │
├──────────────────────────────┤
│ Esprit de Tablas             │  ← DM Serif 23px
│ Tablas Creek · 2021 · Spec's │  ← Archivo 11.5px faded
│ dark cherry  garrigue  leather │  ← brass keyline chips
└──────────────────────────────┘
```

### StructureBars
Body / Tannin / Acidity / Finish. Brass fill (`#B08D57`) on paper track (`#EFE6D4`).
5px height, 3px radius. Uppercase 10px label above each bar.

### RegionPoster
Matted print: `cream` padding (10px) + `1.5px ink` outer border + `0.75px brass` inner keyline.
Box shadow: `0 18px 40px -22px rgba(0,0,0,0.5)` (the "print shadow").
Portrait 3:4 aspect ratio.

### Chat bubbles (conversational surfaces — soft radius here)
- Sommelier: stamp avatar (bordeaux circle) + `cream-raised` bubble, `border-radius: 4px 14px 14px 14px`
- User: bordeaux filled bubble, `border-radius: 14px 4px 14px 14px`
- Wine card attached below a sommelier bubble uses the standard WineCard

### Buttons
- Primary: `background: #6E1023`, `color: #F5EFE6`, `border-radius: 0`, no border
- Ghost: transparent + `1.5px inset bordeaux` border, bordeaux text
- Hover: darken (primary) / bordeaux-tint wash (ghost)
- Press: `translateY(1px)`

---

## Voice (sommelier copy + all UI strings)
- Knowledgeable friend, never a textbook. Opinionated and specific.
- Lead with the wine and the place — not food pairings.
- Address the user as **you**; the app recommends as **I**.
- Name the flavor, structure, finish: "dark cherry, garrigue, leather" not "smooth and easy."
- Short paragraphs (2–3 sentences max in conversation).
- Keep the Claude prompt from the root `CLAUDE.md` recommendation engine as the source of truth for voice.

---

## Screens to build (see `design-system/ui_kits/wine-app/` for reference)

1. **Preference capture** — zip, budget slider, style cards (Bold & Tannic / Light & Elegant /
   Earthy & Savory / Bright & Fruity), occasion toggle → Find wines
2. **Chat + recommendations** — split: sommelier chat left, wine cards right
3. **Wine dossier** — region poster hero, wine detail, structure bars, contour divider,
   local store availability with map pins, "More from this region" grid
4. **Discover** — region poster grid, click → wine dossier

---

## Region poster art-direction spec
For generating/sourcing new region posters so they feel like one family:
- **Format:** portrait 3:4, full-bleed, matte vintage-lithograph finish
- **Palette:** muted + warm — sage/olive greens, dusty golds, dusk blues, soft terracotta.
  Must sit happily next to bordeaux + brass.
- **Subject:** defining landscape (vineyard rows, trees, horizon). No people, no bottles,
  no text baked in (the app overlays region name + coordinates).
- **Light:** golden-hour or soft overcast. Never harsh or high-gloss.
- **Fallback:** striped diagonal placeholder until a real poster is ready.

---

## Don't
- Don't use Inter, Roboto, drop shadows on everything, purple gradients, or rounded
  cards with a colored left border.
- Don't put the serif below 23px — it's a display face only.
- Don't add icons for their own sake. Brand is type- and line-led. Use Lucide (thin
  stroke, 1.5px) only where genuinely functional (search, map-pin, chevrons, sliders).
- Don't put contour maps on wine cards in grids.
