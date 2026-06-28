-- Replace partial unique index with a full unique constraint so PostgREST
-- ON CONFLICT (upc_canonical) works in scraper upserts.
-- PostgreSQL unique constraints allow multiple NULLs, so wines without a
-- barcode (upc_canonical IS NULL) are unaffected.

DROP INDEX IF EXISTS idx_wines_upc_canonical;

ALTER TABLE wines
  ADD CONSTRAINT wines_upc_canonical_unique UNIQUE (upc_canonical);
