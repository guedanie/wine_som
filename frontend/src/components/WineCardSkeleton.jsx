// Placeholder shown in the recommendations panel while the sommelier's
// narrative streams — the picks arrive as one event only after the narrative
// finishes generating, so this fills the gap and signals bottles are coming.
export default function WineCardSkeleton({ variant }) {
  const bar = (w, h = 12) => (
    <div style={{
      width: w, height: h, borderRadius: 2,
      background: 'var(--paper)', animation: 'skeleton-pulse 1.4s ease-in-out infinite',
    }} />
  );

  if (variant === 'landscape') {
    return (
      <div style={{ border: '1.5px solid var(--border)', background: 'var(--cream)', display: 'flex', minHeight: 120 }}>
        <div style={{ padding: '14px 16px', borderRight: '0.75px solid var(--border)', minWidth: 130, display: 'flex', flexDirection: 'column', gap: 10, flex: 'none' }}>
          {bar(70, 8)}
          {bar(50, 8)}
          <div style={{ marginTop: 'auto' }}>{bar(48, 22)}</div>
        </div>
        <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: 9 }}>
          {bar('80%', 16)}
          {bar('45%', 10)}
          <div style={{ display: 'flex', gap: 5, marginTop: 4 }}>{bar(46, 16)}{bar(38, 16)}{bar(52, 16)}</div>
        </div>
      </div>
    );
  }

  // portrait (mobile sheet)
  return (
    <div style={{ border: '1.5px solid var(--border)', background: 'var(--cream)' }}>
      <div style={{ padding: '11px 14px', borderBottom: '0.75px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>{bar(90, 8)}{bar(60, 8)}</div>
        {bar(44, 22)}
      </div>
      <div style={{ padding: '11px 14px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {bar('75%', 16)}
        {bar('40%', 10)}
        <div style={{ display: 'flex', gap: 5, marginTop: 2 }}>{bar(46, 16)}{bar(38, 16)}</div>
      </div>
    </div>
  );
}
