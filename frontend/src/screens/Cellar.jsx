import { useState, useEffect, useCallback } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { listCellar, drinkBottle, removeBottle } from '../lib/cellar.js';
import { windowStatus } from '../lib/drinkingWindow.js';
import { postFeedback } from '../lib/api.js';
import AddBottleModal from '../components/AddBottleModal.jsx';
import useIsMobile from '../lib/useIsMobile.js';

const PHASE_COLOR = { hold: 'var(--faded)', ready: 'var(--sage)', soon: 'var(--bordeaux)', past: 'var(--bordeaux)' };

function BottleRow({ b, onDrink, onRemove }) {
  const ws = (b.drink_from || b.drink_to) ? windowStatus({ from: b.drink_from, to: b.drink_to }) : null;
  const sub = [b.region, b.purchase_date ? `bought ${b.purchase_date}` : null].filter(Boolean).join(' · ');
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 11, color: 'var(--faded)', minWidth: 36, flex: 'none' }}>{b.vintage ?? '—'}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {b.name}{b.quantity > 1 && <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginLeft: 8 }}>×{b.quantity}</span>}
        </div>
        {sub && <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 2 }}>{sub}</div>}
      </div>
      {/* drinking window */}
      <div style={{ width: 96, flex: 'none' }}>
        {ws && (
          <>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, color: PHASE_COLOR[ws.phase], textAlign: 'right', marginBottom: 4, whiteSpace: 'nowrap' }}>{ws.label}</div>
            <div style={{ height: 3, background: 'var(--paper)', border: '1px solid var(--border)' }}>
              <div style={{ height: '100%', width: `${ws.fill}%`, background: 'var(--brass)' }} />
            </div>
          </>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, flex: 'none' }}>
        <button onClick={() => onDrink(b)} title="Drank it" aria-label="Drank it"
          style={{ border: '1px solid var(--border)', background: 'none', color: 'var(--faded)', borderRadius: 0, padding: '5px 8px', fontFamily: 'var(--font-sans)', fontSize: 11, cursor: 'pointer' }}>
          Drank it
        </button>
        <button onClick={() => onRemove(b)} title="Remove" aria-label="Remove"
          style={{ border: '1px solid var(--border)', background: 'none', color: 'var(--faded)', borderRadius: 0, padding: '5px 8px', cursor: 'pointer' }}>
          ✕
        </button>
      </div>
    </div>
  );
}

export default function Cellar() {
  const { authState, user, requireSignIn } = useAuth();
  const isMobile = useIsMobile();
  const [bottles, setBottles] = useState(null);   // null = loading
  const [adding, setAdding] = useState(false);
  const [rating, setRating] = useState(null);     // { bottle } after "Drank it" → quick 👍/👎

  const refresh = useCallback(() => {
    if (!user) { setBottles([]); return; }
    listCellar(user.id).then(setBottles);
  }, [user]);
  useEffect(() => { refresh(); }, [refresh]);

  const pad = isMobile ? '18px 16px 48px' : '28px 36px 64px';

  if (authState !== 'signed_in') {
    return (
      <div style={{ maxWidth: 900, margin: '0 auto', padding: pad, textAlign: 'center' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 30, color: 'var(--ink)', marginTop: 40 }}>Your cellar.</div>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', maxWidth: 400, margin: '10px auto 20px', lineHeight: 1.6 }}>
          Sign in to track what you're holding — with a drinking window for each bottle so you know what to open when.
        </p>
        <button onClick={() => requireSignIn()}
          style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '12px 22px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
          Sign in with email
        </button>
      </div>
    );
  }

  const onDrink = async (b) => { await drinkBottle(user.id, b); refresh(); setRating({ bottle: b }); };
  const onRemove = async (b) => { await removeBottle(user.id, b.id); refresh(); };
  // Rate the wine you just drank → feeds the same personalization signal as chat
  // thumbs (only catalog bottles carry a wine_id to tie the feedback to).
  const rateDrunk = (vote) => {
    const b = rating?.bottle;
    if (b?.wine_id) {
      postFeedback({ type: 'wine_card', entity_id: b.wine_id, vote, session_id: `cellar-${user.id}`, user_id: user.id, zip: null });
    }
    setRating(null);
  };
  const count = bottles?.reduce((n, b) => n + (b.quantity || 1), 0) ?? 0;

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: pad }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600 }}>
            Cellar · {count} bottle{count !== 1 ? 's' : ''}
          </div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--ink)', marginTop: 4 }}>What you're holding</div>
        </div>
        <button onClick={() => setAdding(true)}
          style={{ background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '9px 16px', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, cursor: 'pointer', flex: 'none' }}>
          + Add bottle
        </button>
      </div>

      {bottles === null ? (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)' }}>Loading…</div>
      ) : bottles.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '44px 20px', border: '1px solid var(--border)' }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--ink)' }}>Nothing in your cellar yet.</div>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', maxWidth: 360, margin: '10px auto 18px', lineHeight: 1.6 }}>
            Add a bottle you've bought — from our catalog or anywhere — and I'll track its drinking window.
          </p>
          <button onClick={() => setAdding(true)}
            style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '11px 20px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
            Add a bottle
          </button>
        </div>
      ) : (
        <div style={{ border: '1.5px solid var(--ink)' }}>
          {bottles.map(b => <BottleRow key={b.id} b={b} onDrink={onDrink} onRemove={onRemove} />)}
        </div>
      )}

      {adding && (
        <AddBottleModal userId={user.id} onClose={() => setAdding(false)} onAdded={() => { setAdding(false); refresh(); }} />
      )}

      {/* Quick rate after "Drank it" — feeds personalization (like the chat thumbs) */}
      {rating && (
        <div role="dialog" aria-label="Rate the wine you drank"
          style={{ position: 'fixed', left: '50%', bottom: 24, transform: 'translateX(-50%)', zIndex: 90,
            display: 'flex', alignItems: 'center', gap: 14, background: 'var(--ink)', color: 'var(--cream)',
            border: '1px solid var(--ink)', padding: '12px 16px', boxShadow: '0 12px 40px rgba(0,0,0,0.3)',
            animation: 'toastUp 0.28s ease both', maxWidth: '92vw' }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            Enjoy the <span style={{ fontFamily: 'var(--font-serif)', fontSize: 15 }}>{rating.bottle.name}</span>?
          </span>
          {[['up', ThumbsUp, 'var(--sage)'], ['down', ThumbsDown, 'var(--bordeaux)']].map(([v, Icon, active]) => (
            <button key={v} onClick={() => rateDrunk(v)} aria-label={v === 'up' ? 'Loved it' : 'Not for me'}
              style={{ width: 32, height: 32, borderRadius: 2, border: '1px solid rgba(239,230,212,0.35)', background: 'transparent', color: 'var(--cream)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
              onMouseEnter={e => { e.currentTarget.style.background = active; e.currentTarget.style.borderColor = active; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(239,230,212,0.35)'; }}>
              <Icon size={15} strokeWidth={1.75} />
            </button>
          ))}
          <button onClick={() => setRating(null)} aria-label="Dismiss"
            style={{ background: 'none', border: 'none', color: 'rgba(239,230,212,0.6)', cursor: 'pointer', fontSize: 16, padding: '0 2px' }}>×</button>
        </div>
      )}
    </div>
  );
}
