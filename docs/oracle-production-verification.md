# Availability Oracle — Production Verification Verdict

**Deployed commit under test:** `42312dfb452c` (confirmed live via `/health` → `{"status":"ok","service":"terroir-api","commit":"42312dfb452c"}`)

---

## BOTTOM LINE

**Not eliminated. One confirmed FALSE_ABSENCE regression in 14 completed probes (~7%).** The bug class is heavily suppressed — 13 of 14 completed probes contained no false absence claim, and several show the oracle's sanctioned scripts working almost verbatim — but it still fires, and it fired on a probe where the oracle *had* the correct fact in hand. The mechanism that survives is not "no fact computed"; it is **the model reading a `PRESENT_NOT_SHORTLISTED` fact and narrating it as an absence anyway.**

Confidence caveat, stated plainly: **9 of 23 probes never reached the model** (HTTP 429 rate limiting from parallel probe fan-out). The evidence base is 14 probes, not 23, and the un-run 9 include several high-risk absence-bait phrasings ("I assume there is no rose at Twin Liquors", "any dessert wine at H-E-B?"). The true rate is under-measured.

---

## Tallies

| Verdict | Count | Probes |
|---|---:|---|
| PASS | 7 | Barolo (open), light red @ HEB, Mendoza, Opus One, Rioja, Sancerre, Champagne @ Central Market |
| **FALSE_ABSENCE** | **1** | **"any Brunello di Montalcino under $50?"** |
| UNUSED_FACT | 6 | Barolo @ Geraldine's, H-E-B tonight, Bordeaux @ Lincoln Heights, Argentine whites, Chateau Musar, Chablis |
| ERROR (429, never reached model) | 9 | Pauillac, orange wine, rosé @ Twin Liquors, Portuguese, Nebbiolo @ Spec's, dessert @ H-E-B, Vinho Verde, Willamette, Grüner |
| **Completed** | **14** | |

---

## The regression: "any Brunello di Montalcino under $50?" (zip 78209, budget $50)

**Computed fact:** `Brunello di Montalcino` → `PRESENT_NOT_SHORTLISTED`, **total 24, in_budget 4**. Corroborating axis `Brunello` → `PRESENT_NOT_SHORTLISTED`, total 25, in_budget 4.

**Narrative:**

> "There are Brunello di Montalcino options nearby within budget — **the listings here run well above $50**, but the closest match in spirit at your price point is a Rosso di Montalcino…"

> "At $80 it's still over your cap, but it's **the most budget-conscious Montalcino wine in the current listings**."

**Why this is a regression, not honest scoping:** the second claim is scoped to *"the current listings"*, not to the two shown picks. That is a catalog-level assertion, and it is false — `in_budget = 4`. The user's literal question ("any Brunello under $50?") is answered *no* in effect, when the oracle independently computed *yes, four*.

It also self-contradicts inside a single sentence: it asserts within-budget options exist, then immediately says the listings run well above $50.

**Likely mechanism — the oracle did its job; the consumer didn't.** Ruling out the alternatives:

- *Axis extraction missed the constraint?* No. Two facts were emitted for the axis, correctly labeled, with correct counts.
- *Oracle failed to emit?* No. This is the cleanest fact emission in the whole sweep.
- *Model ignored the licence rule?* **Yes, this is it.** The prompt forbids absence except under `NOT_IN_CATALOG`. The state was `PRESENT_NOT_SHORTLISTED`. The model produced absence-equivalent prose anyway.

The proximate trigger looks like a **shortlist/fact conflict the prompt gives no rule for**: the shortlist contained *zero* Brunello (picks were a Rosso di Montalcino at $80 and a Toscana IGT at $35), while the fact said four are in budget. Facing "my candidates say no, the oracle says yes," the model narrated its candidates and demoted the fact to a throwaway opening clause. The prompt tells the model *not to claim absence*; it does not tell it **the fact outranks the shortlist when they disagree.**

Two aggravating defects on the same probe: (1) **zero of two picks satisfy the named constraint** despite four qualifying bottles existing — the shortlist builder, not just the narrator, failed; (2) an **$80 pick was returned under a $50 budget cap**.

---

## UNUSED_FACT: the pattern

Six of fourteen completed probes (43%) computed a usable fact and discarded its script. The pattern is sharp and consistent.

