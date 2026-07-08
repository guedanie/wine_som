import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Btn from '../components/Btn.jsx';
import { buildApiReq, VARIETAL_OPTS } from '../lib/regions.js';
import { track } from '../lib/analytics.js';
import useIsMobile, { loadZip, saveZip } from '../lib/useIsMobile.js';

const STYLE_OPTS = [
  ['Bold & Tannic',   'dark fruit · grip · structure'],
  ['Light & Elegant', 'red fruit · silk · lift'],
  ['Earthy & Savory', 'herb · iron · leather'],
  ['Bright & Fruity', 'juicy · fresh · easy'],
];
const OCCASIONS = ['Tonight', 'This weekend', 'Cellar it'];
const WINE_TYPES = ['Red', 'White', 'Rosé', 'Sparkling'];

export default function PreferenceCapture() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [zip,      setZip]      = useState(loadZip);
  const [budget,   setBudget]   = useState(60);
  const [styles,   setStyles]   = useState(['Bold & Tannic']);
  const [occasion, setOccasion] = useState('Tonight');

  const [wineTypes, setWineTypes] = useState([]);
  const toggleType = t => setWineTypes(p => p.includes(t) ? p.filter(x => x !== t) : [...p, t]);

  const [grapes,       setGrapes]      = useState([]);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const toggleGrape = g => setGrapes(p => p.includes(g) ? p.filter(x => x !== g) : [...p, g]);

  const [freeText, setFreeText] = useState('');

  const toggle = s => setStyles(p => p.includes(s) ? p.filter(x => x !== s) : [...p, s]);
  const valid  = zip.length === 5 && (styles.length > 0 || freeText.trim().length > 0);

  const handleSubmit = () => {
    saveZip(zip);
    const prefs  = { zip, budget, styles, occasion, wineTypes, grapes, freeText };
    const apiReq = buildApiReq(prefs);
    track('preferences_submitted', {
      budget, occasion, styles_count: styles.length,
      wine_types: wineTypes.length, has_free_text: !!freeText?.trim(),
    });
    navigate('/recommend', { state: { prefs, apiReq } });
  };

  if (isMobile) {
    return (
      <div style={{ overflowY: 'auto', height: '100%', WebkitOverflowScrolling: 'touch' }}>
        <div style={{ padding: '28px 20px 40px' }}>
          <div style={{ marginBottom: 28 }}>
            <Eyebrow>The sommelier</Eyebrow>
            <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 34, lineHeight: 1.05, color: 'var(--ink)', margin: '8px 0 0' }}>Tonight's brief</h1>
            <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--ink-2)', margin: '10px 0 0' }}>
              Tell me what you're after. I'll find what's near you.
            </p>
          </div>

          {/* Style grid 2×2 */}
          <div style={{ marginBottom: 28 }}>
            <Eyebrow style={{ display: 'block', marginBottom: 12 }}>What you're in the mood for</Eyebrow>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {STYLE_OPTS.map(([s, sub]) => {
                const on = styles.includes(s);
                return (
                  <button key={s} onClick={() => toggle(s)} style={{
                    cursor: 'pointer', padding: '14px 12px', textAlign: 'left', borderRadius: 0,
                    border: on ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)',
                    background: on ? 'var(--bordeaux-tint)' : 'var(--cream-raised)',
                    transition: 'all .15s',
                  }}>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, color: on ? 'var(--bordeaux)' : 'var(--ink)', lineHeight: 1.2 }}>{s}</div>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, color: 'var(--faded)', marginTop: 4, lineHeight: 1.3 }}>{sub}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Budget */}
          <div style={{ marginBottom: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
              <Eyebrow>Budget per bottle</Eyebrow>
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--bordeaux)' }}>up to ${budget}</span>
            </div>
            <input type="range" min={15} max={200} step={5} value={budget}
              onChange={e => setBudget(+e.target.value)}
              style={{ width: '100%', height: 4 }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-sans)', fontSize: 10, color: 'var(--faded)', marginTop: 6 }}>
              <span>$15</span><span>$200</span>
            </div>
          </div>

          {/* Wine type */}
          <div style={{ marginBottom: 28 }}>
            <Eyebrow style={{ display: 'block', marginBottom: 12 }}>Wine type</Eyebrow>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {WINE_TYPES.map(t => {
                const on = wineTypes.includes(t.toLowerCase());
                return (
                  <button key={t} onClick={() => toggleType(t.toLowerCase())} style={{
                    cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13,
                    padding: '9px 16px', border: '1.5px solid', borderRadius: 999, minHeight: 44,
                    borderColor: on ? 'var(--bordeaux)' : 'var(--border)',
                    background: on ? 'var(--bordeaux)' : 'none',
                    color: on ? 'var(--cream)' : 'var(--ink-2)',
                    transition: 'all .15s',
                  }}>{t}</button>
                );
              })}
            </div>
          </div>

          {/* Occasion pills */}
          <div style={{ marginBottom: 28 }}>
            <Eyebrow style={{ display: 'block', marginBottom: 12 }}>Occasion</Eyebrow>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {OCCASIONS.map(o => (
                <button key={o} onClick={() => setOccasion(o)} style={{
                  cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13,
                  padding: '9px 16px', border: '1.5px solid', borderRadius: 999, minHeight: 44,
                  borderColor: occasion === o ? 'var(--bordeaux)' : 'var(--border)',
                  background: occasion === o ? 'var(--bordeaux)' : 'none',
                  color: occasion === o ? 'var(--cream)' : 'var(--ink-2)',
                  transition: 'all .15s',
                }}>{o}</button>
              ))}
            </div>
          </div>

          {/* Free text */}
          <div style={{ marginBottom: 28 }}>
            <Eyebrow style={{ display: 'block', marginBottom: 10 }}>Anything specific?</Eyebrow>
            <input
              value={freeText}
              onChange={e => setFreeText(e.target.value)}
              placeholder="A store, region, grape, or occasion…"
              style={{ fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '12px 13px', width: '100%', boxSizing: 'border-box', borderRadius: 0, outline: 'none' }}
            />
          </div>

          {/* ZIP */}
          <div style={{ marginBottom: 32 }}>
            <Eyebrow style={{ display: 'block', marginBottom: 10 }}>Your zip code</Eyebrow>
            <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
              <span style={{ padding: '12px 14px', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)' }}>◎</span>
              <input
                value={zip}
                onChange={e => setZip(e.target.value.replace(/\D/g, '').slice(0, 5))}
                placeholder="ZIP code" maxLength={5} inputMode="numeric"
                style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-sans)', fontSize: 16, color: 'var(--ink)', padding: '12px 8px 12px 0' }}
              />
            </div>
          </div>

          <Btn onClick={handleSubmit} disabled={!valid}
            style={{ width: '100%', justifyContent: 'center', opacity: valid ? 1 : 0.5 }}>
            Find my wines →
          </Btn>
        </div>
      </div>
    );
  }

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
            style={{ marginTop: 8, fontFamily: 'var(--font-sans)', fontSize: 15, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '11px 13px', width: '100%', boxSizing: 'border-box', borderRadius: 0, outline: 'none' }}
          />
        </div>
        <div style={{ flex: 1.3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Eyebrow>Budget ceiling</Eyebrow>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 23, color: 'var(--bordeaux)' }}>${budget}</span>
          </div>
          <input type="range" min={15} max={150} value={budget}
            onChange={e => setBudget(+e.target.value)}
            style={{ width: '100%', marginTop: 14 }}
          />
        </div>
      </div>

      <div style={{ marginTop: 28 }}>
        <Eyebrow>Wine type</Eyebrow>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
          {WINE_TYPES.map(t => {
            const on = wineTypes.includes(t.toLowerCase());
            return (
              <button key={t} onClick={() => toggleType(t.toLowerCase())}
                style={{ cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, padding: '8px 18px', borderRadius: 0, border: on ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)', background: on ? 'var(--bordeaux)' : 'var(--cream-raised)', color: on ? 'var(--cream)' : 'var(--ink)', transition: 'all .15s var(--ease)' }}>
                {t}
              </button>
            );
          })}
          <span style={{ alignSelf: 'center', fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>
            {wineTypes.length === 0 ? 'Any type' : ''}
          </span>
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
                <div style={{ fontSize: 11.5, letterSpacing: '0.02em', color: on ? 'var(--cream)' : 'var(--faded)', marginTop: 3 }}>{sub}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ marginTop: 28 }}>
        <label style={{ display: 'block' }}><Eyebrow>What are you feeling tonight?</Eyebrow></label>
        <input
          value={freeText}
          onChange={e => setFreeText(e.target.value)}
          placeholder="e.g. I'm at HEB Lincoln Heights · looking for a Bordeaux blend from California"
          style={{ marginTop: 8, fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '11px 13px', width: '100%', boxSizing: 'border-box', borderRadius: 0, outline: 'none' }}
        />
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 5 }}>
          Optional — name a store, region, grape, or occasion
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        <button
          onClick={() => setAdvancedOpen(o => !o)}
          style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Eyebrow>Advanced search</Eyebrow>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
            {advancedOpen ? '▲' : '▼'}
          </span>
        </button>

        {advancedOpen && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)', marginBottom: 10 }}>
              Filter by grape varietal — any that match
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {VARIETAL_OPTS.map(g => {
                const on = grapes.includes(g);
                return (
                  <button key={g} onClick={() => toggleGrape(g)}
                    style={{ cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 12, padding: '6px 14px', borderRadius: 0, border: on ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)', background: on ? 'var(--bordeaux)' : 'var(--cream-raised)', color: on ? 'var(--cream)' : 'var(--ink)', transition: 'all .15s var(--ease)' }}>
                    {g}
                  </button>
                );
              })}
            </div>
          </div>
        )}
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
