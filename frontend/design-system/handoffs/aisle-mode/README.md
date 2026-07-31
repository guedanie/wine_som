# Handoff: Somm — Aisle Mode (two doors into the recommendation thread)

## Overview
**Somm** is an editorial wine atlas (React + Vite PWA, FastAPI backend) that recommends real bottles
available at retailers near the user. Today's recommendation flow assumes one posture: *"I'm at home,
deciding what to buy"* — set a zip, drag a budget slider, tap style cards and an occasion pill, get
picks. That's deliberate and considered, and it stays the primary path.

This handoff adds the other posture: **"I'm standing in the wine aisle holding two bottles and I want
an answer now."** In that moment chips and sliders are friction — the user wants to ask a question,
not configure a search.

The two are **not two products**. They are two faces of the same window, and the app already routes
them: `/` (`PreferenceCapture`) and `/recommend` (`ChatRecommend`). This work makes that pair legible,
gives the conversational face a proper front door, and adds store-level context.

## About the Design Files
`Somm - Aisle Mode.html` is a **design reference created in HTML** — a canvas prototype showing the
switch options, both doors, streaming states, answer shapes, and failure states. It is **not
production code to copy**. Recreate it in the existing codebase using the real components; every
pattern in the prototype was matched against `main` (see *Grounding* below).

**Do not hardcode hexes and do not author a `:root` block** — import
`frontend/design-system/colors_and_type.css` and use its tokens and semantic classes.

## Fidelity
**High-fidelity.** Layout, copy, states and interaction rules are specified. The considered-mode face
in the prototype is cropped to the frame (style grid, budget, occasion); wine type, free text and zip
continue below the fold exactly as `PreferenceCapture` renders them.

---

## Grounding — what this was built against
Read these before changing anything; the prototype already conforms to them.

| Concern | Source of truth |
|---|---|
| Tokens, `.t-*` classes | `frontend/design-system/colors_and_type.css` |
| Brand mark ("The Pin") | `frontend/src/components/Stamp.jsx` — a cream map pin with a bordeaux wine glass cut into it. **Not** the contour-circle in `assets/mark-terroir*.svg`, which is stale. |
| Top bar + tab bar | `frontend/src/components/MobileChrome.jsx` — five tabs: Recommend · Discover · Search · Saved · You |
| Chat grammar, streaming, picks | `frontend/src/screens/ChatRecommend.jsx` |
| Considered-mode controls | `frontend/src/screens/PreferenceCapture.jsx` |
| Thinking state | `frontend/src/components/WineGlassLoader.jsx` |
| Price chip | `frontend/src/components/PriceMarker.jsx` |
| Keyframes | `frontend/src/index.css` |
| Recommendation API | `backend/api/routers/recommend.py` |

Two token facts that are easy to get wrong: **`--border-strong` is `var(--ink)`** (it is the 1.5px
editorial frame colour, not a soft grey — use `--border` for hairlines), and **`--font-mono` is the
system stack**, not a webfont. `.t-eyebrow` / `.t-coord` are 11px Archivo.

---

## The chosen structure: two doors, two depths of context

### The switch — tabs, not a toggle
Replace the mode question with **two underlined labels sharing the header's ink rule**:
`PLAN A BOTTLE` | `ASK`. Active label is `--ink` with a `2.5px --bordeaux` bottom border pulled onto
the header rule; inactive is **`--faded`** (not `--faded-2` — the inactive label is the only
persistent signal that the second face exists, and it must pass contrast). Both labels are tap
targets; horizontal swipe between faces also works.

Rejected alternatives, documented in the prototype: a boxed segmented control (reads as a *setting*
with two values rather than two pages) and an edge-peek sliver (most self-teaching but permanently
taxes 30px from the primary flow to teach something once).

**`PLAN A BOTTLE` stays the default landing** — most sessions are people who don't know what to get.

### Door 2 — the standing invitation
A persistent strip above the tab bar on the considered face: a map-pin glyph, **"In a store right
now? Just ask me instead."**, and a right chevron, on `--bordeaux-tint` with a `0.75px --brass` top
keyline. Tapping it crosses to the Ask face **and** opens the store picker.

A tab says *there is another view*; the strip says *here is when you'd want it*. That's the part a
toggle can't do, and it's how someone learns aisle mode exists before they're standing in an aisle
needing it. It may be dismissible after first use.

