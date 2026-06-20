-- Product image URL captured by scrapers (Spec's CDN, Shopify CDN).
-- Hotlinked reference; self-hosting deferred until/unless links break.
ALTER TABLE wines ADD COLUMN IF NOT EXISTS image_url TEXT;
