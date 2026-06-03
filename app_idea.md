# Claude Code Prompt: Wine Recommendation App — Foundational Build

## Project Overview

Build a foundational wine recommendation application that combines local retail availability with rich wine knowledge to deliver personalized recommendations based on user preference, budget, and location.

The app has three core pillars:
1. **Wine Knowledge Layer** — enriched wine data from external APIs and databases (Vivino, Wine Folly, etc.)
2. **Retail Availability Layer** — scraped or API-sourced inventory data by store and zip code
3. **Recommendation Engine** — a Claude-powered conversational interface that combines both layers to match wines to user preferences

---

## Phase 1: Project Structure & Tech Stack

Scaffold a full-stack application with the following structure:

```
wine-app/
├── backend/
│   ├── api/               # FastAPI or Express REST endpoints
│   ├── scrapers/          # Web scraping modules (Selenium/Playwright)
│   ├── enrichment/        # Wine knowledge API integrations
│   ├── db/                # Database models and migrations
│   └── recommender/       # Recommendation logic and Claude API integration
├── frontend/
│   ├── components/        # React components
│   ├── pages/             # App pages (search, recommendations, wine detail)
│   └── hooks/             # Custom hooks for API calls
├── data/
│   └── seed/              # Sample CSV data (provided) for local dev
└── docker-compose.yml
```

**Preferred stack:**
- Backend: Python (FastAPI) with SQLAlchemy ORM
- Database: PostgreSQL with pgvector extension (for future embedding-based similarity search)
- Frontend: React + Tailwind CSS
- Scraping: Playwright (handles JS-rendered pages better than BeautifulSoup)
- Task Queue: Celery + Redis (for async scraping jobs)
- AI Layer: Anthropic Claude API (claude-sonnet-4-20250514)

---

## Phase 2: Database Schema

Create the following core tables:

### `wines`
- id, upc, name, producer/brand, varietal, region, sub_region, country
- vintage_year, bottle_size, wine_type (red/white/rosé/sparkling/dessert)
- avg_price, created_at, updated_at

### `wine_details` (enriched from external sources)
- wine_id (FK), vivino_id, winc_id, or other external IDs
- description, tasting_notes, flavor_profile (JSON array: e.g. ["dark cherry", "tobacco", "graphite"])
- structure_profile (JSON: body, tannin, acidity, finish_length)
- vintage_notes, critic_score, source_url
- region_summary, soil_type, climate_notes

### `retail_inventory`
- id, wine_id (FK), retailer_name, store_id, store_name
- address, city, state, zip_code, latitude, longitude
- price, in_stock, last_scraped_at

### `user_preferences`
- id, session_id or user_id
- budget_min, budget_max, preferred_styles (JSON), excluded_styles (JSON)
- preferred_regions (JSON), zip_code, created_at

### `recommendation_sessions`
- id, user_id/session_id, conversation_history (JSON), recommendations (JSON), created_at

---

## Phase 3: Wine Knowledge Enrichment

Build an enrichment pipeline that pulls wine data from external sources and populates `wine_details`. Implement the following integrations:

### 3a. Vivino (Web Scraping)
- Target: `https://www.vivino.com/search/wines?q={wine_name}`
- Extract: wine ratings, tasting notes, flavor profile tags, critic scores, vintage notes
- Use Playwright to handle dynamic content loading
- Implement polite scraping: randomized delays (2–5s), respect robots.txt, cache results in DB to avoid repeat scraping
- Store raw JSON response alongside parsed fields for debugging

### 3b. Wine Folly (Content API or Scraping)
- Target wine region profiles, grape variety guides
- Extract: region description, soil/climate notes, grape characteristics, style descriptors
- Map extracted data to `wine_details.region_summary` and `structure_profile`
- Wine Folly has structured content — parse their region and grape pages to build a regional knowledge base

### 3c. Fallback: OpenAI/Claude Enrichment
- For wines not found in Vivino or Wine Folly, use the Claude API with a structured prompt to generate:
  - Tasting note profile based on varietal + region + vintage
  - Structure profile (body, tannin, acidity)
  - Regional context
- Tag these records as `source: "ai_generated"` vs `source: "scraped"` for transparency

### 3d. Enrichment Trigger
- On new wine ingestion: automatically queue enrichment job via Celery
- Expose a manual `/api/enrich/{wine_id}` endpoint for on-demand enrichment
- Build a simple admin dashboard page showing enrichment status per wine

---

## Phase 4: Retail Availability Scraper

Build scrapers for the following retailers, structured as modular, swappable classes with a shared `BaseScraper` interface:

```python
class BaseScraper:
    def search_by_zip(self, zip_code: str) -> list[RetailInventoryItem]
    def search_by_wine(self, wine_name: str, zip_code: str) -> list[RetailInventoryItem]
    def get_store_inventory(self, store_id: str) -> list[RetailInventoryItem]
```

