-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ── wines ────────────────────────────────────────────────────────────────────
CREATE TABLE wines (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  upc          TEXT UNIQUE,
  name         TEXT NOT NULL,
  brand        TEXT,
  varietal     TEXT,
  region       TEXT,
  sub_region   TEXT,
  country      TEXT,
  vintage_year INTEGER,
  bottle_size  TEXT DEFAULT '750ml',
  wine_type    TEXT CHECK (wine_type IN ('red','white','rosé','sparkling','dessert','fortified')),
  avg_price    NUMERIC(8,2),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── wine_details ─────────────────────────────────────────────────────────────
-- structure_profile uses GrapeMinds native 1-10 scale:
-- {sweetness, acidity, tannins, alcohol, body, finish}
CREATE TABLE wine_details (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id                  UUID REFERENCES wines(id) ON DELETE CASCADE,
  grapeminds_id            TEXT,
  vivino_id                TEXT,
  wine_searcher_lwin       TEXT,
  description              TEXT,
  description_long         TEXT,
  tasting_notes            TEXT,
  tasting_notes_long       TEXT,
  pairing                  TEXT,
  pairing_long             TEXT,
  flavor_profile           JSONB DEFAULT '[]',
  structure_profile        JSONB DEFAULT '{}',
  vintage_notes            TEXT,
  critic_score             NUMERIC(4,1),
  drinking_window_start    INTEGER,
  drinking_window_end      INTEGER,
  drinking_window_young    TEXT,
  drinking_window_ripe     TEXT,
  drinking_window_storage  TEXT,
  region_summary           TEXT,
  soil_type                TEXT,
  climate_notes            TEXT,
  grape_variety_notes      TEXT,
  source                   TEXT DEFAULT 'pending',
  grapeminds_enriched_at   TIMESTAMPTZ,
  enriched_at              TIMESTAMPTZ,
  source_url               TEXT,
  UNIQUE(wine_id)
);

-- ── retail_inventory ─────────────────────────────────────────────────────────
CREATE TABLE retail_inventory (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id         UUID REFERENCES wines(id) ON DELETE SET NULL,
  upc             TEXT,
  retailer_name   TEXT NOT NULL,
  store_id        TEXT,
  store_name      TEXT,
  address         TEXT,
  city            TEXT,
  state           TEXT,
  zip_code        TEXT,
  latitude        NUMERIC(9,6),
  longitude       NUMERIC(9,6),
  price           NUMERIC(8,2),
  in_stock        BOOLEAN DEFAULT TRUE,
  last_scraped_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(upc, store_id)
);

-- ── user_preferences ─────────────────────────────────────────────────────────
CREATE TABLE user_preferences (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  budget_min        NUMERIC(8,2) DEFAULT 10,
  budget_max        NUMERIC(8,2) DEFAULT 50,
  preferred_styles  JSONB DEFAULT '[]',
  excluded_styles   JSONB DEFAULT '[]',
  preferred_regions JSONB DEFAULT '[]',
  zip_code          TEXT,
  knowledge_level   TEXT DEFAULT 'enthusiast',
  willing_to_decant BOOLEAN DEFAULT TRUE,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

-- ── recommendation_sessions ──────────────────────────────────────────────────
CREATE TABLE recommendation_sessions (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_history JSONB DEFAULT '[]',
  recommendations      JSONB DEFAULT '[]',
  preference_snapshot  JSONB,
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ── user_saved_wines ─────────────────────────────────────────────────────────
CREATE TABLE user_saved_wines (
  id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id  UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  wine_id  UUID REFERENCES wines(id) ON DELETE CASCADE,
  notes    TEXT,
  rating   INTEGER CHECK (rating BETWEEN 1 AND 5),
  saved_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, wine_id)
);

-- ── scraper_runs ─────────────────────────────────────────────────────────────
CREATE TABLE scraper_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_name   TEXT,
  status          TEXT CHECK (status IN ('running','success','failed')),
  records_updated INTEGER DEFAULT 0,
  error_message   TEXT,
  started_at      TIMESTAMPTZ DEFAULT NOW(),
  completed_at    TIMESTAMPTZ
);

-- ── indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX idx_wines_upc         ON wines(upc);
CREATE INDEX idx_wines_region      ON wines(region);
CREATE INDEX idx_wines_varietal    ON wines(varietal);
CREATE INDEX idx_inv_zip           ON retail_inventory(zip_code);
CREATE INDEX idx_inv_wine_id       ON retail_inventory(wine_id);
CREATE INDEX idx_inv_retailer      ON retail_inventory(retailer_name);
CREATE INDEX idx_details_wine_id   ON wine_details(wine_id);
CREATE INDEX idx_details_flavor    ON wine_details USING GIN(flavor_profile);
CREATE INDEX idx_details_structure ON wine_details USING GIN(structure_profile);
CREATE INDEX idx_prefs_user        ON user_preferences(user_id);
CREATE INDEX idx_sessions_user     ON recommendation_sessions(user_id);

-- ── row level security ───────────────────────────────────────────────────────
ALTER TABLE user_preferences        ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_saved_wines        ENABLE ROW LEVEL SECURITY;
ALTER TABLE wines                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE wine_details            ENABLE ROW LEVEL SECURITY;
ALTER TABLE retail_inventory        ENABLE ROW LEVEL SECURITY;

-- Public read on catalog tables (service_role bypasses RLS for writes)
CREATE POLICY "Public read wines"     ON wines            FOR SELECT USING (TRUE);
CREATE POLICY "Public read details"   ON wine_details     FOR SELECT USING (TRUE);
CREATE POLICY "Public read inventory" ON retail_inventory FOR SELECT USING (TRUE);

-- Users manage only their own rows
CREATE POLICY "Own preferences"
  ON user_preferences FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Own sessions"
  ON recommendation_sessions FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Own saved wines"
  ON user_saved_wines FOR ALL USING (auth.uid() = user_id);
