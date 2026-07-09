import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';
import { listCellar } from '../lib/cellar.js';
import Stamp from '../components/Stamp.jsx';
import { loadZip } from '../lib/useIsMobile.js';

// Mobile account home. Signed out → an invite (never a wall). Signed in →
// profile band, stat tiles, preferences, link rows, sign out.
export default function Account() {
  const { authState, user, savedIds, requireSignIn, signOut } = useAuth();
  const navigate = useNavigate();
  const [cellarCount, setCellarCount] = useState(null);
  useEffect(() => {
    if (!user) return;
    listCellar(user.id).then(rows => setCellarCount(rows.reduce((n, b) => n + (b.quantity || 1), 0)));
  }, [user]);

  if (authState !== 'signed_in') {
    return (
      <div style={{ height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '32px 28px', gap: 18 }}>
        <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--paper)', border: '1.5px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Stamp size={40} />
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', lineHeight: 1.15 }}>Your bottles, your palate.</div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', maxWidth: 300, lineHeight: 1.6 }}>
          No account needed to browse. Sign in to save bottles and get picks tuned to your taste.
        </div>
        <button onClick={() => requireSignIn()}
          style={{ width: '100%', maxWidth: 320, background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '13px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
          Sign in with email
        </button>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>Passwordless · free · takes 10 seconds</div>
      </div>
    );
  }

  const email = user?.email ?? '';
  const name = email.split('@')[0] || 'You';
  const zip = loadZip();
  const cellar = cellarCount ?? 0;

  const StatTile = ({ label, value, unit }) => (
    <div style={{ background: 'var(--cream)', padding: '16px 18px' }}>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--bordeaux)', marginTop: 4 }}>{value}</div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>{unit}</div>
    </div>
  );

  const LinkRow = ({ label, value, valueColor, onClick, disabled }) => (
    <button onClick={disabled ? undefined : onClick} disabled={disabled}
      style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', borderBottom: '1px solid var(--border)', padding: '14px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.55 : 1 }}>
      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: valueColor ?? 'var(--faded)' }}>{value} →</span>
    </button>
  );

  return (
    <div style={{ height: '100%', overflowY: 'auto', WebkitOverflowScrolling: 'touch' }}>
      {/* Profile band */}
      <div style={{ background: 'var(--bordeaux-deep)', padding: 20, borderBottom: '0.75px solid var(--brass)', display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--bordeaux)', border: '1px solid var(--brass)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
          <Stamp size={44} reversed />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--cream)', textTransform: 'capitalize' }}>{name}</div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'rgba(239,230,212,0.55)', wordBreak: 'break-all' }}>{email}</div>
        </div>
      </div>

      {/* Stat tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'var(--border)' }}>
        <StatTile label="Saved" value={savedIds.length} unit={`bottle${savedIds.length !== 1 ? 's' : ''}`} />
        <StatTile label="Cellar" value={cellar} unit={`bottle${cellar !== 1 ? 's' : ''}`} />
      </div>

      {/* Preferences */}
      <div style={{ padding: '22px 20px 8px' }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600, marginBottom: 10 }}>Your preferences</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {[zip, 'Recent picks'].map(chip => (
            <span key={chip} style={{ background: 'var(--paper)', border: '1px solid var(--border)', borderRadius: 0, padding: '4px 10px', fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--brass-deep, #5C4A2E)' }}>{chip}</span>
          ))}
        </div>
        <button onClick={() => navigate('/')}
          style={{ background: 'none', border: 'none', color: 'var(--bordeaux)', fontFamily: 'var(--font-sans)', fontSize: 13, cursor: 'pointer', padding: '12px 0 0' }}>
          Edit preferences →
        </button>
      </div>

      {/* Link rows */}
      <div style={{ borderTop: '1px solid var(--border)', marginTop: 8 }}>
        <LinkRow label="Saved bottles" value={savedIds.length} onClick={() => navigate('/saved')} />
        <LinkRow label="Cellar" value={cellar} onClick={() => navigate('/cellar')} />
        <LinkRow label="Taste profile" value="Soon" valueColor="var(--sage)" disabled />
      </div>

      {/* Sign out */}
      <div style={{ padding: 20 }}>
        <button onClick={signOut}
          style={{ width: '100%', background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '12px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.04em', cursor: 'pointer' }}>
          Sign out
        </button>
      </div>
    </div>
  );
}
