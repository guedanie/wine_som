import { REGION_POSTERS, REGION_META } from '../lib/regions.js';

function CompassRose() {
  const angles = [0, 45, 90, 135, 180, 225, 270, 315];
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="16" fill="none" stroke="var(--brass)" strokeWidth="0.75" />
      {angles.map((a, i) => {
        const rad = (a * Math.PI) / 180;
        const r1 = 13, r2 = i % 2 === 0 ? 10 : 12;
        return (
          <line
            key={a}
            x1={18 + Math.cos(rad) * r1} y1={18 + Math.sin(rad) * r1}
            x2={18 + Math.cos(rad) * r2} y2={18 + Math.sin(rad) * r2}
            stroke="var(--brass)" strokeWidth={i % 2 === 0 ? 1 : 0.75}
          />
        );
      })}
      <text x="18" y="8" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="5" fill="var(--brass)">N</text>
      <circle cx="18" cy="18" r="2" fill="var(--bordeaux)" />
    </svg>
  );
}

export default function Poster({ region, className, compact }) {
  const src  = REGION_POSTERS[region];
  const meta = REGION_META[region];

  return (
    <div className={className} style={{ width: '100%' }}>
      {/* Header above frame */}
      {meta && !compact && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.3em', textTransform: 'uppercase', color: 'var(--faded)' }}>
            {meta.country}
          </div>
          <div style={{ flex: 1, height: '0.75px', background: 'var(--border)' }} />
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--sage)', letterSpacing: '0.1em' }}>
            {meta.coord}
          </div>
        </div>
      )}

      {/* Frame */}
      <div style={{ background: 'var(--cream)', padding: 10, border: '1.5px solid var(--ink)', boxShadow: 'var(--shadow-print)' }}>
        <div style={{ border: '0.75px solid var(--brass)', padding: 4 }}>
          {src ? (
            <img src={src} alt={region} style={{ display: 'block', width: '100%', aspectRatio: '372/494', objectFit: 'cover' }} />
          ) : (
            <div style={{ aspectRatio: '372/494', background: 'repeating-linear-gradient(135deg,var(--bordeaux-deep) 0px,var(--bordeaux-deep) 8px,var(--bordeaux) 8px,var(--bordeaux) 16px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.22em', color: 'var(--cream)', opacity: 0.5 }}>REGION POSTER</span>
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--cream)', opacity: 0.7 }}>{region}</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer below frame */}
      {meta && !compact && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 32, lineHeight: 1, color: 'var(--ink)' }}>
            {region}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 7 }}>
            <CompassRose />
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--ink-2)', letterSpacing: '0.1em' }}>
                {meta.coord}
              </div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, color: 'var(--faded)', marginTop: 2, letterSpacing: '0.04em' }}>
                {meta.subregion}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
