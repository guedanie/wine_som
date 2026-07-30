# Deterministic Availability Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the counted availability truth ourselves, so the user sees it even when the narrative hedges or agrees with a false premise.

**Architecture:** A pure `availability_lines(facts, top, budget_max)` in `availability.py`; a new `availability` SSE frame after `picks`; an eyebrow-styled strip under the sommelier message in `ChatRecommend.jsx`.

**Tech Stack:** Python 3.9 (`Optional[...]`, never `X | None`), FastAPI SSE, React, pytest, vitest.

**Env:** Backend from `/Users/danielguerrero/dev/wine_app/backend` with `/usr/bin/python3` (bare `python3` is a BROKEN stub). **Frontend from `/Users/danielguerrero/dev/wine_app/frontend`** (vitest/vite fail from the repo root). Never stage `.claude/settings.local.json`. **Run whole test FILES before committing** — a `-k` filter has twice hidden a module-scope fixture collision; namespace new fixtures (`_AL_*`).

**Reference:** spec `docs/superpowers/specs/2026-07-30-availability-line-design.md`; failures in `docs/oracle-verification-round2.md`.

**Current shapes:**
- `availability.py`: `_fold`, states (`NOT_IN_CATALOG`, `PRESENT_OUT_OF_BUDGET`, `PRESENT_NOT_SHORTLISTED`, `PRESENT_SHORTLISTED`, `UNMEASURED`), `count_shortlisted(axis, top)`, `axis_label`. Facts are dicts: `{label, state, total, in_budget, min_price, max_price}` built in `recommend.py`'s `event_gen`.
- `recommend.py` `event_gen`: emits `{"type":"picks", ...}` at line ~653; `resolved["availability_facts"]` is set just before `stream_recommendations`; the fact-building loop has the axis `a` in hand.
- `ChatRecommend.jsx`: on `picks`, walks backward to the last `role === 'sommelier'` message and attaches `picks` — the strip follows the same pattern.
- Design system: `.t-eyebrow` (uppercase, tracked, `--text-muted`) in `frontend/design-system/colors_and_type.css`. No emoji, no new colors (`frontend/CLAUDE.md`).

**IMPORTANT — facts must carry their axis.** Lines need `count_shortlisted(axis, top)` and the narrow-beats-broad guard, so the fact dicts built in `event_gen` must also carry `"axis": a` (the source axis dict). Task 2 adds that.

---

### Task 1: `availability_lines` (pure)

**Files:**
- Modify: `backend/recommendation/availability.py`
- Test: `backend/tests/test_availability.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_availability.py` (namespace `_AL_*`):

