-- Stores thumbs up/down votes on wine cards and sommelier messages.
-- One row per (session_id, entity_id, type) — upserted on every vote change.
CREATE TABLE feedback (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  type        TEXT        NOT NULL CHECK (type IN ('wine_card', 'sommelier_message')),
  entity_id   TEXT        NOT NULL,
  vote        TEXT        CHECK (vote IN ('up', 'down')),
  session_id  TEXT        NOT NULL,
  user_id     TEXT,
  zip         TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, entity_id, type)
);

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role full access on feedback" ON feedback
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT ALL ON feedback TO service_role;
