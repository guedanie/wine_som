// Budget carried across turns — the client half of the contract whose backend
// half lives in `recommendation/budget.py`.
//
// budget_min/budget_max are hard SQL filters on every inventory query and can't
// be omitted, so a conversation with no stated budget sends the wide sentinel
// below, which the backend reads as "no budget stated". Once the user says a
// number out loud the backend echoes it back on a `budget` SSE frame, and the
// client carries THAT from then on — which is what stops `budget_max` lying
// about what the user asked for.

// Matches WIDE_BUDGET_THRESHOLD's intent in recommendation/budget.py: anything
// at or above 1000 there reads as unstated, and this is the value we send.
export const WIDE_BUDGET_MIN = 0;
export const WIDE_BUDGET_MAX = 10000;

/**
 * Apply a `budget` SSE frame to a request object.
 *
 * Returns the SAME object when the frame is unusable, so a malformed frame can
 * never blank a budget the user actually set — callers rely on that identity.
 */
export function applyBudgetFrame(req, frame) {
  const max = frame?.max;
  if (typeof max !== 'number' || !(max > 0)) return req;
  // min is allowed to legitimately be 0 (a floor of "no minimum"), so it needs
  // its own finite-number check rather than reusing max's `> 0` guard — the
  // two look asymmetric but are each doing the right thing for their field.
  // req itself is legitimately undefined on ASK turn 1 (no nav apiReq yet).
  const min = Number.isFinite(frame.min) ? frame.min : (req?.budget_min ?? WIDE_BUDGET_MIN);
  return { ...req, budget_min: min, budget_max: max };
}
