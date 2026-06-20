-- Canonical 11-digit UPC core for cross-retailer dedup (HEB full UPC-A vs Spec's
-- zero-padded core normalize to the same value). The UNIQUE index is added by the
-- merge script (backend/scripts/merge_duplicate_wines.py) AFTER existing duplicates
-- are merged — creating it here would fail against current duplicate rows.
ALTER TABLE wines ADD COLUMN IF NOT EXISTS upc_canonical TEXT;
