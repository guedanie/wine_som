# Feedback Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add thumbs up/down feedback to wine cards (Pattern A) and sommelier messages (Pattern B), with a follow-up bubble on thumbs-down and a backend endpoint that persists votes.

**Architecture:** Pattern A adds a brass-filled thumb footer to every WineCard. Pattern B adds a "Was this useful?" row below each sommelier bubble; a thumbs-down appends a follow-up message (UI-only, no AI call). Both patterns fire `POST /api/feedback` optimistically. A new `feedback` Supabase table stores one row per (session_id, entity_id, type) via upsert. Session ID is a `crypto.randomUUID()` generated once per ChatRecommend mount.

**Tech Stack:** FastAPI (backend), Pydantic, supabase-py, React 19, lucide-react (new dep — thumb icons), @testing-library/react, pytest-asyncio

**Design reference:** `/Users/danielguerrero/Downloads/design_handoff_feedback_capture/README.md` — all pixel values, colors, and interaction states are specified there. Match exactly.

## Global Constraints

- Python 3.9.6 — use `Optional[str]` from `typing`, NOT `str | None`
- Pattern A: thumb buttons 26×26px, border-radius 2px, brass fill (`var(--brass)`) when voted (either direction), `var(--border)` border + transparent bg when unvoted
- Pattern B: thumb buttons 24×24px, border-radius 2px; voted-up = sage (`var(--sage)`) fill; voted-down = bordeaux (`var(--bordeaux)`) fill
- Transition on all vote state changes: `all 140ms cubic-bezier(.25,.46,.45,.94)`
- Thumb icons: Lucide `ThumbsUp` / `ThumbsDown`, strokeWidth 1.75; size 12px in Pattern A, 11px in Pattern B
- Stop propagation on thumb button clicks so card's `onClick` does not fire
- Vote is a toggle: clicking the active thumb deselects it (sets to null); clicking the opposite thumb switches
- Follow-up bubble text (exact): `"Noted — what didn't land? The **grape variety**, the **price point**, or the **region**?"` — `**bold**` words render in `var(--bordeaux)` using existing markdown-bold renderer
- Follow-up bubble is appended only on first thumbs-down per message (toggling off the down vote does not remove the follow-up)
- `postFeedback` is fire-and-forget — no loading state, swallow network errors
- Backend: `POST /api/feedback` returns `{"ok": true}`; uses service_role client (write operation)
- All frontend tests run from `frontend/` with `npm run test:run`; all backend tests from `backend/` with `python3 -m pytest tests/ -m "not integration" -v`

---

### Task 1: Supabase migration + backend feedback endpoint

**Files:**
- Create: `supabase/migrations/20260630000001_feedback_table.sql`
- Modify: `backend/api/schemas.py` (add `FeedbackRequest`)
- Create: `backend/api/routers/feedback.py`
- Modify: `backend/api/main.py` (register router)
- Test: `backend/tests/test_feedback_api.py`

**Interfaces:**
- Produces: `POST /api/feedback` — accepts `FeedbackRequest`, returns `{"ok": true}`
- Produces: `FeedbackRequest` Pydantic model with fields: `type`, `entity_id`, `vote`, `session_id`, `user_id`, `zip`

- [ ] **Step 1: Create the Supabase migration**

Create `supabase/migrations/20260630000001_feedback_table.sql`:

```sql
-- Stores thumbs up/down votes on wine cards and sommelier messages.
-- One row per (session_id, entity_id, type) — upserted on every vote change.
CREATE TABLE feedback (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  type        TEXT        NOT NULL CHECK (type IN ('wine_card', 'sommelier_message')),
  entity_id   TEXT        NOT NULL,
  vote        TEXT        CHECK (vote IN ('up', 'down')),
  session_id  TEXT        NOT NULL,
  user_id     TEXT,
  zip         TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, entity_id, type)
);

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role full access on feedback" ON feedback
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT ALL ON feedback TO service_role;
```

