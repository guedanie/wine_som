import Tag from './Tag.jsx';

export default function WineCard({ wine, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', cursor: onClick ? 'pointer' : 'default', transition: 'transform .18s var(--ease), box-shadow .18s var(--ease)' }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-card)'; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      <div style={{ padding: '13px 14px', borderBottom: '0.75px solid var(--brass)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          {wine.tagline && (
            <div style={{ fontSize: 9.5, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--faded)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {wine.tagline}
            </div>
          )}
          {wine.coord && (
            <div style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 4 }}>{wine.coord}</div>
          )}
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--bordeaux)', flex: 'none' }}>${wine.price}</div>
      </div>
      <div style={{ padding: '13px 14px 14px' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 23, lineHeight: 1.05, color: 'var(--ink)' }}>{wine.name}</div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-2)', marginTop: 3 }}>{wine.retailer}</div>
        {wine.flavors?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, marginTop: 11, flexWrap: 'wrap' }}>
            {wine.flavors.map(t => <Tag key={t}>{t}</Tag>)}
          </div>
        )}
      </div>
    </div>
  );
}
