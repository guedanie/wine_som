# Claude Code Prompt: Wine Recommendation App — Foundational Build
# Architecture: Supabase-first

## Project Overview

Build a foundational wine recommendation application that combines local retail availability with rich wine knowledge to deliver personalized recommendations based on user preference, budget, and location.

The app has three core pillars:
1. **Wine Knowledge Layer** — enriched wine data from GrapeMinds API, Wine-Searcher API, and Apify/Vivino scraping
2. **Retail Availability Layer** — scraped or API-sourced inventory data by store and zip code
3. **Recommendation Engine** — a Claude-powered conversational interface that combines both layers to match wines to user preferences

---

## Architecture Philosophy: Supabase-First

This app uses **Supabase as the unified backend platform** — replacing the separate PostgreSQL + Redis + custom auth stack with a single, integrated service. This reduces infrastructure complexity, eliminates auth build time, and cuts 3–4 weeks off the initial build.

**Why Supabase over the traditional stack:**
- PostgreSQL database with pgvector support — same DB, managed for you
- Built-in Row Level Security (RLS) — user data isolation without custom middleware
- Auth built-in — email/password, Google, Apple sign-in out of the box; no Clerk or Auth0 needed
- Realtime subscriptions — useful for live recommendation updates
- Edge Functions — serverless functions for scraper triggers and enrichment jobs
- Storage — for wine label images and assets
- Free tier covers up to 500MB DB + 50K MAUs; Pro tier at $25/month for production

**What still runs separately:**
- FastAPI backend (thin API layer for complex logic, scraping orchestration, Claude API calls)
- Playwright scrapers (run on EC2 or as scheduled jobs)
- Anthropic Claude API

---

## Phase 1: Project Structure & Tech Stack

Scaffold a full-stack application with the following structure:

```
wine-app/
├── backend/
│   ├── api/               # FastAPI REST endpoints (thin layer over Supabase)
│   ├── scrapers/          # Playwright web scraping modules
│   ├── enrichment/        # GrapeMinds, Wine-Searcher, Apify integrations
│   └── recommender/       # Candidate scoring + Claude API integration
├── frontend/
│   ├── components/        # React components
│   ├── pages/             # App pages (home, chat, wine detail, profile)
│   └── hooks/             # Supabase client hooks + custom API hooks
├── supabase/
│   ├── migrations/        # SQL migration files (tracked in version control)
│   ├── functions/         # Supabase Edge Functions (scraper triggers, enrichment)
│   └── seed.sql           # Seed script for local dev
├── data/
│   └── seed/              # Sample CSV data (Fair_Oaks_Stores_Analysis.csv)
└── docker-compose.yml     # Local Supabase instance + FastAPI
```

**Full tech stack:**
- **Database + Auth + Realtime**: Supabase (PostgreSQL 15 + pgvector + Supabase Auth)
- **Backend API**: Python (FastAPI) — handles scraping orchestration, enrichment pipeline, Claude API calls
- **Frontend**: React + Tailwind CSS + Supabase JS client (`@supabase/supabase-js`)
- **Scraping**: Playwright (JS-rendered pages; runs on EC2 t4g.small)
- **Async jobs**: Supabase Edge Functions + pg_cron (replaces Celery + Redis entirely)
- **AI Layer**: Anthropic Claude API (`claude-sonnet-4-20250514`)
- **Email**: Supabase Auth handles transactional auth emails; Resend for recommendation digests
- **Local dev**: Supabase CLI (`supabase start`) spins up a full local Supabase instance

**Environment variables needed (.env):**
```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
ANTHROPIC_API_KEY=
GRAPEMINDS_API_KEY=
WINE_SEARCHER_API_KEY=
APIFY_API_KEY=
RESEND_API_KEY=
```

---

## Phase 2: Supabase Schema & Auth Setup

### 2a. Authentication Setup

Configure Supabase Auth in the dashboard:
- Enable email/password sign-up
- Enable Google OAuth (for frictionless onboarding)
- Enable Apple OAuth (required for iOS App Store compliance)
- Set redirect URLs for local dev (`http://localhost:3000`) and production
- Configure email templates for welcome and password reset

