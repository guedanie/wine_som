import { useState, useEffect, useRef } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import Stamp from './Stamp.jsx';
import WineGlassLoader from './WineGlassLoader.jsx';
import useIsMobile from '../lib/useIsMobile.js';
import uuid from '../lib/uuid.js';
import Tag from './Tag.jsx';
import { streamSomm, postFeedback } from '../lib/api.js';

const _EASE = 'all 140ms cubic-bezier(.25,.46,.45,.94)';

const CHIPS_RED = [
  'Is this a good vintage?',
  'Should I decant it?',
  'What food pairs?',
  'Cellar potential?',
  'Cheaper alternative?',
];
const CHIPS_WHITE = [
  'Serve temperature?',
  'Drink now or wait?',
  'What food pairs?',
  'Similar styles?',
  'Cheaper alternative?',
];

function isWhiteStyle(wineType) {
  const t = (wineType ?? '').toLowerCase();
  return t.includes('white') || t.includes('rosé') || t.includes('rose') || t.includes('sparkling') || t.includes('orange');
}

function initialChips(wine) {
  const base = isWhiteStyle(wine.wine_type) ? CHIPS_WHITE : CHIPS_RED;
  return base.map(c =>
    wine.vintage ? c.replace('this a good vintage', `${wine.vintage} a good year`) : c
  );
}

function ThumbBtn({ direction, voted, onClick }) {
  const Icon = direction === 'up' ? ThumbsUp : ThumbsDown;
  const label = direction === 'up' ? 'Helpful' : 'Not helpful';
  const activeColor = direction === 'up' ? 'var(--sage)' : 'var(--bordeaux)';
  return (
    <button
      type="button"
      title={label}
      onClick={e => { e.stopPropagation(); onClick(direction); }}
      style={{
        cursor: 'pointer', width: 24, height: 24, borderRadius: 2,
        border: voted ? `1px solid ${activeColor}` : '1px solid var(--border)',
        background: voted ? activeColor : 'transparent',
        color: voted ? 'var(--cream)' : 'var(--faded)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: _EASE, padding: 0,
      }}
    >
      <Icon size={11} strokeWidth={1.75} />
    </button>
  );
}

function SommelierBubble({ children, vote, onVote }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12 }}>
      <Stamp size={28} reversed />
      <div style={{ flex: 1 }}>
        <div style={{ background: 'var(--cream-raised)', border: '1px solid var(--border)', borderRadius: '4px 12px 12px 12px', padding: '11px 13px', fontFamily: 'var(--font-sans)', fontSize: 13, lineHeight: 1.55, color: 'var(--ink-2)' }}>
          {children}
        </div>
        {onVote && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 5, paddingLeft: 4 }}>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.06em', color: 'var(--faded)' }}>Was this useful?</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <ThumbBtn direction="up"   voted={vote === 'up'}   onClick={onVote} />
              <ThumbBtn direction="down" voted={vote === 'down'} onClick={onVote} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function UserBubble({ children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <div style={{ background: 'var(--bordeaux)', color: 'var(--cream)', borderRadius: '12px 4px 12px 12px', padding: '10px 13px', fontSize: 13, lineHeight: 1.5, maxWidth: '80%' }}>
        {children}
      </div>
    </div>
  );
}

