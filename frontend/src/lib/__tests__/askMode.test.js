// frontend/src/lib/__tests__/askMode.test.js
import { buildAskReq, ASK_INTENT_PILLS } from '../askMode.js';

// jsdom's opaque origin makes localStorage null — in-memory stub (repo pattern).
beforeEach(() => {
  const store = {};
  vi.stubGlobal('localStorage', {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('buildAskReq', () => {
  it('sends the wide-budget sentinel and the message', () => {
    const req = buildAskReq({ zip: '78209', message: 'caymus or bonanza?' });
    expect(req).toMatchObject({
      zip_code: '78209', budget_min: 0, budget_max: 10000,
      message: 'caymus or bonanza?', conversational: false,
    });
    expect(req.store_ref).toBeUndefined();
  });
  it('carries store_ref, history and conversational when given', () => {
    const req = buildAskReq({
      zip: '78209', message: 'and under $30?', storeRef: 's1',
      history: [{ role: 'user', content: 'hi' }], conversational: true,
    });
    expect(req.store_ref).toBe('s1');
    expect(req.conversation_history).toHaveLength(1);
    expect(req.conversational).toBe(true);
  });

  it('omitting budget params still yields the wide sentinel', () => {
    const req = buildAskReq({ zip: '78209', message: 'caymus or bonanza?' });
    expect(req).toMatchObject({ budget_min: 0, budget_max: 10000 });
  });

  it('passing a spoken budget overrides the sentinel', () => {
    const req = buildAskReq({
      zip: '78209', message: 'and under $60?', budgetMin: 0, budgetMax: 60,
    });
    expect(req).toMatchObject({ budget_min: 0, budget_max: 60 });
  });
});

describe('ASK_INTENT_PILLS', () => {
  it('has the four handoff intents', () => {
    expect(ASK_INTENT_PILLS.map(p => p.label)).toEqual(
      ['Compare two', 'Is this good?', 'What is this?', 'Pair with dinner']);
    ASK_INTENT_PILLS.forEach(p => expect(p.fill.length).toBeGreaterThan(0));
  });
});
