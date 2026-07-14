import { Bookmark } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';

// The watch affordance (design: price-intelligence handoff, Surface 4).
// Ghost bordeaux "Watch price" → solid bordeaux "Watching", matching the
// `watch` chip variant. Anonymous tap stashes the pending-watch intent and
// opens the contextual sign-in nudge (via toggleWatch). Renders nothing when
// auth isn't configured — the affordance is account-bound by design.
export default function WatchPriceButton({ wineId, name, fullWidth = false }) {
  const { isConfigured, isWatched, toggleWatch } = useAuth();
  if (!isConfigured || !wineId) return null;
  const watching = isWatched(wineId);
  return (
    <button
      type="button"
      onClick={() => toggleWatch({ wine_id: wineId, name })}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
        width: fullWidth ? '100%' : 'auto',
        fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, letterSpacing: '0.05em',
        padding: '9px 16px', borderRadius: 0, cursor: 'pointer',
        border: '1.5px solid var(--bordeaux)',
        background: watching ? 'var(--bordeaux)' : 'transparent',
        color: watching ? 'var(--cream)' : 'var(--bordeaux)',
        transition: 'all 140ms cubic-bezier(.25,.46,.45,.94)',
      }}
    >
      <Bookmark size={13} strokeWidth={1.75} fill={watching ? 'currentColor' : 'none'} />
      {watching ? 'Watching' : 'Watch price'}
    </button>
  );
}
