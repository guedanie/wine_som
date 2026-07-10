# CLAUDE.md — building the Somm wine app

You are building a wine‑recommendation web app called **Somm**. This file tells
you how to make it look and feel right. Read `README.md` for the full brand; this
is the working brief.

## The one‑liner
**Every bottle is a place.** An editorial wine atlas: each wine is a destination,
rendered with illustrated travel posters, drawn contour maps, and framed,
serif‑led editorial chrome. Confident, warm, opinionated — a knowledgeable friend,
never a textbook.

## Use the tokens — don't invent values
All color, type, spacing, radii and shadow values live in **`colors_and_type.css`**.
Import it (or port the `:root` variables into your Tailwind theme) and reference
the tokens. Do not hardcode hexes.

Tailwind mapping (suggested):
```js
// tailwind.config — theme.extend.colors
ink:'#1A1A1A', body:'#33312C', faded:'#6B6453',
bordeaux:'#6E1023', 'bordeaux-deep':'#560B1B', brass:'#B08D57', sage:'#7C8A5A',
paper:'#EFE6D4', cream:'#F5EFE6', 'cream-raised':'#FBF8F2',
// fontFamily
serif:['"DM Serif Display"','Georgia','serif'], sans:['Archivo','system-ui','sans-serif'],
```

## Non‑negotiables (the brand's spine)
1. **Type pairing:** DM Serif Display for anything expressive (region/wine names,
   hero display, ledes). Archivo for all UI/body/labels. Monospace only for
   coordinates/codes. Big serif + calm sans is the core tension.
2. **The frame:** important surfaces (posters, wine cards, dossiers) use a 1.5px
   ink border with a 0.75px brass inner keyline — a matted print.
3. **The contour map** is the connective motif, used sparingly. Reserve it for
   the **wine profile / dossier page** (section dividers, store markers) and as an
   imagery stand-in when no poster exists — NOT on wine cards in grids, where it
   gets busy. (Generate procedurally — see `ui_kits/wine-app/shared.jsx`
   `Contours`.)
4. **Region posters** are the hero imagery layer — matte, vintage‑lithograph.
5. **Mostly sharp corners** (radius 0–2px). Soft radius (8px) + pills ONLY on
   conversational/chat surfaces.
6. **No emoji. No gradients** (except the subtle radial inside a bordeaux field).
   No glassmorphism, no glows.
7. **Eyebrows & coordinates** are UPPERCASE tracked; region/wine names are serif
   Title Case; everything else sentence case.

## Voice (for all generated copy & the sommelier prompt)
Knowledgeable friend, not a textbook. Opinionated and specific — name the flavor,
structure and finish. Don't lead with food pairings. Short paragraphs. Address the
user as "you"; the app recommends as "I". (The brief's system prompt in
`uploads/app_idea.md` is the canonical sommelier voice — keep it.)

## Components to build (see the UI kit for reference implementations)
- **WineCard** — framed, editorial header (tagline + coordinates + brass keyline),
  price in serif bordeaux, flavor tags as brass keyline chips. The contour map is
  NOT used on cards — keep it for the dossier/profile page where it has room.
  `ui_kits/wine-app/shared.jsx`.
- **StructureBars** — body / tannin / acidity / finish, brass fill on paper track.
- **Poster** — matted region print (or striped placeholder).
- **Chat** — sommelier bubble (stamp avatar) + user bubble; soft radius here.
- **Preference capture, dossier, discovery** — see the four screen files.

## Region poster art‑direction spec (for whoever generates/sources them)
So a Tuscany and a Paso Robles poster feel like one family:
- **Format:** portrait 3:4, full‑bleed illustration, matte vintage‑lithograph
  finish (think mid‑century travel poster — see `assets/poster-tuscany.png`).
- **Palette:** muted and warm — sage/olive greens, dusty golds, dusk blues, soft
  terracotta. Slightly desaturated. Must sit happily next to bordeaux + brass.
- **Subject:** the region's defining landscape (vineyard rows, signature trees,
  a building or horizon). No people, no bottles, no text baked in (the app adds
  the region name + coordinates as a caption).
- **Light:** golden‑hour or soft overcast; never harsh or high‑gloss.
- **Fallback:** when a poster doesn't exist, use the procedural contour map field
  on a bordeaux‑deep ground.

## Don't
- Don't use Inter/Roboto, drop shadows everywhere, purple gradients, or rounded
  cards with a colored left border. None of that is Somm.
- Don't let the serif get small — it's for display sizes (23px+).
- Don't add icons for their own sake; the brand is type‑ and line‑led (Lucide,
  thin stroke, only where genuinely useful).
