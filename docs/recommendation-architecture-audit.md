# Somm: Eliminating the False-Absence Bug Class

*Architecture proposal — audit synthesis, 2026-07-29. Grounded in five verified audit dimensions (retrieval-loss, grounding-absence, intent-coverage, scorer-selection, regression-harness). Every claim below traces to a finding that survived adversarial verification; where verifiers overturned or disputed a finding, that is stated inline.*

---

## 1. Root diagnosis

**Somm has no availability oracle. Absence is never computed — it is inferred by an LLM from a 12-row shortlist.**

The single core architectural mistake is that **one artifact, the candidate shortlist, is overloaded to answer two incompatible questions**:

1. *What should I recommend?* — a ranking problem, correctly solved by a bounded, personalized, diversity-capped top-12.
2. *What exists near this user?* — a closed-world availability question, which a bounded ranked sample structurally **cannot** answer.

Because those two questions share one data structure, every mechanism that legitimately narrows the *recommendation* (an unordered `LIMIT 500` per retailer, `_MAX_CANDIDATES = 12`, `_VARIETAL_CAP = 4`, the enrichment gate, the personalization weights, the staleness cutoff, the budget clamp) silently also narrows the *evidence base for absence*. And `_SYSTEM_PROMPT` then hands the model a ready-made denial phrase — `"nothing matching that turned up nearby"` (`claude_client.py:131`) — with no rule that ever forbids denial and no computed fact to check it against.

Only **two** availability facts are ever computed and passed to the model: `named_bottle_found` (`recommend.py:495`) and `retailer_has_fit` (`recommend.py:450-451`). Both were added reactively, per incident. Region, appellation, grape, wine_type, store, price-band and every compound ask get **no computed fact at all**. Worse, the pipeline already computes the exact predicate it needs and throws it away: `deep_fetch_reason` (`candidate_filters.py:53-75`) returns `"weak"` precisely when no selected candidate satisfies the stated constraint, and that verdict is consumed only to trigger `_constraint_fetch` — never rendered into the prompt, and never re-evaluated after the deep fetch (verified: `reason == "weak"` both before and after, Rioja still 0/12).

Two corollaries of the same mistake:

- **The patch strategy cannot terminate.** Each of the six fixes added another bespoke query builder (`_targeted_rows`, `_retailer_rows`, `_named_fetch`, `_constraint_fetch`) with its own predicate, limit, budget policy and staleness policy — and each new builder reintroduced the original defect. `_named_fetch`, the fix for bug #5, is a flat OR over name tokens with `.limit(80)` and no `.order()`: measured at 78230, `"Chateau Musar"` matches 1,021 rows, and **0 of the 1 true all-token matches survived the arbitrary 80**. The intent axis space is open (appellation, vintage, producer, sweetness, oak, format, organic, ABV, compounds), so "one targeted fetch per axis" is unbounded by construction.
- **Nothing in the repo can express the violated property.** No CI runs any test (`.github/workflows/` = `daily-vivino.yml`, `weekly-scrape.yml`; `grep -rn "pytest\|vitest" .github/` → no matches). The endpoint harness `_make_db_mock` (`tests/test_recommend_api.py:70-86`) returns the same rows for every table and every filter chain, which makes the failure state of interest — *"the DB has matching rows and the pool has none"* — literally unrepresentable; a line-tracer confirms `_targeted_rows`, `_retailer_rows`, `_named_fetch`, `_constraint_fetch` and the whole retailer branch are **100% unexecuted** under test.

---

## 2. Retrieval vs. selection vs. grounding

The bug history conflates three distinct layers. Separating them is the precondition for fixing the class, because **a retrieval fix cannot fix a grounding bug and vice versa** — bug #6 proves it: retrieval was correct, the Barolo was on the user's screen, and the answer was still "no Barolos."

### Layer A — Retrieval (bugs #1–#5)
The matching row never reaches the pool.

