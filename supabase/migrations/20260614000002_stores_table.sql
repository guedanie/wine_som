-- One row per physical store; metadata lives here once instead of on every inventory row.
CREATE TABLE stores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  retailer_name TEXT NOT NULL,
  store_id      TEXT NOT NULL,
  name          TEXT,
  address       TEXT,
  city          TEXT,
  state         TEXT,
  zip_code      TEXT,
  latitude      NUMERIC(9,6),
  longitude     NUMERIC(9,6),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (retailer_name, store_id)
);
CREATE INDEX idx_stores_zip ON stores(zip_code);

ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read stores" ON stores FOR SELECT USING (TRUE);
GRANT SELECT ON stores TO anon, authenticated;
GRANT ALL    ON stores TO service_role;

-- FK column on inventory (nullable during backfill)
ALTER TABLE retail_inventory ADD COLUMN store_ref UUID REFERENCES stores(id) ON DELETE CASCADE;

-- Seed stores from existing inventory (one row per retailer+store_id)
INSERT INTO stores (retailer_name, store_id, name, address, city, state, zip_code, latitude, longitude)
SELECT DISTINCT ON (retailer_name, store_id)
       retailer_name, store_id, store_name, address, city, state, zip_code, latitude, longitude
FROM retail_inventory
WHERE store_id IS NOT NULL
ORDER BY retailer_name, store_id;

-- Link every inventory row to its store
UPDATE retail_inventory ri SET store_ref = s.id
FROM stores s
WHERE ri.retailer_name = s.retailer_name AND ri.store_id = s.store_id;

-- GUARD: fails (and rolls back the whole migration) if any row failed to link
ALTER TABLE retail_inventory ALTER COLUMN store_ref SET NOT NULL;

-- Drop denormalized columns (also drops the old UNIQUE(upc, store_id))
ALTER TABLE retail_inventory
  DROP COLUMN retailer_name, DROP COLUMN store_id, DROP COLUMN store_name,
  DROP COLUMN address, DROP COLUMN city, DROP COLUMN state, DROP COLUMN zip_code,
  DROP COLUMN latitude, DROP COLUMN longitude;

-- New uniqueness: one inventory row per wine per store
ALTER TABLE retail_inventory ADD CONSTRAINT uq_inv_upc_store UNIQUE (upc, store_ref);
