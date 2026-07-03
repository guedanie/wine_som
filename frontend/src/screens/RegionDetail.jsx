import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import RegionMap from '../components/RegionMap.jsx';
import {
  REGION_META, REGION_POSTERS, REGION_DETAILS, SLUG_TO_REGION,
} from '../lib/regions.js';
import { getSubregionCounts } from '../lib/api.js';

const STRIPE_BG = 'repeating-linear-gradient(135deg, var(--paper), var(--paper) 11px, #E6DAC2 11px, #E6DAC2 22px)';

function FactCell({ label, value, sub, borderRight, borderBottom }) {
  return (
    <div style={{
      padding: '14px 16px',
      borderRight: borderRight ? '1px solid var(--border)' : 'none',
      borderBottom: borderBottom ? '1px solid var(--border)' : 'none',
    }}>
      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 5 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink)', lineHeight: 1.2 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 3 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

// Match a curated sub-region name to DB sub_region counts (case-insensitive
// containment either way — "Montalcino" matches "Brunello di Montalcino").
function countFor(name, counts) {
  if (!counts) return null;
  const target = name.toLowerCase();
  let total = 0;
  for (const [sub, n] of Object.entries(counts)) {
    const s = sub.toLowerCase();
    if (s.includes(target) || target.includes(s)) total += n;
  }
  return total > 0 ? total : null;
}

export default function RegionDetail() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const region = SLUG_TO_REGION[slug];
  const meta   = REGION_META[region];
  const detail = REGION_DETAILS[region];
  const poster = REGION_POSTERS[region];

  const [counts, setCounts] = useState(null);

  useEffect(() => {
    if (!region) return;
    getSubregionCounts(region).then(d => setCounts(d.counts)).catch(() => {});
  }, [region]);

  if (!region || !detail) {
    return (
      <div style={{ maxWidth: 1060, margin: '0 auto', padding: '28px 36px 80px' }}>
        <p className="t-body">Region not found.</p>
      </div>
    );
  }

  const latText = `Same parallel as ${detail.parallelNote}`;

  return (
    <div style={{ maxWidth: 1060, margin: '0 auto', padding: '28px 36px 80px' }}>
      <button
        onClick={() => navigate('/discover')}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 24 }}
      >
        ← Discovery
      </button>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 48, alignItems: 'start' }}>
        {/* Left — poster */}
        <div>
          <div style={{ background: 'var(--cream)', padding: 10, border: '1.5px solid var(--ink)', boxShadow: 'var(--shadow-print)' }}>
            <div style={{ border: '0.75px solid var(--brass)' }}>
              {poster ? (
                <img src={poster} alt={region}
                  style={{ display: 'block', width: '100%', aspectRatio: '372/494', objectFit: 'cover' }} />
              ) : (
                <div style={{ aspectRatio: '372/494', background: STRIPE_BG }} />
              )}
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginTop: 12 }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--ink)' }}>{meta.country}</span>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.14em', color: 'var(--sage)', whiteSpace: 'nowrap' }}>{meta.coord}</span>
          </div>
        </div>

        {/* Right — content */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="t-eyebrow" style={{ whiteSpace: 'nowrap' }}>Region Dossier</span>
            <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            <span className="t-coord" style={{ whiteSpace: 'nowrap' }}>{meta.coord}</span>
          </div>

          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 52, lineHeight: 1.0, color: 'var(--ink)', margin: '10px 0 0' }}>
            {region}
          </h1>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--faded)', marginTop: 6 }}>
            {meta.country}
          </div>

          <div style={{ height: 1, background: 'var(--border)', maxWidth: 540, margin: '22px 0 18px' }} />

          {/* Facts grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', maxWidth: 540, border: '1px solid var(--border)' }}>
            <FactCell label="Climate"  value={detail.climate}  sub={detail.climateSub}  borderRight borderBottom />
            <FactCell label="Soil"     value={detail.soil}     sub={detail.soilSub}     borderBottom />
            <FactCell label="Altitude" value={detail.altitude} sub={detail.altitudeSub} borderRight />
            <FactCell label="Latitude" value={meta.coord}      sub={latText} />
          </div>

          {/* Principal varietals */}
          <div style={{ marginTop: 28, maxWidth: 540 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 10 }}>
              Principal Varietals
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {detail.varietals.map(v => (
                <span key={v} style={{
                  fontFamily: 'var(--font-sans)', fontSize: 11, letterSpacing: '0.04em',
                  color: '#5C4A2E', border: '1px solid var(--brass)', padding: '4px 10px',
                  whiteSpace: 'nowrap',
                }}>
                  {v}
                </span>
              ))}
            </div>
          </div>

          {/* Sub-regions */}
          <div style={{ marginTop: 28, maxWidth: 540 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 4 }}>
              Sub-Regions
            </div>
            {detail.subregions.map(s => {
              const n = countFor(s.name, counts);
              return (
                <div key={s.name} style={{ display: 'flex', alignItems: 'center', padding: '11px 0', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--brass)', flex: 'none' }} />
                    <span style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {s.name}
                    </span>
                  </div>
                  <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.12em', color: 'var(--sage)', marginLeft: 12, whiteSpace: 'nowrap', flex: 'none' }}>
                    {s.coord}
                  </span>
                  {n != null && (
                    <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginLeft: 18, whiteSpace: 'nowrap' }}>
                      {n} wine{n !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Map */}
          <div style={{ marginTop: 28, maxWidth: 540 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 10 }}>
              Where it is
            </div>
            <RegionMap latlng={detail.latlng} zoom={detail.zoom} subregions={detail.subregions} />
          </div>

          {/* CTA */}
          <div style={{ marginTop: 28 }}>
            <button
              onClick={() => navigate(`/region/${encodeURIComponent(region)}`)}
              style={{
                fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500, letterSpacing: '0.04em',
                background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none',
                padding: '11px 22px', cursor: 'pointer',
              }}
            >
              Explore wines from {region} →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
