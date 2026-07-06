import { describe, test, expect, beforeEach, vi } from 'vitest';
import { naturalChatMode } from '../flags.js';

function setSearch(search) {
  Object.defineProperty(window, 'location', {
    value: { search }, writable: true, configurable: true,
  });
}

beforeEach(() => {
  // jsdom's opaque origin makes localStorage null — provide an in-memory one.
  const store = {};
  vi.stubGlobal('localStorage', {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
    clear: () => { for (const k in store) delete store[k]; },
  });
  setSearch('');
});

describe('naturalChatMode', () => {
  test('defaults to false with no param and empty storage', () => {
    expect(naturalChatMode()).toBe(false);
  });

  test('?natural=1 enables and persists it', () => {
    setSearch('?natural=1');
    expect(naturalChatMode()).toBe(true);
    // sticky: still true after the param is gone
    setSearch('');
    expect(naturalChatMode()).toBe(true);
  });

  test('?natural=0 clears the persisted flag', () => {
    localStorage.setItem('somm_natural', '1');
    setSearch('?natural=0');
    expect(naturalChatMode()).toBe(false);
    setSearch('');
    expect(naturalChatMode()).toBe(false);
  });
});
