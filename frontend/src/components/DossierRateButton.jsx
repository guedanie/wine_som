import { useState, useEffect } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { supabase } from '../lib/supabase.js';
import { postFeedback } from '../lib/api.js';

// Thumbs up/down on the dossier — feeds the same personalization signal as the
// chat thumbs. Loads the user's existing vote for this wine (RLS). Anonymous
// tap opens the sign-in prompt so the rating ties to the account.
export default function DossierRateButton({ wineId, zip }) {
  const { isConfigured, authState, user, requireSignIn } = useAuth();
  const [vote, setVote] = useState(null);

  useEffect(() => {
    if (!supabase || !user || !wineId) return;
    let alive = true;
    supabase.from('feedback').select('vote')
      .eq('type', 'wine_card').eq('entity_id', wineId)
      .order('created_at', { ascending: false }).limit(1)
      .then(({ data }) => { if (alive && data?.[0]) setVote(data[0].vote); });
    return () => { alive = false; };
  }, [user, wineId]);

  if (!isConfigured || !wineId) return null;

  const onVote = (dir) => {
    if (authState !== 'signed_in') { requireSignIn(); return; }
    const next = vote === dir ? null : dir;   // toggle off = clear the signal
    setVote(next);
    postFeedback({ type: 'wine_card', entity_id: wineId, vote: next, session_id: `dossier-${user.id}`, user_id: user.id, zip: zip ?? null });
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600 }}>Rate this</span>
      {[['up', ThumbsUp, 'Loved it', 'var(--sage)'], ['down', ThumbsDown, 'Not for me', 'var(--bordeaux)']].map(([dir, Icon, label, active]) => (
        <button key={dir} type="button" onClick={() => onVote(dir)} title={label} aria-label={label}
          style={{ width: 30, height: 30, borderRadius: 2, cursor: 'pointer',
            border: vote === dir ? `1px solid ${active}` : '1px solid var(--border)',
            background: vote === dir ? active : 'transparent',
            color: vote === dir ? 'var(--cream)' : 'var(--faded)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 140ms cubic-bezier(.25,.46,.45,.94)' }}>
          <Icon size={14} strokeWidth={1.75} />
        </button>
      ))}
    </div>
  );
}
