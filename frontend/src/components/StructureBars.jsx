const RULER_W = 284;
const RULER_TICKS = 10;

function RulerBar({ label, value }) {
  const fillW = Math.round(value * RULER_W);
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-2)', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ position: 'relative', width: RULER_W }}>
        <svg width={RULER_W} height={18} style={{ display: 'block' }}>
          <line x1={0} y1={0} x2={RULER_W} y2={0} stroke="var(--brass)" strokeWidth={0.75} opacity={0.4} />
          {Array.from({ length: RULER_TICKS + 1 }).map((_, i) => {
            const x = (i / RULER_TICKS) * RULER_W;
            const major = i % 5 === 0;
            return <line key={i} x1={x} y1={0} x2={x} y2={major ? 10 : 6} stroke="var(--brass)" strokeWidth={major ? 1 : 0.75} opacity={major ? 0.7 : 0.4} />;
          })}
        </svg>
        <div style={{ position: 'relative', height: 4, marginTop: 2 }}>
          <div style={{ position: 'absolute', inset: 0, background: 'var(--paper)', border: '0.5px solid rgba(176,141,87,0.3)' }} />
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: fillW, background: 'var(--brass)' }} />
          <div style={{ position: 'absolute', left: fillW, top: -16, transform: 'translateX(-50%)' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--bordeaux)', whiteSpace: 'nowrap', letterSpacing: '0.05em' }}>
              {Math.round(value * 100)}
            </div>
          </div>
          <div style={{ position: 'absolute', left: fillW, top: -2, bottom: -2, width: 1.5, background: 'var(--bordeaux)', transform: 'translateX(-50%)' }} />
        </div>
      </div>
    </div>
  );
}

const SCALE_LABELS = ['Low', 'Med', 'High', 'Max'];
const SEGS = 20;

function SegmentedBar({ label, value }) {
  const filled = Math.round(value * SEGS);
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
        <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>{label}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--brass)', letterSpacing: '0.08em' }}>{Math.round(value * 100)}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        {SCALE_LABELS.map(t => (
          <span key={t} style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, color: 'var(--faded-2)', letterSpacing: '0.08em' }}>{t}</span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 2 }}>
        {Array.from({ length: SEGS }).map((_, i) => (
          <div key={i} style={{
            flex: 1, height: 6, borderRadius: 1,
            background: i < filled ? 'var(--brass)' : 'var(--paper)',
            border: '0.5px solid', borderColor: i < filled ? 'var(--brass)' : 'rgba(176,141,87,0.25)',
          }} />
        ))}
      </div>
    </div>
  );
}

export default function StructureBars({ items, variant = 'ruler' }) {
  const gap = variant === 'ruler' ? 22 : 20;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {items.map(([label,, value]) =>
        variant === 'segmented'
          ? <SegmentedBar key={label} label={label} value={value} />
          : <RulerBar     key={label} label={label} value={value} />
      )}
    </div>
  );
}
