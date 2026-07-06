// Client feature flags. Sticky via localStorage so a flag set once (via URL
// query param) applies across navigation — handy for A/B testing behaviors on
// the live app before flipping the default.

const NATURAL_OFF_KEY = 'somm_natural_off';

// Natural chat mode (DEFAULT ON): follow-up questions get conversational
// answers instead of always spawning a fresh set of wine cards. Opt out with
// ?natural=0 (persisted); ?natural=1 clears the opt-out.
export function naturalChatMode() {
  try {
    const p = new URLSearchParams(window.location.search).get('natural');
    if (p === '0') localStorage.setItem(NATURAL_OFF_KEY, '1');
    if (p === '1') localStorage.removeItem(NATURAL_OFF_KEY);
    return localStorage.getItem(NATURAL_OFF_KEY) !== '1';
  } catch {
    return true;   // default on even if localStorage is unavailable
  }
}
