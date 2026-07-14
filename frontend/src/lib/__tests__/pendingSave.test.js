import { describe, test, expect, beforeEach, vi } from 'vitest';
import { setPendingSave, getPendingSave, clearPendingSave } from '../pendingSave.js';

beforeEach(() => {
  const store = {};
  vi.stubGlobal('localStorage', {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  });
});

describe('pendingSave (carry a save intent through the magic-link round-trip)', () => {
  test('round-trips a pending wine', () => {
    setPendingSave({ wine_id: 'w1', name: 'Esprit de Tablas' });
    expect(getPendingSave()).toEqual({ wine_id: 'w1', name: 'Esprit de Tablas' });
  });

  test('returns null when nothing pending', () => {
    expect(getPendingSave()).toBeNull();
  });

  test('clear removes the pending wine', () => {
    setPendingSave({ wine_id: 'w1' });
    clearPendingSave();
    expect(getPendingSave()).toBeNull();
  });

  test('malformed storage is treated as nothing pending (never throws)', () => {
    localStorage.setItem('somm_pending_save', '{not json');
    expect(() => getPendingSave()).not.toThrow();
    expect(getPendingSave()).toBeNull();
  });
});

describe('pending watch intent', () => {
  it('round-trips a watch through storage and clears', async () => {
    const { setPendingWatch, getPendingWatch, clearPendingWatch } = await import('../pendingSave.js');
    setPendingWatch({ wine_id: 'w9', name: 'Esprit' });
    expect(getPendingWatch()).toEqual({ wine_id: 'w9', name: 'Esprit' });
    clearPendingWatch();
    expect(getPendingWatch()).toBeNull();
  });
});
