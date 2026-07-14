# Design brief — price history, deals & price watches

You're designing the price-intelligence layer for **Somm**, an editorial wine
atlas that recommends bottles available at stores near the user (live private
beta; installable mobile PWA + desktop web). Before anything else, read the
design system — `frontend/CLAUDE.md` in this repo. The non-negotiables that
will shape this work: DM Serif Display + Archivo pairing, ink frames with
brass keylines, sharp corners (pills only on conversational surfaces),
bordeaux/brass/cream palette, **no emoji**, and a voice that's a knowledgeable
friend — never a discount catalog.

## The idea

We quietly track every bottle's price at every store, week over week. Nobody
else in the user's life knows that the Rioja they liked is $4 cheaper at
Twin Liquors this week than it was in June. Somm should. Three product moments
fall out of that:

1. **Price context on the bottle** — when you're looking at a wine, show how
   its price has moved and where it's cheapest nearby. "Was $24.99 through
   June, $19.99 at H-E-B since Sunday."
2. **Deals as discovery** — a browsable way to find what's *worth grabbing
   this week* near you. Not a bargain bin: an editorial cut ("good wine whose
   price just moved"), consistent with a sommelier's opinionated voice.
3. **Price watches (designs now, ships later)** — a signed-in user marks a
   bottle to watch; we notify them when its price drops nearby. The backend
   for notifications isn't built yet, but the *affordance* (where the watch
   action lives, what state it shows, what the notification says) should be
   designed with the other two so it doesn't get bolted on.

## What the data honestly supports (design to this, not past it)

- **Weekly snapshots, not live prices.** Scrapes run Sundays; a "drop" is a
  week-over-week event. Copy must say *this week*, never *today/right now*.
- **Per bottle × per store.** A wine can drop at H-E-B and not at Spec's. Price
  claims are always anchored to a named store ("at H-E-B on Broadway").
- **History starts June 2026.** At design time there are ~6 weekly points per
  bottle at best — a sparkline will look thin. Consider whether a mini-chart
  earns its place yet vs. a written "was/now + since when" treatment that
  gracefully upgrades as history deepens.
- **Most bottles most weeks: no change.** The interesting set is a few hundred
  to a few thousand movements per week across ~90k in-stock rows. Sparse-state
  design is the real design problem: a wine with no price movement should
  still feel complete, and the deals surface should feel curated, not empty.
- **Out-of-stock transitions are also tracked** — "back in stock" is available
  as a secondary signal if useful.

## Surfaces to design

1. **Wine dossier (mobile + desktop)** — the price-context module. Where does
   it sit relative to the availability list (store + address + price rows that
   exist today)? How does "cheapest nearby" read? What does it look like when
   there's no history worth showing?
2. **Wine card + mobile pick message** — a price-drop marker. Cards carry an
   editorial header strip and brass keyline chips; mobile picks are
   conversational messages with a `◎ store` pill. The marker must whisper, not
   shout — closer to a cellar note ("↓ $5 this week at H-E-B") than a sale
   burst. Decide whether it appears in the somm's own voice (inside the pick's
   tasting note) or as chrome (a chip), and keep one pattern everywhere.
3. **Deals discovery** — where does "worth grabbing this week" live? A rail on
   Discover, a filter, its own screen? How is it ranked and framed so it reads
   as sommelier judgment (wine quality × price movement) rather than a
   percent-off grid?
4. **Watch + notification (future-proofing)** — the watch action on a dossier
   (icon? state when watching?), the sign-in nudge for anonymous users (the
   app is anonymous-first with optional magic-link accounts — watching is the
   natural "worth creating an account" moment), and the notification content
   itself (PWA push and/or email — write it in the somm's voice).

## Voice guardrails

The somm never says "30% OFF!!!" — they say *"the '21 Rioja you liked just
dropped to $19 at Twin Liquors — worth grabbing before it goes back up."*
Price talk is always grounded in the wine and the place. Sentence case,
specific numbers, named stores, no urgency theatrics.

## Deliverables

- Flows/mocks for the four surfaces above (mobile-first; desktop where layouts
  diverge), including sparse/empty states.
- One reusable price-movement treatment (chip/note/module) specified against
  the existing tokens, with exact copy patterns.
- The watch → sign-in → notification flow, even though notification ships later.

## Open questions we'd like design's opinion on

- Does price history earn a visualization at 6–10 weekly points, or is prose
  ("was/now, since when") stronger until the data deepens?
- Should deals be personal (biased by the user's taste profile/saved bottles)
  from day one, or is a general editorial cut the right first ship?
- Where's the line between helpful ("cheapest nearby: $17 at Spec's") and
  making Somm feel like a price-comparison engine rather than a sommelier?
