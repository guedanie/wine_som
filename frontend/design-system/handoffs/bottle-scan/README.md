# Handoff: Somm — Bottle Scan (photo → identify → buy / save)

## Overview
This package specifies **Bottle Scan** for **Somm**, an editorial wine atlas (React + Vite PWA,
desktop + mobile). The user shows their sommelier a bottle — snaps the **label** or scans the
**barcode** — Somm identifies it, then does one of two useful things: **tells you where to buy it
nearby**, or **remembers it for you** (save / cellar / "I drank this").

It's the bridge between the physical world and the atlas, serving two moments:
1. **In the aisle** — holding an unfamiliar bottle: "is this any good, and is it cheaper elsewhere
   near me?" One-handed, hurried, variable lighting.
2. **At the table** — a friend poured something great: "remember this for me." The wine may not be
   stocked anywhere nearby — that's fine; **remembering is the product.**

## About the Design Files
The file in this bundle is a **design reference created in HTML** — a single self-contained canvas
prototype (`Somm - Bottle Scan.html`) showing look, states, and behavior. It is **not production
code to copy**. The task is to **recreate these designs in Somm's existing React + Vite codebase**,
reusing established atoms (WineCard header, StructureBars, ratings badge, flavor chips, availability
rows, price-drop chip, contextual sign-in nudge sheet, chat bubble grammar, tab bar) and the design
tokens in `colors_and_type.css` (`:root` CSS variables). This feature should look like it was always
there. **Do not hardcode hexes** — use the variables. Hexes below are for spec self-sufficiency only.

## Fidelity
**High-fidelity.** Colors, type, spacing, borders, and states are specified. The pin/avatar mark is a
**placeholder glyph** (cream pin in a bordeaux circle) — swap in the real "The Pin" SVG. Bottle
thumbnails are **striped placeholders** — real label crops/catalog shots swap in.

---

## The data + tech reality (design to this, not past it)
- **Two-tier identification.**
  - **Tier 1 — barcode:** instant, exact, free. Catalog keyed by `upc_canonical`. **54% of the live
    catalog (10,881 of 20,274 wines) has a real scannable barcode** — so barcode is the fast path
    when it exists, label photo is the universal fallback.
  - **Tier 2 — label photo → Claude vision** → producer / wine name / vintage read off the label →
    fuzzy match against the ~20k-wine catalog.
- **Vision takes 2–5s.** The **identifying wait is a first-class state**, not a spinner flash — the
  somm "squinting at the label," consistent with the streamed "Looking deeper into the cellar…"
  chat pattern.
- **Confidence is a spectrum — five first-class result states** (see below). Never a dead end,
  never "no results found."
- **Vintage is catalog identity today.** A product-family layer is a future spec. The bottle in hand
  may be the 2019 while stores stock the 2021 → treat vintage as a **soft confirm**, not a mismatch
  error.
- **Anonymous-first.** Identify works signed out. Save/cellar taps by an anonymous user open the
  existing **contextual sign-in nudge** (magic link, pending-intent carried through the round-trip —
  same pattern as price watches).
- **PWA camera constraints.** iOS PWA: `<input type="file" capture="environment">` is the reliable
  path (full-screen OS camera, returns a photo). Live `getUserMedia` viewfinder is flaky in
  standalone mode → design for the **native-camera round-trip** (tap → OS camera → return → identify),
  with a **live-viewfinder barcode scanner as progressive enhancement**. Photos are sent for
  identification only, not stored — say so quietly (one line, not a privacy banner).
- **No history/feed in v1.** "Recently scanned" is a later layer on the account home — note the seam,
  don't design the surface.

---

