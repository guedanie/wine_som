// frontend/src/screens/ChatRecommend.jsx
import { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate, Navigate } from 'react-router-dom';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import Eyebrow from '../components/Eyebrow.jsx';
import Btn from '../components/Btn.jsx';
import Stamp from '../components/Stamp.jsx';
import WineCard from '../components/WineCard.jsx';
import WineGlassLoader from '../components/WineGlassLoader.jsx';
import WineCardSkeleton from '../components/WineCardSkeleton.jsx';
import CompareFrame from '../components/CompareFrame.jsx';
import { streamRecommend, postFeedback, getNearbyStores } from '../lib/api.js';
import { buildAskReq, ASK_INTENT_PILLS } from '../lib/askMode.js';
import { loadZip, saveZip } from '../lib/useIsMobile.js';
import { naturalChatMode } from '../lib/flags.js';
import { track } from '../lib/analytics.js';
import { useAuth } from '../lib/auth.jsx';
import { buildTasteContext } from '../lib/taste.js';
import { deriveWineCardMeta } from '../lib/regions.js';
import { formatMiles } from '../lib/format.js';
import PriceMarker from '../components/PriceMarker.jsx';
import useIsMobile from '../lib/useIsMobile.js';
import uuid from '../lib/uuid.js';

// item 38: the latest chat session, cached so browser back / refresh on the
// SAME run restores instead of re-firing Sonnet. Keyed by the submission's
// reqId — a fresh submission has a new reqId and never matches.
const CHAT_CACHE_KEY = 'somm_chat_cache';
function loadCachedSession(reqId) {
  if (!reqId) return null;
  try {
    const parsed = JSON.parse(sessionStorage.getItem(CHAT_CACHE_KEY));
    return parsed?.reqId === reqId ? parsed.chatState : null;
  } catch { return null; }
}

const DEFAULT_FOLLOWUPS = ["Anything from Burgundy?", "What about under $30?", "Something to cellar"];

function SommelierBubble({ children, vote, onVote }) {
  return (
    <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 14 }}>
      <Stamp size={32} reversed />
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

// The deterministic availability strip: counted truth in system voice, set
// apart from the sommelier's prose. Eyebrow type only — no emoji, no colors,
// no box (frontend/CLAUDE.md).
function AvailabilityStrip({ lines }) {
  if (!lines?.length) return null;
  return (
    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 3 }}>
      {lines.map((l, i) => (
        <span key={i} className="t-eyebrow" style={{ lineHeight: 1.5 }}>{l}</span>
      ))}
    </div>
  );
}

function UserBubble({ children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
      <div style={{ background: 'var(--bordeaux)', color: 'var(--cream)', borderRadius: '14px 4px 14px 14px', padding: '11px 15px', fontSize: 14, lineHeight: 1.5, maxWidth: '78%' }}>
        {children}
      </div>
    </div>
  );
}

