-- price_watches: bottles a signed-in user watches for price drops (price
-- intelligence Phase D — the watch affordance ships now, the notifier later).
-- Same RLS shape as favorites/cellar: rows are scoped to their owner and
-- written directly via supabase-js — no backend endpoint. service_role keeps
-- full access for the future notifier (join watches × fresh_price_drops).
CREATE TABLE IF NOT EXISTS price_watches (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    wine_id    UUID NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, wine_id)
);
CREATE INDEX IF NOT EXISTS idx_price_watches_user ON price_watches (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_price_watches_wine ON price_watches (wine_id);

ALTER TABLE price_watches ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own price watches" ON price_watches
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
GRANT ALL ON price_watches TO authenticated;
GRANT ALL ON price_watches TO service_role;
