import { Bookmark } from 'lucide-react';

// The price-movement marker — the connective atom of the price-intelligence
// layer (design: frontend/design-system/handoffs/price-intelligence/README.md).
// One chip, four variants, reused across cards, dossier, picks, deals.
// It whispers like a cellar note, never a sale burst. Rule: no movement → no
// chip (the explicit "steady" variant is for the dossier module only, where
// the price context is the subject).

const VARIANTS = {
  drop:    { color: 'var(--bordeaux)',   border: 'var(--bordeaux)',      bg: 'var(--bordeaux-tint)',      glyph: '↓' },
  steady:  { color: 'var(--faded)',      border: 'var(--border-strong)', bg: 'transparent',               glyph: '—' },
  restock: { color: 'var(--sage-deep)',  border: 'var(--sage)',          bg: 'rgba(124,138,90,0.10)',     glyph: '●' },
  watch:   { color: 'var(--brass-deep)', border: 'var(--brass)',         bg: 'var(--cream-raised)',       glyph: null },
};

const fmtAmount = a => (Number.isInteger(a) ? `$${a}` : `$${a.toFixed(2)}`);

function copyFor(variant, { amount, store, sinceLabel }) {
  const at = store ? ` · ${store}` : '';
  if (variant === 'drop')    return `${fmtAmount(amount)} ${sinceLabel ?? 'this week'}${at}`;
  if (variant === 'steady')  return `steady ${sinceLabel ?? ''}`.trim();
  if (variant === 'restock') return `back in stock${at}`;
  return 'watching';
}

export default function PriceMarker({ variant = 'drop', amount, store, sinceLabel, small }) {
  const v = VARIANTS[variant] ?? VARIANTS.drop;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
      padding: small ? '2px 8px' : '4px 9px 4px 8px',
      border: `0.75px solid ${v.border}`, borderRadius: 0,
      color: v.color, background: v.bg, whiteSpace: 'nowrap',
    }}>
      {variant === 'watch'
        ? <Bookmark size={11} strokeWidth={1.75} />
        : <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 12, lineHeight: 1 }}>{v.glyph}</span>}
      {copyFor(variant, { amount, store, sinceLabel })}
    </span>
  );
}