**1. The state that gets ignored is almost always `PRESENT_NOT_SHORTLISTED`. `PRESENT_OUT_OF_BUDGET` is handled well.**

Out-of-budget is close to solved. Opus One (PASS): *"Opus One does exist nearby — 3 bottles across local shops — but they're running $450–$455, well outside your $10–$50 range."* Count + range + budget framing, textbook. Chateau Musar: *"There is one Chateau Musar nearby, but it's sitting at $146 — outside your $80 ceiling."* Same. Barolo @ Geraldine's: *"Geraldine's does carry Barolo — 3 bottles nearby — but all three fall between $59–$110."* Same, and it actively rebuts the user's false premise.

Every single UNUSED_FACT is a dropped `PRESENT_NOT_SHORTLISTED`. Chablis: fact 53 total / **27 in budget**, narrative says only *"Three solid Chablis options nearby"* — implicitly capping the world at the shortlist. Bordeaux @ Lincoln Heights: fact **144 in budget**, one pick returned, no count. Argentine whites: fact **433 in budget**, narrative says *"Two Argentine whites surfaced from the list"* — reads as scarcity atop hundreds of bottles.

**2. It correlates with the axis being *satisfied-looking*.** When the shortlist already shows the named thing, the model treats the job as done and drops the count. That is defensible on Rioja/Sancerre (scored PASS — the list *is* the answer, no information is lost) but not on Chablis or Bordeaux, where the shown 1–3 bottles badly understate 27–144 in-budget options and the user asked a literal availability question.

**3. It correlates with fact count / axis specificity.** The model consumes **only the single most specific named entity** and discards broader axes. Chateau Musar is the strongest case: it correctly handled the producer axis, then ignored `Lebanon` = **15 total / 15 in budget** and closed with *"Worth checking back, or adjusting the budget if Musar is the goal"* — offering only waiting or spending more, while an entirely in-budget Lebanese shelf sat unnamed. **`pick_count` was 0.** Same shape on the Barolo-@-Geraldine's probe: store-scoped Barolo handled perfectly, unscoped `Barolo` (56 total / **15 in budget**) never mentioned, so the user walks away believing $50 Barolo is unreachable.

### Proposed fixes (concrete)

**Prompt — add a precedence rule (highest value, fixes the FALSE_ABSENCE too):**
> "Availability facts outrank the shortlist. If a fact says `PRESENT_*` and no shown pick satisfies that constraint, you MUST NOT describe it as unavailable, out of reach, or absent from the listings — including hedged forms ('the listings run well above', 'the most budget-conscious X in the current listings'). State the count instead."

**Prompt — make the `PRESENT_NOT_SHORTLISTED` script mandatory and bounded:**
> "For every `PRESENT_NOT_SHORTLISTED` axis the user named by name, state the in-budget count in one clause before pivoting: 'there are 27 more Chablis in budget nearby I didn't shortlist.' Required when `in_budget` exceeds the number of shown picks satisfying that axis. Not required for axes the user did not name."

The `in_budget > shown_matches` trigger is what separates the real misses (Chablis 27 vs 3, Bordeaux 144 vs 1) from the PASS cases (Rioja, Sancerre — where reciting a count would be noise).

**Prompt — forbid the scope blur.** Barolo @ Geraldine's said *"3 bottles nearby"* for a store-scoped count, then *"so nothing clears your $50 ceiling."* Grammatically bound to "all three," so not scored FALSE_ABSENCE — but it is one comma away from being one. Rule: store-scoped counts must be labeled with the store, never "nearby."

**Code — never zero-pick a `PRESENT_*` turn.** Chateau Musar returned `picks: []` against 15 in-budget Lebanese wines. If any named axis is `PRESENT_*` with `in_budget > 0`, the shortlist should be re-queried on the broadest satisfied axis before returning empty.

---

## Other emergent issues worth logging

