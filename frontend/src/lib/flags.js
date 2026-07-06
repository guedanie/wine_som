// Client feature flags. Sticky via localStorage so a flag set once (via URL
// query param) applies across navigation — handy for A/B testing behaviors on
// the live app before flipping the default.

const NATURAL_KEY = 'somm_natural';

// Natural chat mode: follow-up questions get conversational answers instead of
// always spawning a fresh set of wine cards. Toggle with ?natural=1 / ?natural=0.
export function naturalChatMode() {
  try {
    const p = new URLSearchParams(window.location.search).get('natural');
    if (p === '1') localStorage.setItem(NATURAL_KEY, '1');
    if (p === '0') localStorage.removeItem(NATURAL_KEY);
    return localStorage.getItem(NATURAL_KEY) === '1';
  } catch {
    return false;   // localStorage unavailable (private mode / opaque origin)
  }
}