- [ ] **Step 2: Apply the migration to Supabase**

Run this in the Supabase SQL editor (dashboard → SQL Editor) or via CLI:
```bash
supabase db push
```

Verify the `feedback` table exists in the Supabase dashboard before continuing.

- [ ] **Step 3: Write the failing backend tests**

Create `backend/tests/test_feedback_api.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from api.main import app


def _make_db_mock():
    db = MagicMock()
    upsert_resp = MagicMock()
    upsert_resp.data = [{"id": "uuid-1"}]
    db.table.return_value.upsert.return_value.execute.return_value = upsert_resp
    return db


@pytest.mark.asyncio
async def test_post_feedback_wine_card():
    with patch("api.routers.feedback.get_service_client", return_value=_make_db_mock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "wine_card",
                "entity_id": "wine-uuid-1",
                "vote": "up",
                "session_id": "sess-1",
            })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_post_feedback_sommelier_message():
    with patch("api.routers.feedback.get_service_client", return_value=_make_db_mock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "sommelier_message",
                "entity_id": "msg-uuid-1",
                "vote": "down",
                "session_id": "sess-1",
                "zip": "78209",
            })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_post_feedback_null_vote_deselect():
    with patch("api.routers.feedback.get_service_client", return_value=_make_db_mock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/feedback", json={
                "type": "wine_card",
                "entity_id": "wine-uuid-1",
                "vote": None,
                "session_id": "sess-1",
            })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_post_feedback_invalid_type_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/feedback", json={
            "type": "invalid_type",
            "entity_id": "wine-uuid-1",
            "vote": "up",
            "session_id": "sess-1",
        })
    assert resp.status_code == 422
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd backend
python3 -m pytest tests/test_feedback_api.py -v
```

Expected: 4 failures — `feedback` router not yet registered.

- [ ] **Step 5: Add `FeedbackRequest` to `schemas.py`**

Append to `backend/api/schemas.py`:

```python
class FeedbackRequest(BaseModel):
    type: str
    entity_id: str
    vote: Optional[str] = None
    session_id: str
    user_id: Optional[str] = None
    zip: Optional[str] = None
```

- [ ] **Step 6: Create `backend/api/routers/feedback.py`**

```python
from fastapi import APIRouter
from api.schemas import FeedbackRequest
from db import get_service_client

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", status_code=200)
async def post_feedback(body: FeedbackRequest):
    client = get_service_client()
    client.table("feedback").upsert(
        {
            "type":       body.type,
            "entity_id":  body.entity_id,
            "vote":       body.vote,
            "session_id": body.session_id,
            "user_id":    body.user_id,
            "zip":        body.zip,
        },
        on_conflict="session_id,entity_id,type",
    ).execute()
    return {"ok": True}
```

- [ ] **Step 7: Register the router in `backend/api/main.py`**

Change line 6:
```python
from api.routers import wines, enrichment, recommend, region
```
to:
```python
from api.routers import wines, enrichment, recommend, region, feedback
```

Add after `app.include_router(region.router)`:
```python
app.include_router(feedback.router)
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd backend
python3 -m pytest tests/test_feedback_api.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 9: Run full unit suite for regressions**

```bash
cd backend
python3 -m pytest tests/ -m "not integration" -v
```

Expected: all pass (169 including 4 new).

- [ ] **Step 10: Commit**

```bash
git add supabase/migrations/20260630000001_feedback_table.sql \
        backend/api/schemas.py \
        backend/api/routers/feedback.py \
        backend/api/main.py \
        backend/tests/test_feedback_api.py
