-- Price history — append-only log of price changes per (wine × store).
--
-- Scrapers do a FULL-REFRESH upsert into retail_inventory (on_conflict
-- upc,store_ref), overwriting price in place — so the previous price is
-- otherwise lost every run. Price alerts + price trends need "new vs old",
-- and history cannot be reconstructed retroactively. This table (fed by a
-- trigger on retail_inventory) captures the deltas without touching the
-- scrapers. Phase 1 of price alerts: capture now, build the alert UX after
-- user accounts exist.

CREATE TABLE IF NOT EXISTS price_history (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wine_id        UUID REFERENCES wines(id)  ON DELETE CASCADE,
    store_ref      UUID REFERENCES stores(id) ON DELETE CASCADE,
    upc            TEXT,
    price          NUMERIC(8,2),
    curbside_price NUMERIC(8,2),
    in_stock       BOOLEAN,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_history_wine  ON price_history (wine_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_price_history_store ON price_history (store_ref, wine_id, recorded_at DESC);

-- Trigger: log the initial price on insert, and any price/curbside change after.
-- Delta-only — a no-change re-scrape upsert (price IS NOT DISTINCT) writes
-- nothing, so most of the ~33k weekly rows never hit this table.
-- SECURITY DEFINER so the insert always succeeds regardless of the writer's RLS.
CREATE OR REPLACE FUNCTION log_price_change() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF (TG_OP = 'INSERT')
     OR (NEW.price          IS DISTINCT FROM OLD.price)
     OR (NEW.curbside_price IS DISTINCT FROM OLD.curbside_price) THEN
    INSERT INTO price_history (wine_id, store_ref, upc, price, curbside_price, in_stock)
    VALUES (NEW.wine_id, NEW.store_ref, NEW.upc, NEW.price, NEW.curbside_price, NEW.in_stock);
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_price_history ON retail_inventory;
CREATE TRIGGER trg_price_history
  AFTER INSERT OR UPDATE ON retail_inventory
  FOR EACH ROW EXECUTE FUNCTION log_price_change();

-- One-time baseline: snapshot every current price so history has a starting
-- point for wines already in retail_inventory (their rows already exist, so the
-- trigger would not otherwise log them until their next change).
INSERT INTO price_history (wine_id, store_ref, upc, price, curbside_price, in_stock, recorded_at)
SELECT wine_id, store_ref, upc, price, curbside_price, in_stock, COALESCE(last_scraped_at, NOW())
FROM retail_inventory
WHERE price IS NOT NULL;

-- RLS + grants: scraper writes via the trigger (service_role); app reads later.
ALTER TABLE price_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role full access on price_history" ON price_history
  FOR ALL TO service_role USING (true) WITH CHECK (true);
GRANT ALL ON price_history TO service_role;
GRANT SELECT ON price_history TO anon;
