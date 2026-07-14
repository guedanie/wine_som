# Handoff: Somm — Price Intelligence (Price History · Deals · Price Watches)

## Overview
This package specifies the **price-intelligence layer** for **Somm**, an editorial wine atlas
(React + Vite PWA, desktop + mobile) that recommends bottles available at stores near the user.
Somm quietly tracks every bottle's price at every store, week over week, and surfaces that in three
product moments:

1. **Price context on the bottle** — how a wine's price has moved and where it's cheapest nearby.
2. **Deals as discovery** — an editorial cut of "good wine whose price just moved" near you.
3. **Price watches (designs now, ships later)** — a signed-in user watches a bottle; Somm notifies
   them when its price drops nearby. Notification backend isn't built yet, but the affordance and
   copy are designed here so it isn't bolted on later.

All of it is unified by **one reusable price-movement marker** (a chip) so the pattern is identical
across cards, dossier, picks, deals, and account surfaces.

## About the Design Files
The file in this bundle is a **design reference created in HTML** — a single self-contained canvas
prototype (`Somm - Price Intelligence.html`) showing look, states, and behavior. It is **not
production code to copy**. The task is to **recreate these designs in Somm's existing React + Vite
codebase**, reusing established components (WineCard, StructureBars, store/availability rows, chat
pick bubbles, nav, tab bar, sign-in sheet) and the design tokens in `colors_and_type.css`
(`:root` CSS variables). This feature should look like it has always been part of the app.

**Do not hardcode hexes** — use the CSS variables. Hexes below are for spec self-sufficiency only.

## Fidelity
**High-fidelity.** Final colors, type, spacing, borders, and interaction states are specified.
The pin/avatar mark is a **placeholder glyph** (cream pin in a bordeaux circle) — swap in the real
"The Pin" SVG when wiring up.

---

## The data reality (design to this, not past it)
Every design decision below follows from these constraints — honor them in copy and logic:

- **Weekly snapshots, not live prices.** Scrapes run Sundays. A "drop" is a **week-over-week**
  event. Copy always says **"this week"** / "since Sunday" / "through June" — **never "today" or
  "right now."**
- **Per bottle × per store.** A wine can drop at H-E-B and not at Spec's. **Every price claim is
  anchored to a named store** ("$19.99 at H-E-B on Broadway").
- **History starts June 2026.** At launch there are ~6 weekly points per bottle. **Prose leads;
  no real chart** — a thin week-marker strip is a supporting glyph that upgrades to a sparkline
  as history deepens.
- **Most bottles, most weeks: no change.** The **sparse / no-movement state is the common case**
  and must feel complete, not empty. The interesting set is a few hundred–few thousand movements/
  week across ~90k in-stock rows.
- **Out-of-stock transitions are tracked** — "back in stock" is a secondary signal.

---

## Design Tokens
Reference as CSS variables from `colors_and_type.css`. Hexes for completeness.

| Token | Hex | Use |
|---|---|---|
| `--ink` | `#1A1A1A` | Primary text, 1.5px frames |
| `--ink-2` | `#33312C` | Body text |
| `--faded` | `#6B6453` | Muted labels, eyebrows, "steady" state |
| `--faded-2` | `#9E9282` | Struck-through "was" price, timestamps |
| `--bordeaux` | `#6E1023` | Primary; prices; **drop** marker; watching state |
| `--bordeaux-deep` | `#560B1B` | Pressed; dark notification/hero fields |
| `--bordeaux-tint` | `#F5ECEE` | Drop-chip fill; best-price row wash; ghost hover |
| `--brass` | `#B08D57` | 0.75px keyline; chip borders; week-strip prev bar |
| `--brass-deep` | `#5C4A2E` | Chip text on light |
| `--sage` | `#7C8A5A` | Coordinates; **back-in-stock** marker |
| `--sage-deep` | `#556037` | Back-in-stock chip text |
| `--paper` | `#EFE6D4` | Sunken track backgrounds; week-strip base bars |
| `--cream` | `#F5EFE6` | Base background |
| `--cream-raised` | `#FBF8F2` | Raised cards, modules, chips |
| `--border` | `rgba(26,26,26,0.15)` | Hairline rules |
| `--border-strong` | `rgba(26,26,26,0.28)` | Steady-chip border, store pill |

**Type:** `DM Serif Display` for expressive text — prices, wine/region names, module headlines,
notification headlines (**never below 23px**). `Archivo` (400–700) for all UI/body/labels.
`DM Mono` for coordinates, week counts, timestamps only.
**Casing:** UPPERCASE tracked (`0.14–0.26em`, weight 600) for eyebrows/coordinates; serif Title Case
for wine/region names; sentence case elsewhere.
**Radii:** sharp (`0`) everywhere — frames, cards, chips, buttons, inputs. Soft (`4px 14px 14px 14px`
bubble, `999px` pills, `14px` sheet top) ONLY on conversational surfaces (chat bubble, store pill,
bottom sheet). **No emoji, no gradients** (except the allowed radial in a bordeaux field), no glows.

---

## THE PRICE-MOVEMENT MARKER (the connective atom — build first, reuse everywhere)

