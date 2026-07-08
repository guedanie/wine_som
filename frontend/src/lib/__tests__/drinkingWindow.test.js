import { describe, test, expect } from 'vitest';
import { drinkingWindow, windowStatus } from '../drinkingWindow.js';

describe('drinkingWindow (varietal + vintage → year range)', () => {
  test('age-worthy red gets a long window from its vintage', () => {
    const w = drinkingWindow('Cabernet Sauvignon', 'red', 2015);
    expect(w.from).toBe(2019);   // vintage + peak-start
    expect(w.to).toBe(2030);     // vintage + window-end
  });

  test('crisp white is a short, drink-young window', () => {
    const w = drinkingWindow('Sauvignon Blanc', 'white', 2024);
    expect(w.to - w.from).toBeLessThanOrEqual(2);
  });

  test('falls back to wine_type when varietal is unknown', () => {
    const w = drinkingWindow(null, 'red', 2022);
    expect(w).not.toBeNull();
    expect(w.to).toBeGreaterThan(w.from);
  });

  test('returns null without a vintage (non-vintage / unknown)', () => {
    expect(drinkingWindow('Cabernet Sauvignon', 'red', null)).toBeNull();
  });
});

describe('windowStatus (where are we in the window)', () => {
  test('before the window → hold', () => {
    const s = windowStatus({ from: 2028, to: 2038 }, 2026);
    expect(s.phase).toBe('hold');
    expect(s.label).toMatch(/Hold to 2028/);
  });

  test('deep in the window → ready / peak', () => {
    const s = windowStatus({ from: 2019, to: 2030 }, 2026);
    expect(s.phase).toBe('ready');
  });

  test('last year of the window → drink soon', () => {
    const s = windowStatus({ from: 2020, to: 2026 }, 2026);
    expect(s.phase).toBe('soon');
    expect(s.label).toMatch(/soon/i);
  });

  test('past the window → past its peak', () => {
    const s = windowStatus({ from: 2012, to: 2018 }, 2026);
    expect(s.phase).toBe('past');
  });

  test('fill is clamped 0–100', () => {
    expect(windowStatus({ from: 2020, to: 2030 }, 2010).fill).toBe(0);
    expect(windowStatus({ from: 2020, to: 2030 }, 2040).fill).toBe(100);
  });
});
