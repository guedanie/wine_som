import { useLocation, useNavigate } from 'react-router-dom';
import Stamp from './Stamp.jsx';
import { SLUG_TO_REGION } from '../lib/regions.js';
import { loadZip } from '../lib/useIsMobile.js';

// ── Top bar (56px) ──────────────────────────────────────────────
export function TopBar() {
  const { pathname, state } = useLocation();
  const navigate = useNavigate();
  const zip = state?.zip ?? state?.prefs?.zip ?? loadZip();

  let title = 'Somm';
  let sub = 'Wine Atlas';
  let back = null;

  if (pathname === '/recommend') {
    title = `Tonight, near ${zip}`;
    sub = null;
  } else if (pathname.startsWith('/wine/')) {
    const name = state?.pick?.name ?? 'Wine';
    title = name.split(' ').slice(0, 3).join(' ');
    sub = null;
    // Restore the chat session on back — navigate(-1) returns to the ORIGINAL
    // /recommend history entry (no _restored), which re-runs the recommendation.
    const chatState = state?.chatState ?? state?.pick?.chatState ?? null;
    back = chatState
      ? () => navigate('/recommend', {
          state: { prefs: chatState.prefs, apiReq: chatState.apiReq, _restored: chatState },
        })
      : () => navigate(-1);
  } else if (pathname === '/discover') {
    title = 'Discover';
    sub = null;
  } else if (pathname.startsWith('/regions/') || pathname.startsWith('/region/')) {
    const slug = pathname.split('/')[2] ?? '';
    title = SLUG_TO_REGION[slug] ?? decodeURIComponent(slug) ?? 'Region';
    sub = null;
    back = () => navigate(-1);
  } else if (pathname === '/search') {
    title = 'Search';
    sub = null;
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', padding: '0 16px', height: 56,
      background: 'var(--cream)', borderBottom: '1.5px solid var(--ink)',
      gap: 10, flexShrink: 0,
    }}>
      {back ? (
        <button onClick={back} aria-label="Back" style={{
          cursor: 'pointer', border: 'none', background: 'none', color: 'var(--faded)',
          fontSize: 22, padding: '0 4px 0 0', lineHeight: 1, minWidth: 36, minHeight: 44,
          display: 'flex', alignItems: 'center',
        }}>←</button>
      ) : (
        <Stamp size={26} />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 21, lineHeight: 1, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {title}
        </div>
        {sub && (
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 8, letterSpacing: '0.28em', textTransform: 'uppercase', color: 'var(--faded)' }}>
            {sub}
          </div>
        )}
      </div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.06em', color: 'var(--faded)', border: '1px solid var(--border)', padding: '5px 10px', flexShrink: 0 }}>
        ◎ {zip}
      </div>
    </div>
  );
}

// ── Bottom tab bar (56px + safe area) ───────────────────────────
const TABS = [
  {
    id: 'recommend', label: 'Recommend', to: '/',
    match: p => p === '/' || p === '/recommend' || p.startsWith('/wine/'),
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    id: 'discover', label: 'Discover', to: '/discover',
    match: p => p === '/discover' || p.startsWith('/region'),
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
      </svg>
    ),
  },
  {
    id: 'search', label: 'Search', to: '/search',
    match: p => p === '/search',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
        <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    id: 'saved', label: 'Saved', to: '/saved',
    match: p => p === '/saved',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
];

export function BottomTabs() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  return (
    <div style={{
      display: 'flex', background: 'var(--cream)', borderTop: '1.5px solid var(--ink)',
      flexShrink: 0, paddingBottom: 'env(safe-area-inset-bottom, 0px)',
    }}>
      {TABS.map(tab => {
        const active = tab.match(pathname);
        return (
          <button key={tab.id} onClick={() => navigate(tab.to)} style={{
            flex: 1, cursor: 'pointer', background: 'none', border: 'none',
            padding: '10px 0 12px', display: 'flex', flexDirection: 'column',
            alignItems: 'center', gap: 3,
            color: active ? 'var(--bordeaux)' : 'var(--faded)',
          }}>
            {tab.icon}
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: active ? 600 : 400 }}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