git commit -m "feat: feedback table migration + POST /api/feedback endpoint"
```

---

### Task 2: Frontend Pattern A — thumbs on WineCard

**Files:**
- Modify: `frontend/package.json` (add lucide-react)
- Modify: `frontend/src/components/WineCard.jsx` (add thumb footer)
- Modify: `frontend/src/lib/api.js` (add `postFeedback`)
- Modify: `frontend/src/screens/ChatRecommend.jsx` (add `wineVotes` state + `sessionId` + wire up)
- Modify: `frontend/src/components/__tests__/components.test.jsx` (add WineCard thumb tests)

**Interfaces:**
- Consumes: `POST /api/feedback` from Task 1
- Produces: `WineCard` accepts two new optional props: `vote: 'up'|'down'|null` and `onVote: (direction: 'up'|'down') => void`. When `onVote` is absent the thumb footer is not rendered (backward compat).
- Produces: `postFeedback(payload)` in `api.js` — fire-and-forget async function

- [ ] **Step 1: Install lucide-react**

```bash
cd frontend
npm install lucide-react
```

Verify it appears in `package.json` under `dependencies`.

- [ ] **Step 2: Write failing WineCard tests**

In `frontend/src/components/__tests__/components.test.jsx`, append inside the `describe('WineCard', ...)` block:

```javascript
describe('WineCard feedback thumbs', () => {
  it('renders thumb buttons when onVote is provided', () => {
    render(<WineCard wine={wine} onVote={() => {}} vote={null} />);
    expect(screen.getByTitle('Good pick')).toBeInTheDocument();
    expect(screen.getByTitle('Not for me')).toBeInTheDocument();
  });

  it('does not render thumb buttons when onVote is absent', () => {
    render(<WineCard wine={wine} />);
    expect(screen.queryByTitle('Good pick')).not.toBeInTheDocument();
  });

  it('calls onVote with "up" when up thumb is clicked', () => {
    const onVote = vi.fn();
    render(<WineCard wine={wine} onVote={onVote} vote={null} />);
    fireEvent.click(screen.getByTitle('Good pick'));
    expect(onVote).toHaveBeenCalledWith('up');
  });

  it('calls onVote with "down" when down thumb is clicked', () => {
    const onVote = vi.fn();
    render(<WineCard wine={wine} onVote={onVote} vote={null} />);
    fireEvent.click(screen.getByTitle('Not for me'));
    expect(onVote).toHaveBeenCalledWith('down');
  });

  it('thumb click does not bubble to card onClick', () => {
    const onVote = vi.fn();
    const onClick = vi.fn();
    render(<WineCard wine={wine} onClick={onClick} onVote={onVote} vote={null} />);
    fireEvent.click(screen.getByTitle('Good pick'));
    expect(onVote).toHaveBeenCalled();
    expect(onClick).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd frontend
npm run test:run
```

Expected: 5 new failures about missing thumb buttons.

- [ ] **Step 4: Add `postFeedback` to `frontend/src/lib/api.js`**

Append to `frontend/src/lib/api.js`:

```javascript
export function postFeedback(payload) {
  fetch(`${BASE}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => {});
}
```

- [ ] **Step 5: Update `frontend/src/components/WineCard.jsx`**

Replace the entire file with:

```jsx
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import Tag from './Tag.jsx';

const _THUMB_EASE = 'all 140ms cubic-bezier(.25,.46,.45,.94)';

function ThumbBtn({ direction, voted, onClick }) {
  const title = direction === 'up' ? 'Good pick' : 'Not for me';
  const Icon  = direction === 'up' ? ThumbsUp : ThumbsDown;
  return (
    <button
      type="button"
      title={title}
      onClick={e => { e.stopPropagation(); onClick(direction); }}
      style={{
        cursor: 'pointer',
        width: 26, height: 26,
        borderRadius: 2,
        border: voted ? '1px solid var(--brass)' : '1px solid var(--border)',
        background: voted ? 'var(--brass)' : 'transparent',
        color: voted ? 'var(--cream)' : 'var(--faded)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: _THUMB_EASE,
        padding: 0,
      }}
    >
      <Icon size={12} strokeWidth={1.75} />
    </button>
  );
}

export default function WineCard({ wine, onClick, vote, onVote }) {
  return (
    <div
      onClick={onClick}
      style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', cursor: onClick ? 'pointer' : 'default', transition: 'transform .18s var(--ease), box-shadow .18s var(--ease)' }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-card)'; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      <div style={{ padding: '13px 14px', borderBottom: '0.75px solid var(--brass)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          {wine.tagline && (
            <div style={{ fontSize: 9.5, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--faded)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {wine.tagline}
            </div>
          )}
          {wine.coord && (
            <div style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 4 }}>{wine.coord}</div>
          )}
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--bordeaux)', flex: 'none' }}>${wine.price}</div>
      </div>
      <div style={{ padding: '13px 14px 14px' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 23, lineHeight: 1.05, color: 'var(--ink)' }}>{wine.name}</div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-2)', marginTop: 3 }}>{wine.retailer}</div>
        {wine.flavors?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, marginTop: 11, flexWrap: 'wrap' }}>
            {wine.flavors.map(t => <Tag key={t}>{t}</Tag>)}
          </div>
        )}
      </div>
      {onVote && (
        <div style={{ padding: '7px 12px 10px', borderTop: '0.75px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
          <ThumbBtn direction="up"   voted={vote === 'up'}   onClick={onVote} />
          <ThumbBtn direction="down" voted={vote === 'down'} onClick={onVote} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Wire up `wineVotes` and `sessionId` in `ChatRecommend.jsx`**

Add these imports at the top of `frontend/src/screens/ChatRecommend.jsx`:

```javascript
import { postFeedback } from '../lib/api.js';
```

Add these state declarations inside `ChatRecommend` (after existing state, before hooks):

```javascript
const [sessionId]  = useState(() => crypto.randomUUID());
const [wineVotes,  setWineVotes]  = useState({});
```

Add this handler function inside `ChatRecommend` (after `handleFollowup`):

```javascript
function handleWineVote(wineId, direction) {
  const current = wineVotes[wineId] ?? null;
  const next    = current === direction ? null : direction;
  setWineVotes(prev => ({ ...prev, [wineId]: next }));
  postFeedback({ type: 'wine_card', entity_id: wineId, vote: next, session_id: sessionId, zip: prefs.zip });
}
```

In the WineCard render inside the picks grid, change:

```jsx
<WineCard
  key={pick.wine_id}
  wine={pick}
  onClick={() => navigate('/wine/' + pick.wine_id, {
    state: {
      pick,
      chatState: { messages, picks, prefs, apiReq },
    },
  })}
/>
```

to:

```jsx
<WineCard
  key={pick.wine_id}
  wine={pick}
  vote={wineVotes[pick.wine_id] ?? null}
  onVote={direction => handleWineVote(pick.wine_id, direction)}
  onClick={() => navigate('/wine/' + pick.wine_id, {
    state: {
      pick,
      chatState: { messages, picks, prefs, apiReq },
    },
  })}
/>
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd frontend
npm run test:run
```

Expected: all previous tests pass + 5 new WineCard thumb tests pass (total ≥ 64).

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
        frontend/src/components/WineCard.jsx \
        frontend/src/lib/api.js \
        frontend/src/screens/ChatRecommend.jsx \
        frontend/src/components/__tests__/components.test.jsx
git commit -m "feat: Pattern A thumbs on wine cards + postFeedback API call"
```

---

### Task 3: Frontend Pattern B — thumbs on sommelier message + follow-up bubble

**Files:**
- Modify: `frontend/src/screens/ChatRecommend.jsx` (add message IDs, `messageVotes` state, feedback row on `SommelierBubble`, follow-up append)
- Modify: `frontend/src/screens/__tests__/ChatRecommend.test.jsx` (add Pattern B tests)

**Interfaces:**
- Consumes: `postFeedback` from Task 2, `sessionId` state from Task 2
- Consumes: `SommelierBubble` local component — extend to accept `vote`, `onVote` props
- Produces: each message in `messages` array gains an `id: string` field and optional `noFeedback: boolean`

- [ ] **Step 1: Write the failing Pattern B tests**

In `frontend/src/screens/__tests__/ChatRecommend.test.jsx`, add after existing tests:

```javascript
it('shows "Was this useful?" row under sommelier messages', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are your picks.' };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Here are your picks.')).toBeInTheDocument());
  expect(screen.getByText('Was this useful?')).toBeInTheDocument();
});

it('appends follow-up bubble on thumbs-down of sommelier message', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are your picks.' };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Was this useful?')).toBeInTheDocument());
  await userEvent.click(screen.getByTitle('Not helpful'));
  expect(screen.getByText(/what didn't land/i)).toBeInTheDocument();
});

it('does not append a second follow-up when toggling thumbs-down off', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are your picks.' };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Was this useful?')).toBeInTheDocument());
  await userEvent.click(screen.getByTitle('Not helpful'));
  await userEvent.click(screen.getByTitle('Not helpful')); // toggle off
  expect(screen.getAllByText(/what didn't land/i)).toHaveLength(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend
npm run test:run
```

Expected: 3 new failures — no feedback row rendered yet on SommelierBubble.

- [ ] **Step 3: Update `SommelierBubble` and `ChatRecommend.jsx`**

In `ChatRecommend.jsx`, replace the `SommelierBubble` component definition with:

```jsx
function SommelierBubble({ children, vote, onVote }) {
  return (
    <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 14 }}>
      <div style={{ width: 32, height: 32, borderRadius: '50%', flex: 'none', background: 'var(--bordeaux)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Stamp size={20} reversed />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ background: 'var(--cream-raised)', border: '1px solid var(--border)', borderRadius: '4px 14px 14px 14px', padding: '13px 15px', fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.55, color: 'var(--ink-2)' }}>
          {children}
        </div>
        {onVote && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, paddingLeft: 4 }}>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.06em', color: 'var(--faded)' }}>Was this useful?</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {[['up', ThumbsUp, 'Helpful', 'var(--sage)'], ['down', ThumbsDown, 'Not helpful', 'var(--bordeaux)']].map(([dir, Icon, label, activeColor]) => (
                <button
                  key={dir}
                  type="button"
                  title={label}
                  onClick={e => { e.stopPropagation(); onVote(dir); }}
                  style={{
                    cursor: 'pointer',
                    width: 24, height: 24,
                    borderRadius: 2,
                    border: vote === dir ? `1px solid ${activeColor}` : '1px solid var(--border)',
                    background: vote === dir ? activeColor : 'transparent',
                    color: vote === dir ? 'var(--cream)' : 'var(--faded)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 140ms cubic-bezier(.25,.46,.45,.94)',
                    padding: 0,
                  }}
                >
                  <Icon size={11} strokeWidth={1.75} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

Add the Lucide import at the top of `ChatRecommend.jsx`:

```javascript
import { ThumbsUp, ThumbsDown } from 'lucide-react';
```

- [ ] **Step 4: Add message IDs and `messageVotes` state to `ChatRecommend`**

Add state declaration (after `wineVotes` from Task 2):

```javascript
const [messageVotes, setMessageVotes] = useState({});
```

Update every place messages are pushed to add `id: crypto.randomUUID()`. There are three places:

**1. Initial user message** (in `useEffect`):
```javascript
setMessages([{ id: crypto.randomUUID(), role: 'user', text: parts.join(' · ') }]);
```

**2. First sommelier token** (in `callRecommend`):
```javascript
setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'sommelier', text: event.text }]);
```

**3. Follow-up user message** (in `handleFollowup`):
```javascript
setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', text }]);
```

Add the message vote handler function inside `ChatRecommend` (after `handleWineVote`):

```javascript
function handleMessageVote(messageId, direction) {
  const current = messageVotes[messageId] ?? null;
  const next    = current === direction ? null : direction;
  setMessageVotes(prev => ({ ...prev, [messageId]: next }));
  if (direction === 'down' && current !== 'down') {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role: 'sommelier',
      text: "Noted — what didn't land? The **grape variety**, the **price point**, or the **region**?",
      noFeedback: true,
    }]);
  }
  postFeedback({ type: 'sommelier_message', entity_id: messageId, vote: next, session_id: sessionId, zip: prefs.zip });
}
```

- [ ] **Step 5: Update the message render loop to pass feedback props**

In `ChatRecommend.jsx`, replace the message render loop:

```jsx
{messages.map((m, i) =>
  m.role === 'user'
    ? <UserBubble key={i}>{m.text}</UserBubble>
    : <SommelierBubble key={i}>
        {m.text.split('\n\n').map((para, j) => (
          <p key={j} style={{ margin: j > 0 ? '10px 0 0' : 0 }}>
            {para.split(/\*\*([^*]+)\*\*/g).map((part, k) =>
              k % 2 === 1
                ? <strong key={k} style={{ fontFamily: 'var(--font-serif)', fontWeight: 600 }}>{part}</strong>
                : part
            )}
          </p>
        ))}
      </SommelierBubble>
)}
```

with:

```jsx
{messages.map((m, i) =>
  m.role === 'user'
    ? <UserBubble key={m.id ?? i}>{m.text}</UserBubble>
    : <SommelierBubble
        key={m.id ?? i}
        vote={messageVotes[m.id] ?? null}
        onVote={m.noFeedback ? undefined : dir => handleMessageVote(m.id, dir)}
      >
        {m.text.split('\n\n').map((para, j) => (
          <p key={j} style={{ margin: j > 0 ? '10px 0 0' : 0 }}>
            {para.split(/\*\*([^*]+)\*\*/g).map((part, k) =>
              k % 2 === 1
                ? <strong key={k} style={{ color: 'var(--bordeaux)' }}>{part}</strong>
                : part
            )}
          </p>
        ))}
      </SommelierBubble>
)}
```

Note: the bold parts in the follow-up bubble now render in `var(--bordeaux)` per the design spec (changed from `fontFamily: 'var(--font-serif)', fontWeight: 600` to `color: 'var(--bordeaux)'`).

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd frontend
npm run test:run
```