```python
from recommendation.availability import availability_lines


def _AL_fact(label, state, total=10, in_budget=10, mn=None, mx=None, axis=None):
    return {"label": label, "state": state, "total": total, "in_budget": in_budget,
            "min_price": mn, "max_price": mx,
            "axis": axis or {"kind": "place", "value": label, "scope": None}}


def test_lines_not_shortlisted_states_count_and_none_shown():
    lines = availability_lines(
        [_AL_fact("Mendoza", PRESENT_NOT_SHORTLISTED, 401, 394, 4.18, 72.62)], [], 50.0)
    assert len(lines) == 1
    assert "394" in lines[0] and "Mendoza" in lines[0]
    assert "none in this list" in lines[0].lower()


def test_lines_not_shortlisted_silent_when_shortlist_covers_it():
    top = [{"region": "Rioja"}, {"region": "Rioja"}]
    f = _AL_fact("Rioja", PRESENT_NOT_SHORTLISTED, 5, 2,
                 axis={"kind": "place", "value": "Rioja", "scope": None})
    assert availability_lines([f], top, 50.0) == []      # in_budget (2) <= shown (2)


def test_lines_out_of_budget_names_range_and_cap():
    f = _AL_fact("Barolo at Geraldine's", PRESENT_OUT_OF_BUDGET, 3, 0, 59.0, 110.0,
                 axis={"kind": "place", "value": "Barolo", "scope": "Geraldine's"})
    line = availability_lines([f], [], 50.0)[0]
    assert "3" in line and "59" in line and "110" in line and "50" in line
    assert "Geraldine's" in line


def test_lines_not_in_catalog_is_the_only_absence():
    line = availability_lines(
        [_AL_fact("Muscadet", NOT_IN_CATALOG, 0, 0)], [], 50.0)[0]
    assert "no muscadet" in line.lower()


def test_lines_shortlisted_is_silent():
    assert availability_lines([_AL_fact("Rioja", PRESENT_SHORTLISTED, 9, 9)], [], 50.0) == []


def test_lines_narrow_axis_beats_broad():
    """The Brunello failure: the model cited Montalcino (broader) instead of the axis the
    user named. The line must render the NARROWEST matching axis only."""
    facts = [
        _AL_fact("Montalcino", PRESENT_NOT_SHORTLISTED, 34, 12),
        _AL_fact("Brunello di Montalcino", PRESENT_NOT_SHORTLISTED, 24, 4),
        _AL_fact("Brunello", PRESENT_NOT_SHORTLISTED, 25, 4),
    ]
    lines = availability_lines(facts, [], 50.0)
    joined = " | ".join(lines).lower()
    assert "brunello di montalcino" in joined
    assert "montalcino," not in joined          # the broad axis is suppressed
    assert len(lines) == 1


def test_lines_reports_remainder_not_total_when_some_shown():
    top = [{"region": "Chablis"}]
    f = _AL_fact("Chablis", PRESENT_NOT_SHORTLISTED, 53, 27,
                 axis={"kind": "place", "value": "Chablis", "scope": None})
    line = availability_lines([f], top, 40.0)[0]
    assert "26 more" in line.lower()           # 27 in budget - 1 shown


def test_lines_empty_and_capped():
    assert availability_lines([], [], 50.0) == []
    many = [_AL_fact(f"Region{i}", PRESENT_NOT_SHORTLISTED, 50, 40) for i in range(6)]
    assert len(availability_lines(many, [], 50.0)) <= 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

Add to `backend/recommendation/availability.py`:

```python
_MAX_LINES = 3


def _money(v: Optional[float]) -> str:
    return f"${v:,.0f}" if v is not None else ""


def availability_lines(facts: List[Dict[str, Any]], top: List[Dict[str, Any]],
                       budget_max: float) -> List[str]:
    """Short factual strings the CLIENT renders verbatim — the counted truth, stated by us
    rather than by the model.

    Two rounds of prompt hardening still left the model able to substitute a broader axis
    ("Montalcino, 12" for the requested "Brunello di Montalcino, 4") or agree with a false
    premise ("No Mendoza here" against 394 in budget). Rendering the number ourselves makes
    those failures visible instead of authoritative.

    Only informative facts produce a line; `PRESENT_SHORTLISTED` is silent because the picks
    already answer it."""
    if not facts:
        return []

    # Narrow beats broad: drop any axis whose value is contained in another axis's value
    # (Montalcino vs Brunello di Montalcino). Structurally prevents axis substitution.
    def _val(f):
        return _fold((f.get("axis") or {}).get("value") or f.get("label"))

    kept = []
    for f in facts:
        v = _val(f)
        if not v:
            continue
        if any(v != _val(o) and v in _val(o) for o in facts):
            continue                      # a more specific axis covers this one
        kept.append(f)

    lines: List[str] = []
    for f in kept:
        if len(lines) >= _MAX_LINES:
            break
        state = f.get("state")
        axis = f.get("axis") or {}
        name = axis.get("value") or f.get("label")
        scope = axis.get("scope")
        where = f"at {scope}" if scope else "nearby"
        rng = ""
        if f.get("min_price") is not None and f.get("max_price") is not None:
            rng = f" ({_money(f['min_price'])}–{_money(f['max_price'])})"

        if state == NOT_IN_CATALOG:
            lines.append(f"No {name} {where}")
        elif state == PRESENT_OUT_OF_BUDGET:
            lines.append(f"{f.get('total')} {name} {where}{rng} · above your "
                         f"{_money(budget_max)}")
        elif state == PRESENT_NOT_SHORTLISTED:
            shown = count_shortlisted(axis, top) if axis else 0
            in_budget = f.get("in_budget") or 0
            if in_budget <= shown:
                continue                  # the shortlist already represents the ask
            if shown:
                lines.append(f"{in_budget - shown} more {name} in budget {where}{rng}")
            else:
                lines.append(f"{in_budget} {name} in budget {where}{rng} · "
                             f"none in this list")
        elif state == UNMEASURED:
            lines.append(f"Couldn't confirm {name} {where}")
    return lines
