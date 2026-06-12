-- HEB exposes two price contexts per item: ONLINE (in-store shelf/sale price, lower)
-- and CURBSIDE (curbside pickup + delivery price, ~4% higher). retail_inventory.price
-- holds the canonical in-store price; this column keeps the curbside price alongside it.
ALTER TABLE retail_inventory ADD COLUMN IF NOT EXISTS curbside_price NUMERIC(8,2);
