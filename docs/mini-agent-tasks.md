# Mini agent tasks — Spec's migration + extraction run-logging

Two tasks for the agent working on the Mac mini (`~/dev/wine_app`). Context:
root `CLAUDE.md` (gotchas: Python 3.9 — `Optional[str]` not `str | None`; run
backend commands from `backend/` so `../.env` resolves). The Twin Liquors
setup is the pattern to copy for anything launchd: `scripts/com.somm.twin-liquors.plist`
+ `scripts/run_twin_liquors_launchd.sh` (edit hardcoded paths to `~/dev/wine_app`).

---

## Task 1 — Move the Spec's scraper to the mini ✅ DONE 2026-07-13

**Landed:** `scrapers/base.py` upsert de-dup by conflict key (Landmine A) +
`scrapers/specs.py::SpecsRateLimited` retry/backoff on non-JSON, 60s pause
between rate-limited stores, polite sleep 0.5s→1.0s (Landmine B) + new
`backend/scripts/{run_specs_launchd.sh,com.somm.specs.plist}` (Sun 05:00 CT,
loaded on the mini). Spec's step removed from `.github/workflows/weekly-scrape.yml`
+ CLAUDE.md + this scrapers.md. First real run: Sunday 2026-07-19.

<details><summary>Original brief (kept for context)</summary>


**Why:** Spec's blocks datacenter IPs. Every GitHub-cron run since 2026-07-01
completed "successfully" with 0 records; the last real run was **2026-06-19**
(33,456 records). Verified 2026-07-13 from a residential IP: the API works
perfectly (`_fetch_wine_page(69, 1)` → 96/96 products parsed). Same story as
Twin Liquors/Vivino — the fix is the same: run it here.

**What:** a weekly LaunchAgent (Sunday, pick a slot that doesn't overlap Twin
at 04:00 CT or extraction at 03:00 CT — 05:00 CT works) running:

```python
import asyncio
from scrapers.specs import SpecsScraper, SA_STORE_NUMBERS, AUSTIN_STORE_NUMBERS, DALLAS_STORE_NUMBERS
asyncio.run(SpecsScraper().run_full(SA_STORE_NUMBERS + AUSTIN_STORE_NUMBERS + DALLAS_STORE_NUMBERS))
```

(That's the exact invocation the GitHub workflow used — see the Spec's step in
`.github/workflows/weekly-scrape.yml`.) Wrap it like
`run_twin_liquors_launchd.sh` does (Slack notify via `lib_notify_slack.sh`,
logs to `~/Library/Logs/`). Takes ~30 min for all stores.

### ⚠️ Landmine A — duplicate-conflict upsert error (expect it on run 1)

The last runs that actually reached the DB (2026-07-05, three attempts) all
died with:

```
ON CONFLICT DO UPDATE command cannot affect row a second time
```

That means one upsert batch contained the same conflict key twice. Candidate
sites, in likelihood order:

1. `scrapers/base.py` `_upsert_wines` — `on_conflict="upc_canonical"`; two
   products on one page can normalize to the same canonical UPC.
2. `scrapers/base.py` `_upsert_inventory` — `on_conflict="upc,store_ref"`;
   same raw UPC listed twice for one store.
3. `scrapers/specs.py` `_upsert_wine_details` — `on_conflict="wine_id"`; two
   UPCs mapping to one wine_id.

**Fix: de-dupe each batch by its conflict key before upserting (keep the last
occurrence).** TDD it — a unit test that feeds a batch with a duplicate key
and asserts the upsert payload contains it once. Fix it in `base.py` so every
scraper benefits, plus the specs-local `_upsert_wine_details`.

### ⚠️ Landmine B — no throttle resilience

