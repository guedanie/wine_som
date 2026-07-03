import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import { DISCOVERY_REGIONS, regionSlug } from '../lib/regions.js';

function RegionCard({ region, onClick }) {
  return (
    <div onClick={onClick} style={{ cursor: 'pointer' }}>
      <Poster region={region.name} />
      <div style={{ marginTop: 10 }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, color: 'var(--ink)', lineHeight: 1 }}>{region.name}</div>
        <div style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 3 }}>{region.coord}</div>
      </div>
    </div>
  );
}

export default function Discovery() {
  const navigate = useNavigate();
  const tier1    = DISCOVERY_REGIONS.filter(r => r.tier === 1);
  const tier2    = DISCOVERY_REGIONS.filter(r => r.tier === 2);

  function openRegion(r) {
    navigate(`/regions/${regionSlug(r.name)}`);
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24, marginTop: 36 }}>
        {tier1.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, margin: '52px 0 28px' }}>
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', whiteSpace: 'nowrap' }}>More regions</span>
        <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 24 }}>
        {tier2.map(r => <RegionCard key={r.name} region={r} onClick={() => openRegion(r)} />)}
      </div>
    </div>
  );
}