| Defect | Evidence |
|---|---|
| Breadth fetch is an unordered `LIMIT 500`/retailer, no `.order()` (`recommend.py:33, 234`) | 78230: 15,615 fresh in-budget rows nearby, 2,000 fetched = **12.8%**; byte-identical row order across 4 consecutive runs → the blind spot is **deterministic, not flaky** |
| `sub_region` is never SELECTed, queried, or scored anywhere in the recommender (`INVENTORY_SELECT` `recommend.py:84-90`; `grep sub_region recommendation/ api/routers/recommend.py` → 0 hits) | 6,264 wines carry an appellation there. Region-only vs. full place union at 78209: Sancerre 0→39, Chablis 3→30, Brunello 0→9, Russian River 2→67. Catalog-wide: `sub_region ilike '%Pauillac%'` = 159 wines, **all** with `region = 'Bordeaux'`, backing 333 in-stock rows; `region ilike '%Pauillac%'` = 11 |
| Five near-duplicate query builders with drifted predicates | `_constraint_fetch` grape predicate is `grapes.cs.["{g.title()}"]` — exact containment on a free-text array. `["Nero d'Avola"]`→54 wines, `["Nero D'Avola"]`→**0**; `["Xarel·lo"]`→26 vs `["Xarel·Lo"]`→0. 23 of 465 nearby grape spellings differ from their `.title()`; the column also holds duplicate spellings (`Xarel·lo`/`Xarel-lo`), so even correct casing retrieves one variant |
| Every fetch filter is accent-sensitive `ilike`; all in-memory matching is accent-folded (`scorer.py:96`, `candidate_filters.py:196`) | `region ilike '%Rhône%'` = 344 vs `'%Rhone%'` = 27; live Haiku emits the *losing* spelling (`'Rhone Valley'` → 9 in-stock rows vs `'%Rhône%'` → 973) |
| Enum/column vocabulary drift | intent enum says `rose`; DB has **1,017 `'rosé'` and 0 `'rose'`**. Live Haiku returns `'rose'` even when the user types the accent. `apply_type_gate` keeps 50/1,955 candidates, **0 of them rosés** |
| Staleness fail-open is pool-level, not per-retailer (`recommend.py:250-256`) | `scraper_runs` 2026-07-26: H-E-B `failed / 502`, Central Market `failed`. H-E-B's 4,139 in-budget rows are benched at both 78209 and 78230; because 15,615 other rows survive, the retry never fires. **41% of in-budget nearby inventory silently dropped from breadth** |
| Deep fetch's trigger set ⊃ its capability set | `deep_fetch_reason` fires `"weak"` on unmet grape ∪ region ∪ **wine_type**; `_constraint_fetch` builds conds from grape ∪ region only → returns `[]`. Free-text type asks emit "Looking deeper into the cellar…" and re-fetch nothing. Compound instance: "any dessert wine at H-E-B?" → 0 in breadth, 0 in the type-blind `_retailer_rows` 300, gate fails open, deep fetch no-op, while those stores stock 10 in-budget dessert rows |
| One-way `max_price` (`intent.py:112-116`) + all fetches filtered on `req.budget_*`, not `resolved` | "up to 150" with no bottle name is silently discarded; `_named_fetch` is the only budget-blind path |
| `regions` overwrites and orphans the primary `region` (`intent.py:101-105`) | Live: "a nice Left Bank Bordeaux, maybe Pauillac or Margaux" → `region='Bordeaux'`, `regions=['Pauillac','Margaux']`; every place-aware consumer uses `regions or [region]`, so the fallback can never fire and the only string that reaches those 333 rows is discarded |

### Layer B — Selection (the missing middle, and the most under-appreciated finding)
The matching row **is** in the pool and ranking removes it. This is neither retrieval nor grounding and no shipped fix addresses it.

`score_candidates` is a single additive sum with no notion of constraint satisfaction. The taste-profile weights are correctly gated (`scorer.py:227,230,235`: `not want_regions` / `not want_body` / `not want_type` — "the request always wins"). `_W_SIMILAR = 2.5` and `_W_DISLIKE = 2.0` have **no such gate**, while an explicitly named region is worth `_W_REGION = 1.5` and a named grape `_W_GRAPE = 2.0`.

Measured on the live 78209 pool (n≈1,955, $10–50), matches in the final top-12:

```
ask=Rioja    (95 in pool):  anon 12/12 → +1 saved Napa Cab 0/12 → +profile 0/12
ask=Loire    (141):         12/12 → 0/12 → 0/12
ask=Piedmont (324):         12/12 → 0/12 → 0/12
ask=Riesling (71):          12/12 → 1/12  → 0/12
grapes=[Cabernet]+red:      12/12 → 2/12 after ONE thumbs-down on a California Cab
```