`specs.py` has none of the backoff machinery Twin needed: no retry on a
failed/HTML page fetch (a `json.loads` failure just breaks to the next store —
that's how the silent-zero happened), no rate-limit pause. From one
residential IP hammering ~30 stores × ~35 pages, throttling is plausible.
Borrow the shape of `twin_liquors.py`'s `_fetch` (bounded retries with
backoff; a custom exception when it never clears so the runner can pause and
resume) and consider raising the polite `time.sleep(0.5)` between pages.

### Cleanup once the mini job is live

- **Remove the Spec's step from `.github/workflows/weekly-scrape.yml`**
  (including its entry in the Slack `OUTCOMES` list and the "all 10 scrapers"
  wording). If it stays, the GH run keeps writing silent-zero rows, and
  `scripts/verify_scrape_runs.py` (runs at the end of that workflow) will
  correctly flip them and turn the workflow red every Sunday.
- Add a comment there mirroring the Twin Liquors one ("runs on the
  residential-IP mini").
- Update root `CLAUDE.md`: retail-data bullet (Spec's moves into the
  "runs on the mini" list; drop the ⚠️) and `docs/reference/scrapers.md`.

### Acceptance

- `scraper_runs` row: `retailer_name="Spec's"`, `status="success"`,
  `records_updated` in the tens of thousands (Jun 19 baseline: 33,456).
- Store rows keep their addresses (the scraper now writes `stores.address`).
- `cd backend && python3 -m scripts.verify_scrape_runs --since-hours 24`
  exits 0 after the run.
- **Required — the wrapper must run its own sweep + verify after the scrape:**
  `python3 -m scripts.sweep_delisted --since-hours 6 && python3 -m scripts.verify_scrape_runs --since-hours 6`.
  The Sunday GitHub workflow runs these too, but only over runs already
  FINISHED when it fires (~10:30 UTC last week) — a Spec's job at 05:00 CT
  (10:00 UTC) races it and would miss its weekly sweep/verify entirely. Both
  scripts are idempotent, so double coverage is harmless; self-running them
  makes the job self-contained regardless of GH cron delays.

---

</details>

---

## Task 2 — Extraction job should write a `scraper_runs` row ✅ DONE 2026-07-13

**Landed:** `enrichment/extraction/run_extraction.py` now books a scraper_runs
row (`retailer_name="Extraction (local qwen)"`, `status="running"` at start)
and finalizes it (`success`/`failed` with `records_updated` = written wines +
`error_message` on exception) inside a try/finally that re-raises so
`run_extraction_launchd.sh` still surfaces a nonzero exit and skips the
`persist_structure` chain on failure. Tests in
`tests/test_run_extraction_lifecycle.py` (success, records_updated, failure
paths). First real logged run: Sunday 2026-07-19.

<details><summary>Original brief (kept for context)</summary>


**Why:** the weekly extraction LaunchAgent (`com.somm.extraction-enrich`, Sun
03:00 CT) is invisible to monitoring — it writes no `scraper_runs` row, so
`scripts/verify_scrape_runs.py` (the silent-failure alarm added 2026-07-13)
can't see it. If it dies, the only symptom is varietal/region NULL coverage
slowly drifting up.

**What:** have the extraction run insert a `scraper_runs` row at start
(`retailer_name="Extraction (local qwen)"`, `status="running"`) and finalize
it (`success`/`failed`, `records_updated` = wines written, `error_message` on
failure). Columns: `id, retailer_name, status, records_updated, error_message,
started_at, completed_at`. Mirror how `scrapers/twin_liquors.py run_full`
manages its row. Best placed in `enrichment/extraction/run_extraction.py` so
manual runs are logged too; make sure the `persist_structure.py` chaining in
`scripts/run_extraction_launchd.sh` still runs on success.

The verifier treats `status="running"` as in-flight (not an issue), flips
`success` + 0 records to failed, and alerts on failed/partial — so once this
lands, a dead extraction Sunday becomes a red workflow + Slack ping instead
of silent drift.

**Optional follow-on:** same treatment for the Vivino LaunchAgent
(2×/day) — lower priority since it visibly moves `vivino_enriched_at`.

### Acceptance

- Sunday's extraction produces a `scraper_runs` row with a real
  `records_updated`.
- Killing the job mid-run (or an exception) leaves a `failed` row that
  `verify_scrape_runs.py` reports.
- Unit tests for the run-row lifecycle (mock supabase, success + failure paths).

</details>

---

## Task 3 — Wine-type + region backfills ✅ DONE 2026-07-14

**Landed (all three subtasks, run from the mini):**

1. Portuguese retype: 8 rows retyped (incl. manual calls on Chryseia + Quinta
   Maria Izabel → red), 8 genuine Ports/Madeiras kept dessert.
2. Rhône fragments: 24 → 'Rhône'; 3 CdP-as-region rows → region 'Rhône' +
   sub_region 'Châteauneuf-du-Pape'; 1 bonus catch (a Paso Robles wine filed
   as CdP → Central Coast).
3. Validation pass: `scripts/revalidate_regions.py` (+ tests) applied 2,195
   changes — 1,975 country fills, 137 region corrections, sub_region fills.
   **Bulk NULLING was deferred**: a dry run showed the evidence gate would
   null 3,804 mostly-correct producer-knowledge regions (Grgich Hills→Napa
   class) — appellation coverage is too thin to null at rest. The script
   reports deferred rows; revisit when coverage improves.
4. **Bordeaux residue sweep (2026-07-14):** reference gained the Bordeaux
   satellites (Côtes de Francs/Castillon/Blaye/Bourg, Lussac/Montagne/
   Puisseguin-Saint-Émilion, Cadillac, Loupiac, Listrac), 'Bdx' shorthand, and
   `_fold` now expands retail 'St./Ste.' → Saint/Sainte. 71 misfiles hand-fixed
   (a DRC La Tâche(!), 9 Champagnes, 7 Burgundies, Napa/California cabs, Chile/
   Argentina brands, Fleur du Cap, an Austrian Wachau Riesling, a vermouth, 2
   Sta. Rita Hills pinots, 6 unknowns → honest null). Residue 151 → 73 (6% of
   1,093), all genuine petit-château Bordeaux kept.
5. **Rhône residue sweep (2026-07-14, after bc2fa15's satellite expansion):**
   of 45 still-unevidenced Rhône rows, ~30 are genuinely Rhône (northern-Rhône
   producers, CdP domaines, Vaucluse VdF) and were kept; 15 misfiles fixed by
   hand — the audit's four (Savoie white, Prosecco, Italian sparkler, Clos Du
   Val→Napa) plus a sake(!), a Chablis, a Sancerre, 4 Envínate Ribeira Sacra,
   Rombauer Carneros, a Burgundy Aligoté, Kivelstadt→Sonoma, XOBC→null.

Dry-running also exposed + fixed real gazetteer bugs (all TDD'd, live for the
weekly extraction too): "Latour" firing inside Louis Latour / Georges de
Latour, "Santa Rita" inside Santa Rita Hills AVA, "Gloria" inside Gloria
Ferrer, château hits overriding explicit conflicting appellations (Chateau
Saint Pierre Pomerol → Saint-Julien), description mentions ("in the style of
Pétrus") false-firing, stale sub_regions surviving producer hits, and
single-word château needles now require a preceding Chateau word. Burgundy
appellation list expanded (Santenay, Côte de Nuits-Villages, etc.).

<details><summary>Original brief (kept for context)</summary>

Code is already on main (word-boundary + Portuguese-vocabulary
`infer_wine_type` in `utils/__init__.py`; extraction gazetteer + evidence gate
in `enrichment/extraction/`). What remains is applying it to EXISTING rows:

1. **Portuguese dessert-typed rows** — 12 of 28 already retyped from the
   laptop (2026-07-13). Remaining: re-run the retype over
   `wine_type='dessert' AND name ilike '%portug%'` with the new vocabulary
   (catches Touriga/Loureiro/Encruzado/Espumante rows). 8 genuine
   Ports/Madeiras will correctly stay dessert; ~2 with no textual signal
   (Chryseia, Quinta Maria Izabel — actually Douro table reds) may need a
   manual call.
2. **Rhône region fragments** — `region IN ('Rhone','Rhone Valley','Rhône
   Valley')` → `'Rhône'` (~24 rows), and `region='Châteauneuf-du-Pape'`
   (4 rows) → `region='Rhône', sub_region='Châteauneuf-du-Pape'`.
3. **The bigger one (CLAUDE.md item 27)**: a validation/re-extraction pass
   over existing rows with the new evidence gate + gazetteer — nulls
   hallucinated regions (a Savoie white and a Prosecco are filed under Rhône
   today) and fixes Requingua-class producer misattributions in bulk. Run
   `_post_process(rec, source_text=name+description)` over rows with a
   region set; write back only changed fields; count + Slack-report changes.
</details>

---

## Task 4 — Grapes backfill + Vivino queue prioritization ✅ DONE 2026-07-14

**Landed (all from the mini):**

1. `enrichment/extraction/reference.py`: `default_grapes_for(appellation,
   wine_type=None)` is now color-aware — dual-color appellations (Graves,
   Pessac-Léognan, Hermitage/Crozes-Hermitage/Saint-Joseph, Côtes de Bordeaux)
   require an explicit `wine_type` before returning a default. Table expanded
   (right-bank satellites + Saint-Émilion Grand Cru, Bordeaux Supérieur,
   Entre-Deux-Mers, Cadillac/Loupiac/Sainte-Croix-du-Mont, northern-Rhône
   crus incl. Condrieu → Viognier + Tavel → Grenache rosé, southern
   satellites, 'Côte du Rhône' singular). `_norm` folds hyphens. New
   `default_grapes_for_region(region, wine_type)` red-only region-level
   fallback (Bordeaux → Merlot-led, Rhône → GSM). New `ALL_DEFAULT_BLENDS` +
   `is_default_blend()` registry, `is_specific_grape()`. Extractor threads
   `wine_type` into the gate on both Haiku + ollama backends.
2. `scripts/backfill_grapes.py` (one-off): 491 grapes-empty of 1,453
   Bordeaux/Rhône rows targeted (region already set, so weekly
   `--null-only` extraction never revisits them). **375 filled** — 34
   trusted specific varietals, 326 appellation blends, 15 region-level
   fallback. 116 left for Vivino (39 no-sub+no-type, 35 unknown-type
   Pessac-Léognan, legit rosés/whites in red appellations, long-tail
   unknown appellations). Bordeaux grapes-empty 33%→7.4% (361→81),
   Rhône 36%→9.7% (130→35). `varietal` set to lead grape only where NULL.
3. `scripts/run_vivino_sample.py`: queue now fills each run's limit in
   tiers — (1) both-null wines (varietal + region NULL, Task 13's Pogo's
   residue), (2) un-enriched Bordeaux/Rhône, (3) rest. `write_facts` may
   now REPLACE `grapes` when the current value is a multi-grape law-default
   blend (`is_default_blend`) — real Vivino data wins; single-grape values
   are never replaced. `--missing-images` path unchanged.
4. `recommendation/scorer.py`: candidate grape sets union in `varietal`
   (symmetric with the liked-wines path; also broadens avoid-term matching
   to varietal text). "Red blend"/"white blend" asks boost any same-type
   wine with a 2+ grape array (`_blend_match`, type-gated). Verified
   end-to-end: a "Red Blend" intent over 135 real candidates ranks 5
   Bordeaux in the top 10.

Fast suite went 495→521 passing. Commits: eb04993..feaa92f (code
878f073..623905a; spec + plan docs committed separately before).