## Design Tokens
Reference as CSS variables from `colors_and_type.css`. Hexes for completeness.

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#1A1A1A` | Primary text, 1.5px frames |
| `--ink-2` | `#33312C` | Body / somm-voice text |
| `--faded` | `#6B6453` | Muted labels, eyebrows, hints |
| `--faded-2` | `#9E9282` | Struck "was" price, mono captions |
| `--bordeaux` | `#6E1023` | Primary; prices; drop chip; save-active; best-store row |
| `--bordeaux-deep` | `#560B1B` | Pressed |
| `--bordeaux-tint` | `#F5ECEE` | Drop chip fill; best-price row wash |
| `--brass` | `#B08D57` | 0.75px keyline; capture corners; scan-line; badge/chip borders |
| `--brass-deep` | `#5C4A2E` | Chip/badge text on light |
| `--sage` / `--sage-deep` | `#7C8A5A` / `#556037` | Coordinates; availability-watch (future) affordance |
| `--paper` | `#EFE6D4` | Sunken tracks; thumbnail stripe base |
| `--cream` | `#F5EFE6` | Base background, camera bottom chrome |
| `--cream-raised` | `#FBF8F2` | Raised cards, icon actions |
| `--border` / `--border-strong` | `rgba(26,26,26,0.15)` / `0.28` | Hairlines; secondary-action borders |
| *(camera field)* | `#22201C` / `#1A1815` | Dark viewfinder ground (only inside the camera surface) |

**Type:** `DM Serif Display` for wine/region names, result headlines, ratings number (**never below
23px** at display size). `Archivo` for all UI/body/somm-voice/labels. `DM Mono` for coordinates,
UPC/codes, and the "photos identify only" line.
**Casing:** UPPERCASE tracked (`0.22–0.24em`, 600) eyebrows/coordinates; serif Title Case wine names;
sentence case everything else.
**Radii:** sharp (`0`) for frames, cards, buttons, inputs, tags. Soft ONLY on conversational
surfaces: **result/nudge bottom sheets** (`16px 16px 0 0`), chat bubble (`4px 14px 14px 14px`),
chat-entry pill (`999px`). **No emoji, no gradients** (the dark camera field is the one allowed dark
ground), no glows. Thin-stroke Lucide icons only where functional (camera, barcode, bookmark,
chevron, decant/pour).

---

## Entry points

**Primary — tab-bar camera FAB.** A bordeaux camera pin raised out of the center of the bottom tab
bar (`44px` circle, `2.5px --cream` ring, subtle bordeaux shadow), labeled **Scan**. Thumb-reachable,
findable in-aisle in ~2s. Reads as "show Somm a bottle," not a barcode utility. (Desktop: a camera
button in the top chrome opens the same flow; on desktop the capture is a centered
modal/drag-drop-a-photo target rather than a full-screen camera.)

**Conversational — inside the Somm chat overlay.** A `Show me the bottle` pill (chat-surface soft
radius) offered when relevant: *"Holding a bottle you don't know? Show me — I'll tell you what it is
and where to find it."* Opens the same capture surface.

Both entries converge on one capture component.

---

## Capture — native-camera round-trip

Full-screen dark camera surface (`#22201C`). Two explicit modes as two buttons pinned at the bottom
(**no auto-detect** to misfire):
- **Label** (default, universal): rectangular framing guides + brass corner marks; hint
  *"Get the whole front label in frame."* A shutter that fires the OS camera
  (`<input capture="environment">`). Below the shutter, a mono line: `PHOTOS IDENTIFY ONLY — NOT
  STORED`.
- **Barcode** (fast, exact): narrower guide box + an animated brass scan-line; hint *"Line up the
  barcode — I'll catch it automatically."* Live viewfinder is the progressive enhancement; caption
  `◎ LIVE SCANNER · 54% OF CATALOG HAS BARCODES`. If a scanned/identified bottle has no barcode,
  gracefully suggest Label mode.

Top bar: `✕` close + a serif title (`Show me the bottle` / `Scan the barcode`).

