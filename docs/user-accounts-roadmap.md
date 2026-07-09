# User accounts — roadmap (optional, anonymous-first)

## Vision
Accounts make the Somm *know you* — favorites, your cellar, and a taste profile
turn one-shot anonymous recommendations into personalized, learning ones. But
accounts are **always optional**: the core flow (zip + budget + prefs → recs →
dossier) works fully signed-out. Sign-in is offered contextually (e.g. "Save
this wine") and only ever *adds* capability — it never gates what already works.

## Principles
1. **Anonymous-first, never a wall.** Everything that works today keeps working
   with no login.
2. **sessionId for anon, account on sign-in.** Anonymous users keep today's
   client-side `sessionId` (zero auth rows created). A Supabase auth user is
   created only when someone signs in; their session activity (feedback votes)
   merges to `user_id` at that point.
3. **Auth is client-side; user data is RLS-protected.** `supabase-js` handles
   login/session/JWT in the frontend. User-owned tables (`profiles`,
   `favorites`, `cellar`, `price_watches`) enforce `user_id = auth.uid()` via
   RLS, read/written directly from the frontend — no new backend endpoints.
   The recommendation/search backend stays anonymous and unchanged.

## Auth methods
- **Magic link (email)** — build first. Passwordless, Supabase built-in, no
  external setup. `supabase.auth.signInWithOtp({ email })`.
- **Apple OAuth (Sign in with Apple)** — **DEFERRED (2026-07-07 decision).**
  Needs an Apple Developer account ($99/yr) + App ID/Services ID/key + Supabase
  provider config. Not building for now; magic link only. Revisit later.

---

## Phased roadmap

### Phase 0 — Auth foundation (prerequisite for all of the below)
- Enable Supabase email auth (magic link); configure redirect URL + email template.
- Add `supabase-js` to the frontend; an auth context/provider; persist session.
- Optional sign-in entry point (profile icon / "Sign in" in nav) — not a wall.
- `profiles` table (user_id PK → auth.users, zip, default_budget, styles) + RLS.
- On sign-in: merge anon `sessionId` feedback → `user_id` (column already exists).

### Phase 1 — Saved favorites  ← START HERE
- `favorites` table (user_id, wine_id, created_at, unique per pair) + RLS.
- "Save" (heart) on the dossier + wine cards; a "Saved" view.
- Anonymous tap on Save → contextual sign-in prompt, then save.

### Phase 2 — Cellar (wines you own / recently bought) — IN PROGRESS
**Decisions (2026-07-08):** Core scope (add + quantity + purchase date + list +
drinking-window signal + "drank it" consumption). Drinking window from an **auto
heuristic** (varietal+vintage → year range, `lib/drinkingWindow.js`, no LLM,
user can override). **Both add-paths** (dossier "Add to cellar" for catalog
wines + manual "+ Add bottle" for off-catalog).

**Foundation DONE:** `cellar` table (migration `20260708000001`, RLS-scoped,
`wine_id` nullable for off-catalog, denormalized name/vintage/region, quantity,
purchase_date, price_paid, drink_from/drink_to, status owned|consumed, notes);
`lib/drinkingWindow.js` (`drinkingWindow()` + `windowStatus()` → hold/ready/soon/
past + label + fill, TDD'd); `lib/cellar.js` (list/add/update/remove/drinkBottle).

**REMAINING (UI):** Cellar screen (list + drinking-window bars per handoff
screen 7 + "+ Add bottle"), the Add-bottle form (manual + catalog prefill),
dossier "Add to cellar" button, account-screen Cellar tile/link → real count.

### Personalization engine — the north star (behavioral signals first)
**Decisions (2026-07-08):** Build behavioral personalization FIRST (saved +
cellar, no user effort), **re-rank + cite** depth, conversational interview for
the explicit profile later.

**One `taste` pipeline, four signals:** taste profile (explicit, Phase 3) +
saved + cellar + feedback thumbs. The frontend (RLS read) gathers the user's
signals into a compact `taste` object and passes it to `/api/recommend`; the
scorer boosts candidates similar to liked wines / matching the profile, and
Claude cites the link ("close to the Esprit de Tablas you saved").

**"Close to a wine you liked" = data lookup, not embeddings.** Every wine has
grape/region/flavor-tags/structure, so similarity = shared grape (strong) +
region (medium) + flavor-tag overlap (weak). Scorer records the closest liked
wine per candidate (`_similar_to`) → Claude names it.

**Build sequence:**
1. Scorer similarity boost + `_similar_to` tag (backend, TDD). ← starting here
2. `taste` field on RecommendRequest; Claude gets liked wines + citation instruction.
3. Frontend `buildTasteContext(userId)` — saved + cellar → liked_wines with flavors; passed on every recommend.
4. Feedback-as-signal (later): send user_id on votes + RLS read policy + merge on sign-in, then include up/downvoted wines.

### Phase 3 — Somm taste profile (conversational preference interview)
- The Somm asks the client a guided set of questions — like a real sommelier
  interviewing you — to build a persistent taste profile (grapes loved/avoided,
  body, sweetness tolerance, adventurousness, favorite regions, price comfort,
  occasions). Conversational (Somm-chat-driven), not a dry form.
- Stored as structured `taste_profile` on `profiles`.
- Feeds the recommendation engine: merges into intent/scoring so a signed-in
  user gets recs tuned to their profile, not just the current request.

### Phase 4 — Price alerts (unblocks the deferred price-alerts Phase 2)
- `price_watches` (user_id, wine_id, target_price or any-drop).
- Notifier reads `price_history` (already capturing) after each scrape → email/push.
- Depends on the notification channel (email via Supabase, or push for the PWA).

---

## The north star: personalization
Favorites + cellar + taste profile + feedback votes together form a rich user
model. The payoff is the recommendation scorer reading that model for signed-in
users: "you loved these Rhône blends, you own three Barolos, you avoid oaky
Chardonnay" → materially better picks. Each phase adds a signal; Phase 3 makes
it explicit. This is the reason accounts are worth having — not just storage,
but a Somm that learns your palate.

## Data model summary
| Table | Keys | Phase |
|---|---|---|
| `profiles` | user_id PK → auth.users; zip, default_budget, styles, taste_profile | 0 (profile) / 3 (taste) |
| `favorites` | user_id, wine_id, created_at; unique(user_id, wine_id) | 1 |
| `cellar` | user_id, wine_id?, free_text_name, purchase_date, price_paid, qty, status | 2 |
| `price_watches` | user_id, wine_id, target_price | 4 |
| `feedback.user_id` | already exists — populate on sign-in | 0 |

## Needs the user (external setup)
- **Apple OAuth**: Apple Developer account + Sign-in-with-Apple key before wiring.
- Magic link: verify Supabase email settings + set the site/redirect URL to the
  Vercel domain (and localhost for dev).

See root CLAUDE.md; price-alerts capture is already live (`price_history`).
