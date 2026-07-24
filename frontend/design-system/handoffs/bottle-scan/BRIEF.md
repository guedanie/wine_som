# Design brief: Somm — Bottle Scan (photo → identify → buy / save)

*This is the INPUT prompt for the design session. The output should be a handoff bundle in this
directory matching the price-intelligence pattern: a `README.md` spec + a single self-contained
high-fidelity HTML prototype built on `colors_and_type.css` tokens. Read
`frontend/CLAUDE.md` (design system + voice) and the price-intelligence `README.md` (format
reference) first.*

## The feature in one line
The user shows their sommelier a bottle — snaps a photo of the label (or scans the barcode) —
and Somm identifies it, then does one of two useful things: **tells you where to buy it nearby**,
or **remembers it for you** (save / cellar / "I drank this").

## Why it matters
This is the bridge between the physical world and the atlas. The two moments it serves:
1. **In the aisle** — standing in a store holding an unfamiliar bottle: "is this any good, and
   is it cheaper elsewhere near me?" One-handed, hurried, variable lighting.
2. **At the table** — a friend poured something great: "remember this for me." The wine may not
   be stocked anywhere nearby — that's fine, remembering is the product.

## The data + tech reality (design to this, not past it)

- **Two-tier identification.** Tier 1: **barcode scan** — instant, exact, free. The catalog is
  keyed by `upc_canonical`; **54% of the live catalog (10,881 of 20,274 wines) has a real
  scannable barcode**. Tier 2: **label photo → Claude vision** → producer / wine name / vintage
  read off the label → fuzzy match against the ~20k-wine catalog. Design both entry affordances;
  barcode is the fast path when the bottle is in hand, photo is the universal path.
- **Vision takes 2–5 seconds.** The identifying wait is a real state, not a spinner-flash.
  It should feel like the somm squinting at the label ("Let me get a look at it…"), consistent
  with the streamed "Looking deeper into the cellar…" pattern in chat.
- **Confidence is a spectrum — five result states, all first-class:**
  1. **Exact hit** (barcode, or unambiguous label match) → straight to the result sheet.
  2. **A few candidates** (vision read is good but matches 2–4 rows — same producer, different
     bottlings/vintages) → quick disambiguation, thumbnails + name/vintage, one tap.
  3. **Identified but different vintage** — catalog identity is vintage-specific today (a
     product-family layer exists only as a future spec). The bottle in hand may be the 2019
     while nearby stores stock the 2021. Treat vintage as a soft confirm: *"That's Tablas
     Creek's Esprit — I see the 2021 nearby; yours looks like the 2019."* Never a dead end.
  4. **Recognized, not stocked** — vision names the wine but no nearby store carries it.
     Still a success: offer save / cellar, and say so in somm voice (*"Nobody near you stocks
     it — I'll remember it for you."*). Seam for a future availability-watch, mirroring the
     price-watch affordance — design the ghost of it, don't build it.
  5. **Can't read it** — glare, foil, cropped label. A graceful retry with one concrete tip
     (*"Get the whole front label in frame"*), never an error tone.
- **Result sheet content** (when identified + stocked): reuse existing atoms — WineCard header
  pattern, ratings badge, StructureBars, flavor chips, availability rows with store + address +
  price + distance, price-drop chip where one applies. This is largely the dossier compressed
  into a sheet; deep-link to the full dossier.
- **Actions hierarchy (the two jobs):** primary = **where to buy nearby** (availability rows);
  secondary = **Save** / **Add to cellar** / **I drank this** (drank flow feeds the cellar
  rating loop). When not stocked nearby, remembering becomes primary.
- **Anonymous-first.** Identify works signed out. Save/cellar taps by an anonymous user open
  the existing contextual sign-in nudge sheet (magic link, pending-intent carried through the
  round-trip — same pattern as price watches: *"I'll remember this one for you"*).
- **PWA camera constraints.** iOS PWA: `<input type="file" capture="environment">` is the
  reliable path (full-screen native camera, returns a photo); live `getUserMedia` viewfinder is
  possible but flaky in standalone mode. Design for the native-camera round-trip (tap → OS
  camera → return with photo → identifying state), with a live-viewfinder barcode scanner as a
  progressive enhancement. Photos are sent for identification only, not stored — say so
  quietly (one line, not a privacy banner).
- **No history/feed requirement in v1.** A "recently scanned" list is a natural later layer on
  the account home; note the seam, don't design the surface.

## Design questions to explore (genuinely open — bring options)
1. **Entry point(s).** Where does scan live so it's findable in-aisle in 2 seconds? Candidates:
   a camera affordance in the top chrome / tab bar; inside the Somm chat overlay ("show me the
   bottle"); on the account home. It should read as *showing your sommelier a bottle*, not as a
   barcode-scanner utility. Probably one primary home + one conversational entry; you decide.
2. **Capture screen framing.** How much chrome around the native-camera round-trip? Label vs
   barcode mode — a toggle, auto-detect, or two buttons?
3. **The result sheet.** Bottom sheet vs full screen? How does the five-state spectrum collapse
   into one component family without five bespoke layouts?
4. **Disambiguation** interaction for the 2–4 candidate case — fast, one-handed.
5. **Voice.** Somm lines for every state (identifying, found, not-stocked, unreadable, vintage
   mismatch). Grounded, specific, no error-speak. The somm never says "no results found."

## Non-negotiables (from the design system — `frontend/CLAUDE.md`)
- Tokens from `colors_and_type.css` only; no hardcoded hexes. DM Serif Display ≥23px display,
  Archivo UI, DM Mono for coordinates/codes. Sharp corners except conversational surfaces
  (sheets/pills/bubbles). 1.5px ink frame + 0.75px brass keyline on card surfaces. No emoji,
  no gradients, no glows. Thin-stroke Lucide icons only where functional (camera, barcode).
- Voice: knowledgeable friend; the app speaks as **I**, addresses **you**; leads with the wine
  and the place; short sentences; specific numbers and named stores.
- Reuse before invent: WineCard, StructureBars, availability rows, price chip, sign-in nudge
  sheet, chat bubble grammar all exist — this feature should look like it was always there.

## Deliverables (match the price-intelligence handoff)
1. `README.md` — full spec: states, layouts (desktop + mobile), copy for every state, data
   shapes the frontend will consume (e.g. `scanResult: { status: 'exact'|'candidates'|
   'vintage_mismatch'|'unstocked'|'unreadable', wine?, candidates?, availability?, readVintage? }`),
   interaction + behavior rules.
2. `Somm - Bottle Scan.html` — one self-contained hi-fi prototype: entry point in context,
   capture states, identifying state, all five result states, disambiguation, save/cellar
   actions incl. the anonymous sign-in nudge, mobile-first with desktop notes.
