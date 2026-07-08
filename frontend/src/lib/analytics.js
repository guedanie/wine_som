// Thin analytics wrapper around PostHog. No-op unless VITE_POSTHOG_KEY is set,
// so dev/tests/no-key builds are silent and it "just works" once the key lands
// in the deploy env. Every call is wrapped so analytics can never break the UI.
import posthog from 'posthog-js';

let enabled = false;

export function initAnalytics() {
  if (enabled) return true;
  const key = import.meta.env?.VITE_POSTHOG_KEY;
  if (!key) return false;
  try {
    posthog.init(key, {
      api_host: import.meta.env?.VITE_POSTHOG_HOST ?? 'https://us.i.posthog.com',
      capture_pageview: false,   // SPA — we send pageviews on route change
      autocapture: true,
      persistence: 'localStorage',
    });
    enabled = true;
  } catch {
    enabled = false;
  }
  return enabled;
}

export function track(event, props = {}) {
  if (!enabled) return;
  try { posthog.capture(event, props); } catch { /* never break UX */ }
}

export function trackPageview(path) {
  track('$pageview', { $current_url: path });
}

// test-only: reset module state between cases
export function __resetAnalyticsForTest() {
  enabled = false;
}