export default function SommOverlay({ wine }) {
  const isMobile = useIsMobile();
  const [open,         setOpen]         = useState(false);
  const [messages,     setMessages]     = useState([]);
  const [messageVotes, setMessageVotes] = useState({});
  const [sessionId]                     = useState(() => uuid());
  const [chips,        setChips]        = useState(() => initialChips(wine));
  const [loading,      setLoading]      = useState(false);
  const [input,        setInput]        = useState('');
  const scrollRef = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // Fire opening message on first open
  useEffect(() => {
    if (open && messages.length === 0) {
      callSomm('');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function callSomm(message) {
    if (loading) return;
    const history = messages
      .filter(m => !m.noFeedback)
      .map(m => ({ role: m.role === 'sommelier' ? 'assistant' : 'user', content: m.text }));

    setLoading(true);
    let firstToken = true;
    try {
      for await (const event of streamSomm({ wine, message, history })) {
        if (event.type === 'token') {
          if (firstToken) {
            firstToken = false;
            setLoading(false);
            setMessages(prev => [...prev, { id: uuid(), role: 'sommelier', text: event.text }]);
          } else {
            setMessages(prev => {
              const msgs = [...prev];
              msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], text: msgs[msgs.length - 1].text + event.text };
              return msgs;
            });
          }
        } else if (event.type === 'error') {
          setLoading(false);
          setMessages(prev => [...prev, {
            id: uuid(),
            role: 'sommelier',
            text: "I'm having trouble connecting right now. Try again in a moment.",
            noFeedback: true,
          }]);
          return;
        }
      }
    } catch {}
    setLoading(false);
  }

  function handleSend(text) {
    if (!text.trim() || loading) return;
    setMessages(prev => [...prev, { id: uuid(), role: 'user', text }]);
    setInput('');
    callSomm(text);
  }

  function handleChip(chip) {
    setChips(prev => prev.filter(c => c !== chip));
    handleSend(chip);
  }

  function handleMessageVote(messageId, direction) {
    const current = messageVotes[messageId] ?? null;
    const next = current === direction ? null : direction;
    setMessageVotes(prev => ({ ...prev, [messageId]: next }));
    if (direction === 'down' && current !== 'down') {
      setMessages(prev => [...prev, {
        id: uuid(),
        role: 'sommelier',
        text: "Noted — what didn't land? The **grape variety**, the **price point**, or the **region**?",
        noFeedback: true,
      }]);
    }
    postFeedback({ type: 'sommelier_message', entity_id: messageId, vote: next, session_id: sessionId });
  }

  const subtitle = [wine.producer, wine.vintage, wine.store].filter(Boolean).join(' · ');

  return (
    <>
      {/* FAB */}
      {!open && (
        <button
          aria-label="Ask Somm"
          onClick={() => setOpen(true)}
          style={{
            position: 'fixed', bottom: isMobile ? 'calc(76px + env(safe-area-inset-bottom, 0px))' : 32, right: isMobile ? 18 : 36, zIndex: 200,
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--bordeaux)', color: 'var(--cream)',
            border: 'none', borderRadius: 0, cursor: 'pointer',
            padding: '12px 20px 12px 14px',
            fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.04em',
            boxShadow: '0 4px 20px rgba(110,16,35,0.38)',
            transition: _EASE,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bordeaux-deep)'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 28px rgba(110,16,35,0.46)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--bordeaux)'; e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 4px 20px rgba(110,16,35,0.38)'; }}
        >
          <Stamp size={24} reversed />
          Ask Somm
        </button>
      )}

      {/* Backdrop dim */}
      {open && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.12)', pointerEvents: 'none', zIndex: 198 }} />
      )}

      {/* Panel */}
      {open && <div style={isMobile ? {
        position: 'fixed', bottom: 0, left: 0, right: 0, height: '62%',
        background: 'var(--cream)', borderTop: '1.5px solid var(--ink)',
        display: 'flex', flexDirection: 'column', zIndex: 199,
      } : {
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 400,
        background: 'var(--cream)', borderLeft: '1.5px solid var(--ink)',
        display: 'flex', flexDirection: 'column', zIndex: 199,
      }}>
        {/* Context strip */}
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)', background: 'var(--paper)' }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 8.5, letterSpacing: '0.26em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 4 }}>Discussing</div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--ink)', lineHeight: 1.1 }}>{wine.wine_name}</div>
          {subtitle && (
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 3 }}>{subtitle}</div>
          )}
          {wine.price && (
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, color: 'var(--bordeaux)', marginTop: 2 }}>${wine.price}</div>
          )}
          {wine.tags?.length > 0 && (
            <div style={{ display: 'flex', gap: 5, marginTop: 8, flexWrap: 'wrap' }}>
              {wine.tags.slice(0, 3).map(t => <Tag key={t}>{t}</Tag>)}
            </div>
          )}
        </div>

        {/* Panel title bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 18px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <Stamp size={26} reversed />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>Somm</span>
          </div>
          <button
            title="Close"
            onClick={() => setOpen(false)}
            style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 18, color: 'var(--faded)', padding: '2px 6px', lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        {/* Chat scroll */}
        <div ref={scrollRef} style={{ flex: 1, overflow: 'auto', padding: '16px 18px' }}>
          {messages.map((m, i) =>
            m.role === 'user'
              ? <UserBubble key={m.id ?? i}>{m.text}</UserBubble>
              : <SommelierBubble
                  key={m.id ?? i}
                  vote={messageVotes[m.id] ?? null}
                  onVote={m.noFeedback ? undefined : dir => handleMessageVote(m.id, dir)}
                >
                  {m.text.split('\n\n').map((para, j) => (
                    <p key={j} style={{ margin: j > 0 ? '8px 0 0' : 0 }}>
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
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12 }}>
              <Stamp size={28} reversed />
              <WineGlassLoader />
            </div>
          )}
        </div>

        {/* Suggestion chips */}
        {chips.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '8px 18px 4px', borderTop: '1px solid var(--border)' }}>
            {chips.map(c => (
              <button key={c} onClick={() => handleChip(c)} disabled={loading}
                style={{ cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.4 : 1, fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none', borderRadius: 999, padding: '5px 13px', transition: _EASE }}>
                {c}
              </button>
            ))}
          </div>
        )}

        {/* Composer */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 18px 16px' }}>
          <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && input.trim()) handleSend(input.trim()); }}
              placeholder="Ask about this wine…"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: isMobile ? 16 : 13, color: 'var(--ink)', padding: '10px 12px' }}
            />
            <button
              onClick={() => handleSend(input.trim())}
              disabled={loading || !input.trim()}
              style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 14px', cursor: (loading || !input.trim()) ? 'default' : 'pointer', opacity: (loading || !input.trim()) ? 0.4 : 1, fontSize: 15, borderRadius: 0 }}>
              →
            </button>
          </div>
        </div>
      </div>}
    </>
  );
}