Auth is handled entirely by Supabase — no custom auth endpoints needed. In the React frontend, use `@supabase/auth-ui-react` for pre-built sign-in/sign-up components.

### 2b. Database Tables

All tables use UUID primary keys. Enable RLS on all user-facing tables.

```sql
-- Core wine catalog
CREATE TABLE wines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  upc TEXT UNIQUE,
  name TEXT NOT NULL,
  brand TEXT,
  varietal TEXT,
  region TEXT,
  sub_region TEXT,
  country TEXT,
  vintage_year INTEGER,
  bottle_size TEXT DEFAULT '750ml',
  wine_type TEXT CHECK (wine_type IN ('red','white','rosé','sparkling','dessert','fortified')),
  avg_price NUMERIC(8,2),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enriched wine knowledge (from GrapeMinds, Wine-Searcher, Apify/Vivino)
CREATE TABLE wine_details (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id UUID REFERENCES wines(id) ON DELETE CASCADE,
  grapeminds_id TEXT,
  vivino_id TEXT,
  wine_searcher_lwin TEXT,
  description TEXT,
  tasting_notes TEXT,
  flavor_profile JSONB DEFAULT '[]',     -- ["dark cherry","tobacco","graphite"]
  structure_profile JSONB DEFAULT '{}',  -- {body:4,tannin:4,acidity:3,finish:5} scale 1-5
  vintage_notes TEXT,
  critic_score NUMERIC(4,1),
  drinking_window_start INTEGER,
  drinking_window_end INTEGER,
  region_summary TEXT,
  soil_type TEXT,
  climate_notes TEXT,
  grape_variety_notes TEXT,
  source TEXT DEFAULT 'scraped',         -- 'grapeminds'|'wine_searcher'|'vivino'|'ai_generated'
  enriched_at TIMESTAMPTZ,
  source_url TEXT
);

-- Retail store inventory (scraped + seeded from CSV)
CREATE TABLE retail_inventory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id UUID REFERENCES wines(id) ON DELETE SET NULL,
  upc TEXT,
  retailer_name TEXT NOT NULL,
  store_id TEXT,
  store_name TEXT,
  address TEXT,
  city TEXT,
  state TEXT,
  zip_code TEXT,
  latitude NUMERIC(9,6),
  longitude NUMERIC(9,6),
  price NUMERIC(8,2),
  in_stock BOOLEAN DEFAULT TRUE,
  last_scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- User preference profiles (RLS: users see only their own rows)
CREATE TABLE user_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  budget_min NUMERIC(8,2) DEFAULT 10,
  budget_max NUMERIC(8,2) DEFAULT 50,
  preferred_styles JSONB DEFAULT '[]',   -- ["rich","layered","dark fruit"]
  excluded_styles JSONB DEFAULT '[]',    -- ["sweet","light bodied"]
  preferred_regions JSONB DEFAULT '[]',
  zip_code TEXT,
  knowledge_level TEXT DEFAULT 'enthusiast',
  willing_to_decant BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

-- Conversation + recommendation history (RLS: users see only their own rows)
CREATE TABLE recommendation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_history JSONB DEFAULT '[]',
  recommendations JSONB DEFAULT '[]',
  preference_snapshot JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Saved/favorited wines per user (RLS: users see only their own rows)
CREATE TABLE user_saved_wines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  wine_id UUID REFERENCES wines(id) ON DELETE CASCADE,
  notes TEXT,
  rating INTEGER CHECK (rating BETWEEN 1 AND 5),
  saved_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, wine_id)
);

-- Scraper run log (internal/admin only)
CREATE TABLE scraper_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_name TEXT,
  status TEXT CHECK (status IN ('running','success','failed')),
  records_updated INTEGER DEFAULT 0,
  error_message TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
```

### 2c. Row Level Security Policies

