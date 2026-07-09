# Future enhancement: product-family key (vintage-agnostic wine identity)

## The problem
Cross-retailer dedup merges wines by **canonical UPC**. But many wines ship a
**new UPC per vintage** (The Prisoner Red Blend: `…511` vs `…506`), so "same
wine, different vintage" becomes **separate `wines` rows**. Availability then
fragments across those rows — one row shows Spec's, a sibling shows H-E-B — even
though the wine is broadly stocked. Same issue for wines whose retailers use
different UPC encodings that don't normalize to one canonical UPC.

Diagnosed live (2026-07-08): "The Prisoner Red Blend" existed as 3+ rows; the
Spec's-only row hid the fact that H-E-B (incl. Lincoln Heights, in stock, $31.89)
carried it on a different row.

## Phase 1 — DONE (search-layer grouping)
`/api/search` now groups results by a vintage-agnostic normalized name
(`_group_key`), aggregating nearby availability across the vintage rows and
returning `retailers[]`. A search for The Prisoner now shows H-E-B + Spec's in
one result, linked to the best-stocked vintage. This fixes the **visible symptom
in search only** — the underlying rows are still separate, so the dossier,
recommendations, and region counts still see per-vintage fragments.

## Phase 2 — this doc (a real product-family identity)
Give wines a durable **`family_key`** (or `product_id`) = normalized
**producer + vintage-stripped name** (+ maybe size), so every vintage/UPC variant
of the same wine links together everywhere, not just in search.

### Approach
- Add `wines.family_key` (text, indexed). Backfill from producer/brand + a
  normalized, vintage-stripped name (reuse the `_group_key` logic, hardened:
  strip size/pack tokens like "750ml", "1.5L"; handle "California"/"Napa Valley"
  labeling suffixes carefully to avoid over-merging distinct bottlings).
- Scrapers set `family_key` on upsert (cheap — derived from name/brand).
- **Consumers read the family, not the row:**
  - Search: group by `family_key` (replaces the name heuristic).
  - Dossier: "also available as" — show all vintages + combined store availability.
  - Recommendations: dedup candidates by family so one wine doesn't appear as
    multiple vintage rows; aggregate ratings/structure across the family.
  - Region sub-region counts: count families, not rows.
- Keep vintage as a first-class attribute on each row (never blur it) — the
  family groups them; the vintage distinguishes them.

### Risks / care
- **Over-merging:** "The Prisoner Red Blend" vs "…California" vs "…On Premise
  Only" vs the Cabernet — these are genuinely different SKUs. The key must strip
  vintage but NOT collapse distinct bottlings. Needs a curated normalization +
  spot-checks (the same discipline as the flavor/region reference tables).
- **Natural wines** (synthetic `shopify-…` UPCs, no vintage in name) mostly
  don't have this problem; family_key still helps where producers reuse names.
- This is the "fuzzy name/producer/vintage matching" long noted as the
  GrapeMinds matching subsystem in the root CLAUDE.md.

### Rough sequence
1. `family_key` column + backfill script (idempotent, `--dry-run`), spot-check
   against known multi-vintage wines (The Prisoner, Caymus, Meiomi, etc.).
2. Scrapers populate it on upsert.
3. Switch search grouping from `_group_key(name)` to `family_key`.
4. Dossier "other vintages / more stores" section.
5. Recommendation candidate dedup by family.

See `backend/api/routers/search.py` (`_group_key`, Phase 1) and root CLAUDE.md
(cross-retailer UPC dedup).
