// frontend/src/screens/ChatRecommend.jsx
import { useState, useEffect } from 'react';
import { useLocation, useNavigate, Navigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Btn from '../components/Btn.jsx';
import Stamp from '../components/Stamp.jsx';
import WineCard from '../components/WineCard.jsx';
import { recommend } from '../lib/api.js';
import { deriveWineCardMeta } from '../lib/regions.js';

const FOLLOWUPS = ["Anything from Burgundy?", "What about under $30?", "Something to cellar"];

function SommelierBubble({ children }) {
  return (
    <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 14 }}>
      <div style={{ width: 32, height: 32, borderRadius: '50%', flex: 'none', background: 'var(--bordeaux)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Stamp size={20} reversed />
      </div>
      <div style={{ background: 'var(--cream-raised)', border: '1px solid var(--border)', borderRadius: '4px 14px 14px 14px', padding: '13px 15px', fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.55, color: 'var(--ink-2)' }}>
        {children}
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

export default function ChatRecommend() {
  const { state }  = useLocation();
  const navigate   = useNavigate();
  const { prefs, apiReq } = state ?? {};

  const [messages, setMessages] = useState([]);
  const [picks,    setPicks]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [input,    setInput]    = useState('');

  // All hooks must be called before any early return
  useEffect(() => {
    if (!prefs) return;
    setMessages([{ role: 'user', text: prefs.styles.join(', ') + ' · under $' + prefs.budget + ' · ' + prefs.occasion.toLowerCase() }]);
    callRecommend(apiReq);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!prefs) return <Navigate to="/" replace />;

  async function callRecommend(req) {
    setLoading(true);
    setError(null);
    try {
      const data = await recommend(req);
      setMessages(prev => [...prev, { role: 'sommelier', text: data.narrative }]);
      setPicks(data.picks.map(deriveWineCardMeta));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleFollowup = (text) => {
    if (loading || !text.trim()) return;
    const history = messages.map(m => ({ role: m.role, content: m.text }));
    setMessages(prev => [...prev, { role: 'user', text }]);
    callRecommend({ ...apiReq, message: text, conversation_history: history });
  };

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
              ? <UserBubble key={i}>{m.text}</UserBubble>
              : <SommelierBubble key={i}>
                  {m.text.split('\n\n').map((para, j) => (
                    <p key={j} style={{ margin: j > 0 ? '10px 0 0' : 0 }}>{para}</p>
                  ))}
                </SommelierBubble>
          )}
          {loading && <SommelierBubble>Finding the right bottles for you…</SommelierBubble>}
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
            {FOLLOWUPS.map(f => (
              <button key={f} onClick={() => handleFollowup(f)} disabled={loading}
                style={{ cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.4 : 1, fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: 'none', borderRadius: 999, padding: '6px 12px' }}>
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
              disabled={loading}
              style={{ border: 'none', background: 'var(--bordeaux)', color: 'var(--cream)', padding: '0 16px', cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.4 : 1, fontSize: 16, borderRadius: 0 }}>
              →
            </button>
          </div>
        </div>
      </div>

      {/* Wine cards panel */}
      <div style={{ flex: 1, background: 'var(--paper)', overflow: 'auto', padding: '24px 28px' }}>
        {picks.length > 0 && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 18 }}>
              <span className="t-eyebrow">{picks.length} wine{picks.length !== 1 ? 's' : ''} for you</span>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>within 10 mi · in stock</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 18 }}>
              {picks.map(pick => (
                <WineCard
                  key={pick.wine_id}
                  wine={pick}
                  onClick={() => navigate('/wine/' + pick.wine_id, { state: { pick } })}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