```sql
-- user_preferences: users can only read/write their own row
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own preferences"
  ON user_preferences FOR ALL
  USING (auth.uid() = user_id);

-- recommendation_sessions: users can only access their own sessions
ALTER TABLE recommendation_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own sessions"
  ON recommendation_sessions FOR ALL
  USING (auth.uid() = user_id);

-- user_saved_wines: users can only access their own saved wines
ALTER TABLE user_saved_wines ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own saved wines"
  ON user_saved_wines FOR ALL
  USING (auth.uid() = user_id);

-- wines, wine_details, retail_inventory: public read, service_role write
ALTER TABLE wines ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read wines" ON wines FOR SELECT USING (TRUE);

ALTER TABLE wine_details ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read wine_details" ON wine_details FOR SELECT USING (TRUE);

ALTER TABLE retail_inventory ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read inventory" ON retail_inventory FOR SELECT USING (TRUE);
```

### 2d. Indexes

```sql
-- Performance indexes for common query patterns
CREATE INDEX idx_wines_upc ON wines(upc);
CREATE INDEX idx_wines_region ON wines(region);
CREATE INDEX idx_wines_varietal ON wines(varietal);
CREATE INDEX idx_retail_inventory_zip ON retail_inventory(zip_code);
CREATE INDEX idx_retail_inventory_wine_id ON retail_inventory(wine_id);
CREATE INDEX idx_retail_inventory_retailer ON retail_inventory(retailer_name);
CREATE INDEX idx_wine_details_wine_id ON wine_details(wine_id);
CREATE INDEX idx_wine_details_flavor ON wine_details USING GIN(flavor_profile);
CREATE INDEX idx_wine_details_structure ON wine_details USING GIN(structure_profile);
CREATE INDEX idx_user_preferences_user ON user_preferences(user_id);
CREATE INDEX idx_recommendation_sessions_user ON recommendation_sessions(user_id);
```

---

## Phase 3: Seed Data

Build a seed script that ingests the provided H-E-B CSV into the database for local development. This eliminates the need to run live scrapers during development.

**Seed script: `supabase/seed.sql` or `backend/scripts/seed_from_csv.py`**

The CSV at `data/seed/Fair_Oaks_Stores_Analysis.csv` contains:
- `id_upc` → maps to `wines.upc` and `retail_inventory.upc`
- `cust_frndly1_des` + `cust_frndly2_des` → maps to `wines.name`
- `dsc_brand` → maps to `wines.brand`
- `dsc_coo` → maps to `wines.country`
- `dsc_sub_comm` → parse for `wines.region` and `wines.wine_type`
- `id_str`, `cust_frndly_nm`, `add_str`, `cd_zip` → maps to `retail_inventory` store fields
- `sz_item` → maps to `wines.bottle_size`
- `aip` → maps to `retail_inventory.price`
- `max_sales_date` → use as proxy for `retail_inventory.last_scraped_at`

The seed script should:
1. Parse and clean the CSV (handle nulls, normalize text casing)
2. Upsert into `wines` table on `upc` conflict
3. Upsert into `retail_inventory` on `(upc, store_id)` conflict
4. Log counts: "Seeded X wines, Y inventory records across Z stores"

Use Supabase service role key for the seed script (bypasses RLS).

---

## Phase 4: Wine Knowledge Enrichment Pipeline

Build an enrichment pipeline as FastAPI background tasks. Priority order: GrapeMinds first (richest knowledge data), Wine-Searcher second (vintage + pricing), Apify/Vivino third (flavor tags).

### 4a. GrapeMinds Integration (Primary)

```python
# backend/enrichment/grapeminds.py
# Docs: https://grapeminds.eu/developers
# Returns: wine description, tasting notes, grape variety, region, drinking window

async def enrich_from_grapeminds(wine_name: str, producer: str) -> WineDetails:
    # 1. Search endpoint: GET /wines?q={wine_name}&producer={producer}
    # 2. Extract: description, tasting_notes, flavor_profile, grape_variety_notes,
    #             region_summary, drinking_window_start/end
    # 3. Map to wine_details schema
    # 4. Upsert to Supabase wine_details table via service role client
```

### 4b. Wine-Searcher Integration (Vintage + Pricing)

```python
# backend/enrichment/wine_searcher.py
# Docs: https://www.wine-searcher.com/trade/api
# Returns: vintage data, critic scores, price benchmarks, store availability

async def enrich_from_wine_searcher(wine_name: str, vintage: int = None) -> WineDetails:
    # 1. Search by name + optional vintage
    # 2. Extract: critic_score (aggregated), vintage_notes, avg_price benchmark
    # 3. Merge into existing wine_details record (don't overwrite GrapeMinds data)
    # 4. Update wines.avg_price with Wine-Searcher benchmark
```