```

- [ ] **Step 4: Run the whole file**

Run: `cd backend && /usr/bin/python3 -m pytest tests/test_availability.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/recommendation/availability.py backend/tests/test_availability.py
git commit -m "feat(availability): deterministic availability_lines rendered by us, not the model"
```

---

### Task 2: Emit the `availability` SSE frame

**Files:**
- Modify: `backend/api/routers/recommend.py`
- Test: `backend/tests/test_recommend_api.py`

- [ ] **Step 1: Carry the axis on each fact**

In `event_gen`'s fact-building loop, add `"axis": a` to the appended dict (the lines need the
axis for `count_shortlisted` and the narrow-beats-broad guard). Everything else stays.

- [ ] **Step 2: Emit the frame after `picks`**

Add `availability_lines` to the `recommendation.availability` import. In `event_gen`, immediately
after the `yield` of the `picks` frame (~line 653), add:

```python
                    try:
                        _lines = availability_lines(
                            resolved.get("availability_facts") or [], top, req.budget_max)
                        if _lines:
                            yield "data: " + json.dumps(
                                {"type": "availability", "lines": _lines}) + "\n\n"
                    except Exception:
                        logger.exception("AVAILABILITY | line render failed")
```

- [ ] **Step 3: Write the test**

Append to `backend/tests/test_recommend_api.py`, following the file's existing SSE-collection
pattern (read a neighbouring streaming test first and mirror its client/mocks):

```python
def test_availability_frame_emitted_when_lines_exist(...):
    """The counted truth must reach the client even if the narrative hedges."""
    # arrange a response whose resolved availability_facts yield a line, collect SSE frames,
    # assert one frame has type == "availability" and a non-empty "lines" list.


def test_no_availability_frame_when_nothing_informative(...):
    # facts all PRESENT_SHORTLISTED (or none) -> no availability frame in the stream
```
Implement both against the existing harness rather than inventing a new one.

- [ ] **Step 4: Verify + run**

Run:
```bash
cd backend && /usr/bin/python3 -c "import api.routers.recommend"
/usr/bin/python3 -m pytest tests/test_recommend_api.py -q
/usr/bin/python3 -m pytest tests/ -m "not integration" -q
```
Expected: import clean; all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_api.py
git commit -m "feat(recommend): emit availability SSE frame with the counted truth"
```

---

### Task 3: Frontend eyebrow strip

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx`
- Test: `frontend/src/screens/__tests__/ChatRecommend.test.jsx`

**Run frontend commands from `/Users/danielguerrero/dev/wine_app/frontend`.**

- [ ] **Step 1: Write the failing test**

Mirror the file's existing `streamRecommend.mockImplementation(async function* () {...})` pattern
(there is no `mockStream`/`renderChat` helper — match what's there):

```jsx
it('renders the deterministic availability strip', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'No Mendoza here.' };
    yield { type: 'picks', picks: [] };
    yield { type: 'availability', lines: ['394 Mendoza in budget nearby · none in this list'] };
  });
  renderScreen();
  expect(await screen.findByText(/394 Mendoza in budget nearby/i)).toBeInTheDocument();
});

