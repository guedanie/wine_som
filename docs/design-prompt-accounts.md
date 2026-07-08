# Design prompt — user accounts (paste into Claude to generate mockups)

Copy everything below the line into a fresh Claude conversation. It will produce
an interactive HTML mockup you can iterate on, then hand back as a build spec.

---

You are designing UI for **Somm**, an editorial wine-atlas web app (React + Vite
PWA, desktop + mobile). Produce a **single self-contained interactive HTML
artifact** (inline CSS, design tokens as `:root` CSS variables, vanilla JS for
state toggles) mocking a new **optional user-accounts** area. Show each element
in **both desktop and a 390px-wide mobile phone frame**, with its key states.
Match the design system below exactly — this must look like it belongs in the
existing app.

## The product in one line
*Every bottle is a place.* An editorial wine atlas: confident, warm, opinionated
— a knowledgeable sommelier friend, never a textbook.

## Design system (use these tokens as CSS variables)
```
--ink:#1A1A1A  --body:#33312C  --faded:#6B6453
--bordeaux:#6E1023  --bordeaux-deep:#560B1B  --brass:#B08D57  --sage:#7C8A5A
--paper:#EFE6D4  --cream:#F5EFE6  --cream-raised:#FBF8F2  --border:#DDD5C8
```
- **Type:** `DM Serif Display` for anything expressive (headlines, wine/region
  names — never below 23px, it's a display face). `Archivo` for ALL UI, body,
  labels, buttons. Monospace only for coordinates/codes. Load both from Google Fonts.
- **The frame:** important surfaces use a `1.5px solid #1A1A1A` outer border with
  a `0.75px solid #B08D57` brass inner keyline — like a matted print.
- **Corners are SHARP** (`border-radius: 0`) for cards, buttons, inputs, frames.
  Soft radius (8–14px) + pills are reserved ONLY for chat/conversational surfaces.
- **Casing:** UPPERCASE TRACKED for eyebrow labels + coordinates (e.g.
  `SAVED · 12 BOTTLES`). Serif Title Case for wine/region names. Sentence case elsewhere.
- **Buttons:** Primary = `background:#6E1023; color:#F5EFE6; border-radius:0; no border`.
  Ghost = transparent + `1.5px solid #6E1023` border, bordeaux text. Press = translateY(1px).
- **No emoji. No gradients** (except a subtle radial inside a dark bordeaux field).
  No glassmorphism, no drop-shadows-everywhere, no glows. Line-led, type-led.
- **The mark ("The Pin"):** a map-pin with a wine-glass cut as negative space —
  used as the avatar/brand stamp. On bordeaux surfaces it's a cream pin in a
  bordeaux circle. Use a simple 32px bordeaux circle with a cream pin glyph as a
  stand-in; I'll swap the real SVG in.

## Voice (all copy)
Knowledgeable, warm, specific. Address the user as **you**; the app speaks as **I**.
Short. No filler ("Absolutely", "Great!"). Lead with the wine and the place.

## Critical principle: accounts are OPTIONAL and anonymous-first
The entire app works with NO login (enter zip + budget + style → get sommelier
recs → wine dossier). **Sign-in is never a wall** — it's offered *contextually*
(e.g. tapping "Save") and only ever *adds* capability. Sign-in is **email magic
link only** — no passwords, no social login. Copy should make optionality clear,
e.g. "No account needed to browse — sign in to save bottles and get picks tuned
to your taste."

## Screens / elements to mock
Priority 1–5 are what we build first (auth + favorites). 6–7 are the near-future
vision — mock them lightly so we can iterate the whole account area's shape.

1. **Auth entry point**
   - Desktop nav (top bar): signed-OUT shows a ghost "Sign in"; signed-IN shows a
     small pin-avatar that opens a menu (Saved · Cellar · Profile · Sign out).
   - Mobile: a "You" item in the bottom tab bar; signed-out state prompts sign-in,
     signed-in shows the account home.

2. **Magic-link sign-in** (modal on desktop, bottom sheet / full screen on mobile)
   - State A — *enter email*: serif headline ("Save this bottle" or "Sign in"),
     one email input, a primary "Send magic link" button, and a line explaining
     it's passwordless + optional. Small print: what accounts unlock.
   - State B — *check your email*: confirmation ("Check your inbox — I sent a link
     to you@email.com"), a "Resend" affordance, and a way to change the email.

3. **Contextual save prompt** — the same sign-in modal, but headed with the wine
   in context: "Sign in to save **Esprit de Tablas**." (Anonymous tap on Save.)

4. **Save affordance (favorite)** — a "Save" control on the wine dossier and on
   wine cards. States: unsaved and saved. Explore an on-brand treatment (a thin
   bookmark/ribbon line-icon, or a labeled ghost "Save" that becomes "Saved ✓" in
   bordeaux) — NOT a literal heart/emoji. Show it on a dossier and on a compact card.

5. **Saved view** — a screen listing saved wines (reuse the editorial wine-card
   look). Header eyebrow ("SAVED · 12 BOTTLES"), the grid/list, and an **empty
   state** ("Nothing saved yet — tap Save on any bottle and it lands here.").
   Desktop grid + mobile single-column.

6. **(near-future) Account home / profile** — signed-in: email, saved preferences
   (zip · budget · styles, editable), and links to Saved and Cellar. Sign out.

7. **(future vision, light) two teasers** so the account area reads as a whole:
   - **Cellar** — wines you own/recently bought (some not in our catalog): a list
     with vintage, purchase date, and a drinking-window indicator.
   - **Somm taste profile** — a conversational interview where the Somm asks the
     client questions (like a real sommelier) to learn their palate. Mock one
     chat-style question card (soft-radius bubble, a question + 3–4 chip answers).

## Output requirements
- ONE HTML file, self-contained, tokens as `:root` vars, Google Fonts linked.
- Every element shown in **desktop AND a 390px mobile frame**, with its states
  visible (toggle buttons are fine).
- Sharp corners everywhere EXCEPT the taste-profile chat bubble (soft) and the
  mobile bottom sheet (top corners may be soft).
- Briefly annotate each block (a small caption) with what it is / what it does.
- Keep it on-brand: serif headlines, Archivo UI, brass keylines, bordeaux
  primary, no emoji, no gradients.

After you generate it, I'll iterate with you on specifics, then use it as the
build spec.
