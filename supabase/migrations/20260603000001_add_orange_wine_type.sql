-- Add 'orange' to the wines.wine_type enum and fix vermouth/other types
ALTER TABLE wines DROP CONSTRAINT wines_wine_type_check;
ALTER TABLE wines ADD CONSTRAINT wines_wine_type_check
  CHECK (wine_type IN ('red','white','rosé','sparkling','dessert','fortified','orange'));
