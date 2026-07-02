-- Vivino enrichment fields on wines.
-- vivino_wine_id is Vivino's internal ID, resolved once via HTML name search;
-- later refreshes skip the search step. match_score records slug-similarity
-- confidence for auditing match quality.
ALTER TABLE wines
  ADD COLUMN IF NOT EXISTS vivino_wine_id BIGINT,
  ADD COLUMN IF NOT EXISTS vivino_rating REAL,
  ADD COLUMN IF NOT EXISTS vivino_ratings_count INTEGER,
  ADD COLUMN IF NOT EXISTS vivino_match_score REAL,
  ADD COLUMN IF NOT EXISTS vivino_enriched_at TIMESTAMPTZ;
