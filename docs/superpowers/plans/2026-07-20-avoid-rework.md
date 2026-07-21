# `avoid` Hard-Exclusion Rework + Flavor De-Noise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the recommender's `avoid` a reliable hard exclusion (type-aware + word-boundary, no metadata), and remove the metadata `flavor_profile` from flavor scoring.

**Architecture:** Add a conservative term→wine_type map and a pure `wine_excluded_by_avoid(wine, avoid_terms, tags)` function to `recommendation/scorer.py`; replace the inline substring avoid block in `score_candidates` with a call to it; drop `flavor_profile` from the `notes` variable used by flavor `kw_hits`.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), pytest.

**Env:** Run backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3` for all pytest/python commands. Never stage `.claude/settings.local.json`.

**Reference:** spec `docs/superpowers/specs/2026-07-20-avoid-rework-design.md`. Current avoid code is in `recommendation/scorer.py`: `avoid = [_norm(a) ...]` (~line 116), `notes = _norm(tasting_notes) + " " + join(flavor_profile)` (~128), the `haystack`/`if any(...): continue` block (~136-139). The scoring loop already computes `tags = flavor_tags_for(...)` (~127) and normalizes with the module's `_norm` (accent-fold + lower).

---

### Task 1: Term→type map + `wine_excluded_by_avoid`

**Files:**
- Modify: `backend/recommendation/scorer.py` (add near the other module constants/helpers, above `score_candidates`)
- Test: `backend/tests/test_scorer.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_scorer.py` (the file already has `_wine`/`_intent` helpers and imports `score_candidates`; add a direct import of the new function):

```python
from recommendation.scorer import wine_excluded_by_avoid
from recommendation.flavor_profiles import flavor_tags_for


def _tags(w):
    return flavor_tags_for(w.get("varietal"), w.get("grapes"), w.get("region"))


def test_avoid_type_excludes_only_that_type():
    sparkling = _wine("Prosecco", wine_type="sparkling", varietal="Glera",
                      region="Veneto", country="Italy")
    red = _wine("Malbec", wine_type="red")
    assert wine_excluded_by_avoid(sparkling, ["sparkling"], _tags(sparkling)) is True
    assert wine_excluded_by_avoid(red, ["sparkling"], _tags(red)) is False


def test_avoid_type_synonyms_map():
    champ = _wine("Brut", wine_type="sparkling", varietal="Chardonnay", region="Champagne", country="France")
    port = _wine("Tawny", wine_type="fortified", varietal="Touriga Nacional", region="Douro", country="Portugal")
    assert wine_excluded_by_avoid(champ, ["bubbles"], _tags(champ)) is True
    assert wine_excluded_by_avoid(port, ["port"], _tags(port)) is True


def test_avoid_port_does_not_exclude_portuguese_table_wine():
    # 'port' maps to fortified; a Portuguese RED table wine must survive
    douro_red = _wine("Douro Red", wine_type="red", varietal="Touriga Nacional",
                      region="Douro", country="Portugal")
    assert wine_excluded_by_avoid(douro_red, ["port"], _tags(douro_red)) is False


def test_avoid_red_excludes_by_type_not_red_fruit():
    # 'red' -> type red. A white whose grape implies the 'red-fruit' tag must NOT be excluded.
    red = _wine("Cab", wine_type="red", varietal="Cabernet Sauvignon")
    fruity_white = _wine("Pinot Blanc", wine_type="white", varietal="Merlot")  # Merlot -> red-fruit tag
    assert wine_excluded_by_avoid(red, ["red"], _tags(red)) is True
    assert wine_excluded_by_avoid(fruity_white, ["red"], _tags(fruity_white)) is False


def test_avoid_rose_accent_insensitive():
    rose = _wine("Rosado", wine_type="rosé", varietal="Grenache")
    assert wine_excluded_by_avoid(rose, ["rose"], _tags(rose)) is True
    assert wine_excluded_by_avoid(rose, ["pink"], _tags(rose)) is True


