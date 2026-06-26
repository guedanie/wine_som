import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Btn from '../components/Btn.jsx';
import { buildApiReq } from '../lib/regions.js';

const STYLE_OPTS = [
  ['Bold & Tannic',   'dark fruit · grip · structure'],
  ['Light & Elegant', 'red fruit · silk · lift'],
  ['Earthy & Savory', 'herb · iron · leather'],
  ['Bright & Fruity', 'juicy · fresh · easy'],
];
const OCCASIONS = ['Tonight', 'This weekend', 'Cellar it'];

export default function PreferenceCapture() {
  const navigate = useNavigate();
  const [zip,      setZip]      = useState('78209');
  const [budget,   setBudget]   = useState(60);
  const [styles,   setStyles]   = useState(['Bold & Tannic']);
  const [occasion, setOccasion] = useState('Tonight');

  const toggle = s => setStyles(p => p.includes(s) ? p.filter(x => x !== s) : [...p, s]);
  const valid  = zip.length === 5 && styles.length > 0;

  const handleSubmit = () => {
    const prefs  = { zip, budget, styles, occasion };
    const apiReq = buildApiReq(prefs);
    navigate('/recommend', { state: { prefs, apiReq } });
  };

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '56px 32px 80px' }}>
      <Eyebrow>Tonight's bottle</Eyebrow>
      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 56, lineHeight: 1.0, color: 'var(--ink)', margin: '12px 0 0' }}>
        Let's find you a wine.
      </h1>
      <p className="t-body" style={{ marginTop: 14, maxWidth: 520 }}>
        Tell me your taste, your budget and where you are. I'll find bottles worth drinking — available near you tonight.
      </p>

      <div style={{ marginTop: 36, display: 'flex', gap: 28 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: 'block' }}><Eyebrow>Zip code</Eyebrow></label>
          <input
            value={zip}
            onChange={e => setZip(e.target.value.replace(/\D/g, '').slice(0, 5))}
            maxLength={5}
            placeholder="78209"
            style={{ marginTop: 8, fontFamily: 'var(--font-sans)', fontSize: 15, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '11px 13px', width: '100%', boxSizing: 'border-box', outline: 'none' }}
          />
        </div>
        <div style={{ flex: 1.3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Eyebrow>Budget ceiling</Eyebrow>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--bordeaux)' }}>${budget}</span>
          </div>
          <input type="range" min={15} max={150} value={budget}
            onChange={e => setBudget(+e.target.value)}
            style={{ width: '100%', marginTop: 14 }}
          />
        </div>
      </div>

      <div style={{ marginTop: 32 }}>
        <Eyebrow>What are you in the mood for?</Eyebrow>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          {STYLE_OPTS.map(([s, sub]) => {
            const on = styles.includes(s);
            return (
              <button key={s} onClick={() => toggle(s)}
                style={{ textAlign: 'left', cursor: 'pointer', padding: '14px 16px', borderRadius: 0, background: on ? 'var(--bordeaux)' : 'var(--cream-raised)', border: on ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)', transition: 'all .15s var(--ease)' }}>
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: on ? 'var(--cream)' : 'var(--ink)' }}>{s}</div>
                <div style={{ fontSize: 11.5, letterSpacing: '0.02em', color: on ? 'rgba(245,239,230,0.75)' : 'var(--faded)', marginTop: 3 }}>{sub}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ marginTop: 32, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <Eyebrow>Occasion</Eyebrow>
          <div style={{ display: 'flex', marginTop: 12, border: '1.5px solid var(--ink)' }}>
            {OCCASIONS.map((o, i) => (
              <button key={o} onClick={() => setOccasion(o)}
                style={{ cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, padding: '10px 18px', border: 'none', borderLeft: i ? '1.5px solid var(--ink)' : 'none', borderRadius: 0, background: occasion === o ? 'var(--ink)' : 'transparent', color: occasion === o ? 'var(--cream)' : 'var(--ink)' }}>
                {o}
              </button>
            ))}
          </div>
        </div>
        <Btn onClick={handleSubmit} disabled={!valid}>Find wines →</Btn>
      </div>
    </div>
  );
}
