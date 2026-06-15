-- Structured fields extracted by the Haiku fact-extraction job.
ALTER TABLE wines ADD COLUMN IF NOT EXISTS grapes JSONB DEFAULT '[]';  -- full blend, e.g. ["Cabernet Sauvignon","Merlot"]
ALTER TABLE wines ADD COLUMN IF NOT EXISTS abv   NUMERIC(4,1);          -- e.g. 13.9
ALTER TABLE wines ADD COLUMN IF NOT EXISTS body  TEXT;                  -- 'light' | 'medium' | 'full'
