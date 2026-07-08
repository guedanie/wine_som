import { describe, test, expect, beforeEach, vi } from 'vitest';

// Mock the SDK so tests never touch the real browser client.
// vi.hoisted lets the hoisted vi.mock factory reference these safely.
const { capture, init } = vi.hoisted(() => ({ capture: vi.fn(), init: vi.fn() }));
vi.mock('posthog-js', () => ({ default: { init, capture } }));

import { initAnalytics, track, __resetAnalyticsForTest } from '../analytics.js';

beforeEach(() => {
  capture.mockClear();
  init.mockClear();
  __resetAnalyticsForTest();
  vi.unstubAllEnvs();
});

describe('analytics wrapper', () => {
  test('track is a no-op before init (no key) and never throws', () => {
    expect(() => track('anything', { a: 1 })).not.toThrow();
    expect(capture).not.toHaveBeenCalled();
  });

  test('initAnalytics with no key returns false and stays disabled', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', '');
    expect(initAnalytics()).toBe(false);
    track('x');
    expect(capture).not.toHaveBeenCalled();
  });

  test('initAnalytics with a key initializes the SDK and enables tracking', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    expect(initAnalytics()).toBe(true);
    expect(init).toHaveBeenCalledWith('phc_test', expect.any(Object));
    track('recommendation_shown', { picks: 3 });
    expect(capture).toHaveBeenCalledWith('recommendation_shown', { picks: 3 });
  });

  test('init is idempotent (second call does not re-init)', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    initAnalytics();
    initAnalytics();
    expect(init).toHaveBeenCalledTimes(1);
  });

  test('track swallows SDK errors so it never breaks the UI', () => {
    vi.stubEnv('VITE_POSTHOG_KEY', 'phc_test');
    initAnalytics();
    capture.mockImplementationOnce(() => { throw new Error('network'); });
    expect(() => track('pick_opened', { wine_id: 'w1' })).not.toThrow();
  });
});
