# Retailer-Scoped Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a request names a retailer ("anything from HEB?"), actually search that retailer's nearby inventory, show only its wines when it has fits, and word the no-fit case honestly.

**Architecture:** Data-driven `detect_retailer` (candidate_filters.py) with robust H-E-B aliasing; a retailer-scoped targeted fetch in recommend.py that merges that retailer's inventory into the pool; the existing retailer filter then works; a narrative directive for honest has-fit / no-fit wording.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), pytest.

**Env:** Backend commands from `/Users/danielguerrero/dev/wine_app/backend`. Bare `python3` is a BROKEN Homebrew stub — use `/usr/bin/python3`. Never stage `.claude/settings.local.json`. **Run the full test FILE (not just `-k`) before committing** (a `-k` filter once hid a helper-name collision).

**Reference:** spec `docs/superpowers/specs/2026-07-29-retailer-scoped-fetch-design.md`. Current: `_detect_retailer` + `_RETAILER_ALIASES` in `recommend.py` (~lines 80-100, 3 retailers, substring); retailer filter at ~438-443 (`preferred_retailer = _detect_retailer(req.message)` → `retailer_pool` filter); `retailer_to_stores` dict built ~231-235 ({retailer_name: [store_ids]}); `detected_store = detect_store(...)` ~357; targeted-fetch merge ~381-385. `detect_store`/`_store_tokens` in `candidate_filters.py` are the fuzzy-match pattern to mirror (but its stopwords strip "heb", so do NOT reuse them for retailers).

---

### Task 1: `detect_retailer` in candidate_filters + remove the old one

**Files:**
- Modify: `backend/recommendation/candidate_filters.py` (add)
- Modify: `backend/api/routers/recommend.py` (delete `_detect_retailer` + `_RETAILER_ALIASES`; import + call the new one)
- Test: `backend/tests/test_candidate_filters.py`

- [ ] **Step 1: Write the failing tests (all H-E-B variants + multi-word + fuzzy)**

```python
from recommendation.candidate_filters import detect_retailer

_NEARBY = ["H-E-B", "Central Market", "Twin Liquors", "Spec's", "Geraldine's Natural Wines"]


def test_detect_retailer_heb_all_variants():
    for m in ["anything from heb?", "what about HEB", "got any h-e-b picks",
              "show me h.e.b", "HEB please"]:
        assert detect_retailer(m, _NEARBY) == "H-E-B", m


def test_detect_retailer_multiword_and_shorthand():
    assert detect_retailer("anything at central market?", _NEARBY) == "Central Market"
    assert detect_retailer("cm options?", _NEARBY) == "Central Market"
    assert detect_retailer("twin liquors?", _NEARBY) == "Twin Liquors"
    assert detect_retailer("from twin", _NEARBY) == "Twin Liquors"


def test_detect_retailer_typo_tolerant():
    assert detect_retailer("anything at centrl market?", _NEARBY) == "Central Market"


def test_detect_retailer_none_when_unnamed():
    assert detect_retailer("something light and elegant under $40", _NEARBY) is None


def test_detect_retailer_only_returns_nearby():
    # 'kroger' alias target isn't in _NEARBY → not returned
    assert detect_retailer("anything from kroger?", _NEARBY) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k detect_retailer -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `detect_retailer`**

Add to `backend/recommendation/candidate_filters.py` (`re` + `difflib` already imported):

```python
# Retailer shorthands → canonical name. Keyed on the fully-normalized token
# (lowercase, punctuation stripped) so 'heb'/'HEB'/'h-e-b'/'h.e.b' all become 'heb'.
# Only applied when the canonical target is actually nearby.
_RETAILER_ALIASES = {
    "heb": "H-E-B", "specs": "Spec's", "spec": "Spec's",
    "cm": "Central Market", "twin": "Twin Liquors", "ht": "Harris Teeter",
    "geraldines": "Geraldine's", "geraldine": "Geraldine's", "pogos": "Pogo's",
}
# Generic words dropped from a retailer NAME's distinctive tokens.
_RETAILER_GENERIC = {"the", "wine", "wines", "market", "shop", "store", "liquors",
                     "liquor", "selections", "natural", "co", "company", "and"}


