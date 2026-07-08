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
