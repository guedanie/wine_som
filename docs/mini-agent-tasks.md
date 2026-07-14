# Mini agent tasks — Spec's migration + extraction run-logging

Two tasks for the agent working on the Mac mini (`~/dev/wine_app`). Context:
root `CLAUDE.md` (gotchas: Python 3.9 — `Optional[str]` not `str | None`; run
backend commands from `backend/` so `../.env` resolves). The Twin Liquors
setup is the pattern to copy for anything launchd: `scripts/com.somm.twin-liquors.plist`
+ `scripts/run_twin_liquors_launchd.sh` (edit hardcoded paths to `~/dev/wine_app`).

---

## Task 1 — Move the Spec's scraper to the mini

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

## Task 2 — Extraction job should write a `scraper_runs` row

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
