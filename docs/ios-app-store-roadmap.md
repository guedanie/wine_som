# Somm on the iOS App Store — Roadmap / Feasibility Map

**Date:** 2026-07-25 · **Status:** planning (not started)

## TL;DR

Somm is a React 19 + Vite PWA. The right path is **wrap the existing frontend with
[Capacitor](https://capacitorjs.com)** — a native iOS shell around the web app — reusing
100% of the React UI and the entire Railway/Supabase backend unchanged. No React Native
rewrite, no bare WKWebView (Apple rejects those).

**The single biggest risk is App Store Guideline 4.2 (Minimum Functionality):** Apple
rejects apps that are "just a repackaged website." A bare Capacitor wrap of Somm would
likely be rejected. The mitigation is strategically convenient — **two features already on
the Somm roadmap are exactly what Apple wants to see**: bottle-photo label identification
(item 26 → Camera) and price-drop notifications (item 16 notifier → Push). Landing one or
both as *native* integrations turns Somm from "a website in a wrapper" into a genuine app.

Second concern: **alcohol content.** Under Apple's 2025→2026 age-rating overhaul (the old
17+ is gone; new tiers are 13+/16+/18+), an alcohol recommendation app rates **18+** and
should ship a first-launch **age gate**. Somm *recommends and links to local retailers* —
it does not *sell or deliver* alcohol — which keeps it out of the stricter
sales/delivery-app territory, but 18+ + age gate still apply.

## Why Capacitor (and not the alternatives)

| Approach | Verdict |
|---|---|
| **Capacitor wrap** (recommended) | Reuses the React app as-is; `webDir` points at Vite's `dist`; adds an iOS Xcode project; official plugins for Push/Camera/Deep-links. ~10–20% new native glue. |
| React Native rewrite | Months of work re-implementing the whole UI. Not justified. |
| Bare WKWebView wrapper | Cheapest, but the classic Guideline 4.2 rejection. Avoid. |
| PWA-only (no store) | Already works (Add to Home Screen), but no App Store presence, no push on iOS is limited, no discoverability. This is the status quo. |

## What's reused vs. new

**Reused unchanged:** the entire `frontend/` React app, the Railway backend + recommendation
engine, Supabase auth/data, PostHog analytics. The native app loads the same built web
bundle and calls the same API.

**New work:**
1. Capacitor project + iOS shell (config, Xcode project, app icon/splash).
2. **Magic-link auth deep-linking** — today `auth.jsx` uses
   `emailRedirectTo: window.location.origin`; in a native shell that origin is
   `capacitor://localhost`, so the magic-link email would open Safari, not the app. Needs
   **Universal Links** (Associated Domains entitlement) or a custom URL scheme, plus the
   redirect URL added to Supabase's auth allowlist.
3. **Backend allowlists** — add the native origin to the backend CORS `ALLOWED_ORIGINS`
   and to Supabase's redirect allowlist.
4. **At least one native feature** to clear Guideline 4.2 (see Phase 3).
5. **Age gate** (first-launch 18+ confirmation) + age-rating questionnaire.
6. Store assets + privacy compliance (see Phase 4).

## Phased plan

### Phase 0 — Decisions & accounts (blocking)
- **Apple Developer Program** — $99/yr. Choose **Individual** (fast, your name shows as
  seller) vs **Organization** (needs a D-U-N-S number, shows a company name — better for an
  alcohol brand; slower to set up). *Decision needed.*
- **Bundle ID** (e.g. `com.somm.app` / reverse-DNS) + app name reservation in App Store
  Connect.
- **Age-gate approach** — simple first-launch "Are you 21+?" modal (self-attestation, the
  norm for alcohol-info apps) vs a harder gate. *Decision needed.*

### Phase 1 — Capacitor wrap running against prod
- `npm i @capacitor/core @capacitor/cli @capacitor/ios`; `npx cap init` (appId, appName);
  set `webDir: 'dist'`; `npx cap add ios`; `npm run build && npx cap sync`.
- Open in Xcode, run in the simulator, confirm it loads and hits the live Railway API.
- Fix native-origin breakage: CORS + Supabase redirect allowlist (Phase-1 slice).
- **Outcome:** the real app, running natively in the simulator. Low-risk, high-confidence.