**Identifying state (2–5s):** the captured label sits framed and dimmed with a sweeping brass
scan-line; a cream strip at the bottom carries the somm stamp + italic voice
*"Let me get a look at it…"* with animated dots. This is the vision round-trip — a real state.

---

## Result states — ONE bottom-sheet component, five faces

All five are the same sheet family (`16px 16px 0 0`, `1.5px --ink` top border, drag handle, dark
result screen behind). Shared header grammar; the body + **action hierarchy** swaps by `status`.
Sheet on mobile; on desktop the same content is a centered modal card. Deep-link to the full dossier
from any identified state.

### ① Exact hit (`status: 'exact'`)
Barcode or unambiguous label match → straight to a **compressed dossier**. Header: eyebrow
`GOT IT · EXACT MATCH` + `◎ zip`. Row: bottle thumb + serif name + producer·region·vintage + ratings
badge (`93 pts`, brass keyline) + varietal tag. StructureBars (Body/Tannin/Acidity) + flavor chips.
Then `WHERE TO BUY NEAR YOU` availability rows (reuse existing rows; best/cheapest row `--bordeaux-tint`
with bordeaux dot, struck `was` + new price, price-drop chip where one applies).
**Actions:** primary = **`View bottle page`** (deep-links to the full dossier); secondary = a quiet
bookmark **Save** icon. The availability rows already surface where-to-buy inline, so the primary
action carries the user into the full dossier rather than to directions.

### ② A few candidates (`status: 'candidates'`, 2–4 rows)
Good vision read matching same producer / different bottlings or vintages. Somm line: *"That's a
Tablas Creek — which one are you holding?"* A tap list: each row = striped **thumbnail** + serif name
+ sub (style · vintage) + chevron. One tap resolves to ① (or ③). Bottom escape hatch:
`None of these — try again`.

### ③ Different vintage (`status: 'vintage_mismatch'`, `readVintage` ≠ stocked vintage)
Soft confirm, never a dead end. Somm line: *"That's Tablas Creek's Esprit — yours looks like the
**2019**. I see the **2021** nearby; close cousin, worth knowing."* Bottle row shows two tags —
`yours · 2019` (muted) and `nearby · 2021` (bordeaux). Availability rows for the stocked vintage.
**Actions:** `See the 2021` (primary, chase the stocked one) + `Save the 2019` (ghost, remember what
they actually have).

