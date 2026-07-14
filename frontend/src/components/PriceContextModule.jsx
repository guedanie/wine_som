import PriceMarker from './PriceMarker.jsx';
import Eyebrow from './Eyebrow.jsx';

// Dossier price-context module — sits directly above the availability list and
// frames how to read it. Prose leads (history is ~6 weekly points — no real
// chart); the week-marker strip is a supporting glyph that upgrades to a
// sparkline as history deepens. The sparse/steady state is the common case and
// must feel resolved, not empty.
// Design: frontend/design-system/handoffs/price-intelligence/README.md.

const fmt = p => (Number.isInteger(p) ? `$${p}` : `$${p.toFixed(2)}`);

function WeekStrip({ strip, variant, compact }) {
  if (!strip?.length) return null;
  const min = Math.min(...strip);
  const max = Math.max(...strip);
  const range = max - min;
  const H = compact ? 22 : 30;
  const height = p => (range ? 12 + ((p - min) / range) * (H - 12) : H * 0.7);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: H }}>
        {strip.map((p, i) => {
          const isLast = i === strip.length - 1;
          const isPrev = i === strip.length - 2;
          const bg = variant === 'drop' && isLast ? 'var(--bordeaux)'
                   : isPrev ? 'var(--brass)' : 'var(--paper)';
          return (
            <span key={i} style={{
              width: compact ? 5 : 8, height: height(p), background: bg,
              border: '0.75px solid var(--border)', display: 'inline-block',
            }} />
          );
        })}
      </div>
      {!compact && (
        <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 9, letterSpacing: '0.12em', color: 'var(--faded)' }}>
          JUN → NOW
        </span>
      )}
    </div>
  );
}

export default function PriceContextModule({ ctx, compact = false }) {
  if (!ctx || !ctx.cheapest) return null;
  const isDrop = ctx.variant === 'drop';
  const { cheapest } = ctx;
  const sinceMonth = (ctx.since_label || 'since June').replace('since ', '');

  return (
    <div style={{
      background: 'var(--cream-raised)', border: '1px solid var(--border)',
      padding: compact ? '14px 16px' : '18px 20px', marginBottom: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10, paddingBottom: 10, borderBottom: '0.75px solid var(--brass)', marginBottom: 12 }}>
        <Eyebrow>Price this week</Eyebrow>
        <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 10, letterSpacing: '0.08em', color: 'var(--faded)' }}>
          {ctx.weeks_tracked} weekly check{ctx.weeks_tracked === 1 ? '' : 's'} {ctx.since_label ?? ''}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ minWidth: 0 }}>
          {isDrop ? (
            <>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: compact ? 23 : 26, lineHeight: 1.15, color: 'var(--ink)' }}>
                Down to <span style={{ color: 'var(--bordeaux)' }}>{fmt(ctx.to_price)}</span> at {ctx.store}.
              </div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12.5, lineHeight: 1.55, color: 'var(--faded)', marginTop: 6 }}>
                Was {fmt(ctx.from_price)} — it slipped this week.
                {cheapest.delta_vs_next != null && ` Cheapest nearby by ${fmt(cheapest.delta_vs_next)}.`}
              </div>
            </>
          ) : (
            <>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: compact ? 23 : 26, lineHeight: 1.15, color: 'var(--ink)' }}>
                {fmt(cheapest.price)} at {cheapest.retailer} — <span style={{ color: 'var(--faded)' }}>steady so far.</span>
              </div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12.5, lineHeight: 1.55, color: 'var(--faded)', marginTop: 6 }}>
                No movement since I started watching it in {sinceMonth}. I&rsquo;ll flag it here the week it drops.
              </div>
            </>
          )}
          <div style={{ marginTop: 10 }}>
            {isDrop
              ? <PriceMarker variant="drop" amount={ctx.amount} store={compact ? null : ctx.store} />
              : <PriceMarker variant="steady" sinceLabel={ctx.since_label ?? undefined} />}
          </div>
        </div>
        <WeekStrip strip={ctx.strip} variant={ctx.variant} compact={compact} />
      </div>
    </div>
  );
}
