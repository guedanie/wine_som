# Future enhancement: Mac mini enrichment server

A dedicated, always-on Mac mini as the home for the two enrichment jobs that
need a residential IP and/or local compute. Consolidates what's currently
improvised on the dev laptop (nohup + caffeinate, cron paused) into a clean,
unattended box.

## Why a dedicated box
- **Residential IP for Vivino** — Vivino IP-blocklists datacenter ranges (that's
  why the GitHub cron is paused). A home Mac mini's IP works (verified 3/3
  matched from the laptop's residential IP).
- **Local qwen for facts** — zero API cost; the mini runs the extraction batches
  instead of tying up the laptop or paying Haiku.
- **Always awake** — no sleep/lid-close problem, so `launchd` schedules actually
  fire (no `caffeinate` gymnastics).

## Hardware sizing
- **16 GB RAM is sufficient** for `qwen2.5:7b` (4.7 GB on disk, ~5–6 GB resident
  at runtime; macOS ~3–4 GB; comfortable headroom). Apple Silicon runs it well
  via Metal. Do **not** plan on 14B (~9–10 GB, tight) or 32B (won't fit) at 16 GB.
- Disk: repo + Ollama models (~5 GB) + node_modules — trivial for any SSD.

## CRITICAL: clone the repo OUTSIDE ~/Documents
Clone to **`~/dev/wine_app`** (NOT `~/Documents/...`). macOS TCC blocks
background/`launchd` processes from reading `~/Documents`, `~/Desktop`,
`~/Downloads` unless granted Full Disk Access — that's exactly why the launchd
Vivino job failed on the laptop (`Operation not permitted`). A repo under
`~/dev/` has no such protection, so both `launchd` jobs run with zero permission
setup and no Full Disk Access grant needed.

## Setup steps
1. `git clone <repo> ~/dev/wine_app`
2. Copy `.env` to the project root: `~/dev/wine_app/.env` (config.py reads
   `../.env` relative to `backend/`).
3. `cd ~/dev/wine_app/backend && python3 -m pip install -r requirements.txt`
   (Python 3.9+; keep `Optional[str]`, not `str | None` — see root CLAUDE.md).
4. Install Ollama, then `ollama pull qwen2.5:7b`. Confirm `ollama list`.
5. Install the **Vivino launchd job**:
   - Copy `backend/scripts/com.somm.vivino-enrich.plist` →
     `~/Library/LaunchAgents/`, and **edit the two hardcoded paths** from
     `/Users/danielguerrero/Documents/ai_dev/wine_app/backend` to
     `/Users/<you>/dev/wine_app/backend` (ProgramArguments + WorkingDirectory).
   - `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.somm.vivino-enrich.plist`
   - `launchctl kickstart -k gui/$(id -u)/com.somm.vivino-enrich` to test now.
   - Runs 2×/day (10:00/16:00 local), `--limit 300`, logs to
     `~/Library/Logs/somm-vivino.log`.
6. **Facts extraction** — either run on demand
   (`EXTRACTOR_BACKEND=ollama python3 -m enrichment.extraction.run_extraction --null-only`)
   or add a second launchd job wrapping the same command on a weekly cadence.
7. System Settings → Energy: set **"Prevent automatic sleeping"** (or never
   sleep on power) so the schedules always fire.

## What this replaces / unblocks
- Retires the laptop's `nohup` + `caffeinate` improvisation.
- Makes the paused `.github/workflows/daily-vivino.yml` permanently unnecessary.
- Natural place to later run the local-LLM CI cutover (drop Haiku) and the
  blend structure/sweetness hybrid pass.

See root CLAUDE.md (Local Vivino launchd job, Local LLM Extraction sections).

## Handoff state (2026-07-09 — laptop jobs stopped, resume on the mini)
Both laptop enrichment jobs were deliberately stopped 2026-07-09 to migrate here:

- **Facts extraction (qwen2.5:7b)**: stopped mid-run at 2,310/6,463 (~2,054
  written that run). Fully resumable — `--null-only` picks up exactly where it
  left off. Catalog state at stop: **5,516 of 17,619 wines still NULL varietal**.
  Resume: `EXTRACTOR_BACKEND=ollama python3 -m enrichment.extraction.run_extraction --null-only`
  (from `backend/`, Ollama running, model pulled: `ollama pull qwen2.5:7b`).
- **After extraction finishes**: run `python3 scripts/persist_structure.py` —
  the laptop had a watcher armed for this; it was killed with the job, so on the
  mini either chain it manually or script the same until-loop.
- **Vivino**: launchd plist + wrapper ready (step 5 above, path edits required).
  ~16.6k wines have never been Vivino-attempted (`vivino_enriched_at IS NULL`).

Order of operations on the mini: extraction backlog first (it feeds
persist_structure and improves Vivino name matching), Vivino launchd second.

## Twin Liquors weekly scrape (added 2026-07-10 — GitHub-blocked, mini-only)
Twin Liquors (City Hive) is Cloudflare-1015-blocked on GitHub datacenter IPs —
a `workflow_dispatch` test committed **0/12 stores**, same as Vivino. It was
removed from `weekly-scrape.yml` and belongs here (residential IP).

- Wrapper: `backend/scripts/run_twin_liquors_launchd.sh` (logs to
  `~/Library/Logs/somm-twin-liquors.log`). Manual: just run the wrapper.
- Schedule it **weekly** (matches the GitHub cron cadence). Either:
  - a launchd `.plist` (mirror `com.somm.vivino-enrich.plist` — swap the
    ProgramArguments to the twin wrapper, `StartCalendarInterval` weekly), or
  - a cron line: `0 3 * * 0  /Users/<you>/dev/wine_app/backend/scripts/run_twin_liquors_launchd.sh`
- The scraper self-paces (~1 req/s) + backs off on 1015, so a residential IP
  should complete cleanly. 12 stores seeded; expand `STORE_MERCHANT_IDS` from
  the store-locations page for full ~90-store TX coverage.
- Reusable win: the same api_key + client_origin bypass likely unblocks the
  parked Nashville City Hive shops (Corkdorks, Frugal MacDoogal) — build those
  here too if Nashville coverage matters.

---

## Current LaunchAgent roster (2026-08-27)

Seven agents are loaded. `launchctl list | grep somm` should show all of them.

| agent | schedule (CT) | what it does | notes |
|---|---|---|---|
| `com.somm.extraction-enrich` | Sun 03:00 | local qwen extraction + persist_structure + blend/sweetness LLM pass | chain job |
| `com.somm.twin-liquors` | Sun 04:00 | Twin Liquors City Hive sweep | City Hive 1015s datacenter IPs |
| `com.somm.nashville-cityhive` | **Sun 04:30** | Frugal MacDoogal + Corkdorks ×2 | **added 2026-08-26.** Deliberately NOT concurrent with Twin — both hit City Hive and would share one 1015 budget |
| `com.somm.specs` | Sun 05:00 | Spec's scrape + sweep + verify | |
| `com.somm.heb` | **Sun 05:30** | H-E-B via the Incapsula browser session | **added 2026-08-26.** MUST run HEADED — see below |
| `com.somm.vivino-enrich` | 2×/day | Vivino enrichment, 300/run | |
| `com.somm.totalwine` | **every 10 days** | Total Wine canary probe | **added 2026-08-27.** A detector, not a scraper — see below |

### `com.somm.heb` needs a GUI session — this one is different

H-E-B moved `heb.com/graphql` behind Imperva Incapsula (~2026-07-26). Only **patchright
with a HEADED persistent context** clears the challenge: vanilla Playwright is
fingerprint-blocked (errorCode 15) headless *and* headed. A headed browser needs a real
display, so this must run in the **logged-in Aqua session** — a launchd *daemon* has no
display and the browser will not launch.

Check with `launchctl managername` (expect `Aqua`) and `stat -f%Su /dev/console`.
Deliberately **not** `ProcessType Background` and `LowPriorityIO false`: throttled CPU/IO
stalls the Incapsula solve. Wrapped in `caffeinate -i` so a mid-run sleep can't kill the
browser session. Requires `pip install --user patchright` + `patchright install chromium`
(pulls both the headless shell and full Chromium — the **full** build is the one used).

Every other agent here is plain HTTP and needs no GUI.

### `com.somm.totalwine` is a probe, not a scrape

Total Wine has two overlapping defences (item 46): ~40% of requests return a **stripped
page** (no JSON-LD, HTTP 200), plus a **PerimeterX penalty** that 403s everything and decays
in ~10 minutes of quiet. The job therefore makes **ONE canary request** and stops if refused
— PX scores behaviour over time, so a blind retry loop would hold the block open. A blocked
cycle **exits 0 and reports INFO, not FAIL**; alerting on an expected state is how real
alerts get ignored. A green probe crawls only ONE page (`TW_PROBE_PAGES`) before reporting.

Probe history accumulates in `~/Library/Logs/somm-totalwine-probes.tsv` so the decay curve
becomes measured rather than guessed.

### Gotcha: the launchd wrapper exit-code bug (fixed 2026-08-26)

`EXIT=$?` placed **after** a `{ … } >> "$LOG" 2>&1` group captures the group's LAST command
(the trailing `echo`), not the python inside it — so a failed run reported exit 0 and Slack
was told "OK". `run_twin_liquors_launchd.sh` and `run_vivino_launchd.sh` did this for as long
as they had run; `run_specs`/`run_extraction` were always correct (they capture inside the
block). All fixed — redirect per-command and capture the python's status directly. **Copy a
known-good wrapper when adding an agent, and verify a deliberate failure yields non-zero.**

### Gotcha: scraper output looks dead when it isn't

Scraper `print`s mostly lack `flush=True`, so with output redirected to a log the file can
look **empty for many minutes** while a run is perfectly healthy. Don't kill on silence —
check the database instead:
`select count(*) from retail_inventory where last_scraped_at > now() - interval '20 min'`.
