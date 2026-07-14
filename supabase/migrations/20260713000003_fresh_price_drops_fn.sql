-- Deals cut needs "latest change per (wine × store) is a fresh drop" — a
-- window query. Doing it client-side over postgrest fights the 1000-row page
-- cap (initial-insert rows crowd out real drops); one lag()/row_number() pass
-- over the delta-only log is exact and cheap on the existing
-- (store_ref, wine_id, recorded_at DESC) index.
CREATE OR REPLACE FUNCTION fresh_price_drops(store_ids uuid[], since timestamptz)
RETURNS TABLE (wine_id uuid, store_ref uuid, from_price numeric, to_price numeric, amount numeric, recorded_at timestamptz)
LANGUAGE sql STABLE AS $$
  WITH ranked AS (
    SELECT ph.wine_id, ph.store_ref, ph.price, ph.recorded_at,
           lag(ph.price) OVER (PARTITION BY ph.wine_id, ph.store_ref ORDER BY ph.recorded_at) AS prev_price,
           row_number() OVER (PARTITION BY ph.wine_id, ph.store_ref ORDER BY ph.recorded_at DESC) AS rn
    FROM price_history ph
    WHERE ph.store_ref = ANY(store_ids) AND ph.wine_id IS NOT NULL AND ph.price IS NOT NULL
  )
  SELECT ranked.wine_id, ranked.store_ref, ranked.prev_price, ranked.price,
         round(ranked.prev_price - ranked.price, 2), ranked.recorded_at
  FROM ranked
  WHERE ranked.rn = 1
    AND ranked.recorded_at >= since
    AND ranked.prev_price IS NOT NULL
    AND ranked.price < ranked.prev_price
$$;

GRANT EXECUTE ON FUNCTION fresh_price_drops(uuid[], timestamptz) TO anon, authenticated;