The best Rioja falls to overall rank 162. And the safety net fires and is powerless: `deep_fetch_reason` → `"weak"` → `_constraint_fetch` → re-score → **still 0/12**, because the rescue re-runs the same weights; in six measured regions the constraint fetch added **0 rows not already in the pool**. There is no must-include mechanism: `ensure_region_representation` no-ops below 2 regions (`candidate_filters.py:214-215`), and `pin_named_matches` is wired only to the named-bottle path. Root cause of it shipping: every personalization test in `tests/test_scorer.py:222-274` uses a neutral `_intent()` with no ask.

Also in this layer: `_VARIETAL_CAP = 4` makes the effective list **4, not 12**, for any single-grape availability question; and the flavor axis (`_FLAVOR_CAP = 3.0`, joint-largest weight) is inert on the primary chip UI — 13 of the 15 `STYLE_TAG_MAP` tags are not in `FLAVOR_VOCAB` (`'dark fruit'` vs `'dark-fruit'`, `'structure'` vs `'structured'`), so "Bold & Tannic" scores **0.000 on 0/11,253 candidates** while the prompt tells Claude the user asked for it. `tasting_notes` is NULL on **0/21,085** rows, so the `kw_hits` fallback is dead code.

### Layer C — Grounding (bug #6)
The matching row is in the pool, on screen, and the answer denies it.

- `claude_client.py:131` supplies the denial wording and prohibits only the *narrower* claim about "a store's full inventory". Four separate clauses push toward dropping picks (`:26`, `:79-81`, `:144-148`, `:381-384`); **zero** clauses forbid an absence assertion or mandate surfacing a constraint-satisfying listing on the region/grape/appellation/type axes.
- Fit-judgment and availability share one sentence. "I don't think this is a great fit" and "this doesn't exist near you" are the same output.
- `_reconcile_picks_to_narrative` (`recommend.py:110-127`) reconciles picks **to** the narrative, never the reverse, and never drops to empty (`kept or picks`) — so a denial narrative coexists with the emitted cards. That is bug #6's exact user-visible signature, present by design.
- The candidate→prompt projection is lossier than the pool: `grapes` (matched by both the scorer and `_constraint_fetch`) is never rendered; `sub_region` is never even selected; no cardinality is passed, so 12 rows out of 684 nearby Mendozas reads to the model as "this is what exists."
- The pipeline manufactures its own absence claim: the no-fit `retailer_directive` (`claude_client.py:365-369`) instructs "{retailer} doesn't stock a wine matching their profile. Say that plainly" — derived from a budget-clamped, enrichment-gated `limit(300)` fetch, not a count.
- Verification of every absence-related prompt fix is substring-only (`tests/test_claude_client.py:436-496`; `test_retailer_directive_no_fit_is_honest` asserts `"doesn't stock" in msg.lower()`). There is no model-in-the-loop eval for recommendation anywhere — the enrichment side has one (`enrichment/matching/eval/run_eval.py`), the answer layer has none.

**Uncertainty, stated plainly.** Three audits proposed mechanisms for bug #6 and verifiers refuted two of them:
- *Refuted:* "the word Barolo was absent from the prompt." All five Geraldine's Barolos carry "Barolo" in `wines.name`, and `_format_wine` prints the name first. The sub_region-invisible-in-prompt effect is real but small for classic appellations (1–2 wines) and material only for US AVAs (Russian River 17–28, Sonoma Coast 11–17).
- *Plausible, unproven:* the Geraldine's Barolos were **evicted before the prompt**. One verifier simulated the full pipeline: at budget $15–50 the Geraldine's retailer pool contains **zero** Barolos (theirs are $59/$99/$110), `_named_fetch` is not retailer- or store-scoped, and `pin_named_matches(cap=3)` filled all three slots with AOC Barolos ($149/$108/$117) — while the prompt simultaneously asserted `named_bottle_found=True` ("It IS available nearby and leads the listings"), `retailer_has_fit=True` ("every listing below is from Geraldine's"), and `_SYSTEM_PROMPT:130` ("only pick wines from that retailer"). Three computed "facts" the visible rows contradict; the only self-consistent reading is the denial.
- *Also plausible:* the Layer-B eviction mechanism above.

