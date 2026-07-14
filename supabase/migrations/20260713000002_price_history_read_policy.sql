-- The GRANT alone wasn't enough: RLS is enabled on price_history with no
-- SELECT policy, so anon/authenticated still saw 0 rows (silently). It's
-- public pricing data — permissive read policy, same class as the catalog
-- tables. Writes stay trigger-only (SECURITY DEFINER log_price_change).
ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS price_history_public_read ON price_history;
CREATE POLICY price_history_public_read ON price_history
  FOR SELECT TO anon, authenticated USING (true);