Expected: all previous + 3 new Pattern B tests pass.

- [ ] **Step 7: Run full suite (backend + frontend) for regressions**

```bash
cd backend && python3 -m pytest tests/ -m "not integration" -v
cd ../frontend && npm run test:run
```

Expected: both pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/screens/ChatRecommend.jsx \
        frontend/src/screens/__tests__/ChatRecommend.test.jsx
git commit -m "feat: Pattern B thumbs on sommelier messages + follow-up bubble on thumbs-down"
```

---

## Self-Review

**Spec coverage:**
- Pattern A (thumbs on wine card, brass fill, 26×26px, stop-propagation): ✅ Task 2
- Pattern B (thumbs on sommelier message, sage/bordeaux fill, 24×24px, "Was this useful?" label): ✅ Task 3
- Follow-up bubble text exact match, appended on first down vote only: ✅ Task 3
- Toggle behavior (click same → deselect, click opposite → switch): ✅ Task 2 + 3 handlers
- `POST /api/feedback` endpoint with `{"ok": true}` response: ✅ Task 1
- Upsert on (session_id, entity_id, type): ✅ Task 1 migration UNIQUE + router upsert
- Fire-and-forget (no loading state): ✅ Task 2 `postFeedback` uses `.catch(() => {})`
- `noFeedback` flag prevents follow-up bubble from showing feedback row: ✅ Task 3
- Bold words in follow-up bubble render in `var(--bordeaux)`: ✅ Task 3
- Pattern C (session close bar): deprioritized per README, not included ✅

**Placeholder scan:** None.

**Type consistency:** `vote: 'up'|'down'|null` — consistent across WineCard props, ChatRecommend state, FeedbackRequest schema, and DB CHECK constraint.
