import { REGION_POSTERS } from '../lib/regions.js';

export default function Poster({ region, className }) {
  const src = REGION_POSTERS[region];
  return (
    <div className={className} style={{ width: '100%' }}>
      <div style={{ background: 'var(--cream)', padding: 10, border: '1.5px solid var(--ink)', boxShadow: 'var(--shadow-print)' }}>
        <div style={{ border: '0.75px solid var(--brass)', padding: 4 }}>
          {src ? (
            <img src={src} alt={region} style={{ display: 'block', width: '100%', aspectRatio: '372/494', objectFit: 'cover' }} />
          ) : (
            <div style={{ aspectRatio: '372/494', background: 'repeating-linear-gradient(135deg,var(--bordeaux-deep) 0px,var(--bordeaux-deep) 8px,var(--bordeaux) 8px,var(--bordeaux) 16px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.22em', color: 'rgba(245,239,230,0.5)' }}>REGION POSTER</span>
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'rgba(245,239,230,0.7)' }}>{region}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
