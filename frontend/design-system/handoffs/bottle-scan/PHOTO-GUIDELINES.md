# Bottle Scan — test-photo collection guidelines

Ground-truth set for the vision match-rate spike (`scripts/spike_vision_match.py`). The goal is
photos that look like what real users will actually send — **shoot like a hurried user, not a
photographer**: one quick handheld shot, maybe one retake, never staged lighting, never wiping
the label first. ~30 photos total.

Drop photos in `data/exploration/bottle-scan-photos/` and fill one CSV row per photo in
`ground_truth.csv`:

```csv
filename,expected_wine,vintage_on_bottle,in_catalog,circumstance,difficulty,notes
store_shelf_glare_01.jpg,Caymus Cabernet Sauvignon,2021,yes,store,easy,fluorescent glare on gloss
```

`in_catalog` matters: include a handful of bottles you *know* aren't in Somm's inventory —
the "recognized, not stocked" state needs real test cases too.

---

## Circumstance quotas

### 1. At the store — ~12 photos (the primary use case)
Shot standing in the aisle, one-handed, bottle either in hand or still on the shelf.
- [ ] Eye-level shelf, decent light — 2–3 (the baseline)
- [ ] Bottom shelf, shooting downward at an angle — 2
- [ ] Overhead fluorescent glare hitting a glossy or foil label — 2
- [ ] Bottle on shelf with neighbors in frame (cluttered background, other labels visible) — 2
- [ ] Refrigerated case: shot through the glass door, and one with condensation on a chilled white/sparkling — 2
- [ ] Shelf price tag or ribbon partially covering the label — 1
- [ ] One deliberately rushed shot: slight motion blur, label not centered — 1

Also grab **3–4 barcode photos** (back label, straight on) at the store — the barcode tier
needs its own smoke test, and back labels are what users will guess to scan.

### 2. At a restaurant / dinner table — ~8 photos
The "remember this for me" case. Expect the worst lighting of the set.
- [ ] Dim warm light, no flash — 2
- [ ] Same bottle with flash (foil labels will blow out — we want to see how badly) — 1
- [ ] Candlelight / very low light — 1
- [ ] Bottle partly rotated so the label is only ~⅔ visible — 2
- [ ] White in an ice bucket or sweating on the table (condensation + drips) — 1
- [ ] Half-poured bottle held up by a dinner guest, casual framing — 1

### 3. At home — ~6 photos
The control set plus the cellar/drank flow.
- [ ] Good daylight, label square in frame — 2 (this is the accuracy *ceiling* reference)
- [ ] Bottle in a rack or fridge door, shot at whatever angle it sits — 2
- [ ] "I drank this": empty bottle, maybe a stained or peeling label — 2

### 4. Adversarial / control — ~4 photos
- [ ] A photo of a bottle **on a screen** (someone texts you a bottle pic) — 1
- [ ] Back label only, no front label in frame — 1
- [ ] A non-wine bottle (beer or a spirit) — 1 — the pipeline should *decline*, not force a match
- [ ] Extreme close-up where only part of the wine name is legible — 1

---

## Bottle-type coverage (spread across the circumstances above)
Difficulty tiers — aim for roughly **⅓ easy / ⅓ mid / ⅓ obscure**:
- **Easy**: big grocery labels with the varietal printed (Apothic, Caymus, Kim Crawford tier).
- **Mid**: regional labels where producer + appellation are printed but no varietal
  (Rioja, Côtes du Rhône, mid-tier domestic).
- **Obscure (the stress tier)**: Pogo's-style fine wine — minimal text, small type, no grape,
  maybe only a producer name and a village. These are the same bottles the extraction pipeline
  already struggles with; weight them heavily.

And make sure the set includes at least one each of:
- [ ] Foil / metallic / embossed label (glare magnet)
- [ ] Sparkling with foil cage and neck wrap
- [ ] Dark antique glass with a dark label (low contrast)
- [ ] A wide wrap-around label (text distorts on the curve)
- [ ] Script/handwritten typeface
- [ ] A non-English label (German, Portuguese, or Italian long-form)

---

## Shooting rules (keep the set honest)
1. Phone camera app, default settings, portrait orientation.
2. One shot, at most one retake — if a real user would give up and retype the name, that's data.
3. Don't clean, flatten, or reposition labels; don't chase the light.
4. Log the CSV row immediately (expected wine + vintage as printed) — labels are hard to
   re-identify a week later, which is itself a lesson about the feature.
