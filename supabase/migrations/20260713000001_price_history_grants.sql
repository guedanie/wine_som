-- price_history is public pricing data (it powers the dossier price-context
-- module and the deals cut), but it was created without read grants — anon
-- silently saw 0 rows, so the Phase A price context rendered steady-only in
-- prod. Same catalog-read class as wines/retail_inventory.
GRANT SELECT ON price_history TO anon, authenticated;
