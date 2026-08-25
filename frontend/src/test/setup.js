// frontend/src/test/setup.js
import '@testing-library/jest-dom';
import { beforeEach, vi } from 'vitest';

// Node 22+ ships a native `localStorage` that is DISABLED unless started with
// `--localstorage-file`, so under the jsdom test environment `globalThis.localStorage`
// is `undefined` and any test that touches it directly throws
// ("Cannot read properties of undefined"). jsdom used to provide one; it no longer
// does on current Node. Give every test a fresh in-memory Storage so the suite is
// Node-version-independent. Per-file `vi.stubGlobal('localStorage', …)` still overrides
// this for tests that need bespoke behavior; `vi.unstubAllGlobals()` in a file's
// afterEach is fine — this beforeEach reinstalls it before the next test.
beforeEach(() => {
  const store = new Map();
  vi.stubGlobal('localStorage', {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: k => { store.delete(k); },
    clear: () => { store.clear(); },
    key: i => [...store.keys()][i] ?? null,
    get length() { return store.size; },
  });
});