The proposal below does not depend on resolving this: it fixes the grounding layer so that *no* mechanism in Layers A or B can produce a spoken false absence, and it adds the detector that would attribute the next one.

---

## 3. Target architecture

Four changes, each removing a whole class rather than an axis.

### (a) Availability becomes a deterministic computed fact

Introduce an **availability oracle**, called after intent resolution and before prompt build:

```python
availability_facts(resolved_intent, nearby_store_ids) -> list[AvailabilityFact]
```

For every constraint the intent names — each region/appellation/country, each grape, each wine_type, each named bottle, each ×(retailer|store) compound — issue `count='exact'` queries (plus min/max price) against the **full nearby inventory**: no `LIMIT`, no budget clamp, no staleness filter, no enrichment gate, no type gate, matching `region OR sub_region OR country OR varietal OR grapes OR name` through the normalized predicate from (b). These are COUNT queries, not row fetches — cheap, cacheable per (zip, axis, value), and independent of every narrowing stage that caused the bugs.

Each fact resolves to exactly one of four states, which is the vocabulary the narrative is allowed to use:

| State | Meaning | Sanctioned script |
|---|---|---|
| `NOT_IN_CATALOG` | count == 0 over full nearby inventory | the only case where absence may be spoken |
| `PRESENT_OUT_OF_BUDGET` | count > 0, in-budget count == 0 | "there are 3 Barolos at Geraldine's, $59–$110 — above your $50 cap" |
| `PRESENT_NOT_SHORTLISTED` | in-budget count > 0, 0 in the top-12 | "there are 95 Riojas nearby; here's the closest thing I surfaced" — **never** absence |
| `PRESENT_SHORTLISTED(n, idx)` | n of the listings satisfy it | must be surfaced (see (c)) |
| `UNMEASURED` | retailer's freshest row is stale, or the axis has no queryable column (flavor, oak, organic, format) | "I can't filter on that" / "H-E-B prices are from July 19" |

`UNMEASURED` is what closes the intent-coverage gap without inventing data: an unrepresentable axis stops degrading into a generic sample plus a confident denial and instead degrades into a stated capability limit. It also fixes the staleness class properly — the pipeline must never represent *"retailer has nothing"* and *"retailer was not fetched"* with the same empty list.

`retailer_has_fit=False` is retired in favor of a fact from this block; the "doesn't stock" directive is deleted.

### (b) One filter spec, no more per-axis fetches

Collapse `_fetch_rows`, `_targeted_rows`, `_retailer_rows`, `_named_fetch`, `_constraint_fetch` into **one parameterized inventory query** whose predicate comes from a single pure function:

```python
filter_spec(resolved_intent, scope) -> FilterSpec   # pure, unit-testable, no I/O
run_query(FilterSpec, *, budget: BudgetPolicy, staleness: StalenessPolicy, limit, order)
```

Rules the spec enforces once, for every path:

- **Place is a hierarchy, not a string.** One predicate: `region OR sub_region OR country`, accent-folded on both sides, backed by a normalized/`unaccent()` expression-indexed projection (or generated `*_norm` columns). Add `sub_region` to `INVENTORY_SELECT`, to the candidate dict, to `_cand_in_place`, to `deep_fetch_reason`, and to the scorer's region axis. Collapse `region`/`regions` into one ordered list with `regions[0]` as the derived primary, and **union parent into the fetch set** rather than choosing between parent and child.
- **Grapes match through the vocabulary the enrichment layer already owns** (`reference.CORE_GRAPES`) with alias resolution (Syrah/Shiraz, Grenache/Garnacha, Pinot Gris/Grigio) and normalized comparison — never `.title()`-guessing the stored casing, and never a single exact-containment spelling.
- **Type is canonicalized at the boundary** — one accent-fold + alias function applied to the enum value and the stored column, so `rose`/`rosé` and the `fortified`/`dessert` fold live in one place. Chip types and parsed types resolve into **one** resolved-type set consumed identically by the gate, the scorer, and the prompt.
- **Staleness fails open per retailer**, inside the loop, with the recovered rows marked `stale_since` and surfaced as an `UNMEASURED` fact — not silently benched.
- **A spoken price replaces the slider ceiling** for the targeted/named paths, and the window becomes a prompt fact so an out-of-budget bottle is "above your budget", never "not available".