### Target Retailers (Priority Order):
1. **Total Wine & More** (`totalwine.com`) — largest US wine retailer, good structured data
2. **H-E-B / Central Market** (`heb.com`) — key for Texas market (we have sample data already)
3. **BevMo** (`bevmo.com`)
4. **Spec's Wines** (`specsonline.com`) — critical for Texas
5. **Instacart API** — aggregates across multiple retailers, may offer structured access

### Scraper Requirements:
- Accept zip code as primary filter for store proximity
- Extract: wine name, UPC/SKU, price, store name, store address, in-stock status
- Store results in `retail_inventory` with `last_scraped_at` timestamp
- Implement retry logic and error handling per retailer
- Schedule refresh: run scrapers every 24–48 hours via Celery beat

### Seed Data:
A sample CSV is available at `data/seed/Fair_Oaks_Stores_Analysis.csv`. Use this to:
- Seed the `retail_inventory` table for local development
- Use as the reference schema for what scraped data should look like
- The CSV contains: UPC, product name, brand, country, sub-category, store ID, store name, address, zip code, bottle size, item count, avg price, last sale date, rank

---

## Phase 5: Recommendation Engine

Build a Claude-powered recommendation engine that synthesizes wine knowledge and local availability into personalized suggestions.

### 5a. Preference Collection
Build a structured preference object collected via conversational UI:

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

### 5b. Candidate Retrieval
Given user preferences, query the DB for candidate wines:
- Filter `retail_inventory` by zip_code proximity (within 15 miles) and price range
- Join with `wine_details` to get flavor/structure profiles
- Score candidates using a simple weighted match against style_preferences
- Return top 10–15 candidates to pass to Claude

### 5c. Claude Recommendation Prompt
Pass candidates + user preferences to Claude with the following system prompt:

```
You are an expert wine sommelier. Given the user's preferences and a list of wines 
currently available at stores near them, recommend 3–5 wines with substantive 
explanations. For each wine:
- Explain why it matches their stated preferences (be specific about flavor, structure, finish)
- Mention the region and what makes it distinctive
- Note the vintage if known and whether it's drinking well now
- Include the store name, address, and price
- Be opinionated — if one wine clearly stands out, say so

Do not lead with food pairings. Write like a knowledgeable friend, not a textbook.
Use short paragraphs. Avoid vague descriptors without context.
```

### 5d. Conversational Interface
- Build a chat UI component that maintains conversation history
- Support follow-up questions: "anything from Burgundy?", "what about under $30?"
- Pass full conversation history to Claude on each turn for context continuity
- Show wine cards alongside conversation (name, store, price, flavor tags)

---

## Phase 6: Frontend UI

Build the following pages/components:

### Home / Preference Capture
- Zip code input with store proximity selector
- Budget slider
- Style selector (visual card-based: "Bold & Tannic", "Light & Elegant", "Earthy & Savory", etc.)
- Drinking occasion: Tonight / Weekend / Cellar

### Chat / Recommendation Interface
- Split-panel layout: chat on left, wine cards on right
- Wine cards show: name, producer, region, price, store, flavor tags, structure indicators (body/tannin/acidity bars)
- "Find at another store" button per wine card
- Thumbs up/down feedback per recommendation

### Wine Detail Page
- Full wine profile: region map, tasting notes, vintage history, structure profile
- Local availability table (store name, address, price, distance)
- Related wines (same region, similar style)

### Admin / Scraper Dashboard (internal)
- Scraper status per retailer (last run, success rate, records updated)
- Enrichment queue status
- Ability to manually trigger scrape or enrich jobs

---

## Phase 7: API Endpoints

Expose the following REST endpoints:

```
POST /api/preferences          # Save user preference session
GET  /api/wines/search         # Search wines by name/region/varietal
GET  /api/wines/{id}           # Get wine detail with enrichment
GET  /api/availability         # Get local availability by zip + wine_id
POST /api/recommend            # Get Claude-powered recommendations
POST /api/chat                 # Continue recommendation conversation
POST /api/scrape/trigger       # Manually trigger scraper (admin)
POST /api/enrich/{wine_id}     # Manually trigger enrichment (admin)
GET  /api/admin/status         # Scraper and enrichment status
```

---

## Development Notes & Constraints

- **Scraping ethics**: implement rate limiting, caching, and respect robots.txt on all scrapers. Where a retailer offers a public API or data partnership, prefer that over scraping.
- **API keys needed**: Anthropic API key (Claude), and optionally Vivino API access if available
- **Local dev**: use the seed CSV to avoid hitting scrapers during development
- **Environment**: use `.env` for all secrets, never hardcode keys
- **Testing**: write unit tests for the candidate retrieval scoring logic and enrichment parsers
- **Error handling**: all scraper and enrichment failures should fail gracefully and log to a `scrape_errors` table

---

## Start Here (Phase 1 Task)

Begin by:
1. Scaffolding the project structure above
2. Setting up Docker Compose with PostgreSQL + Redis
3. Creating the database schema with SQLAlchemy models
4. Building a seed script that ingests the provided CSV into `wines` and `retail_inventory`
5. Exposing a basic `/api/wines/search` endpoint that queries the seeded data

Confirm each phase before moving to the next.