it('renders no availability strip when the event is absent', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are some wines.' };
    yield { type: 'picks', picks: [] };
  });
  renderScreen();
  await screen.findByText(/Here are some wines/i);
  expect(screen.queryByText(/in budget nearby/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/screens/__tests__/ChatRecommend.test.jsx`
Expected: the first new test FAILS.

- [ ] **Step 3: Handle the event**

In `callRecommend`'s event loop, add a branch (mirroring how `picks` attaches to the last
sommelier message):
```jsx
        } else if (event.type === 'availability') {
          const lines = event.lines || [];
          if (lines.length) {
            setMessages(prev => {
              const msgs = [...prev];
              for (let k = msgs.length - 1; k >= 0; k--) {
                if (msgs[k].role === 'sommelier') { msgs[k] = { ...msgs[k], availability: lines }; break; }
              }
              return msgs;
            });
          }
        }
```

- [ ] **Step 4: Render the strip**

In the sommelier message rendering (BOTH the mobile and desktop layouts — the file has two),
after the paragraph body and before the attached picks, add:
```jsx
{m.availability?.length > 0 && (
  <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 3 }}>
    {m.availability.map((l, i) => (
      <span key={i} className="t-eyebrow" style={{ lineHeight: 1.5 }}>{l}</span>
    ))}
  </div>
)}
```
No emoji, no new colors, no box — `t-eyebrow` only (per `frontend/CLAUDE.md`).

- [ ] **Step 5: Run the whole test file + full frontend suite**

Run:
```bash
cd frontend && npx vitest run src/screens/__tests__/ChatRecommend.test.jsx
npx vitest run
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx frontend/src/screens/__tests__/ChatRecommend.test.jsx
git commit -m "feat(chat): render the deterministic availability strip"
```

---

### Task 4: Acceptance + docs

**Files:**
- Modify: `backend/scripts/verify_availability_oracle.py`, `docs/reference/recommendation.md`

- [ ] **Step 1: Replay both red-team failures**

Extend `main()` in `scripts/verify_availability_oracle.py` to build facts for the two failing
probes and assert the line is right:
```python
    print("— the two red-team false-absence cases now produce a correct line —")
    from recommendation.availability import availability_lines
    terms = terms_in_message("nothing from Mendoza right?", catalog_terms(sb))
    mendoza = facts_for(sb, nearby, {"regions": [], "grapes": [], "wine_type": None,
                                     "wine_name": None}, fallback_terms=terms)
    m_facts = [{"label": l, "state": s, "total": c["total"], "in_budget": c["in_budget"],
                "min_price": c.get("min_price"), "max_price": c.get("max_price"),
                "axis": {"kind": "place", "value": l, "scope": None}}
               for l, s, c in mendoza]
    m_lines = availability_lines(m_facts, [], 50.0)
    print(f"  mendoza -> {m_lines}")
    assert m_lines and "in budget" in m_lines[0], "expected a Mendoza availability line"

    bru = facts_for(sb, nearby, {"regions": ["Brunello di Montalcino"], "grapes": [],
                                 "wine_type": None, "wine_name": None})
    b_facts = [{"label": l, "state": s, "total": c["total"], "in_budget": c["in_budget"],
                "min_price": c.get("min_price"), "max_price": c.get("max_price"),
                "axis": {"kind": "place", "value": l, "scope": None}}
               for l, s, c in bru]
    b_lines = availability_lines(b_facts, [], 50.0)
    print(f"  brunello -> {b_lines}")
    assert b_lines, "expected a Brunello availability line"
    assert any("brunello" in l.lower() for l in b_lines), "must name the axis the user asked for"
```
(`facts_for` already accepts `fallback_terms`; no signature change needed.)

- [ ] **Step 2: Run it**

Run: `cd backend && /usr/bin/python3 -m scripts.verify_availability_oracle 2>&1 | grep -vE "NotOpenSSL|warnings.warn"`
Expected: prints both lines and `OK`. Record the actual strings.

- [ ] **Step 3: Docs**

In `docs/reference/recommendation.md`, extend the availability-oracle section with a
"Deterministic availability line" subsection: why (two prompt rounds left 2 FALSE_ABSENCE via axis
substitution + sycophantic agreement), what renders per state, the narrow-beats-broad guard, the
computed remainder, the SSE frame, the eyebrow strip, and the honest limitation (it guarantees the
truth is *shown*, not that the prose agrees; the tripwire alerts on disagreement).

- [ ] **Step 4: Full suites**

Run:
```bash
cd backend && /usr/bin/python3 -m pytest tests/ -m "not integration" -q
cd ../frontend && npx vitest run
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_availability_oracle.py docs/reference/recommendation.md
git commit -m "test+docs: availability-line acceptance replaying both red-team failures"
```

---

## Self-Review Notes

- **Spec coverage:** §1 lines→T1; §2 SSE→T2; §3 frontend→T3; §4 unchanged prompt/tripwire (no work); testing→each + T4. All covered.
- **Type consistency:** `availability_lines(facts, top, budget_max)` identical in T1 def, T2 call, T4 acceptance. Fact dicts gain `"axis"` in T2 and are consumed in T1 — T2 Step 1 exists precisely so T1's guard has its input.
- **Both guards trace to measured failures:** narrow-beats-broad ⇐ Brunello/Montalcino substitution; computed remainder ⇐ the model labelling `in_budget` as the remainder across 4 probes.
- **Fails open:** the emit is wrapped; a render failure logs and the stream continues. No line is ever a hard requirement of the response.
- **Design system:** `t-eyebrow` only, no emoji/colors/boxes, both layouts (`frontend/CLAUDE.md`).