Then fix the truncation inversion. **Rank before truncating, in the database.** Two acceptable shapes:

1. *Preferred:* push the deterministic scorer's mechanical axes (type, grape@array, place, price distance, rating, tier) into a SQL/RPC ranking function and return the top-N ranked **over the whole nearby store set**.
2. *Acceptable interim:* keep scoring in Python but make the fetch exhaustive-but-projected — select only scoring columns, paginate `.order("id").range()` over the full nearby set (15.6k rows at the largest zip is a few hundred KB), score everything, hydrate the full payload for the top 12 only.

Either way the named path becomes an **AND-with-relaxation ladder** (all tokens → drop the most common token → …) over an ordered result, ideally `pg_trgm`/`websearch_to_tsquery` on `wines.name`, and it is **scoped by `detected_retailer`/`detected_store`** rather than searching all nearby stores and then pinning three arbitrary rows. The enrichment gate is exempted on the name-directed path (a user naming a bottle should not be gated on whether enrichment reached it — measured 10.6% drop at Pogo's, the fine-wine catalog people name explicitly, vs 1.7% at Spec's).

Finally: carry intent forward as conversation state. `parse_message`, `detect_store` and `detect_retailer` see only `req.message`, so turn 2 ("anything cheaper?") loses region/grape/retailer/bottle and reverts to a generic sample while the model still remembers the constraint from the history preamble — reproduced: turn 1 with `region="Bordeaux"` gives 11/12 Bordeaux, the same intent with the NL region dropped gives **0/12**. Persist the resolved intent on the existing `recommendation_sessions` row and let a follow-up express a delta with explicit reset semantics.

### (c) Constraint satisfaction becomes a tier, and the prompt cannot assert absence

**Selection.** Partition scored candidates into *satisfies the explicit ask* / *does not*. Fill the list from the satisfying tier first; let the additive score (including personalization) order **within** each tier. Personalization then chooses *which* Rioja instead of *whether* Rioja exists. Generalize `ensure_region_representation` into `ensure_constraint_representation(top, scored, resolved)` covering region, appellation, grape, type and named retailer/store **at cardinality 1**, invoked as the last step of `_score_and_select`. Make `deep_fetch_reason` load-bearing: if it still returns non-None after the deep fetch, pin the best satisfying candidates (the `pin_named_matches` mechanism already works — it is just wired to one path) and pass `ask_satisfied: false` to the prompt. Raise or ask-scope `_VARIETAL_CAP` so a single-grape availability question is not capped at 4.

**Prompt.** Three hard rules:

1. **Absence assertions are forbidden in the narrative.** Delete the supplied denial phrase. The only sentences permitted about what does or does not exist are the sanctioned scripts keyed to an `AvailabilityFact` state. "I judged this a poor fit" and "this does not exist nearby" become different sentences with different licences.
2. **Any listing flagged as satisfying the user's literal constraint MUST appear in `picks`.** "Never pad" applies to unrequested filler, never to a constraint match.
3. **The projection must be lossless with respect to anything that can cause selection.** If a field can make a wine match (`sub_region`, `grapes`, `wine_type`), `_format_wine` renders it, plus a per-listing `[matches: Barolo (appellation), Nebbiolo (grape)]` annotation and the axis cardinality ("Barolo: 3 nearby, $59–$110; 12 listings shown of 95 Rioja matches"). A test should assert *every field in the place/grape/type predicate is rendered by `_format_wine`*.

Add a **post-stream narrative audit** (in-process, ~30 lines): regex the assembled narrative for the absence family; if it fires while any `AvailabilityFact` for that axis is `PRESENT_*`, log `FALSE_ABSENCE_SUSPECT`, emit a server-side event, and Slack-alert. This is the only mechanism that catches the bug-#6 shape at all — note that over the 290 persisted sessions, absence assertions distributed `{0 picks: 4, 1: 3, 2: 2, 3: 3}`, i.e. **8 of 12 occurred on turns that returned picks**, so a zero-pick metric alone would have caught roughly a third.

### (d) What the regression suite asserts