### 4c. Apify/Vivino Integration (Flavor Tags)

```python
# backend/enrichment/vivino_apify.py
# Apify actor: mrbridge/vivino-powerful-scraper
# Returns: community flavor tags with mention counts, structure profile

async def enrich_from_vivino(wine_name: str, producer: str) -> WineDetails:
    # 1. Trigger Apify actor run via API
    # 2. Poll for completion (Apify webhooks preferred)
    # 3. Extract: flavor_profile tags, structure_profile (body/acidity/tannin/sweetness)
    # 4. Merge flavor tags into wine_details.flavor_profile JSONB array
    # Note: tag as source='vivino'; cost ~$0.003/result
```

### 4d. Claude AI Fallback

```python
# backend/enrichment/claude_enrichment.py
# Used when GrapeMinds + Vivino return no results

async def enrich_from_claude(wine_name: str, varietal: str, region: str, vintage: int) -> WineDetails:
    # Prompt Claude to generate structured tasting profile
    # Request JSON output: {description, tasting_notes, flavor_profile[], structure_profile{}}
    # Tag as source='ai_generated' in wine_details
```

### 4e. Enrichment Orchestrator

```python
# backend/enrichment/orchestrator.py

async def enrich_wine(wine_id: str):
    # 1. Fetch wine from Supabase
    # 2. Try GrapeMinds → merge results
    # 3. Try Wine-Searcher → merge results
    # 4. If flavor_profile still empty → try Apify/Vivino
    # 5. If still empty → Claude fallback
    # 6. Upsert final wine_details to Supabase
    # 7. Update wines.updated_at
```

### 4f. Enrichment Trigger via Supabase Edge Function

Create a Supabase Edge Function (`supabase/functions/trigger-enrichment/index.ts`) that:
- Listens for new rows in `wines` table via Supabase webhook
- Calls the FastAPI `/api/enrich/{wine_id}` endpoint
- Can also be triggered manually via the admin dashboard

---

## Phase 5: Retail Availability Scrapers

Build scrapers as modular Python classes. All scrapers write directly to Supabase via the service role client.

```python
# backend/scrapers/base_scraper.py

class BaseScraper:
    supabase: Client  # Supabase service role client

    async def search_by_zip(self, zip_code: str) -> list[RetailInventoryItem]: ...
    async def search_by_wine(self, wine_name: str, zip_code: str) -> list[RetailInventoryItem]: ...
    async def upsert_inventory(self, items: list[RetailInventoryItem]) -> None:
        # Upsert to retail_inventory on conflict (upc, store_id)
        # Update last_scraped_at timestamp
```

### Target Retailers (Priority Order):

1. **Wine-Searcher API** — preferred over scraping; covers Total Wine + 38K other stores. Use API for store-level availability before building scrapers.
2. **H-E-B** (`heb.com`) — Texas primary; seed data already available from CSV
3. **Spec's Wines** (`specsonline.com`) — Texas critical; scrapable
4. **Total Wine & More** (`totalwine.com`) — largest national retailer
5. **Instacart API** — aggregates multiple retailers; evaluate for structured access

### Scraper Implementation Notes:
- Use Playwright with randomized delays (2–5s between requests)
- Respect `robots.txt` — check before each new domain
- Never bypass CAPTCHAs or authentication walls
- Cache results in Supabase; do not re-scrape wines enriched within 24 hours
- Log all runs to `scraper_runs` table with status, record counts, errors
- Schedule via `pg_cron` in Supabase (replaces Celery beat): run every 24–48 hours

---

## Phase 6: Recommendation Engine

The recommendation engine queries Supabase for candidate wines, scores them, and passes them to Claude for sommelier-quality narrative recommendations.

### 6a. User Preference Object

Collected via conversational UI and persisted to `user_preferences` table via Supabase JS client:

```json
{
  "budget": { "min": 15, "max": 50 },
  "zip_code": "78209",
  "wine_type": "red",
  "style_preferences": ["rich", "layered", "long finish", "dark fruit", "tobacco"],
  "avoid": ["light bodied", "sweet"],
  "regions_interested": ["Paso Robles", "Napa", "Argentina"],
  "drinking_window": "tonight",
  "willing_to_decant": true,
  "knowledge_level": "enthusiast"
}
```

### 6b. Candidate Retrieval (Supabase Query)

```python
# backend/recommender/candidate_retrieval.py

async def get_candidates(preferences: UserPreferences) -> list[WineCandidate]:
    # Query Supabase with supabase-py client
    # 1. Filter retail_inventory by zip_code (exact match first; expand radius if <5 results)
    # 2. Filter by price BETWEEN budget_min AND budget_max
    # 3. Join wines + wine_details
    # 4. Filter by wine_type if specified
    # 5. Score each candidate:
    #    - flavor_profile overlap with style_preferences (+2 per match)
    #    - excluded_styles penalty (-5 per match)
    #    - region bonus if in preferred_regions (+3)
    #    - in_stock bonus (+10; deprioritize out-of-stock)
    # 6. Return top 12-15 candidates sorted by score
```

### 6c. Claude Recommendation Prompt

```python
SOMMELIER_SYSTEM_PROMPT = """
You are an expert wine sommelier with deep knowledge of global wine regions, 
terroir, producer styles, and vintage history. Your role is to help users 
discover wines that match their specific preferences.

Rules:
- Recommend 3–5 wines from the provided candidate list only
- For each wine, explain specifically why it matches the user's stated preferences
  (reference flavor profile, structure, finish — be concrete, not generic)
- Mention the region and what makes it distinctive (climate, soil, grape character)
- Note the vintage if known and whether it is drinking well now
- Include store name, address, and price for each recommendation
- Be opinionated — if one wine clearly stands out, say so directly
- Do not lead with food pairings unless explicitly asked
- Write like a knowledgeable friend, not a textbook
- Use short paragraphs; avoid bullet-heavy lists
- Avoid vague descriptors without context ("great balance" means nothing — 
  balance of what? Between tannin and fruit? Acidity and richness?)
"""

async def get_recommendations(
    preferences: UserPreferences,
    candidates: list[WineCandidate],
    conversation_history: list[dict]
) -> str:
    # Build user message with preferences + candidate wine data as context
    # Pass full conversation_history for multi-turn support
    # Call Claude API with SOMMELIER_SYSTEM_PROMPT
    # Return narrative recommendation text
    # Save to recommendation_sessions via Supabase
```

### 6d. Conversation Persistence

All conversation turns are saved to `recommendation_sessions` in Supabase:
- On each user message: append to `conversation_history` JSONB array
- On each Claude response: append assistant turn + update `recommendations` JSONB
- Use Supabase Realtime to stream recommendation updates to the frontend
- Support follow-up questions by passing full history on each API call

---

## Phase 7: Frontend UI

Use `@supabase/supabase-js` and `@supabase/auth-ui-react` throughout. Never call the Supabase service role key from the frontend — use anon key only; RLS handles security.

### Auth Pages
- Sign up / Sign in using `<Auth>` component from `@supabase/auth-ui-react`
- Google and Apple OAuth buttons
- "Continue without account" option → creates anonymous session, prompts to save at end

### Home / Preference Capture
- Zip code input with store proximity selector (5 / 10 / 15 miles)
- Budget range slider ($10–$150)
- Style selector (visual card-based): "Bold & Tannic", "Rich & Layered", "Light & Elegant", "Earthy & Savory", "Bright & Fruity"
- Drinking occasion: Tonight / This Weekend / Cellaring
- If logged in: pre-populate from `user_preferences` table

### Chat / Recommendation Interface
- Split-panel layout (desktop): chat on left, wine cards on right
- Single-column stacked layout (mobile/PWA)
- Wine cards show: name, producer, region, vintage, price, store name + address, flavor tags, structure bars (body/tannin/acidity on 1–5 scale)
- "Find at another store" button → queries `retail_inventory` for same wine at other locations
- Thumbs up/down feedback → saved to `user_saved_wines` with implicit rating
- "Save this wine" button → upserts to `user_saved_wines` via Supabase JS client