### Phase 2 — Auth deep-linking
- Add `@capacitor/app` deep-link handling; register Universal Links (Associated Domains)
  or a custom scheme; point `emailRedirectTo` at the app link; add it to Supabase.
- **Outcome:** magic-link sign-in reopens the app, session restored. (Trickiest technical
  piece — good candidate for the Xcode AI assist.)

### Phase 3 — Native feature(s) to clear Guideline 4.2
Pick at least one, ideally used in the *core* flow:
- **Bottle-photo identification (roadmap item 26)** — `@capacitor/camera` → capture a label
  → Claude vision → match to `wines`. This is a genuinely native, on-brand feature and the
  strongest 4.2 answer.
- **Price-drop push notifications (roadmap item 16 notifier)** — `@capacitor/push-notifications`
  + APNs; ties into the existing `price_watches` table. Push is the feature Apple most
  expects to see.
- **Offline/app-like polish** — register a real service worker (there is none today) so the
  shell caches and behaves app-like, not like a live website.
- **Outcome:** Somm reads as a real app, not a wrapped site.

### Phase 4 — Store assets & compliance
- **Icon** 1024×1024 (have 512 — needs upscale/redraw), launch screen, screenshots for
  required device sizes.
- **Privacy Policy URL** (required) + **App Privacy "nutrition label"** — disclose: email
  (auth), coarse location/zip, analytics (PostHog), any device identifiers. If we keep
  zip *typed* (not GPS), no CoreLocation permission is needed — simpler review. Adding
  "use my location" later means a CoreLocation purpose string.
- **Age rating questionnaire** → 18+ (alcohol references), plus the in-app age gate.
- Support URL, marketing copy.

### Phase 5 — TestFlight → review → submit
- Archive in Xcode → App Store Connect → **TestFlight** (move the existing private-beta
  testers here) → submit for review.
- **Anticipate review questions:** a 4.2 challenge (answer: the native features from Phase
  3) and possibly an alcohol/age question (answer: 18+ rating + age gate, recommendation
  not sale).

## Where the "Claude in Xcode" assist fits

Capacitor auto-generates most of the iOS project; the hand-written native bits are small
and well-scoped — ideal for an in-Xcode AI assistant:
- Associated Domains / URL-scheme entitlements + the Swift deep-link handler (Phase 2).
- Push-notification capability + APNs registration glue (Phase 3).
- Camera permission purpose strings + any custom plugin wiring (Phase 3).
- Signing/entitlements/`Info.plist` edits.

The web-side work (Capacitor config, deep-link JS, camera/push JS, service worker, age gate)
is normal React work done here in the repo.

## Decisions locked (2026-07-25)
1. **Developer account: Individual** ($99/yr, personal name as seller).
2. **Lead 4.2 native feature: Camera bottle-ID (roadmap item 26)** — snap a label → Claude
   vision → match to inventory. Item 26 will need its own brainstorm/design when built.
3. **Scope now: map only** — no code yet; revisit to start Phase 1 (Capacitor wrap) when ready.

## Still-open decisions (for when we start)
- Age gate: simple 18+/21+ self-attestation modal — confirm wording/threshold.
- Keep location as typed-zip (simpler review) vs add GPS "near me".

## Sources
- [App Store Review Guidelines: Will Your Webview App Be Rejected? — MobiLoud](https://www.mobiloud.com/blog/app-store-review-guidelines-webview-wrapper)
- [Fix Apple Guideline 4.2 Rejection: Minimum Functionality — ShopApper](https://shopapper.com/fix-apple-guideline-4-2-rejection-minimum-functionality-explained/)
- [Apple Overhauls App Store Age Ratings — MacRumors](https://www.macrumors.com/2025/07/25/apple-overhauls-app-store-age-ratings/)
- [Age ratings values and definitions — Apple Developer](https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions/)
- [Building Cross-Platform Mobile Apps with React Vite and CapacitorJS — Medium](https://medium.com/@dev.sreerages/building-cross-platform-mobile-apps-with-react-vite-and-capacitorjs-dbaa1f9f061c)
