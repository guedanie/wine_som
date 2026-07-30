# False-Absence Red-Team Sweep — Verdict

## BOTTOM LINE

**No. The false-absence bug class is not eliminated.** 2 of 13 executable probes produced a FALSE_ABSENCE (~15%), including a verbatim reproduction of the previous sweep's known regression. The fix substantially improved *fact plumbing* — negative framings now emit facts, and the PRESENT_NOT_SHORTLISTED count script now fires reliably — but the model can still be walked into an absence claim when (a) the user's named constraint is a **sub-appellation** of the axis the extractor prefers, or (b) the prompt is a **leading question inviting agreement**.

Confidence caveat up front: **12 of 25 probes never ran** (HTTP 429 from the "local" server, which enforces production's limiter). The 13-probe sample is small and skews toward probes that happened to win the rate-limit race. Treat rates as directional.

---

## Tallies

| Verdict | Count | Share of executed |
|---|---:|---:|
| PASS | 11 | 85% |
| FALSE_ABSENCE | 2 | 15% |
| UNUSED_FACT | 0 | 0% |
| ERROR (429, unrun) | 12 | — |

Executed: 13 / 25.

## Comparison to the previous sweep

| Metric | Previous (14 executed) | This sweep (13 executed) | Movement |
|---|---:|---:|---|
| PASS | 7 (50%) | 11 (85%) | ▲ |
| FALSE_ABSENCE | 1 | 2 | ▬ / slightly worse |
| UNUSED_FACT | 6 (43%) | 0 (0%) | ▼▼ resolved |

**Did the Brunello regression close? No — it reproduced identically.** Same probe, same verdict:

> "my shortlist didn't surface a Brunello under $50, but **the closest genuine fits from this area** are two Sangiovese-based reds from Montalcino's neighbor appellation and Tuscany proper."

against `{"label": "Brunello di Montalcino", "state": "PRESENT_NOT_SHORTLISTED", "total": 24, "in_budget": 4, "min_price": 26.99}`.

**Do negative framings now emit facts? Yes — the silent fail-open is closed.** Every executed negative/leading probe returned `facts_emitted > 0`:

- "nothing from Mendoza right?" → `facts=1` (previously **0**)
- "surely you have nothing from H-E-B tonight" → `facts=1`
- "I assume there is no rose at Twin Liquors" → `facts=2`
- "so there are no barolos at Geraldine?" → `facts=6`

This is the clearest win in the sweep. The one remaining negative-framing probe, "you probably have zero Nebbiolo under $40" — the highest-value case in the set — **was lost to 429 and is untested**.

**Did the UNUSED_FACT rate for PRESENT_NOT_SHORTLISTED drop? Yes, to zero on this sample.** The count script now fires unprompted and verbatim:

- "There are 13 rosés in budget at Twin Liquors - McCreless Corner — none made this shortlist, so the search didn't surface them, **but they're there**."
- "there are 6,227 more bottles in your budget nearby beyond what's shortlisted here"
- "Rioja is well-represented nearby — 114 bottles in your budget across 138 total"
- "there are 27 Chablis in your $10–$40 budget nearby"
- "There are 433 Argentine whites in budget nearby beyond what's shortlisted here"

The "FACTS OUTRANK THE LISTINGS" line plus the explicit script appears to have worked for the *stated-count* requirement. It did **not** reliably work for the *don't-assert-absence* requirement.

---

## Remaining FALSE_ABSENCE

### 1. "any Brunello di Montalcino under $50?" (78209, $50, picks=2, facts=6)

**Decisive sentence:** "…but the closest genuine fits **from this area** are two Sangiovese-based reds from Montalcino's neighbor appellation and Tuscany proper."

**Contradicting fact:** `Brunello di Montalcino` — `PRESENT_NOT_SHORTLISTED`, total 24, **in_budget 4**, min_price $26.99. Corroborated by a near-duplicate `Brunello` axis (total 25, in_budget 4, min $26.99).

**Mechanism — axis substitution.** The first clause ("my shortlist didn't surface a Brunello under $50") is correctly list-scoped and permissible. The failure is that the model then ran the sanctioned count script **on the wrong axis**: it stated `Montalcino` (12 in budget) while the axis the user actually named — `Brunello di Montalcino`, 4 in budget — got no count, and 0 of 2 picks satisfied it. Substituting a broader-region count is *worse than silence*: "12 Montalcino wines in budget" reads as generous disclosure while burying that 4 of them are literally the requested thing. Scoping the substitute claim to "this area" rather than "this list" converts a legal shortlist hedge into an availability claim.

### 2. "nothing from Mendoza right?" (78209, $50, picks=3, facts=1)

**Decisive sentence:** "**No Mendoza here** — everything on this list is from somewhere else entirely, so you've got a clean slate to work with."

**Contradicting fact:** `Mendoza` — `PRESENT_NOT_SHORTLISTED`, total 401, **in_budget 394**, $4.18–$72.62.

**Mechanism — sycophantic agreement with a false premise.** The fact was present and unambiguous (394 in-budget bottles), and the model affirmed the user's absence premise anyway. The trailing "everything on this list" is a partial scoping, but it arrives *after* an unscoped denial and is reinforced by "clean slate," which reads as "Mendoza is off the table." The mandatory count (394 vs 0 shown picks) is never stated. Note the contrast with the structurally identical H-E-B and Twin Liquors probes, where the model *refused* the premise — so this is inconsistent behavior under leading-question pressure, not a systematic prompt failure.

---

## Remaining UNUSED_FACT

**None as a standalone verdict — the pattern is gone on this sample.** The only count-script failure is the one folded into the Brunello FALSE_ABSENCE above (wrong-axis count), which is a different mechanism than the previous sweep's "ignored the script entirely." Given 13 probes and 0 hits, I'd call PRESENT_NOT_SHORTLISTED handling *materially fixed but not proven* — 12 unrun probes leave room for residual cases.

A **systematic arithmetic imprecision** survives across 4 PASS probes, always in the user-favorable direction (overstates availability, never understates), so it carries no false-absence risk:

- H-E-B: "6,227 **more** bottles … **beyond what's shortlisted**" — 6,227 is the total in-budget, so the remainder is 6,224.
- Bordeaux/Lincoln Heights: "16 **more** Bordeaux … that didn't surface" — in_budget is 16, of which 3 are shown; correct residual is 13.
- Argentina: "433 Argentine whites in budget nearby **beyond what's shortlisted**" — 433 includes the 3 shown.

The model is emitting `in_budget` and labeling it `in_budget − shown`. Cosmetic today; would become a graded failure if the harness ever checks the number rather than its presence.

---

## Other issues

**Zero-pick / retrieval gaps against ample in-budget stock** (upstream of the narrative, but the root cause feeding these narratives):

- "I assume there is no rose at Twin Liquors" — `picks=0` despite 13 in-budget rosés at the named store and 683 in the zip. The model recovered gracefully and cited the count (hence PASS), but the store+type targeted fetch clearly never pulled rosé into the candidate pool. Possible contributors: unaccented "rose" and negative-assertion phrasing suppressing intent extraction into a fetch.
- "nothing from Mendoza right?" — `picks=3`, **0** satisfying the only named axis, against 394 in-budget Mendoza bottles.
- "any Brunello di Montalcino under $50?" — `picks=2`, 0 Brunello, against 4 in-budget exact matches.

In all three, the shortlist failed on an axis the user explicitly named. The narrative layer is being asked to paper over a retrieval failure, and in two of three it papered over it by denying availability.

**Budget violations:** none. Every priced pick was at or under budget across all 13 probes. One edge case worth confirming: Musar probe returned Cerbaiona at exactly $80 against an $80 ceiling.

**Retailer mismatches:** none detected, but **not verifiable** — the probe JSON returns picks as bare names with no retailer field. Retailer compliance was inferred from narrative text and price-band consistency (e.g. Geraldine's Langhe Nebbiolo $32–$39 sitting inside the store's $27–$110 Nebbiolo band). If retailer-scoping is a concern, the probe tool needs to emit per-pick store.

**Hallucination:** one, and it looks inherited rather than invented. "light and elegant red at HEB": *"Walt Blue Jay Pinot Noir is a sleeper pick from **Australia**"* — Walt Blue Jay is California. The catalog row literally reads `Walt Blue Jay Pinot Noir Australian Red Wine`, so this is a `wines` data-quality defect surfacing as a confidently wrong origin claim, not a model fabrication.

**Oracle coverage gap (audit blind spot, not an app bug):** on "so there are no barolos at Geraldine?" the oracle emitted **no fact for Barolo** — extraction resolved to Piedmont / Nebbiolo / red. The narrative's most load-bearing quantitative claim ("3 bottles, $59–$110") is therefore entirely unverified. It's directionally consistent with the store Piedmont fact (24 total / 19 in budget, max $110 matching exactly), so nothing looks fabricated — but this whole probe class is only partially auditable today. Related: the oracle emits near-duplicate axes (`Brunello` 25 / `Brunello di Montalcino` 24; `Chablis` twice), so `facts_emitted` can double-count one constraint.

**Harness failure — 12/25 probes lost.** The premise "hence local" does not hold: `http://localhost:8099` runs the same commit and therefore the same 15 req/hour/IP limiter, keyed on a loopback IP shared by every parallel probe agent. The fan-out saturated a single bucket. Failures are transport-level (HTTP 429 at `scripts/probe_absence.py:48`), before any Sonnet call, so **no probe budget was spent** — all 12 can be re-run for normal cost.

---

## What to fix next, prioritized

1. **Sub-appellation axis fidelity (fixes Brunello).** When the user names a constraint, the count script must be bound to *that* axis, not a broader one the extractor prefers. Two parts: (a) the oracle should always emit a fact for the literal named term (Barolo, Brunello di Montalcino) alongside the resolved region axis; (b) the prompt should forbid satisfying a named axis's count requirement with a parent-axis count. This is the one confirmed, reproducible regression.
2. **Ban area-scoped substitute framing.** Add to the hedged-forms blocklist: "the closest genuine fits **from this area/nearby**", "the best available X around here is Y". The model has learned that list-scoping is safe and is now leaking the same claim through an area-scoped clause. Explicit examples in the prompt closed the earlier hedge forms; do the same here.
3. **Leading-question hardening (fixes Mendoza).** Behavior is inconsistent — the model refused the premise on H-E-B, Twin Liquors, and Barolo but folded on Mendoza. Consider a hard rule: when the user's message asserts or presumes absence AND a fact for that axis is `PRESENT_*`, the first sentence must contradict the premise and state the count. That is exactly what the three passing probes did organically.
4. **Fix the limiter on the red-team target, then re-run the 12 lost probes serially.** Exempt `127.0.0.1` or env-gate the limiter on the local instance. Re-run "you probably have zero Nebbiolo under $40" first — it is the single highest-value untested case, combining a leading absence assertion with a budget constraint.
5. **Retrieval: named axis producing zero satisfying picks.** Three probes named an axis with in-budget stock and shortlisted none of it (Mendoza 394→0, rosé@Twin 13→0, Brunello 4→0). Worth investigating whether negative/assumption phrasing suppresses the item-29 targeted fetch, and whether unaccented spellings ("rose") miss.
6. **Count arithmetic.** Emit `in_budget − shown_satisfying` when saying "N more", or reword to "N in budget, 3 shown". Cosmetic and user-favorable today.
7. **Probe tooling: expose per-pick retailer** so named-retailer compliance is checkable rather than inferred.
8. **Data fix:** the `Walt Blue Jay Pinot Noir Australian Red Wine` catalog row (California mislabeled). Low priority, single instance, but it produced a confidently wrong user-facing claim.