def test_avoid_orange_phrase_only():
    orange = _wine("Skin Contact", wine_type="orange", varietal="Ribolla Gialla")
    # bare 'orange' is ambiguous -> NOT excluded; the phrase 'orange wine' is
    assert wine_excluded_by_avoid(orange, ["orange"], _tags(orange)) is False
    assert wine_excluded_by_avoid(orange, ["orange wine"], _tags(orange)) is True
    assert wine_excluded_by_avoid(orange, ["skin contact"], _tags(orange)) is True


def test_avoid_grape_country_tag_word_boundary():
    chard = _wine("Big Oak", wine_type="white", varietal="Chardonnay", region="Napa", country="USA")
    italian = _wine("Chianti", wine_type="red", varietal="Sangiovese", region="Tuscany", country="Italy")
    gsm = _wine("Rhone Blend", wine_type="red", varietal="Grenache", region="Rhône", country="France")
    assert wine_excluded_by_avoid(chard, ["chardonnay"], _tags(chard)) is True
    assert wine_excluded_by_avoid(italian, ["italy"], _tags(italian)) is True   # country
    assert wine_excluded_by_avoid(gsm, ["earthy"], _tags(gsm)) is True          # flavor tag


def test_avoid_matches_tasting_notes_not_metadata():
    # real tasting_notes count; metadata flavor_profile must NOT
    noted = _wine("Oaky White", wine_type="white", varietal="Chardonnay",
                  tasting_notes="heavy oak and butter")
    meta = _wine("Clean White", wine_type="white", varietal="Chardonnay",
                 tasting_notes="", flavor_profile=["France", "review-92plus", "oak-barrel"])
    assert wine_excluded_by_avoid(noted, ["oak"], _tags(noted)) is True
    assert wine_excluded_by_avoid(meta, ["oak"], _tags(meta)) is False


def test_avoid_empty_is_false():
    w = _wine("Anything")
    assert wine_excluded_by_avoid(w, [], _tags(w)) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k avoid -v`
Expected: FAIL (`ImportError: cannot import name 'wine_excluded_by_avoid'`).

- [ ] **Step 3: Implement the map + function**

In `backend/recommendation/scorer.py`, above `score_candidates` (and after `_norm` is defined, since it's used), add:

```python
# avoid → wine_type synonyms (conservative: unambiguous words + the two orange
# phrases only). Keys are _norm'd (accent-folded, lowercased). 'sweet'/'orange'/
# 'green' are deliberately absent — sweetness is a different axis, bare 'orange' is
# the fruit, and Vinho Verde ('green') is a region reached via text matching.
_TYPE_FOR_TERM = {
    "sparkling": "sparkling", "bubbles": "sparkling", "bubbly": "sparkling",
    "champagne": "sparkling", "prosecco": "sparkling", "cava": "sparkling", "fizz": "sparkling",
    "rose": "rosé", "pink": "rosé",
    "port": "fortified", "sherry": "fortified", "madeira": "fortified",
    "marsala": "fortified", "fortified": "fortified",
    "dessert": "dessert", "ice wine": "dessert", "icewine": "dessert", "sauternes": "dessert",
    "orange wine": "orange", "skin contact": "orange",
    "red": "red", "white": "white",
}


def wine_excluded_by_avoid(wine: Dict[str, Any], avoid_terms: List[str],
                           tags: set) -> bool:
    """Hard exclusion. A term that names a wine type excludes only wines of that
    resolved type (never falls through to substring — kills port→Portugal,
    red→red-fruit). Any other term word-boundary matches structured fields
    (varietal, name, grapes, region, country, flavor tags, real tasting_notes) —
    NOT the metadata flavor_profile, never a raw substring."""
    if not avoid_terms:
        return False
    wtype = _norm(wine.get("wine_type"))
    parts = [wine.get("varietal"), wine.get("name"), wine.get("region"),
             wine.get("country"), wine.get("tasting_notes")]
    parts += list(wine.get("grapes") or [])
    parts += list(tags or [])
    text = " ".join(_norm(p) for p in parts if p)
    for term in avoid_terms:
        t = _norm(term)
        if not t:
            continue
        mapped = _TYPE_FOR_TERM.get(t)
        if mapped is not None:
            if wtype == _norm(mapped):
                return True
            continue  # type word, wrong type — do NOT substring-match
        if re.search(r"\b" + re.escape(t) + r"\b", text):
            return True
    return False
