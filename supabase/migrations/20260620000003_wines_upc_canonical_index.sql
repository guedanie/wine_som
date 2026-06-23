-- Enforce one wine row per canonical UPC. Added AFTER the merge script
-- (backend/scripts/merge_duplicate_wines.py) has collapsed existing duplicates,
-- so the unique constraint holds. Partial index: synthetic/null canonicals are
-- exempt (Geraldine's natural wines have no barcode and never collide).
CREATE UNIQUE INDEX IF NOT EXISTS idx_wines_upc_canonical
  ON wines(upc_canonical) WHERE upc_canonical IS NOT NULL;
