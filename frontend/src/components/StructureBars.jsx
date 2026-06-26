export default function StructureBars({ items, compact }) {
  return (
    <div style={{ display: 'flex', gap: compact ? 12 : 20 }}>
      {items.map(([label, description, value]) => (
        <div key={label} style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 5 }}>
            <span>{label}</span>
            {!compact && <span style={{ color: 'var(--ink-2)' }}>{description}</span>}
          </div>
          <div style={{ height: 5, borderRadius: 3, background: 'var(--paper)' }}>
            <div style={{ width: `${value * 100}%`, height: '100%', borderRadius: 3, background: 'var(--brass)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}