### Why two doors matter
The doors carry **different depths of context**:
- **The `ASK` tab is general.** It opens clean — no zip prompt, no store prompt, no form. "Is
  Nebbiolo like Pinot Noir?" needs no location, so demanding one would be pure friction and would
  misrepresent the face.
- **The strip is store-specific.** Tapping it is a declaration — *I'm here, now* — so asking which
  store is welcome rather than friction.

**Location is lazy through the tab, eager through the strip.** Same face, same thread; different
amount known on arrival.

---

## Screens

### Ask — empty state (chosen: the single invitation)
Centered in the thread: the 46px reversed Stamp, a serif question **"What can I help you with?"**
(deliberately generic — this door knows no store), a `--faded` line *"Name a bottle, name two, ask
what something is, or just tell me what you're eating. No sliders in here."*, then four intent pills:
`Compare two` · `Is this good?` · `What is this?` · `Pair with dinner`.

Two alternates are in the prototype and were **not** chosen: a list of four worked example questions
(teaches phrasing best, reads listy — its idea survives as the intent pills), and a warm continuation
for returning users (not a competing empty state — it's this screen with history above it; add it
once the thread is persisted).

### Lazy location
When an answer needs shelves, the zip request arrives **inside the conversation** — a somm line
(*"…I can name bottles you'll actually find tonight if you tell me roughly where you are."*) followed
by a sharp `1.5px --ink` field labelled **YOUR ZIP / CITY** and a `Set` button, with *"Asked once —
I'll remember it from here on."* Then the `WineGlassLoader` while it resolves. Skipped entirely when
a zip already exists (`loadZip()` — localStorage `somm_zip`, default `78209`).

### Store picker (from the strip)
Somm asks *"Which one are you standing in? I'll keep my answers to what's on their shelves."* Then a
framed list of nearby stores ranked by distance, closest flagged `closest` in bordeaux, each row
showing branch name + area + miles. Below: a ghost **"Somewhere else — just use my zip"** escape
hatch. Footnote: *"Store is a soft filter, not a cage — I'll still name a better bottle down the road
if there is one."* If no zip exists yet, ask zip then store, back to back.

Once set, location lives as **editable pills in the thread** (not in the top bar — the top bar keeps
its own sharp `MobileChrome` readout).

