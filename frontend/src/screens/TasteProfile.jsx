import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';
import { saveTasteProfile } from '../lib/profile.js';
import { TASTE_QUESTIONS, buildProfile } from '../lib/tasteInterview.js';
import useIsMobile from '../lib/useIsMobile.js';
import Stamp from '../components/Stamp.jsx';

const CHIP = (active) => ({
  fontFamily: 'var(--font-sans)', fontSize: 13, borderRadius: 999,
  border: '1.5px solid var(--bordeaux)', padding: '8px 15px', cursor: 'pointer',
  background: active ? 'var(--bordeaux)' : 'transparent',
  color: active ? 'var(--cream)' : 'var(--bordeaux)',
});

function SommSays({ children }) {
  return (
    <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', marginBottom: 14 }}>
      <Stamp size={32} reversed />
      <div style={{ background: 'var(--cream-raised)', border: '1px solid var(--border)', borderRadius: '4px 14px 14px 14px', padding: '13px 15px', fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.55, color: 'var(--ink-2)', maxWidth: '85%' }}>
        {children}
      </div>
    </div>
  );
}

function YouSaid({ children }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
      <div style={{ background: 'var(--bordeaux)', color: 'var(--cream)', borderRadius: '14px 4px 14px 14px', padding: '9px 14px', fontFamily: 'var(--font-sans)', fontSize: 13, maxWidth: '80%' }}>{children}</div>
    </div>
  );
}

export default function TasteProfile() {
  const { authState, user, requireSignIn } = useAuth();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  // On mobile the chrome gives each screen a fixed-height content area, so the
  // screen must scroll itself — else the growing Q&A pushes Continue off-screen.
  const rootStyle = isMobile
    ? { height: '100%', overflowY: 'auto', WebkitOverflowScrolling: 'touch', padding: '18px 16px 96px' }
    : { maxWidth: 760, margin: '0 auto', padding: '24px 20px 60px' };
  const [step, setStep]       = useState(0);
  const [answers, setAnswers] = useState({});
  const [answered, setAnswered] = useState([]);   // display strings for past Qs
  const [multiSel, setMultiSel] = useState([]);
  const [freeText, setFreeText] = useState('');
  const [done, setDone]       = useState(false);
  const [saving, setSaving]   = useState(false);

  if (authState !== 'signed_in') {
    return (
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '40px 28px', textAlign: 'center' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 30, color: 'var(--ink)' }}>Let's talk palate.</div>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', maxWidth: 400, margin: '10px auto 20px', lineHeight: 1.6 }}>
          A few quick questions and I'll tune every recommendation to your taste. Sign in to start.
        </p>
        <button onClick={() => requireSignIn()}
          style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '12px 22px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
          Sign in with email
        </button>
      </div>
    );
  }

  const q = TASTE_QUESTIONS[step];

  const finish = async (allAnswers) => {
    setSaving(true);
    await saveTasteProfile(user.id, buildProfile(allAnswers));
    setSaving(false);
    setDone(true);
  };

  const advance = (next, display) => {
    setAnswers(next);
    setAnswered(prev => [...prev, { prompt: q.prompt, answer: display }]);
    setMultiSel([]); setFreeText('');
    if (step + 1 < TASTE_QUESTIONS.length) setStep(step + 1);
    else finish(next);
  };

  const pickSingle = (opt) => advance({ ...answers, [q.id]: opt.value }, opt.label);
  const toggleMulti = (label) => setMultiSel(s => (s.includes(label) ? s.filter(x => x !== label) : [...s, label]));
  const submitMulti = () => {
    const vals = [...multiSel, ...(freeText.trim() ? [freeText.trim()] : [])];
    advance({ ...answers, [q.id]: vals }, vals.length ? vals.join(', ') : '—');
  };

  return (
    <div style={rootStyle}>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600, marginBottom: 18 }}>Taste profile</div>

      {answered.map((a, i) => (
        <div key={i}>
          <SommSays>{a.prompt}</SommSays>
          <YouSaid>{a.answer}</YouSaid>
        </div>
      ))}

      {done ? (
        <>
          <SommSays>Got it — I've got your palate now. Every pick from here is tuned to it, and you can retake this anytime.</SommSays>
          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button onClick={() => navigate('/')} style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '11px 18px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>See my picks</button>
            <button onClick={() => navigate('/account')} style={{ background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '11px 18px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Back to account</button>
          </div>
        </>
      ) : (
        <>
          <SommSays>{q.prompt}</SommSays>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingLeft: 42 }}>
            {q.options.map(opt => {
              const label = opt.label;
              const active = q.multi && multiSel.includes(label);
              return (
                <button key={label} onClick={() => (q.multi ? toggleMulti(label) : pickSingle(opt))} style={CHIP(active)}>
                  {label}
                </button>
              );
            })}
          </div>
          {q.multi && (
            <div style={{ paddingLeft: 42, marginTop: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              {q.allowFree && (
                <input value={freeText} onChange={e => setFreeText(e.target.value)} placeholder="or type your own…"
                  style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', borderRadius: 0, padding: '8px 11px', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--ink)', outline: 'none' }} />
              )}
              <button onClick={submitMulti} disabled={saving}
                style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '9px 18px', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', cursor: 'pointer' }}>
                Continue
              </button>
            </div>
          )}
          <div style={{ paddingLeft: 42, marginTop: 16, fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)' }}>
            {step + 1} of {TASTE_QUESTIONS.length} — I'll have your profile after a few more.
          </div>
        </>
      )}
    </div>
  );
}