A small chip. Same component in cards, dossier, picks, deals, notifications. Always carries a
**store and/or "this week"** — it whispers like a cellar note, never a sale burst.

Base: `display:inline-flex; gap:6px; font Archivo 11px/600; letter-spacing:0.04em;
padding:4px 9px 4px 8px; border:0.75px solid; border-radius:0`. A leading glyph (`.arw`, DM Mono
12px) carries the direction.

**Four variants** (`variant: 'drop' | 'steady' | 'restock' | 'watch'`):
- **drop** (default, only slightly loud): `color/border --bordeaux`, `bg --bordeaux-tint`, glyph `↓`.
  Copy: `↓ $5 this week · H-E-B` (store optional when context already names it).
- **steady**: `color --faded`, `border --border-strong`, `bg transparent`, glyph `—`.
  Copy: `— steady since June`. Makes a no-change wine feel complete.
- **restock**: `color --sage-deep`, `border --sage`, `bg rgba(124,138,90,0.10)`, glyph `●`.
  Copy: `● back in stock · Spec's`.
- **watch**: `color/border --brass-deep/--brass`, `bg --cream-raised`, bookmark glyph.
  Copy: `watching`.

**Rule: no movement → no chip.** A steady wine in a grid shows nothing; absence is the design.
(The explicit "steady" chip is used only inside the dossier module where the price context is the
subject.)

**Props:** `{ variant, amount?, store?, sinceLabel? }` → renders the copy patterns above.

---

## Surface 1 · Wine dossier — price-context module

Sits **directly above the availability list** (the existing store + address + price rows). It frames
how to read those rows.

**Layout (desktop):** a `--cream-raised` panel inside the dossier's editorial frame, with a
`0.75px --brass` bottom keyline separating the price header from the store list.
- Header row: eyebrow `PRICE THIS WEEK` (left) + mono `6 weekly checks since June` (right).
- Lede (serif 26px, prose leads): *"Down to **$19.99** at H-E-B on Broadway."* (new number in
  bordeaux). Sub (Archivo, `--faded`): *"Was $24.99 through June — it slipped on Sunday. Cheapest
  nearby by $3; Spec's still has it at $22.99."*
- **Week-marker strip** (right of the lede): a row of ~6 thin bars, `width:8px`, `bg --paper`,
  `0.75px --border`; the previous week bar is `--brass`, the current (dropped) bar is `--bordeaux`
  and shorter. Mono caption `JUN → NOW`. This is a **glyph, not a chart** — it upgrades to a real
  sparkline once history is deep enough to earn one.
- Actions: the **drop chip** + a `Watch price` ghost button.

**Availability list below:** reuse the existing store rows. Flag the cheapest row: `bg
--bordeaux-tint`, bordeaux store-dot, inline `· CHEAPEST` in bordeaux, and show the struck `was`
price above the new `price`. **State "cheapest nearby" exactly once** (in the lede) — do not turn the
list into a comparison engine.

**Sparse / no-movement state (the common case):** replace the lede with *"$28 at Spec's — steady so
far."* (the "so far" in `--faded`) + sub *"No movement since I started watching it in June. I'll flag
it here the week it drops."* Show the **steady chip** + the `Watch price` button. Store list renders
normally with no highlight, no was-price. This must feel resolved and complete.

**Mobile:** same module, stacked; week-strip shrinks to a `22px` inline glyph next to the chip;
`Watch this price` is a full-width ghost button under the price. Store list follows.

---

## Surface 2 · Wine card + mobile pick — the marker in place

Same chip, two homes; **one pattern everywhere**.

**Wine card:** the drop chip leads the brass keyline chip row in the card body (before the flavor
tags). The header price already shows the **new** number; the chip carries the "was" story quietly.
Steady wine → no chip at all (just flavor tags). Reuse the existing WineCard; do not add a contour
map.

**Mobile pick message (conversational):** in the sommelier bubble, the drop chip rides the same line
as the `◎ store` pill (chip `padding:2px 8px` to sit small). The tasting note **also names the drop
in the somm's voice** — *"It dropped $5 at H-E-B on Sunday; worth grabbing before it climbs back."*
— but the chip stays the single visual marker. A steady pick shows only the store pill; the note may
say *"Holding steady at $29."*

**Voice guardrail (all price copy):** grounded in the wine and the place, sentence case, specific
numbers, named stores, no urgency theatrics. Never "30% OFF." Yes: *"the '21 Rioja you liked just
dropped to $19 at Twin Liquors — worth grabbing before it goes back up."*

---

## Surface 3 · Deals discovery — "Worth grabbing this week"

**Placement:** first home is a **rail on Discover** (a curated cut, not a destination you must seek),
with `See all N →` into its own editorial screen.

**Ranking / framing:** ordered by **wine quality × price movement** — sommelier judgment, not
percent-off. Header eyebrow `WORTH GRABBING · WEEK OF JUL 12` + serif title *"Good wine whose price
just moved"* + a lede that states the judgment: *"Not a bargain bin. These are bottles I'd recommend
anyway — they just happen to be cheaper near you this week."*