### Wine Detail Page
- Full wine profile: tasting notes, region summary, grape variety notes, vintage context
- Structure profile visualization (radar or bar chart)
- Local availability table: store name, address, distance, price, in-stock status
- Related wines: query by same region + similar structure_profile

### User Profile Page
- Saved wines list (from `user_saved_wines`)
- Preference settings (edit `user_preferences`)
- Recommendation history (from `recommendation_sessions`)

### Admin Dashboard (service role only — not accessible to regular users)
- Scraper status table: retailer, last run time, records updated, success/fail
- Enrichment queue: wines pending enrichment, enrichment source breakdown
- Manual trigger buttons: "Run H-E-B scraper", "Enrich pending wines"
- Calls FastAPI admin endpoints (authenticated with service role key server-side)

---

## Phase 8: FastAPI Endpoints

The FastAPI layer handles operations that require server-side logic — scraping, enrichment orchestration, and Claude API calls. User data reads/writes go directly from frontend to Supabase where possible.

```
# Wine data (public)
GET  /api/wines/search              # Search by name/region/varietal
GET  /api/wines/{id}                # Wine detail + enrichment data
GET  /api/availability              # Local inventory by zip + wine_id

# Recommendations (authenticated via Supabase JWT)
POST /api/recommend                 # Get Claude recommendations; saves session to Supabase
POST /api/chat                      # Continue conversation; appends to existing session
GET  /api/sessions/{id}             # Fetch recommendation session history

# Enrichment + scraping (admin; authenticated via service role)
POST /api/enrich/{wine_id}          # Trigger enrichment pipeline for one wine
POST /api/enrich/batch              # Enrich all wines missing wine_details
POST /api/scrape/{retailer}         # Trigger scraper for specific retailer
GET  /api/admin/status              # Scraper runs + enrichment queue status
```

**Auth on FastAPI endpoints:** Validate Supabase JWT in Authorization header using `supabase.auth.get_user(token)`. No separate auth middleware needed.

---

## Development Notes & Constraints

**Supabase local dev:**
```bash
npx supabase start          # Starts local Supabase (DB + Auth + Studio)
npx supabase db push        # Apply migrations to local instance
npx supabase db seed        # Run seed.sql
npx supabase functions serve # Run Edge Functions locally
```

**Key constraints:**
- Never use the Supabase service role key in frontend code — anon key only
- All user data tables must have RLS enabled before going to production
- Scraper and enrichment jobs must use service role key (bypasses RLS intentionally)
- Use `.env.local` for all secrets; never hardcode or commit keys
- Playwright scrapers: max 1 request/second per domain; respect robots.txt; never bypass CAPTCHAs
- Tag all enrichment sources (`grapeminds`, `wine_searcher`, `vivino`, `ai_generated`) for data quality tracking
- Scraper failures log to `scraper_runs` table and fail gracefully; never crash the API

**Testing priorities:**
1. Candidate retrieval scoring logic (unit tests)
2. Enrichment pipeline merge logic (unit tests — ensure sources don't overwrite each other incorrectly)
3. RLS policies (integration tests — verify users cannot read other users' data)
4. Claude prompt output quality (manual review with real wine candidates)

**Cost awareness:**
- GrapeMinds: free tier for dev; upgrade to paid when enrichment volume exceeds free limits
- Wine-Searcher: 100 free calls/day for dev; budget ~$25–90/month in production
- Apify/Vivino: ~$0.003/result; only trigger for wines missing flavor_profile data
- Claude API: use prompt caching for the SOMMELIER_SYSTEM_PROMPT (saves ~54% on input costs)
- Supabase: free tier for dev; Pro ($25/month) for production

---

## Start Here (Phase 1 Task)

Begin by:
1. Initialize Supabase project (local via CLI + cloud project at supabase.com)
2. Run migrations to create all tables with RLS policies and indexes
3. Configure Supabase Auth (enable email + Google OAuth)
4. Build the CSV seed script and confirm seeded data is queryable
5. Scaffold the FastAPI backend with Supabase client configured
6. Expose a basic `GET /api/wines/search` endpoint that queries seeded data
7. Scaffold the React frontend with Supabase JS client and Auth UI component

Confirm each phase is complete and tests pass before moving to the next.