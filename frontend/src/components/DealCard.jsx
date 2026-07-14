import PriceMarker from './PriceMarker.jsx';

// Rail card for the weekly deals cut (design: price-intelligence handoff,
// Surface 3): framed 230px card, bordeaux-deep top strip with the region
// eyebrow + compact drop chip, serif name, producer/vintage, one-line note,
// then new price + struck was-price + store pill.
const fmt = p => (Number.isInteger(p) ? `$${p}` : `$${p.toFixed(2)}`);

export default function DealCard({ deal, onClick }) {
  const sub = [deal.producer, deal.vintage_year].filter(Boolean).join(' · ');
  const note = deal.tasting_note || (deal.flavor_profile || []).slice(0, 3).join(', ');
  return (
    <div onClick={onClick} style={{
      width: 230, flexShrink: 0, border: '1.5px solid var(--ink)', background: 'var(--cream)',
      cursor: onClick ? 'pointer' : 'default',
      transition: 'transform .18s var(--ease), box-shadow .18s var(--ease)',
    }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(26,26,26,.12)'; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      <div style={{ background: 'var(--bordeaux-deep)', padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-sans)', fontSize: 9, fontWeight: 600, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--cream)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {deal.region || deal.varietal || 'Near you'}
        </span>
        <PriceMarker variant="drop" small amount={deal.amount} />
      </div>
      <div style={{ padding: '12px 14px 14px' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, lineHeight: 1.12, color: 'var(--ink)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {deal.name}
        </div>
        {sub && <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 3 }}>{sub}</div>}
        {note && (
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-2)', marginTop: 8, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {note}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--bordeaux)' }}>{fmt(deal.price)}</span>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded-2, var(--faded))', textDecoration: 'line-through' }}>{fmt(deal.was_price)}</span>
          {deal.retailer && (
            <span style={{ borderRadius: 999, border: '0.75px solid var(--sage)', color: 'var(--sage)', fontFamily: 'var(--font-sans)', fontSize: 10, padding: '1px 8px' }}>
              ◎ {deal.retailer}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