**Deal card (rail):** `230px` framed card; a `--bordeaux-deep` top strip with the region eyebrow +
a compact drop chip; body has serif wine name, producer/vintage, a one-line tasting note, then new
price (serif bordeaux) + struck `was` price + `◎ store` pill. Horizontal scroll.

**Mobile deals screen:** reached from `See all`; header block + single column of framed WineCards,
each with the drop chip + store pill.

**First-ship decision:** general editorial cut for everyone; **bias by taste profile / saved
bottles later** once profiles are richer. Build the ranking so a personalization weight can be added
without restructuring.

---

## Surface 4 · Watch → sign-in → notification (affordance now, delivery later)

Watching is the natural **"worth creating an account"** moment (app is anonymous-first, optional
magic-link accounts — see the User Accounts handoff).

**Watch action (dossier):** a ghost bookmark button.
- Default: `Watch price` — `1.5px --bordeaux` border, bordeaux text, bookmark glyph.
- Watching: `Watching` — fills solid `--bordeaux`, cream text/glyph. Matches the `watch` chip variant
  used elsewhere.

**Anonymous tap → sign-in nudge:** a contextual bottom sheet (never a wall), dossier dimmed behind.
Eyebrow `WATCH THIS PRICE`; serif headline *"I'll tell you when **Esprit de Tablas** drops."* (wine
in bordeaux); body *"Watches live with your account — passwordless, free. Sign in and I'll ping you
the week it gets cheaper near you."*; email input + `Send magic link`; footnote *"No account needed
to browse — this just saves the watch."* On magic-link success, create the watch and reflect the
`Watching` state. (Reuse the magic-link flow from the accounts handoff; carry the pending-watch
intent through the round-trip.)

**Notification copy (ships later — design now):** weekly-snapshot voice, lead with wine + new number,
name the store, say **"this week."**
- **PWA push:** title *"Esprit de Tablas just dropped to $19.99"*; body *"Down $5 at H-E-B on
  Broadway this week — worth grabbing before it climbs back."* Bordeaux stamp avatar.
- **Email:** bordeaux-deep header band with the stamp + `A PRICE YOU'RE WATCHING`; serif headline
  *"The Esprit de Tablas you're watching just dropped to $19.99."*; body naming the was-price, the
  $5 move, the store, and that it's the cheapest since tracking began; `See the bottle` (primary) +
  `Stop watching` (ghost); footer *"You're watching 3 bottles. Prices checked weekly, Sundays. —
  Somm."*

---

## Interactions & Behavior
- **Marker is derived, not decorative:** render a chip only when the weekly diff produces an event
  (drop / restock) or, inside the dossier module, to state "steady." No event → no chip.
- **All price copy is week-anchored + store-anchored.** Never "today"; always a named store.
- **Watch toggle:** signed-in → create/remove watch optimistically, flip button + `watch` chip.
  Signed-out → open the sign-in nudge sheet; on auth success, apply the pending watch.
- **Cheapest-nearby** stated once (dossier lede) + flagged inline on the best store row. Not a
  standalone comparison feature.
- **Deals** re-cut weekly (tie to the Sunday scrape); header shows the week label + count.
- Transitions 0.12–0.18s; buttons press `translateY(1px)`.
- **Responsive:** desktop modules/rails; ≤ ~640px stacks modules, week-strip becomes inline glyph,
  deals rail → single-column screen.

## State Management / Data shapes (stub where backend is pending)
- `priceSnapshot: { wineId, storeId, price, weekOf }` — weekly rows, June 2026 onward.
- `priceMovement: { wineId, storeId, variant:'drop'|'restock'|'steady', amount?, fromPrice?, toPrice?, sinceLabel, weekOf }` — the derived per-bottle×store event the chip and copy read from.
- `cheapestNearby: { wineId, storeId, price, deltaVsNext }` — precomputed for the dossier lede + best-row flag.
- `deals: DealItem[]` — weekly editorial cut, ranked by `qualityScore × movementScore`; leave a
  `personalizationWeight` seam for later taste-biasing.
- `watches: string[]` (wine IDs) on the signed-in user; anonymous **pending-watch** intent held
  through the magic-link round-trip (localStorage / query param), applied on auth success.
- `notification: { channel:'push'|'email', wineId, storeId, fromPrice, toPrice, weekOf }` — copy
  templates above; delivery ships later.

## Assets
- **The Pin** mark — placeholder cream-pin-in-bordeaux-circle SVG in the mock; swap in the real SVG.
- Icons: thin-stroke line icons (bookmark for watch, search, map-pin, chevrons) from the codebase's
  existing set (e.g. Lucide, 1.5px). No emoji.
- Fonts: `DM Serif Display` + `Archivo` + `DM Mono` (Google Fonts; already loaded via
  `colors_and_type.css`).

## Files
- `Somm - Price Intelligence.html` — full hifi prototype: the marker (4 variants), dossier module
  (desktop / sparse / mobile), card + pick, deals rail + mobile screen, watch states, sign-in nudge,
  and push + email notification copy. Interactive: watch-button toggle.
- `colors_and_type.css` — design tokens (`:root` variables). **Use these variables directly.**
