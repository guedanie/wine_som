# Somm 🍷

**An editorial wine atlas.** Enter your zip code, budget, and taste — get
Claude-powered sommelier recommendations for wines actually **in stock at
retailers near you**, with per-store pricing.

> Live private beta since 2026-07-05 · San Antonio, Austin, Nashville, Charlotte,
> Winston-Salem, Dallas · installable PWA.

---

## What it does

- **Conversational recommendations.** Describe what you want ("something bold for
  tonight under $40") and a Claude sommelier picks real, locally-available bottles
  and explains why — leading with the wine and the place, never a textbook.
- **Local availability + pricing.** A zip → nearby-store radius lookup means every
  pick is something you can actually buy this afternoon, at that store's price.
- **Personalized.** Save bottles, track a cellar, thumbs-up/down picks, and take a
  short taste-profile interview — the engine re-ranks toward your palate and the
  Somm can say "close to the Barolo you own."
- **Discovery.** Browse by region with illustrated travel posters, drawn contour
  maps, structure rulers, and per-sub-region availability near you.

## Architecture

```
React SPA (Vercel)  ──►  FastAPI (Railway)  ──►  Supabase (Postgres + Auth)
   Somm chat, PWA         recommend / search        wines, inventory, users
                          scrapers, enrichment       (RLS-scoped user data)
                                │
                    Claude (Haiku) · scrapers · enrichment
```

- **Frontend** — React 19 + Vite + Tailwind. Anonymous-first; optional
  magic-link accounts (saved bottles, cellar, taste profile) via Supabase Auth.
- **Backend** — Python 3.9 + FastAPI. Deterministic knowledge-based scorer
  shortlists candidates; Claude picks + writes the narrative.
- **Data** — 11 retail scrapers feeding ~120k inventory rows across TX/TN/NC;
  layered enrichment (retailer data → Vivino → local LLM → deterministic tables).

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite, Tailwind v3, react-router v7 |
| Backend | Python 3.9, FastAPI, supabase-py |
| DB / Auth | Supabase (Postgres, RLS, magic-link auth) |
| AI | Anthropic Claude (Haiku — recommendations + fact extraction) |
| Scraping | urllib / curl (Shopify, GraphQL, City Hive), Kroger official API |
| Geo | pgeocode (offline US zip centroids) |
| Hosting | Vercel (web) · Railway (api) · Supabase (db) |

## Retail coverage (11 scrapers)

H-E-B · Central Market · Spec's · Kroger · Harris Teeter · Twin Liquors ·
Pogo's · Geraldine's · AOC Selections · US Natural Wine · Antonelli's · Harvest
Wine Market — across San Antonio, Austin, Dallas, Nashville, and the Carolinas.

## Getting started

Requires Python **3.9** and Node 18+. Secrets live in `.env` (see the key list
in `CLAUDE.md`).

```bash
# Backend  (from backend/)
cd backend
pip install -r requirements.txt
python3 -m uvicorn api.main:app --reload      # http://localhost:8000  (docs: /docs)

# Frontend (from frontend/)
cd frontend
npm install
npm run dev                                    # http://localhost:5173

# Tests
cd backend  && python3 -m pytest tests/ -m "not integration"
cd frontend && npx vitest run
```

> Run backend commands **from `backend/`** so `../.env` resolves, and frontend
> commands **from `frontend/`** so Vitest/Vite find their config.

## Automation

- **Weekly scrape** (`.github/workflows/weekly-scrape.yml`) — GitHub Actions,
  Sundays 02:00 CT: 10 scrapers + incremental fact extraction, Slack summary.
- **Enrichment jobs on a residential-IP Mac mini** — Vivino, local-LLM
  extraction, and Twin Liquors (all blocked on datacenter IPs). See
  `docs/mac-mini-enrichment-server.md`.

## Repo layout

```
backend/     FastAPI app, scrapers, enrichment, recommendation engine, tests
frontend/    React SPA (screens, components, design system)
supabase/    SQL migrations
docs/        design specs, implementation plans, runbooks
data/        store registries + API-probe findings
CLAUDE.md    agent/contributor guide — status, conventions, gotchas
```

## Documentation

- **`CLAUDE.md`** — the working guide: build status, critical gotchas,
  per-system technical notes, roadmap.
- **`frontend/CLAUDE.md`** — design system (type, color, components, voice).
- **`docs/`** — implementation plans, the Mac mini runbook, product-family design.
- **`data/exploration/`** — how each retailer's API was reverse-engineered.
