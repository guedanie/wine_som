-- Item 32: soft-delete non-wine catalog noise. Nullable; NULL = active.
ALTER TABLE public.wines
    ADD COLUMN IF NOT EXISTS excluded_at timestamptz,
    ADD COLUMN IF NOT EXISTS exclusion_reason text;

COMMENT ON COLUMN public.wines.excluded_at IS
    'Set when a row is soft-deleted as non-wine (item 32). NULL = active wine.';
