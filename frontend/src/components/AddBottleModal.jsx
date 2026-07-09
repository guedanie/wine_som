import { useState } from 'react';
import useIsMobile from '../lib/useIsMobile.js';
import { addBottle } from '../lib/cellar.js';
import { drinkingWindow, windowStatus } from '../lib/drinkingWindow.js';

const WINE_TYPES = ['red', 'white', 'rosé', 'sparkling', 'dessert'];

const INPUT = { width: '100%', boxSizing: 'border-box', border: '1.5px solid var(--ink)', background: 'var(--cream)', borderRadius: 0, padding: '9px 11px', fontFamily: 'var(--font-sans)', fontSize: 15, color: 'var(--ink)', outline: 'none' };
const LABEL = { display: 'block', fontFamily: 'var(--font-sans)', fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600, margin: '0 0 5px' };

// Module-level so inputs keep identity across renders (no remount on keystroke).
function Field({ label, id, value, onChange, type = 'text', placeholder, flex }) {
  return (
    <div style={{ flex: flex ?? 1, minWidth: 0 }}>
      <label style={LABEL} htmlFor={id}>{label}</label>
      <input id={id} type={type} value={value} placeholder={placeholder} onChange={onChange} style={INPUT} />
    </div>
  );
}

// Add a bottle to the cellar — manual entry, or prefilled from a catalog wine.
export default function AddBottleModal({ userId, prefill = null, onClose, onAdded }) {
  const isMobile = useIsMobile();
  const [f, setF] = useState({
    name: prefill?.name ?? '',
    vintage: prefill?.vintage ? String(prefill.vintage) : '',
    region: prefill?.region ?? '',
    varietal: prefill?.varietal ?? '',
    wine_type: prefill?.wine_type ?? 'red',
    quantity: '1',
    purchase_date: '',
    price_paid: '',
    notes: '',
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }));

  const vintage = f.vintage ? parseInt(f.vintage, 10) : null;
  const win = drinkingWindow(f.varietal || null, f.wine_type, vintage);
  const winStatus = win ? windowStatus(win) : null;

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!f.name.trim() || saving) return;
    setSaving(true);
    const bottle = {
      wine_id: prefill?.wine_id ?? null,
      name: f.name.trim(),
      vintage,
      region: f.region.trim() || null,
      varietal: f.varietal.trim() || null,
      wine_type: f.wine_type,
      quantity: Math.max(1, parseInt(f.quantity, 10) || 1),
      purchase_date: f.purchase_date || null,
      price_paid: f.price_paid ? parseFloat(f.price_paid) : null,
      notes: f.notes.trim() || null,
    };
    const row = await addBottle(userId, bottle);
    setSaving(false);
    if (row) { onAdded?.(row); onClose?.(); }
  };

  const fld = (label, k, opts = {}) => (
    <Field label={label} id={`bf-${k}`} value={f[k]} onChange={e => set(k, e.target.value)} {...opts} />
  );

  const panel = (
    <form onSubmit={submit} style={{ background: 'var(--cream-raised)', border: '1.5px solid var(--ink)' }}>
      <div style={{ padding: '20px 24px 14px', borderBottom: '0.75px solid var(--brass)' }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600, marginBottom: 8 }}>Add to cellar</div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)' }}>What did you get?</div>
      </div>
      <div style={{ padding: '18px 24px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {fld('Wine name', 'name', { placeholder: 'e.g. Produttori del Barbaresco' })}
        <div style={{ display: 'flex', gap: 12 }}>
          {fld('Vintage', 'vintage', { type: 'number', placeholder: '2019' })}
          {fld('Quantity', 'quantity', { type: 'number' })}
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          {fld('Varietal', 'varietal', { placeholder: 'Nebbiolo', flex: 1.4 })}
          <div style={{ flex: 1, minWidth: 0 }}>
            <label style={LABEL} htmlFor="bf-type">Type</label>
            <select id="bf-type" value={f.wine_type} onChange={e => set('wine_type', e.target.value)} style={INPUT}>
              {WINE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        {fld('Region', 'region', { placeholder: 'Piedmont' })}
        <div style={{ display: 'flex', gap: 12 }}>
          {fld('Purchased', 'purchase_date', { type: 'date' })}
          {fld('Price paid', 'price_paid', { type: 'number', placeholder: '$' })}
        </div>
        {winStatus && (
          <div style={{ background: 'var(--paper)', border: '1px solid var(--border)', padding: '9px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 9.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faded)', fontWeight: 600 }}>Window</span>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: winStatus.phase === 'soon' || winStatus.phase === 'past' ? 'var(--bordeaux)' : 'var(--sage)' }}>
              {winStatus.label} <span style={{ color: 'var(--faded)' }}>· est. {win.from}–{win.to}</span>
            </span>
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
          <button type="submit" disabled={!f.name.trim() || saving}
            style={{ flex: 1, background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', borderRadius: 0, padding: '12px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', cursor: (!f.name.trim() || saving) ? 'default' : 'pointer', opacity: (!f.name.trim() || saving) ? 0.5 : 1 }}>
            {saving ? 'Adding…' : 'Add to cellar'}
          </button>
          <button type="button" onClick={onClose}
            style={{ background: 'transparent', border: '1.5px solid var(--bordeaux)', color: 'var(--bordeaux)', borderRadius: 0, padding: '12px 18px', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            Cancel
          </button>
        </div>
      </div>
    </form>
  );

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(26,24,18,0.72)', display: 'flex', alignItems: isMobile ? 'flex-end' : 'center', justifyContent: 'center', overflowY: 'auto' }}>
      <div onClick={e => e.stopPropagation()} role="dialog" aria-modal="true"
        style={{ width: isMobile ? '100%' : 460, maxWidth: '96vw', margin: isMobile ? 0 : 'auto' }}>
        {panel}
      </div>
    </div>
  );
}