def _norm_retailer(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _retailer_name_tokens(name: str) -> List[str]:
    """Distinctive normalized tokens of a retailer name (generic words dropped)."""
    raw = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    return [_norm_retailer(t) for t in raw if t not in _RETAILER_GENERIC and _norm_retailer(t)]


def detect_retailer(message: str, nearby_retailers: List[str]) -> Optional[str]:
    """Return the canonical nearby retailer named in the message, or None. Matches
    case/punctuation-insensitively (heb/HEB/h-e-b/h.e.b → H-E-B) via an alias map,
    then falls back to fuzzy token match against the nearby retailer names. Only ever
    returns a retailer present in `nearby_retailers`."""
    if not message or not nearby_retailers:
        return None
    nearby_set = set(nearby_retailers)
    msg_tokens = [t for t in (_norm_retailer(w) for w in message.split()) if t]
    if not msg_tokens:
        return None
    # 1) alias hit (whole-token match; only if the target is nearby)
    for t in msg_tokens:
        target = _RETAILER_ALIASES.get(t)
        if target and target in nearby_set:
            return target
    # 2) fuzzy match distinctive tokens of each nearby retailer name
    best, best_score = None, 0
    for r in nearby_retailers:
        name_toks = _retailer_name_tokens(r)
        if not name_toks:
            continue
        score = sum(1 for nt in name_toks
                    if difflib.get_close_matches(nt, msg_tokens, n=1, cutoff=0.8))
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 1 else None
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py -k detect_retailer -v`
Expected: PASS.

- [ ] **Step 5: Replace the old detector in recommend.py**

In `backend/api/routers/recommend.py`: delete `_RETAILER_ALIASES` and `_detect_retailer` (~lines 80-100). Add `detect_retailer` to the `recommendation.candidate_filters` import. (Wiring of the call happens in Task 2.)

- [ ] **Step 6: Run the full candidate_filters + recommend-api files**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_candidate_filters.py tests/test_recommend_api.py -q`
Expected: PASS. (If a recommend-api test referenced `_detect_retailer`, update it to `detect_retailer(msg, [...])`; report if so.)

- [ ] **Step 7: Commit**

```bash
git add backend/recommendation/candidate_filters.py backend/api/routers/recommend.py backend/tests/test_candidate_filters.py
git commit -m "feat(recommend): data-driven detect_retailer with robust H-E-B aliasing"
```

---

### Task 2: Retailer targeted fetch + wiring

**Files:**
- Modify: `backend/api/routers/recommend.py`

- [ ] **Step 1: Compute the detected retailer early**

Near `detected_store = detect_store(...)` (~line 357), add:

```python
    detected_retailer = detect_retailer(req.message, list(retailer_to_stores))
```

- [ ] **Step 2: Add the retailer-scoped fetch + merge**

After the targeted-fetch merge block (~line 381-385, where `targeted` is merged), add:

```python
    def _retailer_rows(store_ids: list) -> list:
        def _q(since: Optional[str]) -> list:
            q = (supabase.table("retail_inventory").select(INVENTORY_SELECT)
                 .in_("store_ref", store_ids).eq("in_stock", True)
                 .gte("price", req.budget_min).lte("price", req.budget_max))
            regions = resolved.get("regions") or (
                [resolved["region"]] if resolved.get("region") else [])
            conds = []
            for p in regions:
                conds += [f"region.ilike.%{p}%", f"country.ilike.%{p}%"]
            if conds:
                q = q.or_(",".join(conds), reference_table="wines")
            if since:
                q = q.gte("last_scraped_at", since)
            return q.limit(300).execute().data or []
        return _q(stale_cutoff) or _q(None)

    if detected_retailer and retailer_to_stores.get(detected_retailer):
        rlr = [c for c in (_row_to_candidate(r)
                           for r in _retailer_rows(retailer_to_stores[detected_retailer])) if c]
        if rlr:
            candidates = merge_candidates(candidates, rlr)
            logger.info("RETAILER FETCH | %r → +%d rows", detected_retailer, len(rlr))
```

- [ ] **Step 3: Update the filter block to use `detected_retailer` + set narrative signals**

Replace the existing filter block (~438-443):
```python
    preferred_retailer = _detect_retailer(req.message)
    if preferred_retailer:
        retailer_pool = [c for c in candidates if preferred_retailer in (c.get("retailer") or "")]
        if retailer_pool:
            candidates = retailer_pool
            logger.info("RETAILER FILTER | %r → %d candidates", preferred_retailer, len(candidates))
```
with:
```python
    if detected_retailer:
        retailer_pool = [c for c in candidates if detected_retailer in (c.get("retailer") or "")]
        resolved["requested_retailer"] = detected_retailer
        resolved["retailer_has_fit"] = bool(retailer_pool)
        if retailer_pool:
            candidates = retailer_pool
            logger.info("RETAILER FILTER | %r → %d candidates", detected_retailer, len(candidates))
```

- [ ] **Step 4: Verify import + run recommend-api + full fast suite**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend"
/usr/bin/python3 -m pytest tests/test_recommend_api.py tests/ -m "not integration" -q
```
Expected: import clean; suite passes.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py
git commit -m "feat(recommend): retailer-scoped targeted fetch + honest-wording signals"
```

---

### Task 3: Narrative wording (has-fit / no-fit)

**Files:**
- Modify: `backend/recommendation/claude_client.py` (`_build_user_message`)
- Test: `backend/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_retailer_directive_has_fit():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}],
                              _intent(requested_retailer="H-E-B", retailer_has_fit=True))
    assert "H-E-B" in msg and "from these" in msg.lower()


def test_retailer_directive_no_fit_is_honest():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}],
                              _intent(requested_retailer="H-E-B", retailer_has_fit=False))
    assert "doesn't stock" in msg.lower() or "does not stock" in msg.lower()


def test_no_retailer_directive_when_unset():
    msg = _build_user_message([{"wine_id": "1", "name": "X"}], _intent())
    assert "from these" not in msg.lower() and "doesn't stock" not in msg.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -k retailer -v`
Expected: FAIL.

- [ ] **Step 3: Build + insert the directive**

In `_build_user_message`, after the `comparison_directive` block, add:

```python
    retailer_directive = ""
    req_retailer = intent.get("requested_retailer")
    if req_retailer:
        if intent.get("retailer_has_fit"):
            retailer_directive = (
                f"\n\nThe user asked for {req_retailer}; every listing below is from "
                f"{req_retailer} — recommend from these.")
        else:
            retailer_directive = (
                f"\n\nThe user asked for {req_retailer}, but {req_retailer} doesn't stock a wine "
                f"matching their profile. Say that plainly, then offer the closest fits from other "
                f"nearby shops in the listings.")
```

Add `f"{retailer_directive}"` to the `return (...)` assembly, right after `f"{comparison_directive}"`.

- [ ] **Step 4: Run to verify pass + full file**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_claude_client.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/claude_client.py backend/tests/test_claude_client.py
git commit -m "feat(recommend): honest has-fit/no-fit narrative for named retailers"
```

---

### Task 4: Acceptance replay + docs

**Files:**
- Create: `backend/scripts/verify_retailer_fetch.py`
- Modify: `CLAUDE.md`, `docs/reference/recommendation.md`

- [ ] **Step 1: Write the acceptance script**

Create `backend/scripts/verify_retailer_fetch.py`:
```python
"""Acceptance: 'anything from heb?' for a light-red profile at 78230 now surfaces
H-E-B wines (was 0). Run from backend/: /usr/bin/python3 -m scripts.verify_retailer_fetch"""
from db import get_supabase_client
from recommendation.candidate_filters import detect_retailer
from utils.geo import find_nearby_store_ids

ZIP = "78230"
SEL = "price, wine_id, wines!inner(id, name, varietal, wine_type)"


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    meta = sb.table("stores").select("id,retailer_name").in_("id", nearby).execute().data
    r2s = {}
    for s in meta:
        r2s.setdefault(s["retailer_name"], []).append(s["id"])

    detected = detect_retailer("anything from heb?", list(r2s))
    print(f"detected retailer: {detected!r}")
    assert detected == "H-E-B", "expected H-E-B detection"

    rows = (sb.table("retail_inventory").select(SEL).in_("store_ref", r2s[detected])
            .eq("in_stock", True).gte("price", 10).lte("price", 60)
            .eq("wines.wine_type", "red").limit(300).execute().data or [])
    print(f"H-E-B red candidates under $60 near {ZIP}: {len(rows)}")
    assert len(rows) > 0, "expected H-E-B reds to exist"
    print("sample:", [x["wines"]["name"][:40] for x in rows[:5]])
    print("OK — retailer detection + scoped fetch surface H-E-B inventory")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd backend && /usr/bin/python3 -m scripts.verify_retailer_fetch 2>&1 | grep -vE "NotOpenSSL|warnings.warn"`
Expected: `detected retailer: 'H-E-B'`, a positive red count, sample names, `OK`.

- [ ] **Step 3: Update docs**

- `docs/reference/recommendation.md`: add a "Named-retailer fetch" note under the candidate-fetch section (data-driven `detect_retailer` + aliasing, retailer-scoped targeted fetch, retailer-only filter when fits exist, honest has-fit/no-fit wording).
- `CLAUDE.md`: add a one-line note (recommender now handles retailer-scoped requests, 2026-07-29).

- [ ] **Step 4: Full fast suite**

Run: `cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_retailer_fetch.py CLAUDE.md docs/reference/recommendation.md
git commit -m "test+docs: retailer-scoped fetch acceptance + reference"
```

---

## Self-Review Notes

- **Spec coverage:** §1 detection→T1; §2 fetch→T2; §3 filter→T2; §4 wording→T3; §5 testing→each + T4. All covered.
- **H-E-B aliasing:** `_norm_retailer` strips punctuation so `heb`/`HEB`/`h-e-b`/`h.e.b` → `heb` → alias → "H-E-B"; T1 asserts all variants. Derive-from-nearby alone can't catch H-E-B (name → h/e/b tokens), which is exactly why the alias map is required — noted.
- **Type consistency:** `detect_retailer(message, nearby_retailers)` identical across T1 def, T2 call, T4 acceptance. `requested_retailer`/`retailer_has_fit` set in T2, read in T3.
- **Only-nearby guarantee:** aliases resolve only if the target ∈ nearby; fuzzy matches iterate `nearby_retailers` — a non-nearby chain (Kroger when absent) returns None (T1 asserts).
- **Filter firmness:** retailer_pool non-empty → candidates = retailer_pool (retailer-only); empty → keep pool (fallback) + `retailer_has_fit=False` drives the honest no-fit wording.