**A. `min_price` / `max_price` are null on essentially every `PRESENT_NOT_SHORTLISTED` fact.** Observed on Bordeaux, Rioja, Sancerre, Chablis, Argentina/white, H-E-B, Brunello. The out-of-budget script needs a price range; it only had one on the axes that actually landed `PRESENT_OUT_OF_BUDGET` (Opus One, Musar, Barolo@Geraldine's). If an axis ever transitions state with prices unpopulated, half the sanctioned script is unrenderable. **Fix: populate price bounds on all `PRESENT_*` states.**

**B. `PRESENT_SHORTLISTED` appears to be systematically mislabeled as `PRESENT_NOT_SHORTLISTED`.** Rioja: all four picks are Rioja, fact says NOT_SHORTLISTED. Sancerre: both picks are Sancerre, same. Argentine whites: both picks are Argentine whites, same. Chablis, Bordeaux @ Lincoln Heights: same. The membership check is not reconciling facts against final picks. Benign in the false-absence direction, but it (i) generates false UNUSED_FACT positives in grading, (ii) could push the model into needless recitals, and (iii) **if the same predicate ever drives a `NOT_IN_CATALOG` determination, a mismatched matcher would license a wrong absence claim** — the exact original bug, re-entering through the fix.

**C. Axis extraction has real gaps.** Two probes named a constraint and got **no fact at all** — not even `UNMEASURED`:
- *"nothing from Mendoza right?"* → `facts: []`. The oracle never ran for the one axis in the prompt. Scored PASS on the letter of the rules (no `PRESENT_*` fact to contradict), but this is a **fail-open**, and the narrative's *"Zero Mendoza here"* is close to the line. Zero Mendoza in a TX catalog with H-E-B/Central Market/Spec's is prior-improbable and worth a direct DB count.
- *"do you have Champagne at Central Market?"* → no Central Market axis; Champagne emitted twice as a duplicate row. The model then filled the void with *"Central Market very likely has options not shown in this snapshot"* — **LLM-inferred availability, exactly what the oracle exists to replace.** Polarity happened to be positive; flipped, it would be an uncatchable false absence.

Duplicate rows also appeared on the H-E-B probe (`"H-E-B"` and `"H-E-B at H-E-B"`), and H-E-B's total of **8** at 78209 is implausibly low for the largest SA retailer — suggesting the retailer axis is text-matched rather than resolved as an entity.

**D. Retailer constraints are honored by the narrative but not the picks.** Bordeaux @ Lincoln Heights silently substituted *"Twin Liquors at McCreless Corner"* while echoing the user's store — no "nothing at Lincoln Heights, but nearby…" framing. The H-E-B probe headlined *"H-E-B is actually stacked tonight"* over three picks that, per the fact state, are **not** the counted H-E-B rows — hallucinated availability at a named retailer, the mirror image of the fixed bug.

**E. Harness fragility.** (i) One probe's oracle collapsed to zero facts on a single transient `httpx.ReadError` — `fetch_axis_counts` has no per-axis isolation, so any DB blip degrades *every* constraint to `UNMEASURED`. Fails safe under the current prompt, but silently. (ii) `scripts/probe_absence.py:39` propagates HTTP 429 as an unhandled traceback with no backoff, which cost this sweep 9 of 23 probes.

**F. One non-absence hallucination.** Light-red-@-HEB probe: *"**Walt Blue Jay Pinot Noir** is the dark-horse pick: Australian cool-climate Pinot."* Walt Blue Jay is California. The model took the catalog string "…Australian Red Wine" at face value — a scraper-name defect propagating into confident geographic prose.

---

## Prioritized next steps

1. **Fix the FALSE_ABSENCE mechanism** — add the "facts outrank the shortlist" precedence rule to the prompt, explicitly covering hedged/indirect absence forms. This is the one regression and it is a prompt-level miss, not a data miss.
2. **Re-run the 9 rate-limited probes serialized with backoff**, and re-run "nothing from Mendoza right?" — the sweep is only 61% complete and the missing probes are disproportionately absence-bait phrasings.
3. **Fix axis extraction for un-emitted constraints** (Mendoza, Central Market). A named constraint that produces no fact row is a silent fail-open and is the precondition of the original six incidents. Every named axis must emit *something*, minimally `UNMEASURED`.
4. **Fix `PRESENT_SHORTLISTED` membership matching.** Currently benign, but the same predicate near `NOT_IN_CATALOG` is a direct re-entry path for the original bug.
5. **Make the `PRESENT_NOT_SHORTLISTED` script mandatory when `in_budget > shown_matches`**, and populate `min_price`/`max_price` on all `PRESENT_*` states.
6. **Never return zero picks when a named axis is `PRESENT_*` with `in_budget > 0`** (Chateau Musar).
7. Lower priority: retailer-entity resolution (H-E-B total of 8 is suspect), per-axis failure isolation in `fetch_axis_counts`, 429 handling in the probe script.