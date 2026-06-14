-- One-to-many GrapeMinds candidate matches per wine (top 3 by confidence).
CREATE TABLE wine_grapeminds_matches (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wine_id       UUID NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
  grapeminds_id TEXT NOT NULL,
  display_name  TEXT,
  producer_name TEXT,
  color         TEXT,
  confidence    NUMERIC(4,3),
  rank          INTEGER,
  is_primary    BOOLEAN DEFAULT FALSE,
  matched_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (wine_id, grapeminds_id)
);

CREATE INDEX idx_gm_matches_wine    ON wine_grapeminds_matches(wine_id);
CREATE INDEX idx_gm_matches_primary ON wine_grapeminds_matches(wine_id) WHERE is_primary;

ALTER TABLE wine_grapeminds_matches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read gm matches" ON wine_grapeminds_matches FOR SELECT USING (TRUE);
GRANT SELECT ON wine_grapeminds_matches TO anon, authenticated;
GRANT ALL    ON wine_grapeminds_matches TO service_role;

-- Confidence of the primary match, denormalized for easy recommender reads.
ALTER TABLE wine_details ADD COLUMN IF NOT EXISTS match_confidence NUMERIC(4,3);
