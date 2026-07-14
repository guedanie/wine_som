import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import DealCard from '../components/DealCard.jsx';
import { DISCOVERY_REGIONS, regionSlug } from '../lib/regions.js';
import { getDeals } from '../lib/api.js';
import { track } from '../lib/analytics.js';
import useIsMobile, { loadZip } from '../lib/useIsMobile.js';

// The weekly deals rail — a curated cut on Discover, not a destination you
// must seek. Renders nothing when the week has no cut (absence is the design).
function DealsRail({ compact }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  useEffect(() => {
    getDeals(loadZip(), 10).then(setData).catch(() => {});
  }, []);
  if (!data || data.deals.length === 0) return null;
  const open = deal => {
    track('deal_opened', { wine_id: deal.wine_id, retailer: deal.retailer, source: 'rail' });
    navigate(`/wine/${deal.wine_id}`, {
      state: { pick: {
        wine_id: deal.wine_id, name: deal.name, price: deal.price, retailer: deal.retailer,
        region: deal.region, varietal: deal.varietal, image_url: deal.image_url,
        vivino_rating: deal.vivino_rating, vivino_ratings_count: deal.vivino_ratings_count,
        store_address: deal.store_address,
        price_drop: { amount: deal.amount, from_price: deal.was_price, to_price: deal.price },
      } },
    });
  };
  return (
    <div style={{ margin: compact ? '0 0 28px' : '36px 0 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 12 }}>
        <Eyebrow>Worth grabbing · Week of {data.week_of}</Eyebrow>
        <button onClick={() => navigate('/deals')} style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0, fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--bordeaux)', whiteSpace: 'nowrap' }}>
          See all {data.count} →
        </button>
      </div>
      <div style={{ display: 'flex', gap: 14, overflowX: 'auto', paddingBottom: 6, WebkitOverflowScrolling: 'touch' }}>
        {data.deals.map(d => <DealCard key={d.wine_id} deal={d} onClick={() => open(d)} />)}
      </div>
    </div>
  );
}

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
          <DealsRail compact />
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

      <DealsRail />

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