### Streaming
The layout must be composed at every frame; nothing reflows when picks land.
1. **Thinking** — reversed Stamp + `WineGlassLoader` (default text *"Thinking about your next
   bottle"*), plus the `status` event text when present (the backend sends *"Looking deeper into the
   cellar…"*).
2. **Narrative streaming** — text arrives token by token with a `2px --bordeaux` caret animating on
   `blink`.
3. **Picks pending** — a pulsing `.t-eyebrow` **"Pouring your picks…"** indented to align with the
   bubble (`padding-left: 43px`). *Not* a second glass loader.
4. **Picks land one at a time**, then the factual availability strip.

### Pick messages (Option C — unchanged from `ChatRecommend`)
The somm's *why* note leads at 12.5px; then a **`0.75px --border` divider**; then one wrapping row
holding the tappable bordeaux serif name (with brass underline and `→`), the price in `--ink`, the
sage `◎ retailer · distance` pill, the `PriceMarker` when a drop applies, and the Vivino rating when
present. No card chrome. **No flavor-tag chips** — source doesn't render them here.

Store pills always read **`◎ store · distance`**. No aisle numbers anywhere; we have no shelf data.

### Availability strip
Eyebrow type only — `.t-eyebrow`, `line-height 1.5`, `gap 3`, no box, no rule, no colour. It is the
counted truth in system voice, deliberately unglamorous, and reaches the user even when the narrative
hedges. Rendered from the `availability` event's `lines`.

### Answers with no cards
Education and pairing answers legitimately return no picks — the layout must not assume cards.
**Chosen closer: a single offer in the somm's voice** — *"Want me to find you a good one here?"* with
`Yes, find one` / `No thanks`. One offer converts an explanation into a purchase without pretending
cards were coming. Follow-up-question chips (also prototyped) are better on desktop and risk feeling
like a quiz on a phone.

### Two-bottle comparison (chosen: facts frame, then verdict)
The signature aisle moment. Framing bubble, then a **sharp `1.5px --ink` two-column frame** — this
part is data, not conversation — with rows for price, body, tannin and food; the winning column
washed `--bordeaux-tint` with a `MINE` flag. Then the **verdict in a bubble** in the somm's voice.
Then **the pick as a normal wine message**, so it's tappable, savable and thumbable like any other
recommendation. Then the availability strip.

The design system's own logic does the work here: data is sharp, conversation is soft.

A second shape is kept for one case only — **verdict-first in serif** ("Neither, if I'm honest.") when
the honest answer is a third bottle. Same grammar, different opening move.

### Failure states
- **Dropped request** — the somm apologises in character (*"Lost you for a second — the signal in
  here is doing me no favors. Your question's saved; tap when you've got a bar or two."*), never
  "Network error". The question is preserved verbatim, one `Ask again` retry, and recent answers stay
  readable so a user mid-aisle can still find the bottle. Top bar readout reads `No signal`.
- **Half-arrived answer** (the common in-store failure) — **what arrived stays**; one pick is still
  useful. The retry asks only for the remainder (`Finish the answer`), which also spends fewer
  requests against the rate limit.

---

## Backend work required
Read from `backend/api/routers/recommend.py` — three real deltas, one of them new:

**1. Add `store_ref` to `RecommendRequest`** *(the decision taken)*. Store context currently comes
from free text via `detect_store(req.message, stores_meta)`, which then scopes the targeted fetch
(`.eq("store_ref", detected_store["id"])`) and re-sorts the shortlist toward that store — so the
pipeline is already there. Pass the picked store as a **structured field** instead of re-parsing it
from prose every turn: when `req.store_ref` is present, use it directly as `detected_store` and skip
detection. Keeps the store an explicit session fact.

**2. No budget assumption in the aisle.** `budget_min`/`budget_max` are **hard SQL filters on every
query and cannot be omitted** — so aisle mode must send a **wide range** (e.g. `0`–`10000`) rather
than dropping the field, and the prompt must not say "outside your budget" unless a budget was
actually stated in the sentence. Precedent exists: `_named_fetch()` already ignores budget
deliberately, so a named bottle is never hidden by the slider — exactly the bottle-in-hand case.

**3. Two named bottles in one query.** `parse_message` resolves a single `wine_name`, and the
`"named"` deep-fetch path calls `_named_fetch(resolved["wine_name"])` singular. Comparison needs a
list: parse 2+ bottle names, fetch each, and pin both into the shortlist (`comparison_regions` is the
existing precedent for the 2+ case, at region level). **This is the single highest-value backend fix
for this mode.**

**Rate limit:** `RateLimiter(limit=15, window_seconds=3600)` per IP on `/api/recommend` (`/api/somm`
is 40/hr; `RATE_LIMITS_OFF=1` disables). **This design assumes the limit is raised** — no throttle UI
anywhere, because follow-ups are the entire point of a thread and a visible counter would poison it.
The partial-retry above helps by not re-spending a request on a whole answer.

**Already works — don't rebuild:** no-card answers (the `conversational` flag flows from
`naturalChatMode()` into `stream_recommendations`), the availability oracle and its lines, progressive
`pick` events, and retailer-level scoping via `detect_retailer`.

## Data & state
- SSE event contract (unchanged): `status` · `token` · `pick` · `picks` (+`session_id`) ·
  `availability` · `suggestions` · `error` · `[DONE]`.
- `mode: 'plan' | 'ask'` — which face is showing; persists across navigation.
- `storeRef: string | null` + `storeLabel` — the standing store; editable pill; cleared by "Somewhere
  else".
- `zip` — `loadZip()`/`saveZip()`, localStorage `somm_zip`.
- Thread persists with full scrollback; follow-ups expected. `pendingQuestion` survives a failed
  request.
- Nearby = `find_nearby_store_ids(zip, radius_miles=10)`; inventory older than 10 days is benched
  (weekly Sunday scrape — hence "checked Sunday" phrasing).

## Voice
Knowledgeable friend; the app speaks as **I**, addresses **you**. Lead with the wine and the place.
Short sentences, specific numbers, named stores. Sentence case except UPPERCASE tracked eyebrows.
Never "no results found", never "error", never urgency theatrics. The somm is opinionated — "Neither,
if I'm honest" is on-brand; hedging is not.

## Files
- `Somm - Aisle Mode.html` — the prototype: three switch approaches + three discoverability
  iterations, both doors, lazy location, store picker, three empty-state options, streaming states,
  no-card closers, two comparison shapes, and two failure states. Build notes panel records the
  assumptions.
- `colors_and_type.css` — the design tokens, synced from `frontend/design-system/`. **Import it.**
