import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';
import { listFavorites } from '../lib/favorites.js';
import WineCard from '../components/WineCard.jsx';
import useIsMobile from '../lib/useIsMobile.js';

// Turn a favorites row (joined to wines) into a WineCard-shaped object. No price
// here — the card links to the dossier, which shows current pricing/stores.
function toCard(row) {
  const w = row.wines || {};
  return {
    id: w.id ?? row.wine_id,
    name: w.name,
    tagline: (w.region || w.varietal || 'Saved').toUpperCase(),
    retailer: [w.varietal, w.country].filter(Boolean).join(' · '),
    vivino_rating: w.vivino_rating,
    vivino_ratings_count: w.vivino_ratings_count,
    flavors: [],
  };
}

export default function Saved() {
  const { user, authState, requireSignIn, savedIds } = useAuth();
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);   // null = loading

  useEffect(() => {
    if (!user) { setRows([]); return; }
    let alive = true;
    listFavorites(user.id).then(r => { if (alive) setRows(r); });
    return () => { alive = false; };
  }, [user, savedIds.length]);

  const pad = isMobile ? '18px 16px 48px' : '28px 36px 64px';

  // Signed out → invite, never a wall.
  if (authState !== 'signed_in') {
    return (
      <div style={{ maxWidth: 1060, margin: '0 auto', padding: pad, textAlign: 'center' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 30, color: 'var(--ink)', marginTop: 40 }}>Your list.</div>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', maxWidth: 380, margin: '10px auto 20px', lineHeight: 1.6 }}>
          Sign in to save bottles and keep a running list while you explore.
        </p>
        <button onClick={() => requireSignIn()}
          style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '12px 22px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
          Sign in with email
        </button>
      </div>
    );
  }

  const count = rows?.length ?? 0;

  return (
    <div style={{ maxWidth: 1060, margin: '0 auto', padding: pad }}>
      <div style={{ marginBottom: 22 }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600 }}>
          Saved · {count} bottle{count !== 1 ? 's' : ''}
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--ink)', marginTop: 4 }}>Your list</div>
      </div>

      {rows === null ? (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)' }}>Loading…</div>
      ) : count === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 20px' }}>
          <div style={{ width: 48, height: 48, margin: '0 auto 16px', border: '1.5px solid var(--brass)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="21" viewBox="0 0 18 24" fill="none" stroke="var(--brass)" strokeWidth="1.5" strokeLinejoin="round"><path d="M2 2h14v20l-7-5-7 5V2z" /></svg>
          </div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)' }}>Nothing saved yet.</div>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', maxWidth: 340, margin: '10px auto 20px', lineHeight: 1.6 }}>
            Tap the bookmark on any bottle and it lands here. I'll keep track while you explore.
          </p>
          <button onClick={() => navigate('/')}
            style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '11px 20px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
            Browse wines
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: isMobile ? 10 : 14 }}>
          {rows.map(row => {
            const card = toCard(row);
            return <WineCard key={card.id} wine={card} onClick={() => navigate('/wine/' + card.id)} />;
          })}
        </div>
      )}
    </div>
  );
}
