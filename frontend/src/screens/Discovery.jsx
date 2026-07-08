import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import { DISCOVERY_REGIONS, regionSlug } from '../lib/regions.js';
import { track } from '../lib/analytics.js';
import useIsMobile from '../lib/useIsMobile.js';

function RegionCard({ region, onClick }) {
  return (
    <div onClick={onClick} style={{ cursor: 'pointer', minWidth: 0 }}>
      <Poster region={region.name} compact />
      <div style={{ marginTop: 10 }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, color: 'var(--ink)', lineHeight: 1 }}>{region.name}</div>
        <div style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 3 }}>{region.coord}</div>
      </div>
    </div>
  );
}

export default function Discovery() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const tier1    = DISCOVERY_REGIONS.filter(r => r.tier === 1);
  const tier2    = DISCOVERY_REGIONS.filter(r => r.tier === 2);

  function openRegion(r) {
    track('region_opened', { region: r.name, tier: r.tier });
    navigate(`/regions/${regionSlug(r.name)}`);
  }

  if (isMobile) {
    return (
      <div style={{ overflowY: 'auto', height: '100%', WebkitOverflowScrolling: 'touch' }}>
        <div style={{ padding: '22px 16px 40px' }}>
          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 34, lineHeight: 1.05, color: 'var(--ink)', margin: '0 0 6px' }}>Browse by place</h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.6, color: 'var(--ink-2)', margin: '0 0 22px' }}>
            Every region is a poster. Start somewhere.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 18 }}>
            {tier1.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '32px 0 18px' }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--ink)', whiteSpace: 'nowrap' }}>More regions</span>
            <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 18 }}>
            {tier2.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '44px 32px 80px' }}>
      <Eyebrow>Discover</Eyebrow>
      <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 56, lineHeight: 1.0, color: 'var(--ink)', margin: '12px 0 0' }}>
        Browse by place.
      </h1>
      <p className="t-body" style={{ marginTop: 12, maxWidth: 520 }}>
        Every region is a poster; every poster is a map. Start somewhere and follow the wine home.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 24, marginTop: 36 }}>
        {tier1.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, margin: '52px 0 28px' }}>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', whiteSpace: 'nowrap' }}>More regions</span>
        <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 24 }}>
        {tier2.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
      </div>
    </div>
  );
}
