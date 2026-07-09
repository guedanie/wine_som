import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';
import Stamp from './Stamp.jsx';

// Desktop nav auth entry: ghost "Sign in" when anonymous; a pin-avatar + menu
// when signed in. Renders nothing if auth isn't configured (app stays anon).
export default function AuthNav() {
  const { authState, user, isConfigured, requireSignIn, signOut, savedIds } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  if (!isConfigured) return null;

  if (authState !== 'signed_in') {
    return (
      <button onClick={() => requireSignIn()}
        style={{ background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '7px 16px', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', cursor: 'pointer' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--bordeaux-tint, #F4E6E2)'; }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}>
        Sign in
      </button>
    );
  }

  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)} aria-label="Account"
        style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--bordeaux)', border: 'none', padding: 0, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Stamp size={30} reversed />
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
          <div style={{ position: 'absolute', top: 42, right: 0, zIndex: 41, minWidth: 200, background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', boxShadow: '0 12px 40px rgba(0,0,0,0.22)' }}>
            <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)', wordBreak: 'break-all' }}>{user?.email}</div>
            </div>
            <button onClick={() => { setOpen(false); navigate('/saved'); }}
              style={{ ...menuItem, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Saved</span>
              {savedIds.length > 0 && (
                <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, fontWeight: 600, border: '1px solid var(--border)', background: 'var(--paper)', padding: '2px 7px' }}>{savedIds.length}</span>
              )}
            </button>
            <button onClick={() => { setOpen(false); navigate('/cellar'); }} style={menuItem}>Cellar</button>
            <button onClick={() => { setOpen(false); signOut(); }}
              style={{ ...menuItem, color: 'var(--bordeaux)', borderBottom: 'none' }}>
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

const menuItem = {
  width: '100%', textAlign: 'left', background: 'none', border: 'none',
  borderBottom: '1px solid var(--border)', padding: '11px 16px',
  fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--ink)', cursor: 'pointer',
};
