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
import { streamRecommend, postFeedback } from '../lib/api.js';
import { naturalChatMode } from '../lib/flags.js';
import { track } from '../lib/analytics.js';
import { useAuth } from '../lib/auth.jsx';
import { buildTasteContext } from '../lib/taste.js';
import { deriveWineCardMeta } from '../lib/regions.js';
import { formatMiles } from '../lib/format.js';
import PriceMarker from '../components/PriceMarker.jsx';
import useIsMobile from '../lib/useIsMobile.js';
import uuid from '../lib/uuid.js';

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
  const { prefs, apiReq, _restored } = state ?? {};

  // Personalized recommendations: gather the user's liked/owned wines so the
  // scorer can boost + cite ("close to X you saved"). Null when signed out.
  // Fail-soft: a taste hiccup must never block the recommendation itself.
  const tasteFor = () => (user ? buildTasteContext(user.id).catch(() => null) : Promise.resolve(null));

  const [sessionId]    = useState(() => _restored?.sessionId    ?? uuid());
  const [wineVotes,    setWineVotes]    = useState(() => _restored?.wineVotes    ?? {});
  const [messageVotes, setMessageVotes] = useState(() => _restored?.messageVotes ?? {});
  const [messages,   setMessages]  = useState(() => _restored?.messages ?? []);
  const [picks,      setPicks]     = useState(() => _restored?.picks    ?? []);
  const [followups,  setFollowups] = useState(() => _restored?.followups ?? DEFAULT_FOLLOWUPS);
  const [loading,    setLoading]   = useState(() => !_restored);
  const [streaming,  setStreaming] = useState(false);
  const [statusText, setStatusText] = useState(null);
  const [error,      setError]     = useState(null);
  const [input,      setInput]     = useState('');

  // All hooks must be called before any early return. Wait for auth to resolve
  // (getSession is async) so a signed-in user's taste context is attached to the
  // FIRST recommendation instead of racing to null.
  const firedRef = useRef(false);
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

  if (!prefs) return <Navigate to="/" replace />;

  async function callRecommend(req) {
    setLoading(true);
    setStreaming(false);
    setError(null);
    let firstToken = true;
    try {
      for await (const event of streamRecommend(req)) {
        if (event.type === 'token') {
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
            const enriched = event.picks.map(deriveWineCardMeta);
            track('recommendation_shown', { count: enriched.length });
            setPicks(enriched);                       // desktop side panel
            setMessages(prev => {                     // mobile inline: attach to last sommelier msg
              const msgs = [...prev];
              for (let k = msgs.length - 1; k >= 0; k--) {
                if (msgs[k].role === 'sommelier') { msgs[k] = { ...msgs[k], picks: enriched }; break; }
              }
              return msgs;
            });
          }
        } else if (event.type === 'suggestions') {
          setFollowups(event.suggestions);
        } else if (event.type === 'error') {
          setError(event.message);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setStreaming(false);
      setStatusText(null);
    }
  }

  function handleWineVote(wineId, direction) {
    const current = wineVotes[wineId] ?? null;
    const next    = current === direction ? null : direction;
    setWineVotes(prev => ({ ...prev, [wineId]: next }));
    track('feedback_voted', { type: 'wine_card', vote: next });
    postFeedback({ type: 'wine_card', entity_id: wineId, vote: next, session_id: sessionId, user_id: user?.id ?? null, zip: prefs.zip });
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
    postFeedback({ type: 'sommelier_message', entity_id: messageId, vote: next, session_id: sessionId, user_id: user?.id ?? null, zip: prefs.zip });
  }

  const handleFollowup = (text) => {
    if (loading || streaming || !text.trim()) return;
    const history = messages.map(m => ({ role: m.role, content: m.text }));
    setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
    tasteFor().then(taste => callRecommend({ ...apiReq, message: text, conversation_history: history, conversational: naturalChatMode(), taste }));
  };

  // Picks arrive as one event only after the narrative finishes generating.
  // While the narrative streams (or before the first token) and picks are
  // still empty, show skeletons so users know bottles are coming — otherwise
  // the panel/sheet sits confusingly empty for a couple seconds.
  const awaitingPicks = (loading || streaming) && picks.length === 0;

  const navToWine = pick => {
    track('pick_opened', { wine_id: pick.wine_id, retailer: pick.retailer, source: 'chat' });
    navigate('/wine/' + pick.wine_id, {
      state: { pick, chatState: { messages, picks, prefs, apiReq, sessionId, wineVotes, messageVotes, followups } },
    });
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
      </SommelierBubble>
    );
    if (!hasPicks) return [intro];
    const pickMsgs = m.picks.map(pick => (
      <PickMessage
        key={(m.id ?? i) + '-' + pick.wine_id}
        pick={pick}
        vote={wineVotes[pick.wine_id] ?? null}
        onVote={direction => handleWineVote(pick.wine_id, direction)}
        onClick={() => navToWine(pick)}
      />
    ));
    return [intro, ...pickMsgs];
  });

  if (isMobile) {
    return (
      <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Chat scroll — Option C: each wine is a conversational message */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 8px', WebkitOverflowScrolling: 'touch' }}>
          {messageList}
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
              onKeyDown={e => { if (e.key === 'Enter' && input.trim()) { handleFollowup(input.trim()); setInput(''); } }}
              placeholder="Ask a follow-up…"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', padding: '11px 12px', minWidth: 0 }}
            />
            <button
              onClick={() => { if (input.trim()) { handleFollowup(input.trim()); setInput(''); } }}
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
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', marginTop: 4 }}>Tonight, near {prefs.zip}</div>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px' }}>
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
              onKeyDown={e => { if (e.key === 'Enter' && input.trim()) { handleFollowup(input.trim()); setInput(''); } }}
              placeholder="Ask a follow-up…"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)', padding: '11px 13px' }}
            />
            <button
              onClick={() => { if (input.trim()) { handleFollowup(input.trim()); setInput(''); } }}
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
