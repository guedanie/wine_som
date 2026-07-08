import { useAuth } from '../lib/auth.jsx';

// Self-contained Save affordance — reads auth directly so every WineCard gets
// Save for free. Unsaved = bordeaux outline bookmark; saved = solid bordeaux.
// Anonymous tap opens the sign-in prompt (via toggleSave). Renders nothing if
// auth isn't configured or there's no wine id.
export default function SaveBookmark({ wine, size = 18, style }) {
  const { isConfigured, isSaved, toggleSave } = useAuth();
  const id = wine?.wine_id ?? wine?.id;
  if (!isConfigured || !id) return null;
  const saved = isSaved(id);

  return (
    <button
      type="button"
      aria-label={saved ? 'Saved' : 'Save'}
      aria-pressed={saved}
      title={saved ? 'Saved' : 'Save'}
      onClick={e => { e.stopPropagation(); toggleSave(wine); }}
      style={{
        width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'none', border: 'none', padding: 0, cursor: 'pointer', ...style,
      }}
    >
      <svg width={size} height={Math.round(size * 24 / 18)} viewBox="0 0 18 24"
        fill={saved ? 'var(--bordeaux)' : 'none'} stroke="var(--bordeaux)" strokeWidth="1.5"
        strokeLinejoin="round">
        <path d="M2 2h14v20l-7-5-7 5V2z" />
      </svg>
    </button>
  );
}