One file, `tests/test_recommend_capability.py`, marked `@pytest.mark.capability`, nightly against live Supabase (not in the fast suite), replacing the four `verify_*.py` scripts — which re-implement the PostgREST queries inline rather than calling production code, and would therefore all still pass if `_targeted_rows` were deleted. (Fairly: `verify_multi_region.py` does call the real `parse_message`, and one verifier measured it as *more permissive* than prod — 300 rows vs 171 for Mendoza — so it could stay green while prod thinned out.)

Structure:

1. **Ground-truth oracle** — a deliberately dumb, fully paginated `.order("id").range()` scan with no limit, no staleness filter, no enrichment gate: `truth(zip, axis, value) -> count`.
2. **Axis generator** derived from live data per seeded zip: top-5 regions, top-5 appellations, top-5 countries, top-5 grapes, every retailer, every nearby store name, every `wine_type`, 3 in-stock bottle names, plus compounds (region+type, retailer+type, country+type, appellation+store). Cases derived from the DB cannot rot.
3. **Filter-aware fake PostgREST** for the fast suite — dispatch on table name, record the filter chain, evaluate `eq/in_/gte/lte/or_(ilike|cs)` against in-memory rows. This makes the canonical regression finally *expressible*: seed an inventory where the only Bordeaux row is at one store and outside the breadth sample, and assert it reaches `top`. The pattern already exists in-repo (`test_recommend_api.py:754-779`) and simply wasn't applied to the paths that broke. Extract the five closures to module level so they are importable.
4. **The invariants**, asserted on the candidate list and the fact block — never on prose:
   - `truth > 0 ⇒ axis_match_count(top) ≥ 1` for every generated (axis, value)
   - `AvailabilityFact.state == NOT_IN_CATALOG ⇔ truth == 0` — the oracle and the fact block must agree
   - every nearby in-stock in-budget row is *scored* (the retrieval-completeness invariant)
   - `test_no_axis_silently_zero`: one aggregate failure printing a table of every (axis, value) where `truth > 0` and `matches == 0` — so a single run enumerates all remaining axes at once instead of one user bug report at a time
5. **Behavioral eval** (~20 fixed intent+candidate-list fixtures, no DB, nightly): for each fixture where a match IS in the list, the narrative must contain no absence assertion scoped to that axis. This is the only test that would catch bug #6; today the entire generation strategy is "the instruction text is present."
6. **Vocabulary contract tests** (fast suite, S): intent enum ∪ chip values ⊆ distinct `wines.wine_type` after canonicalization; `STYLE_TAG_MAP` values ⊆ `FLAVOR_VOCAB` after normalization; grape predicate spellings ⊆ `CORE_GRAPES` aliases. Same drift-guard pattern item 30 used for grapes. Today the frontend test (`regions.test.js:8-11`) *asserts the mismatched forms*, locking the drift in on both sides.
7. **CI** — `ci.yml` runs the 13-second secret-less fast suite on every push/PR as a required check before Railway/Vercel promote `main`; a scheduled job runs the capability + eval suites and Slack-alerts like `verify_scrape_runs` already does.

---

## 4. Prioritized plan

Sequenced highest-value / lowest-risk first. Each item names what it makes *structurally impossible*.

