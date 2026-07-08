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