### ④ Recognized, not stocked (`status: 'unstocked'`)
Vision names it, no nearby store carries it — still a success. Somm line: *"I know this one — Clos
Rougeard's Saumur-Champigny. Nobody near you stocks it right now, but it's a beauty. I'll remember it
for you."* Bottle row (thumb + name + producer·region·vintage + varietal/region tags), no availability
list. **Actions (remembering becomes primary):** `Remember this for me` (bordeaux-outline, primary) +
`Tell me if it shows up nearby` (sage ghost — the **availability-watch future seam**, mirrors the
price-watch; design the ghost, don't build it).

### ⑤ Can't read it (`status: 'unreadable'`)
Glare / foil / cropped. Never an error tone. Somm line: *"Couldn't quite make it out — the glare's
hiding the name. Try again with the whole front label in frame, and I'll get it."* One concrete tip
in a dashed note (*"no flash on foil — tilt the bottle so the label isn't reflecting light back"*).
**Actions:** `Retake the photo` (primary) + `Search by name instead` (ghost → existing search).

---

## Anonymous save → sign-in nudge
Identify works signed out. A **Save / Add to cellar / I drank this** tap by an anonymous user opens
the existing contextual magic-link sheet, headed with the wine: eyebrow `REMEMBER THIS BOTTLE`, serif
*"I'll remember **Le Bourg** for you."*, body *"Saved bottles live with your account — passwordless,
free. Sign in and it's on your list the moment you tap the link."*, email input + `Send magic link`,
footnote *"No account needed to browse — this just saves the bottle."* On magic-link success, apply
the pending save/cellar/drank intent (same pending-intent round-trip as price watches). **`I drank
this`** feeds the cellar rating loop.

## Voice — somm lines per state (grounded, specific, no error-speak; app = "I", user = "you")
- **Identifying:** *"Let me get a look at it…"*
- **Exact:** (no preamble — go straight to the wine and where to buy)
- **Candidates:** *"That's a Tablas Creek — which one are you holding?"*
- **Vintage mismatch:** *"That's Tablas Creek's Esprit — yours looks like the 2019. I see the 2021
  nearby; close cousin, worth knowing."*
- **Not stocked:** *"I know this one — nobody near you stocks it right now, but it's a beauty. I'll
  remember it for you."*
- **Unreadable:** *"Couldn't quite make it out — the glare's hiding the name. Try again with the
  whole front label in frame, and I'll get it."*
The somm never says "no results found," "error," or "invalid."

---

## Interactions & Behavior
- **Entry → capture → identify → result** is one flow; back returns to the live camera, `✕` exits.
- **Mode is explicit** (Label / Barcode buttons); barcode auto-catches in the live scanner, label
  needs a shutter tap (OS camera round-trip).
- **Identifying is a held state** (2–5s), skippable only by cancel; show the somm-voice line.
- **Action hierarchy flips by state:** where-to-buy is primary when stocked (①③), remembering is
  primary when not (④). Save is always available but quiet when buying is the point.
- **Anonymous save** → sign-in nudge → on auth, apply pending intent and reflect saved/cellar state.
- **Deep-link:** any identified result → full dossier (the sheet is the compressed view).
- Transitions 0.12–0.18s; buttons press `translateY(1px)`; sheet slides up from bottom.
- **Responsive:** mobile = full-screen camera + bottom sheets. Desktop = top-chrome camera button →
  centered capture modal (or drag-a-photo) → centered result modal with the same content.

## Data shapes (the frontend consumes)
```ts
scanResult: {
  status: 'exact' | 'candidates' | 'vintage_mismatch' | 'unstocked' | 'unreadable',
  method: 'barcode' | 'label',
  wine?: Wine,                 // exact / vintage_mismatch / unstocked
  candidates?: Wine[],         // candidates (2–4)
  readVintage?: string,        // vintage read off the label (vintage_mismatch)
  availability?: StoreOffer[], // exact / vintage_mismatch (stocked vintage); empty for unstocked
  priceMovement?: PriceMovement, // reuse price-intelligence atom where a drop applies
  confidence?: number          // vision match score, drives exact vs candidates threshold
}
Wine: { id, upcCanonical?, name, producer, region, vintage, rating?, structure, flavorTags[], thumb? }
StoreOffer: { storeId, name, address, distanceMi, price, wasPrice? }
pendingIntent: { type: 'save' | 'cellar' | 'drank', wineId }  // carried through magic-link round-trip
```
Future seams (note, don't build): `availabilityWatch` (mirrors price-watch), `recentlyScanned[]` on
account home, product-family layer collapsing vintages.

## Assets
- **The Pin** mark — placeholder cream-pin-in-bordeaux-circle SVG; swap in the real SVG.
- **Bottle thumbnails** — striped placeholders in the mock; real label crops / catalog shots swap in.
- Icons: thin-stroke Lucide (camera, barcode/scan, bookmark, chevron, decant/pour for "drank"). No emoji.
- Fonts: `DM Serif Display` + `Archivo` + `DM Mono` (Google Fonts; already loaded via `colors_and_type.css`).

## Files
- `Somm - Bottle Scan.html` — full hifi prototype: entry points (tab-bar FAB + chat), capture (label /
  barcode / identifying), all five result states, disambiguation, not-stocked save + availability-watch
  seam, unreadable retry, and the anonymous sign-in nudge. Mobile-first with desktop notes above.
- `colors_and_type.css` — design tokens (`:root` variables). **Use these variables directly.**
