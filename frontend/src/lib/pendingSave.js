// Holds a "save this wine" intent from an anonymous user across the magic-link
// round-trip (they tap Save → sign in → return authenticated → we auto-save).
const KEY = 'somm_pending_save';

export function setPendingSave(wine) {
  try { localStorage.setItem(KEY, JSON.stringify(wine)); } catch { /* private mode */ }
}

export function getPendingSave() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; }
}

export function clearPendingSave() {
  try { localStorage.removeItem(KEY); } catch { /* private mode */ }
}

// Same round-trip mechanism for a "watch this price" intent (price
// intelligence Phase D): tap Watch → sign in → return → the watch is applied.
const WATCH_KEY = 'somm_pending_watch';

export function setPendingWatch(wine) {
  try { localStorage.setItem(WATCH_KEY, JSON.stringify(wine)); } catch { /* private mode */ }
}

export function getPendingWatch() {
  try { return JSON.parse(localStorage.getItem(WATCH_KEY) || 'null'); } catch { return null; }
}

export function clearPendingWatch() {
  try { localStorage.removeItem(WATCH_KEY); } catch { /* private mode */ }
}