// Option C (mobile): each wine is a conversational message — the sommelier's
// note (why) leads, then a tappable wine-name link with inline price + store
// pill. No card chrome; the wine name is the CTA.
function PickMessage({ pick, vote, onVote, onClick }) {
  const price = pick.price != null ? `$${Number(pick.price).toFixed(0)}` : null;
  const hasRating = pick.vivino_rating && pick.vivino_ratings_count > 0;
  const ratingCount = pick.vivino_ratings_count >= 1000
    ? `${Math.round(pick.vivino_ratings_count / 1000)}k`
    : pick.vivino_ratings_count;
  return (
    <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 14 }}>
      <Stamp size={32} reversed />
      <div style={{ flex: 1 }}>
        <div style={{ background: 'var(--cream-raised)', border: '1px solid var(--border)', borderRadius: '4px 14px 14px 14px', padding: '13px 15px' }}>
          {pick.why && (
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12.5, lineHeight: 1.6, color: 'var(--ink-2)' }}>{pick.why}</div>
          )}
          <div style={{ marginTop: pick.why ? 9 : 0, paddingTop: pick.why ? 8 : 0, borderTop: pick.why ? '0.75px solid var(--border)' : 'none', display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" onClick={onClick}
              style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--bordeaux)', background: 'none', border: 'none', borderBottom: '1.5px solid var(--brass)', padding: 0, cursor: 'pointer', lineHeight: 1.1 }}>
              {pick.name}<span style={{ color: 'var(--brass)', fontFamily: 'var(--font-sans)', fontSize: 12, marginLeft: 3 }}>→</span>
            </button>
            {price && <span style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--ink)' }}>{price}</span>}
            {pick.retailer && (
              <span style={{ borderRadius: 999, border: '0.75px solid var(--sage)', color: 'var(--sage)', fontFamily: 'var(--font-sans)', fontSize: 10.5, padding: '2px 9px' }}>
                ◎ {[pick.retailer, formatMiles(pick.distance_miles)].filter(Boolean).join(' · ')}
              </span>
            )}
            {pick.price_drop && <PriceMarker variant="drop" small amount={pick.price_drop.amount} />}
            {hasRating && (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, color: 'var(--brass)', whiteSpace: 'nowrap' }}
                title={`${pick.vivino_ratings_count.toLocaleString()} ratings on Vivino`}>
                {pick.vivino_rating.toFixed(1)}★ · {ratingCount}
              </span>
            )}
          </div>
        </div>
        {onVote && (
          <div style={{ display: 'flex', gap: 4, marginTop: 6, paddingLeft: 4 }}>
            {[['up', ThumbsUp, 'Helpful', 'var(--sage)'], ['down', ThumbsDown, 'Not helpful', 'var(--bordeaux)']].map(([dir, Icon, label, activeColor]) => (
              <button key={dir} type="button" title={label} aria-label={label}
                onClick={e => { e.stopPropagation(); onVote(dir); }}
                style={{ cursor: 'pointer', width: 24, height: 24, borderRadius: 2,
                  border: vote === dir ? `1px solid ${activeColor}` : '1px solid var(--border)',
                  background: vote === dir ? activeColor : 'transparent',
                  color: vote === dir ? 'var(--cream)' : 'var(--faded)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 140ms cubic-bezier(.25,.46,.45,.94)', padding: 0 }}>
                <Icon size={11} strokeWidth={1.75} />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatRecommend() {
  const { state }  = useLocation();
  const navigate   = useNavigate();
  const isMobile   = useIsMobile();
  const { user, ready } = useAuth();
  const { prefs, apiReq, reqId, _restored: _restoredNav } = state ?? {};
  // Navigation state wins (in-app back / patched history entry); the
  // sessionStorage cache covers refresh + PWA restarts on the same run.
  const _restored = _restoredNav ?? loadCachedSession(reqId);

  // Ask face (aisle mode): arriving without a plan-mode brief IS the ask face —
  // it opens clean, no sliders, no redirect. Derived only from route state, so
  // it's safe to compute before hooks.
  const askMode = state?.mode === 'ask' || _restored?.mode === 'ask' || (!prefs && !_restored);

  // Personalized recommendations: gather the user's liked/owned wines so the
  // scorer can boost + cite ("close to X you saved"). Null when signed out.
  // Fail-soft: a taste hiccup must never block the recommendation itself.
  const tasteFor = () => (user ? buildTasteContext(user.id).catch(() => null) : Promise.resolve(null));

  const [askZip, setAskZip]         = useState(() => _restored?.askZip ?? loadZip());
  const [zipConfirmed, setZipConfirmed] = useState(() => Boolean(_restored) || loadZip() != null);
  const [pendingAskText, setPendingAskText] = useState(null);
  const [zipDraft, setZipDraft]     = useState('');
  const [pickerOpen, setPickerOpen] = useState(() => Boolean(state?.openStorePicker));
  const [nearbyStores, setNearbyStores] = useState(null);
  const [storeRef, setStoreRef]     = useState(() => _restored?.storeRef ?? null);
  const [storeLabel, setStoreLabel] = useState(() => _restored?.storeLabel ?? null);
  const [sessionId]    = useState(() => _restored?.sessionId    ?? uuid());
  const [wineVotes,    setWineVotes]    = useState(() => _restored?.wineVotes    ?? {});
  const [messageVotes, setMessageVotes] = useState(() => _restored?.messageVotes ?? {});
  const [messages,   setMessages]  = useState(() => _restored?.messages ?? []);
  const [picks,      setPicks]     = useState(() => _restored?.picks    ?? []);
  const [followups,  setFollowups] = useState(() => _restored?.followups ?? DEFAULT_FOLLOWUPS);
  const [loading,    setLoading]   = useState(() => !_restored && !askMode);
  const [streaming,  setStreaming] = useState(false);
  const [statusText, setStatusText] = useState(null);
  const [error,      setError]     = useState(null);
  const [input,      setInput]     = useState('');

  // All hooks must be called before any early return. Wait for auth to resolve
  // (getSession is async) so a signed-in user's taste context is attached to the
  // FIRST recommendation instead of racing to null.
  const firedRef = useRef(false);
  const lastReqRef = useRef(null);
  useEffect(() => {
    if (!prefs || _restored || !ready || firedRef.current) return;
    firedRef.current = true;
    const parts = [];
    if (prefs.styles?.length)    parts.push(prefs.styles.join(', '));
    if (prefs.wineTypes?.length) parts.push(prefs.wineTypes.join(', '));
    if (prefs.grapes?.length)    parts.push(prefs.grapes.join(', '));
    parts.push('under $' + prefs.budget);
    parts.push(prefs.occasion.toLowerCase());
    if (prefs.freeText?.trim())  parts.push(prefs.freeText.trim());
    setMessages([{ id: uuid(), role: 'user', text: parts.join(' · ') }]);
    tasteFor().then(taste => callRecommend({ ...apiReq, taste }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  // Store picker data — fetched when the picker opens (strip entry or pill tap).
  useEffect(() => {
    if (!pickerOpen || nearbyStores != null || !askMode) return;
    getNearbyStores(askZip)
      .then(r => setNearbyStores(r.stores || []))
      .catch(() => setNearbyStores([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickerOpen]);

  // Persist the evolving session (item 38). Cheap, latest-run-only; the
  // try/catch covers private mode and jsdom's null sessionStorage.
  useEffect(() => {
    if (!messages.length) return;
    try {
      sessionStorage.setItem(CHAT_CACHE_KEY, JSON.stringify({
        reqId: reqId ?? null,
        chatState: { messages, picks, prefs, apiReq, sessionId, wineVotes, messageVotes,
                     followups, mode: askMode ? 'ask' : undefined, askZip, storeRef, storeLabel },
      }));
    } catch { /* private mode */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, picks, followups, wineVotes, messageVotes]);

  if (!prefs && !askMode) return <Navigate to="/" replace />;

  async function callRecommend(req) {
    setLoading(true);
    setStreaming(false);
    setError(null);
    let firstToken = true;
    let turnHadPicks = false;
    let errored = false;
    let sawToken = false;
    lastReqRef.current = req;
    try {
      for await (const event of streamRecommend(req)) {
        if (event.type === 'token') {
          sawToken = true;
          if (firstToken) {
            firstToken = false;
            setStatusText(null);
            setLoading(false);
            setStreaming(true);
            setMessages(prev => [...prev, { id: uuid(), role: 'sommelier', text: event.text }]);
          } else {
            setMessages(prev => {
              const msgs = [...prev];
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], text: msgs[msgs.length - 1].text + event.text };
              return msgs;
            });
          }
        } else if (event.type === 'status') {
          setStatusText(event.text);
        } else if (event.type === 'pick') {
          turnHadPicks = true;
          // Progressive card — render as soon as the model finishes this pick.
          // The final 'picks' event replaces the list wholesale, so any pick
          // reconciled away later disappears and nothing duplicates.
          const one = deriveWineCardMeta(event.pick);
          const appendPick = list => list.some(p => p.wine_id === one.wine_id) ? list : [...list, one];
          setPicks(appendPick);                       // desktop side panel
          setMessages(prev => {                       // mobile inline: attach to last sommelier msg
            const msgs = [...prev];
            for (let k = msgs.length - 1; k >= 0; k--) {
              if (msgs[k].role === 'sommelier') { msgs[k] = { ...msgs[k], picks: appendPick(msgs[k].picks ?? []) }; break; }
            }
            return msgs;
          });
        } else if (event.type === 'picks') {
          if (event.picks.length > 0) {
            turnHadPicks = true;
            const enriched = event.picks.map(deriveWineCardMeta);
            const isComparison = (event.comparison?.length ?? 0) >= 2 && enriched.length >= 2;
            track('recommendation_shown', { count: enriched.length });
            setPicks(enriched);                       // desktop side panel
            setMessages(prev => {                     // mobile inline: attach to last sommelier msg
              const msgs = [...prev];
              for (let k = msgs.length - 1; k >= 0; k--) {
                if (msgs[k].role === 'sommelier') { msgs[k] = { ...msgs[k], picks: enriched, comparison: isComparison }; break; }
              }
              return msgs;
            });
          }
        } else if (event.type === 'availability') {
          // The counted truth, rendered by us — visible even if the narrative
          // hedges or agrees with a false premise. Attaches to the last
          // sommelier message exactly like `picks` does.
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
        } else if (event.type === 'suggestions') {
          setFollowups(event.suggestions);
        } else if (event.type === 'error') {
          errored = true;
          setError(event.message);
        }
      }
    } catch (err) {
      errored = true;
      if (askMode) {
        // In-store failure: apologise in character, keep everything that
        // arrived, preserve the question for a one-tap retry.
        setMessages(prev => [...prev, {
          id: uuid(), role: 'sommelier', noFeedback: true,
          retry: sawToken ? 'finish' : 'again',
          text: "Lost you for a second — the signal in here is doing me no favors. Your question's saved; tap when you've got a bar or two.",
        }]);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
      setStreaming(false);
      setStatusText(null);
      // No-card closer (ask face): one offer converts an explanation into a
      // purchase without pretending cards were coming.
      if (askMode && !turnHadPicks && !errored) {
        setMessages(prev => [...prev, {
          id: uuid(), role: 'sommelier', offer: true, noFeedback: true,
          text: 'Want me to find you a good one here?',
        }]);
      }
    }
  }

  function handleWineVote(wineId, direction) {
    const current = wineVotes[wineId] ?? null;
    const next    = current === direction ? null : direction;
    setWineVotes(prev => ({ ...prev, [wineId]: next }));
    track('feedback_voted', { type: 'wine_card', vote: next });
    postFeedback({ type: 'wine_card', entity_id: wineId, vote: next, session_id: sessionId, user_id: user?.id ?? null, zip: prefs?.zip ?? askZip });
  }

  function handleMessageVote(messageId, direction) {
    const current = messageVotes[messageId] ?? null;
    const next    = current === direction ? null : direction;
    setMessageVotes(prev => ({ ...prev, [messageId]: next }));
    if (direction === 'down' && current !== 'down') {
      setMessages(prev => [...prev, {
        id: uuid(),
        role: 'sommelier',
        text: "Noted — what didn't land? The **grape variety**, the **price point**, or the **region**?",
        noFeedback: true,
      }]);
    }
    postFeedback({ type: 'sommelier_message', entity_id: messageId, vote: next, session_id: sessionId, user_id: user?.id ?? null, zip: prefs?.zip ?? askZip });
  }

  // item 41: history must carry the wines each turn actually showed — a
  // follow-up like "compare these two" is resolvable only from prior picks.
  const historyFrom = msgs => msgs.map(m => ({
    role: m.role, content: m.text,
    ...(m.picks?.length
      ? { picks: m.picks.map(p => ({ wine_id: p.wine_id, name: p.name })) }
      : {}),
  }));

  const handleFollowup = (text) => {
    if (loading || streaming || !text.trim()) return;
    const history = historyFrom(messages);
    setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
    tasteFor().then(taste => callRecommend({ ...apiReq, message: text, conversation_history: history, conversational: naturalChatMode(), taste }));
  };

  // Ask face send: wide-budget sentinel (no sliders in here), structured
  // store_ref when a standing store is set.
  const handleAskSend = (text) => {
    if (loading || streaming || !text.trim()) return;
    // Lazy location: the zip request arrives INSIDE the conversation, once,
    // only when no zip is actually stored (the loadZip default doesn't count).
    if (!zipConfirmed) {
      setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
      setPendingAskText(text);
      return;
    }
    const history = historyFrom(messages);
    setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
    tasteFor().then(taste => callRecommend(buildAskReq({
      zip: askZip, message: text, history: history.length ? history : undefined,
      storeRef, conversational: history.length > 0 && naturalChatMode(), taste,
    })));
  };

  const handleSend = askMode ? handleAskSend : handleFollowup;

  const confirmZip = () => {
    if (zipDraft.length !== 5) return;
    saveZip(zipDraft);
    setAskZip(zipDraft);
    setZipConfirmed(true);
    const text = pendingAskText;
    setPendingAskText(null);
    const history = historyFrom(messages.slice(0, -1));
    tasteFor().then(taste => callRecommend(buildAskReq({
      zip: zipDraft, message: text, history: history.length ? history : undefined,
      storeRef, conversational: false, taste,
    })));
  };

  const zipRequestBubble = pendingAskText != null && (
    <SommelierBubble>
      <div>I can name bottles you'll actually find tonight if you tell me roughly where you are.</div>
      <div style={{ marginTop: 10 }}>
        <span className="t-eyebrow" style={{ display: 'block', marginBottom: 6 }}>YOUR ZIP / CITY</span>
        <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
          <input value={zipDraft} inputMode="numeric" maxLength={5} aria-label="Your zip"
            onChange={e => setZipDraft(e.target.value.replace(/\D/g, '').slice(0, 5))}
            onKeyDown={e => { if (e.key === 'Enter') confirmZip(); }}
            style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', padding: '10px 12px', minWidth: 0 }} />
          <button onClick={confirmZip} style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 16px', cursor: 'pointer', fontSize: 14 }}>Set</button>
        </div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 6 }}>
          Asked once — I'll remember it from here on.
        </div>
      </div>
    </SommelierBubble>
  );

  // In-thread store picker — "I'm here, now." Store is a soft filter.
  const storePickerBubble = pickerOpen && askMode && (
    <SommelierBubble>
      <div>Which one are you standing in? I'll keep my answers to what's on their shelves.</div>
      <div style={{ marginTop: 10, border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
        {(nearbyStores ?? []).map((s, i) => (
          <button key={s.id} onClick={() => { setStoreRef(s.id); setStoreLabel(s.name); setPickerOpen(false); }}
            style={{ display: 'flex', width: '100%', alignItems: 'baseline', gap: 8, textAlign: 'left',
              cursor: 'pointer', background: 'none', border: 'none',
              borderTop: i ? '0.75px solid var(--border)' : 'none', padding: '11px 13px' }}>
            <span style={{ flex: 1, fontFamily: 'var(--font-sans)', fontSize: 13.5, color: 'var(--ink)', fontWeight: 500 }}>
              {s.name}
              {i === 0 && <span style={{ marginLeft: 8, fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--bordeaux)', fontWeight: 600 }}>closest</span>}
            </span>
            {s.distance_miles != null && (
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', whiteSpace: 'nowrap' }}>{s.distance_miles} mi</span>
            )}
          </button>
        ))}
        {nearbyStores == null && (
          <div style={{ padding: '11px 13px', fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>Finding stores near you…</div>
        )}
      </div>
      <button onClick={() => { setStoreRef(null); setStoreLabel(null); setPickerOpen(false); }}
        style={{ marginTop: 8, cursor: 'pointer', background: 'none', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 13px' }}>
        Somewhere else — just use my zip
      </button>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 8 }}>
        Store is a soft filter, not a cage — I'll still name a better bottle down the road if there is one.
      </div>
    </SommelierBubble>
  );

  // The standing location as editable pills, always visible above the composer.
  const contextPills = askMode && (
    <div style={{ display: 'flex', gap: 6, padding: '0 14px 8px', flexWrap: 'wrap' }}>
      <span style={{ borderRadius: 999, border: '0.75px solid var(--border-strong)', color: 'var(--ink-2)', fontFamily: 'var(--font-sans)', fontSize: 10.5, padding: '3px 10px' }}>◎ {askZip}</span>
      {storeLabel && (
        <button onClick={() => setPickerOpen(true)} style={{ cursor: 'pointer', borderRadius: 999, border: '0.75px solid var(--sage)', color: 'var(--sage)', background: 'none', fontFamily: 'var(--font-sans)', fontSize: 10.5, padding: '3px 10px' }}>
          ◎ {storeLabel} · change
        </button>
      )}
    </div>
  );

  // Ask empty state — the single invitation (deliberately generic: this door
  // knows no store).
  const askEmptyState = askMode && messages.length === 0 && !loading && (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '48px 24px 24px', gap: 14 }}>
      <Stamp size={46} reversed />
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--ink)' }}>
        What can I help you with?
      </div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.6, color: 'var(--faded)', maxWidth: 300 }}>
        Name a bottle, name two, ask what something is, or just tell me what you're eating. No sliders in here.
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 6 }}>
        {ASK_INTENT_PILLS.map(p => (
          <button key={p.label} onClick={() => setInput(p.fill)} style={{
            cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 12.5,
            color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none',
            borderRadius: 999, padding: '8px 15px', minHeight: 36,
          }}>{p.label}</button>
        ))}
      </div>
    </div>
  );

  // Picks arrive as one event only after the narrative finishes generating.
  // While the narrative streams (or before the first token) and picks are
  // still empty, show skeletons so users know bottles are coming — otherwise
  // the panel/sheet sits confusingly empty for a couple seconds.
  const awaitingPicks = (loading || streaming) && picks.length === 0;

  const navToWine = pick => {
    track('pick_opened', { wine_id: pick.wine_id, retailer: pick.retailer, source: 'chat' });
    const chatState = { messages, picks, prefs, apiReq, sessionId, wineVotes, messageVotes,
                        followups, mode: askMode ? 'ask' : undefined, askZip, storeRef, storeLabel };
    // Patch the CURRENT history entry before leaving, so the browser's own
    // back button (not just the in-app ←) restores the session instead of
    // re-firing the recommendation (item 38).
    navigate('/recommend', {
      replace: true,
      state: { prefs, apiReq, reqId, mode: askMode ? 'ask' : undefined, _restored: chatState },
    });
    navigate('/wine/' + pick.wine_id, { state: { pick, chatState } });
  };

  // Option C (mobile): the sommelier voice leads. When a message carries picks,
  // the bubble shows only the framing line and each wine becomes its own
  // conversational PickMessage (note + tappable name link + price + store pill).
  const renderBody = (text, i) =>
    text.split('\n\n').map((para, j) => (
      <p key={j} style={{ margin: j > 0 ? '10px 0 0' : 0 }}>
        {para.split(/\*\*([^*]+)\*\*/g).map((part, k) =>
          k % 2 === 1
            ? <strong key={k} style={{ color: 'var(--bordeaux)' }}>{part}</strong>
            : part
        )}
        {streaming && i === messages.length - 1 && j === text.split('\n\n').length - 1 && (
          <span style={{ display: 'inline-block', width: 2, height: 14, background: 'var(--bordeaux)', marginLeft: 2, verticalAlign: 'middle', animation: 'blink 0.9s step-end infinite' }} />
        )}
      </p>
    ));

  // While the answer is still streaming, hold back per-wine paragraphs (they
  // open with a bold **Wine Name** and are destined to become PickMessages) so
  // the bubble never collapses when the cards arrive. The first paragraph (the
  // framing line) always shows; a held paragraph in a no-picks answer reveals
  // at stream end — an addition, never a collapse.
  const holdWineParas = text => {
    const paras = text.split('\n\n');
    return [paras[0], ...paras.slice(1).filter(p => !p.trimStart().startsWith('**'))].join('\n\n');
  };

  // No-card closer buttons — shared by the mobile and desktop message renders.
  const offerButtons = (m) => m.offer && (
    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
      <button onClick={() => { setMessages(prev => prev.filter(x => x.id !== m.id)); handleAskSend('Yes — find me a good one nearby'); }}
        style={{ cursor: 'pointer', background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 14px' }}>Yes, find one</button>
      <button onClick={() => setMessages(prev => prev.map(x => x.id === m.id ? { ...x, offer: false, dismissed: true } : x))}
        style={{ cursor: 'pointer', background: 'none', color: 'var(--bordeaux)', border: '1.5px solid var(--bordeaux)', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 14px' }}>No thanks</button>
    </div>
  );

  const retryButton = (m) => m.retry && (
    <div style={{ marginTop: 10 }}>
      <button onClick={() => { setMessages(prev => prev.filter(x => x.id !== m.id)); if (lastReqRef.current) callRecommend(lastReqRef.current); }}
        style={{ cursor: 'pointer', background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 12.5, padding: '8px 14px' }}>
        {m.retry === 'finish' ? 'Finish the answer' : 'Ask again'}
      </button>
    </div>
  );

  const messageList = messages.flatMap((m, i) => {
    if (m.role === 'user') return [<UserBubble key={m.id ?? i}>{m.text}</UserBubble>];
    const hasPicks = m.picks?.length;
    const isLive = streaming && !hasPicks && i === messages.length - 1;
    // when picks exist, the intro bubble shows only the framing paragraph
    const introText = hasPicks ? (m.text.split('\n\n')[0] || m.text)
                    : isLive   ? holdWineParas(m.text)
                    : m.text;
    const intro = (
      <SommelierBubble
        key={m.id ?? i}
        vote={messageVotes[m.id] ?? null}
        onVote={m.noFeedback ? undefined : dir => handleMessageVote(m.id, dir)}
      >
        {renderBody(introText, i)}
        {offerButtons(m)}
        {retryButton(m)}
        <AvailabilityStrip lines={m.availability} />
      </SommelierBubble>
    );
    if (!hasPicks) return [intro];
    const compare = m.comparison && m.picks.length >= 2
      ? [<CompareFrame key={(m.id ?? i) + '-cmp'} picks={m.picks.slice(0, 2)} />]
      : [];
    const pickMsgs = m.picks.map(pick => (
      <PickMessage
        key={(m.id ?? i) + '-' + pick.wine_id}
        pick={pick}
        vote={wineVotes[pick.wine_id] ?? null}
        onVote={direction => handleWineVote(pick.wine_id, direction)}
        onClick={() => navToWine(pick)}
      />
    ));
    return [intro, ...compare, ...pickMsgs];
  });

  if (isMobile) {
    return (
      <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Chat scroll — Option C: each wine is a conversational message */}
        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overscrollBehavior: 'contain', padding: '16px 16px 8px', WebkitOverflowScrolling: 'touch' }}>
          {askEmptyState}
          {messageList}
          {zipRequestBubble}
          {storePickerBubble}
          {awaitingPicks && !loading && (
            <div style={{ display: 'flex', gap: 11, alignItems: 'center', marginBottom: 14, paddingLeft: 43 }}>
              <span className="t-eyebrow" style={{ animation: 'skeleton-pulse 1.4s ease-in-out infinite' }}>Pouring your picks…</span>
            </div>
          )}
          {loading && (
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 16 }}>
              <Stamp size={32} reversed />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <WineGlassLoader />
                {statusText && (
                  <span className="t-eyebrow" style={{ animation: 'skeleton-pulse 1.4s ease-in-out infinite' }}>
                    {statusText}
                  </span>
                )}
              </div>
            </div>
          )}
          {error && (
            <SommelierBubble>
              <div>{error}</div>
              <div style={{ marginTop: 10 }}>
                <Btn variant="ghost" onClick={() => navigate(-1)}>Try different preferences</Btn>
              </div>
            </SommelierBubble>
          )}
        </div>

        {/* Composer */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '10px 14px 12px', background: 'var(--cream)', flexShrink: 0, zIndex: 1, position: 'relative' }}>
          {contextPills}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
            {followups.map(f => (
              <button key={f} onClick={() => setInput(f)} disabled={loading || streaming}
                style={{ cursor: (loading || streaming) ? 'default' : 'pointer', opacity: (loading || streaming) ? 0.4 : 1, fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none', borderRadius: 999, padding: '7px 13px', minHeight: 34 }}>
                {f}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && input.trim()) { handleSend(input.trim()); setInput(''); } }}
              placeholder={askMode ? 'Ask the sommelier…' : 'Ask a follow-up…'}
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', padding: '11px 12px', minWidth: 0 }}
            />
            <button
              onClick={() => { if (input.trim()) { handleSend(input.trim()); setInput(''); } }}
              disabled={loading || streaming}
              aria-label="Send"
              style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 16px', cursor: (loading || streaming) ? 'default' : 'pointer', opacity: (loading || streaming) ? 0.4 : 1, fontSize: 18, minWidth: 48, borderRadius: 0 }}>
              →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 56px)' }}>
      {/* Chat panel */}
      <div style={{ width: '44%', borderRight: '1.5px solid var(--ink)', display: 'flex', flexDirection: 'column', background: 'var(--cream)' }}>
        <div style={{ padding: '20px 24px 14px', borderBottom: '1px solid var(--border)' }}>
          <Eyebrow>The sommelier</Eyebrow>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', marginTop: 4 }}>
            {askMode ? 'Ask me anything' : `Tonight, near ${prefs?.zip}`}
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '20px 24px' }}>
          {askEmptyState}
          {messages.map((m, i) =>
            m.role === 'user'
              ? <UserBubble key={m.id ?? i}>{m.text}</UserBubble>
              : <div key={m.id ?? i}>
                  <SommelierBubble
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
                    {offerButtons(m)}
                    {retryButton(m)}
                    <AvailabilityStrip lines={m.availability} />
                  </SommelierBubble>
                  {m.comparison && m.picks?.length >= 2 && <CompareFrame picks={m.picks.slice(0, 2)} />}
                </div>
          )}
          {zipRequestBubble}
          {storePickerBubble}
          {loading && (
            <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 14 }}>
              <Stamp size={32} reversed />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <WineGlassLoader />
                {statusText && (
                  <span className="t-eyebrow" style={{ animation: 'skeleton-pulse 1.4s ease-in-out infinite' }}>
                    {statusText}
                  </span>
                )}
              </div>
            </div>
          )}
          {error && (
            <SommelierBubble>
              <div>{error}</div>
              <div style={{ marginTop: 10 }}>
                <Btn variant="ghost" onClick={() => navigate(-1)}>Try different preferences</Btn>
              </div>
            </SommelierBubble>
          )}
        </div>

        {/* Follow-up composer */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '14px 24px 18px' }}>
          {contextPills}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {followups.map(f => (
              <button key={f} onClick={() => handleFollowup(f)} disabled={loading || streaming}
                style={{ cursor: (loading || streaming) ? 'default' : 'pointer', opacity: (loading || streaming) ? 0.4 : 1, fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none', borderRadius: 999, padding: '6px 12px' }}>
                {f}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && input.trim()) { handleSend(input.trim()); setInput(''); } }}
              placeholder={askMode ? 'Ask the sommelier…' : 'Ask a follow-up…'}
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)', padding: '11px 13px' }}
            />
            <button
              onClick={() => { if (input.trim()) { handleSend(input.trim()); setInput(''); } }}
              disabled={loading || streaming}
              style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 16px', cursor: (loading || streaming) ? 'default' : 'pointer', opacity: (loading || streaming) ? 0.4 : 1, fontSize: 16, borderRadius: 0 }}>
              →
            </button>
          </div>
        </div>
      </div>

      {/* Wine cards panel */}
      <div style={{ flex: 1, background: 'var(--paper)', overflow: 'auto', padding: '24px 28px' }}>
        {awaitingPicks && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 18 }}>
              <span className="t-eyebrow" style={{ animation: 'skeleton-pulse 1.4s ease-in-out infinite' }}>Pouring your picks…</span>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>within 10 mi · in stock</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {[0, 1, 2].map(i => <WineCardSkeleton key={i} variant="landscape" />)}
            </div>
          </>
        )}
        {picks.length > 0 && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 18 }}>
              <span className="t-eyebrow">{picks.length} wine{picks.length !== 1 ? 's' : ''} for you</span>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>within 10 mi · in stock</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {picks.map(pick => (
                <WineCard
                  key={pick.wine_id}
                  variant="landscape"
                  wine={pick}
                  vote={wineVotes[pick.wine_id] ?? null}
                  onVote={direction => handleWineVote(pick.wine_id, direction)}
                  onClick={() => navToWine(pick)}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