```

(`re`, `Dict`, `Any`, `List` are already imported in `scorer.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k avoid -v`
Expected: PASS (all new `avoid` tests).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat(scorer): type-aware word-boundary wine_excluded_by_avoid"
```

---

### Task 2: Wire into `score_candidates` + flavor de-noise

**Files:**
- Modify: `backend/recommendation/scorer.py` (`score_candidates` body)
- Test: `backend/tests/test_scorer.py`

- [ ] **Step 1: Write the failing/guard tests**

The existing `test_avoid_list_excludes_wines` (avoid "sweet" via tasting_notes) must still pass. Add a flavor-denoise regression:

```python
def test_flavor_profile_metadata_does_not_score_as_flavor():
    # 'earthy' requested; a wine whose ONLY 'earthy' source is metadata flavor_profile
    # must not get a flavor credit for it. Compare against a genuine earthy grape.
    meta = _wine("Meta", wine_type="red", varietal="Chardonnay", region="Napa",
                 grapes=["Chardonnay"], flavor_profile=["earthy", "review-92plus"])
    genuine = _wine("GSM", wine_type="red", varietal="Grenache", region="Rhône",
                    grapes=["Grenache"])  # Grenache/Rhône -> earthy tag
    result = score_candidates(_intent(wine_type="red", flavors=["earthy"]), [meta, genuine])
    assert result[0]["name"] == "GSM"
```

- [ ] **Step 2: Run to verify the regression fails**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -k "flavor_profile_metadata or avoid_list" -v`
Expected: `test_flavor_profile_metadata_does_not_score_as_flavor` FAILS (metadata currently counts as a flavor kw hit), `test_avoid_list_excludes_wines` passes.

- [ ] **Step 3: Wire the function + de-noise notes**

In `score_candidates`:

Replace the `notes` assignment:
```python
        notes = _norm(wine.get("tasting_notes")) + " " + " ".join(
            _norm(x) for x in (wine.get("flavor_profile") or []))
```
with:
```python
        notes = _norm(wine.get("tasting_notes"))
```

Replace the avoid block:
```python
        # avoid exclusion: search grapes, region, flavor tags, and notes
        haystack = " ".join([notes, region, " ".join(grapes), " ".join(tags)])
        if any(a and a in haystack for a in avoid):
            continue
```
with:
```python
        if wine_excluded_by_avoid(wine, avoid, tags):
            continue
```

`avoid` is still bound earlier as `avoid = [_norm(a) for a in (intent.get("avoid") or [])]`; passing pre-normed terms is fine (`wine_excluded_by_avoid` re-`_norm`s, which is idempotent). Leave that binding as-is.

- [ ] **Step 4: Run the full scorer suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_scorer.py -v`
Expected: PASS (all — new, regression, and existing incl. `test_avoid_list_excludes_wines`, `test_earthy_intent_ranks_gsm_over_fruit_bomb_via_grape_inference`).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/scorer.py backend/tests/test_scorer.py
git commit -m "feat(scorer): wire type-aware avoid + drop flavor_profile metadata from flavor scoring"
```

---

### Task 3: Sweep re-run acceptance + docs

**Files:**
- Modify: `CLAUDE.md` (item 33), `docs/reference/recommendation.md`

- [ ] **Step 1: Re-run the capability sweep and capture the numbers**

Run: `cd backend && /usr/bin/python3 /private/tmp/claude-501/-Users-danielguerrero-dev-wine-app/d3d205d4-950e-4a42-a96e-3899bb0bc7fe/scratchpad/somm_soft_sweep.py 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn`

Note: the scratchpad sweep measures the OLD haystack directly (it has its own `scorer_haystack`), so its avoid section won't auto-reflect the fix. Instead, verify the fix behaviorally with a short inline check and record it:

```bash
cd backend && /usr/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from db import get_supabase_client
from recommendation.scorer import wine_excluded_by_avoid
from recommendation.flavor_profiles import flavor_tags_for
sb=get_supabase_client()
def tags(w): return flavor_tags_for(w.get('varietal'),w.get('grapes'),w.get('region'))
rows=sb.table('wines').select('name,varietal,region,country,wine_type,grapes').order('id').limit(4000).execute().data
def leak(term,wtype):
    typ=[w for w in rows if w.get('wine_type')==wtype]
    return sum(1 for w in typ if not wine_excluded_by_avoid(w,[term],tags(w))), len(typ)
