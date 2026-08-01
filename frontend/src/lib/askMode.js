// frontend/src/lib/askMode.js
// Aisle-mode ("Ask") request shape. Budget is a hard SQL filter that can't be
// omitted, so an unstated budget is the wide-range sentinel the backend's
// recommendation/budget.py treats as "no budget stated".
export function buildAskReq({ zip, message, history, storeRef, conversational = false, taste = null }) {
  const req = {
    zip_code: zip, budget_min: 0, budget_max: 10000,
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
