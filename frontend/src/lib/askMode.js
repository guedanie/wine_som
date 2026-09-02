// frontend/src/lib/askMode.js
// Aisle-mode ("Ask") request shape. Budget is a hard SQL filter that can't be
// omitted, so an unstated budget defaults to the wide-range sentinel the
// backend's recommendation/budget.py treats as "no budget stated" — but once
// the user speaks a number, the backend echoes it back via the `budget` SSE
// frame (see ChatRecommend's `applyBudgetFrame`), and callers pass THAT
// through here as budgetMin/budgetMax so the sentinel stops lying on the
// next turn.
export function buildAskReq({ zip, message, history, storeRef, conversational = false,
                              taste = null, budgetMin = 0, budgetMax = 10000 }) {
  const req = {
    zip_code: zip, budget_min: budgetMin, budget_max: budgetMax,
    style_preferences: [], avoid: [],
    message, conversational, taste,
  };
  if (history?.length) req.conversation_history = history;
  if (storeRef) req.store_ref = storeRef;
  return req;
}

export const ASK_INTENT_PILLS = [
  { label: 'Compare two',      fill: 'Which is better: ' },
  { label: 'Is this good?',    fill: 'Is this any good: ' },
  { label: 'What is this?',    fill: 'What can you tell me about ' },
  { label: 'Pair with dinner', fill: "We're eating " },
];