for term,wt in [('sparkling','sparkling'),('fortified','fortified'),('dessert','dessert')]:
    l,n=leak(term,wt); print(f'avoid {term!r}: {l}/{n} of that type still leak (expect 0)')
fp=sum(1 for w in rows if (w.get('country') or '')!='Portugal' and wine_excluded_by_avoid(w,['port'],tags(w)) and w.get('wine_type')!='fortified')
print(f'avoid port false-positives (non-Portugal non-fortified excluded): {fp} (expect 0)')
" 2>&1 | grep -v NotOpenSSL | grep -v warnings.warn
```
Expected: all type leaks 0/N; port false-positives 0.

- [ ] **Step 2: Update the roadmap**

In `CLAUDE.md` item 33, append to the REMAINING note (or convert it) that the second capability sweep is done and the `avoid` rework landed. Suggested addition after the existing item-33 text:

```markdown
**Second capability sweep DONE 2026-07-20** (soft axes flavor/avoid/body): `avoid` was the one broken hard-exclusion path — rework landed. `wine_excluded_by_avoid` (scorer.py) is now type-aware (conservative term→wine_type map: sparkling/bubbles/champagne→sparkling, port/sherry→fortified, red/white/rosé, orange-wine phrases) excluding by *resolved* wine_type, with word-boundary matching over structured fields (varietal/name/grapes/region/country/flavor-tags/real-tasting_notes) — no metadata, no raw substring. Fixes: "no sparkling" leaked 57%→0, "nothing fortified" 93%→0, avoid "port"→Portugal 41 false-positives→0, avoid "red" no longer nukes red-fruit whites. Also dropped the 100%-metadata `flavor_profile` from the flavor kw-scoring path (was producing phantom flavor matches). Body axis healthy (88% resolvable) — untouched. DEFERRED (data/enrichment, separate item): flavor-invisible 28% of catalog + narrow 15-word parser vocab (buttery/oaky/smoky/etc dropped).
```

- [ ] **Step 3: Update the reference doc**

In `docs/reference/recommendation.md`, in the scorer section, add a short "Avoid (hard exclusion)" note: type-aware term→wine_type map, word-boundary structured matching, no metadata `flavor_profile`, and that flavor scoring no longer reads `flavor_profile`.

- [ ] **Step 4: Run the full fast backend suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS (prior count + the new avoid/denoise tests).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/reference/recommendation.md
git commit -m "docs: second capability sweep done — avoid rework + flavor de-noise"
```

---

## Self-Review Notes

- **Spec coverage:** §1 map→T1; §2 function→T1, wiring→T2; §3 flavor de-noise→T2; acceptance→T3. All covered.
- **Type consistency:** `wine_excluded_by_avoid(wine, avoid_terms, tags)` signature identical across T1 tests, T2 wiring. `_TYPE_FOR_TERM` values are valid `wine_type` strings (`rosé` accented to match the DB; compared via `_norm` on both sides).
- **Backward-compat:** `test_avoid_list_excludes_wines` (avoid "sweet" via tasting_notes) still passes because tasting_notes is included in the avoid text and "sweet" is a non-type term matched by word boundary. `test_earthy_intent_ranks_gsm_...` still passes (grape tag path unchanged).
- **No raw substring anywhere:** type words compare `wtype == _norm(mapped)`; all else uses `\b...\b`.