| # | Change | Impact | Effort | Risk | Makes impossible |
|---|---|---|---|---|---|
| **1** | **CI runs the fast suite; capability + eval jobs scheduled with Slack alerts** | Multiplier on everything below | S | None | Silent decay of every guard added later. (Honestly: would have caught **none** of the six — all were coverage gaps, not regressions. It is insurance, not a cause.) |
| **2** | **Availability oracle + fact block + prompt ban on unsanctioned absence + `PRESENT_OUT_OF_BUDGET`/`UNMEASURED` scripts** | Closes the *spoken* false-absence class independent of retrieval quality | M | Low — additive COUNT queries + prompt text; no change to what is recommended | Somm asserting absence that contradicts a deterministic count. Downgrades every remaining retrieval/selection defect from "confident lie" to "thin shortlist" |
| **3** | **Post-stream narrative audit → `FALSE_ABSENCE_SUSPECT` + server-side `recommend.turn` event; persist resolved intent, detected retailer/store, `deep_fetch_reason`, pool sizes, `raw_rows`, per-query `limit_hit`; request-id minted first; stop swallowing the session insert exception** | Detection stops depending on a human noticing | S | None | Discovering instance #7 from a user report. Also makes retrieval-vs-grounding attribution possible, which took six manual reports to distinguish |
| **4** | **Constraint-satisfaction tier + `ensure_constraint_representation` at cardinality 1 + gate `_W_SIMILAR`/`_W_DISLIKE` on the axes the request named** | Fixes the measured 12/12 → 0/12 collapse for every signed-in user | S–M | Medium — changes ranking; needs the personalization tests rebuilt with a non-neutral `_intent()` | Personalization deciding *whether* the requested style exists. Removes the largest single source of "correct retrieval, wrong shortlist" |
| **5** | **Unified `filter_spec` + one parameterized query: `sub_region` in the place predicate everywhere, accent-folded normalized matching, grape alias resolution, canonical type, spoken-price override, per-retailer staleness fail-open, retailer/store-scoped + AND-relaxation named lookup** | Kills the largest measured retrieval losses (appellations 4–30×, Rhône 108×, `Nero d'Avola` 0→54, rosé 0→110, H-E-B's 41%) and ends predicate drift | M–L | Medium — one shared predicate touches every path; land behind the capability suite from #1 | A predicate fix landing in one of five places. A new axis requiring a new I/O path |
| **6** | **Rank-then-truncate: DB-side ranking (or exhaustive-projected pagination) replacing the unordered `LIMIT 500`/`80`/`200`/`300`** | Retrieval completeness becomes an assertable invariant rather than a coverage percentage | L | Medium–High — perf and behavior change; do last, with #1's invariant test as the gate | An arbitrary row prefix being mistaken for the inventory; ranking after truncation |
| **7** | **Vocabulary contract tests + wire chips into the resolved intent** (`wine_types` list into `intent_from_request`; `'full body'`/`'light body'` chips → `intent["body"]` not a dead flavor string; scorer credits membership in the resolved-type *set*) | Fixes: White chip + "Cellar it" → `resolved wine_type='red'`, +3.0 on reds, prompt asserting "Looking for: red" over white listings; "Bold & Tannic" scoring 0.000 on 100% of candidates | S | Low | Three subsystems answering "what type did the user ask for?" differently. Enum/column drift zeroing a whole type again |
| **8** | ✅ **DONE 2026-09-02 (budget only)** — **Multi-turn intent state** — persist resolved intent per session; parse expresses a delta; run `detect_store`/`detect_retailer` over carried intent | Turn 2 stops reverting to a generic pool while the model still remembers the constraint | M | Medium — needs explicit reset semantics or users get stuck in a stale filter | Every fix in #2–#6 applying only to the first turn. **Budget only** — region/wine_type/grapes/avoid deliberately NOT carried (that is where the stale-filter risk lives; a stale budget is at least visible in the answer's prices). #2–#6 still apply only to turn 1 for those axes. Design: `docs/superpowers/specs/2026-09-02-multi-turn-budget-state-design.md` |
| **9** | **Filter-aware fake PostgREST + extract the five closures to module level** | The canonical regression becomes expressible; the retailer path stops being dead code under test | M | None | A fetch path that is never invoked being indistinguishable from one whose filter is wrong |

Ship order rationale: **#2 and #3 before any retrieval work.** They are additive, low-risk, and they sever the link between *thin retrieval* and *a false claim* — which means the remaining items become quality work under a safety net rather than incident response.

---

## 5. What NOT to do

- **Do not add a seventh targeted fetch.** That is the strategy that produced the drift, and `_named_fetch` — the fix for bug #5 — reproduced the exact defect it was added to fix. If an axis needs coverage it becomes a clause in `filter_spec`, not a new query builder.
- **Do not relax the enrichment gate broadly or loosen the diversity caps.** Measured drop is 2.2% / 3.0% / 4.1% (SA / Dallas / Nashville) and the `skipped` backfill loop makes the caps count-preserving. Two narrow exceptions only: exempt the **name-directed path** (10.6% drop at Pogo's) and ask-scope `_VARIETAL_CAP`. Relaxing these moves single digits while the fetch layer loses 87%.
- **Do not delete the score jitter as a false-absence fix.** Verification refuted the mechanism: `scored` is already score-sorted (`scorer.py:265`) before jitter, so jitter keys to merit rank, not fetch order; the unordered query returned identical order 3/3; and `_W_REGION` 1.5 / `_W_GRAPE` 2.0 / `_W_TYPE` 3.0 all exceed the 0.8 max differential. It matters only for asks with 1–2 matching bottles, and removing it makes those misses *deterministic* rather than fixed. Item #4's constraint tier is the actual remedy.
- **Do not build a vector/semantic search layer.** Every measured miss is a deterministic predicate bug (accent, casing, missing column, wrong table). Embeddings would mask them, not fix them, and would make availability *less* countable.
- **Do not populate `tasting_notes` to revive `kw_hits`.** The column is NULL on 0/21,085 rows. Delete the `kw_hits` branch (`scorer.py:194`) and the `tasting_notes` clause of `wine_excluded_by_avoid`. Likewise `_W_TIER` never fires (0% of the pool has `grapeminds_enriched_at`) — treat it as dead.
- **Do not hand-expand `GRAPE_FLAVORS`/`REGION_FLAVORS` into a taxonomy.** A 32-grape / 14-region text table cannot cover a 22.8k catalog (30.4% of pool wines have a *known* grape and zero tags). Use `structure_profile` — 91.5% populated with real numeric axes — for body/structure asks, and treat un-derivable flavor as `UNMEASURED`.
- **Do not restore `max_price` widening on the breadth fetch.** Widen only the targeted/named/constraint paths; breadth stays on the slider for cost.
- **Do not bulk-NULL producer-knowledge regions.** Already a standing deferred decision (CLAUDE.md item 27): the gate would null 3,804 mostly-correct rows.
- **Do not keep the four `verify_*.py` scripts alongside the capability suite.** Fold and delete; two live-DB harnesses that disagree is worse than one.

## 6. Findings I rank lower than the auditors did

- **`avoid` has no fail-open** — auditor said medium, verifier brute-forced 1,015 realistic combos and emptied the pool **zero** times; the "only hard-exclusion path" claim is also false (the enrichment gate and SQL price/type filters are equally hard). Real residual sub-bug: word-boundary matching against `name` excludes *Dry Creek* Zinfandel on `avoid=["dry"]`. **Low** — a cheap fail-open, not a class.
- **The "nine unrepresentable intent axes"** — collapses to ~3–4 after verification (organic/natural, bottle format, vintage precision, oak). Sweetness, occasion/ageability and producer already map onto existing fields; `abv` *is* selected and `structure_profile.sweetness` *is* rendered. **Medium**, and #2's `UNMEASURED` state handles it honestly without new columns.
- **`_constraint_fetch`'s country-blindness / singular-`region` read** — reproducible numbers (Argentina 9 vs 189) but **inert**: `_targeted_rows` already runs region-OR-country per element of `regions` before scoring, and `if extra:` makes an empty result a no-op. Fixed for free by #5; not worth a standalone patch.
- **CI absence rated critical** — **medium**. All six bugs were coverage gaps, not regressions; a runner over the existing suite would have caught none. Still #1 in the plan, because it is the durability guarantee for #2–#9.
- **"The forensic table is hiding a 7th unpatched bug"** — **refuted**. The Rhône/Lincoln Heights session (2026-07-17T18:00:56 CDT) predates its own fix commit `4e1a26e` by 24 minutes and is the session that *motivated* fix #1; no session in the table postdates the final fix, and the prototype detector runs ~50% false positives. The real content is the missing cumulative harness (#1/#3), not a latent incident.
- **"H-E-B is 100% unreachable"** — **refuted**: all four secondary fetches fail open per query, so H-E-B still surfaces when named, and 32 regions + 31 varietals it stocks exclusively at 78209 self-heal. The genuine blast radius is breadth-only asks with no place/retailer/name/grape hook, where 1,059 of its 1,378 in-budget wines are market-exclusive and invisible. Still worth fixing (#5), but not the emergency it was framed as.
- **"12.8% of nearby inventory is visible"** — true, but the pipeline is a top-12 funnel regardless; coverage matters only when rows relevant to a *stated* constraint fall outside the prefix. The load-bearing part is the **missing `.order()`** (the same wrong answer every time, until the next scrape rewrites row order), not the percentage.
- **"`sub_region` invisibility explains bug #6"** — **refuted** (the appellation is in `wines.name` for 124 of 127 live Barolos, and `_format_wine` prints the name first). The `sub_region` *retrieval and scoring* gap is real and high-priority; the prompt-rendering limb is a minor, AVA-shaped effect.