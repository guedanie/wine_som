import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { identifyBottle } from '../lib/api.js';

// v1 scope: no barcode tier, no save/cellar actions, no sign-in nudge, no
// camera-FAB visual treatment, no desktop modal — see the design doc
// (docs/superpowers/specs/2026-10-26-bottle-identify-frontend-v1-design.md)
// for what's deferred and why. A found wine hands off to the existing
// dossier screen for anything deeper (price, availability, save).

const WRAP = { padding: 24, maxWidth: 480, margin: '0 auto', fontFamily: 'var(--font-sans)' };
const PROMPT = { fontFamily: 'var(--font-serif)', fontSize: 23, color: 'var(--ink)', marginBottom: 16 };
const SOMM_LINE = { fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink-2)', marginBottom: 20, lineHeight: 1.5 };
const BTN = {
  cursor: 'pointer', background: 'var(--bordeaux)', color: 'var(--cream)',
  border: 'none', borderRadius: 0, padding: '12px 20px',
  fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500,
  display: 'inline-block',
};
const GHOST_BTN = {
  cursor: 'pointer', background: 'none', color: 'var(--bordeaux)',
  border: '1.5px inset var(--bordeaux)', borderRadius: 0, padding: '12px 20px',
  fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500,
};
const CARD = {
  border: '1.5px solid var(--ink)', padding: 16, marginBottom: 12, cursor: 'pointer',
};
const WINE_NAME = { fontFamily: 'var(--font-serif)', fontSize: 23, color: 'var(--ink)', marginBottom: 4 };
const WINE_META = { fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)' };

function wineLine(w) {
  return [w.brand, w.vintage_year, w.region].filter(Boolean).join(' · ');
}

export default function Identify() {
  const navigate = useNavigate();
  const [state, setState] = useState('idle'); // idle | identifying | result | error
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setState('identifying');
    try {
      const data = await identifyBottle(file);
      setResult(data);
      setState('result');
    } catch (err) {
      setErrorMessage(err.message || 'Something went wrong.');
      setState('error');
    } finally {
      e.target.value = '';
    }
  }

  function reset() {
    setState('idle');
    setResult(null);
    setErrorMessage('');
  }

  function goToWine(id) {
    navigate(`/wine/${id}`);
  }

  const fileInput = (testId) => (
    <label
      style={BTN}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.currentTarget.querySelector('input').click();
        }
      }}
    >
      Show me the bottle
      <input
        type="file"
        accept="image/*"
        capture="environment"
        data-testid={testId}
        onChange={handleFile}
        style={{ display: 'none' }}
      />
    </label>
  );

  if (state === 'idle') {
    return (
      <div style={WRAP}>
        <div style={PROMPT}>Show me the bottle</div>
        <div style={SOMM_LINE}>Snap the label and I'll tell you what it is.</div>
        {fileInput('identify-file-input')}
      </div>
    );
  }

  if (state === 'identifying') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>Let me get a look at it…</div>
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>{errorMessage}</div>
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  // state === 'result'
  const { status } = result;

  if (status === 'exact' || status === 'vintage_mismatch') {
    const w = result.wine;
    // When the vintage mismatches, the soft-confirm line below already states
    // both years — omit the vintage from the meta line so it isn't duplicated.
    const meta = status === 'vintage_mismatch'
      ? [w.brand, w.region].filter(Boolean).join(' · ')
      : wineLine(w);
    return (
      <div style={WRAP}>
        <div style={CARD} onClick={() => goToWine(w.id)}>
          <div style={WINE_NAME}>{w.name}</div>
          <div style={WINE_META}>{meta}</div>
        </div>
        {status === 'vintage_mismatch' && (
          <div style={SOMM_LINE}>
            I see the {w.vintage_year} nearby — yours looks like the {result.read_vintage}.
          </div>
        )}
        <button style={BTN} onClick={() => goToWine(w.id)}>See where to buy</button>
        <div style={{ marginTop: 12 }}>
          <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
        </div>
      </div>
    );
  }

  if (status === 'candidates') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>A few bottles match — which one is it?</div>
        {(result.candidates || []).map(c => (
          <div key={c.id} style={CARD} onClick={() => goToWine(c.id)}>
            <div style={WINE_NAME}>{c.name}</div>
            <div style={WINE_META}>{wineLine(c)}</div>
          </div>
        ))}
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  if (status === 'unstocked') {
    const named = [result.producer, result.wine_name].filter(Boolean).join(' ');
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>
          {named ? `Nobody near you stocks ${named} right now` : 'Nobody near you stocks that one right now'}
          — hang tight, this list grows every week.
        </div>
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  if (status === 'unreadable') {
    return (
      <div style={WRAP}>
        <div style={SOMM_LINE}>I couldn't quite make that out. Try getting the whole front label in frame.</div>
        <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
      </div>
    );
  }

  // status === 'not_wine'
  return (
    <div style={WRAP}>
      <div style={SOMM_LINE}>I'm not seeing a wine bottle in that photo.</div>
      <button style={GHOST_BTN} data-testid="identify-retake" onClick={reset}>Scan another</button>
    </div>
  );
}
