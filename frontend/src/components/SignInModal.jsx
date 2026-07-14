import { useState } from 'react';
import useIsMobile from '../lib/useIsMobile.js';

// Magic-link sign-in. Desktop = centered modal; mobile = bottom sheet. Two
// states: enter-email (A) → check-inbox (B). A `wine` makes it contextual:
// kind='save' is the save prompt, kind='watch' the price-watch nudge (never a
// wall — design: price-intelligence handoff, Surface 4). Passwordless.
export default function SignInModal({ wine = null, kind = 'save', onClose, signInWithEmail }) {
  const isMobile = useIsMobile();
  const [email, setEmail]   = useState('');
  const [status, setStatus] = useState('idle');   // idle | sending | sent
  const [err, setErr]       = useState(null);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email.trim() || status === 'sending') return;
    setStatus('sending'); setErr(null);
    try {
      const { error } = await signInWithEmail(email.trim());
      if (error) throw error;
      setStatus('sent');
    } catch (e2) {
      setErr(e2?.message || 'Something went wrong — try again.');
      setStatus('idle');
    }
  };

  const isWatch = kind === 'watch' && wine;
  const eyebrow = isWatch ? 'WATCH THIS PRICE' : wine ? 'SAVE TO YOUR LIST' : 'SIGN IN TO SOMM';

  const head = (
    <div style={{ padding: '28px 32px 20px', borderBottom: '0.75px solid var(--brass)' }}>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600, marginBottom: 10 }}>{eyebrow}</div>
      {status === 'sent' ? (
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--ink)', lineHeight: 1.1 }}>Check your inbox.</div>
      ) : isWatch ? (
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--ink)', lineHeight: 1.15 }}>
          I&rsquo;ll tell you when<br /><span style={{ color: 'var(--bordeaux)' }}>{wine.name}</span> drops.
        </div>
      ) : wine ? (
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--ink)', lineHeight: 1.15 }}>
          Sign in to save<br /><span style={{ color: 'var(--bordeaux)' }}>{wine.name}.</span>
        </div>
      ) : (
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--ink)', lineHeight: 1.1 }}>Sign in.</div>
      )}
      {status !== 'sent' && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', marginTop: 8, lineHeight: 1.5 }}>
          {isWatch ? 'Watches live with your account — passwordless, free. Sign in and I’ll ping you the week it gets cheaper near you.'
            : wine ? 'Free · passwordless · takes ten seconds.'
            : 'No account needed to browse — sign in to save bottles and get picks tuned to your taste.'}
        </div>
      )}
      {status !== 'sent' && isWatch && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 6 }}>
          No account needed to browse — this just saves the watch.
        </div>
      )}
    </div>
  );

  const body = status === 'sent' ? (
    <div style={{ padding: '24px 32px 28px' }}>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink-2, var(--body))', lineHeight: 1.6 }}>
        I sent a link to <strong>{email}</strong>. Tap it to sign in — no password needed.
      </div>
      <div style={{ height: 1, background: 'var(--border)', margin: '18px 0 14px' }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button type="button" onClick={submit}
          style={{ background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '10px 18px', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
          Resend link
        </button>
        <button type="button" onClick={() => setStatus('idle')}
          style={{ background: 'none', border: 'none', color: 'var(--faded)', fontFamily: 'var(--font-sans)', fontSize: 12, textDecoration: 'underline', cursor: 'pointer', padding: 0 }}>
          Change email
        </button>
      </div>
    </div>
  ) : (
    <form onSubmit={submit} style={{ padding: '24px 32px 28px' }}>
      <label style={{ display: 'block', fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600, marginBottom: 8 }}>Your email</label>
      <input
        type="email" value={email} autoFocus
        onChange={e => setEmail(e.target.value)}
        placeholder="you@example.com"
        style={{ width: '100%', boxSizing: 'border-box', border: '1.5px solid var(--ink)', background: 'var(--cream)', borderRadius: 0, padding: '11px 14px', fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', outline: 'none' }}
      />
      {err && <div style={{ color: 'var(--bordeaux)', fontSize: 12, marginTop: 8 }}>{err}</div>}
      <button type="submit" disabled={status === 'sending'}
        style={{ width: '100%', marginTop: 16, background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '13px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: status === 'sending' ? 'default' : 'pointer', opacity: status === 'sending' ? 0.6 : 1 }}>
        {status === 'sending' ? 'Sending…' : 'Send magic link'}
      </button>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 12, lineHeight: 1.5 }}>
        No password. I'll send you a one-time link — tap it and you're in.
        <div style={{ color: 'var(--brass-deep, #5C4A2E)', marginTop: 6 }}>What you unlock: saved bottles · cellar tracking · taste profile.</div>
      </div>
      {isMobile && (
        <button type="button" onClick={onClose}
          style={{ width: '100%', marginTop: 12, background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '11px', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
          Not now
        </button>
      )}
    </form>
  );

  if (isMobile) {
    return (
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(26,24,18,0.72)', display: 'flex', alignItems: 'flex-end' }}>
        <div onClick={e => e.stopPropagation()} role="dialog" aria-modal="true"
          style={{ width: '100%', background: 'var(--cream-raised)', borderTop: '1.5px solid var(--ink)', borderRadius: '12px 12px 0 0', boxShadow: '0 -8px 40px rgba(0,0,0,0.28)' }}>
          <div style={{ width: 36, height: 4, background: 'var(--border)', borderRadius: 2, margin: '10px auto 2px' }} />
          {head}{body}
        </div>
      </div>
    );
  }

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(26,24,18,0.72)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} role="dialog" aria-modal="true"
        style={{ width: 420, maxWidth: '92vw', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', boxShadow: '0 12px 40px rgba(0,0,0,0.22)' }}>
        {head}{body}
      </div>
    </div>
  );
}
