-- Cellar (Phase 2 of user accounts) — a user's physical wine inventory.
--
-- Unlike favorites (a pointer to a catalog wine), cellar bottles are often
-- bought elsewhere and aren't in our catalog. So wine_id is NULLABLE and the
-- bottle stands on its own via denormalized name/vintage/region; wine_id links
-- to a catalog wine when there is one (for the dossier link + snapshot). RLS
-- scopes every row to its owner. See docs/user-accounts-roadmap.md.

CREATE TABLE IF NOT EXISTS cellar (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    wine_id       UUID REFERENCES wines(id) ON DELETE SET NULL,   -- nullable; entry survives if catalog wine is removed
    name          TEXT NOT NULL,
    vintage       INT,
    region        TEXT,
    quantity      INT NOT NULL DEFAULT 1,
    purchase_date DATE,
    price_paid    NUMERIC(8,2),
    drink_from    INT,                          -- drinking-window start year
    drink_to      INT,                          -- drinking-window end year
    status        TEXT NOT NULL DEFAULT 'owned', -- owned | consumed
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cellar_user ON cellar (user_id, created_at DESC);

ALTER TABLE cellar ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own cellar" ON cellar
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
GRANT ALL ON cellar TO authenticated;
GRANT ALL ON cellar TO service_role;
