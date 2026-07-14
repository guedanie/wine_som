import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import WineCard from '../components/WineCard.jsx';
import { getDeals } from '../lib/api.js';
import { deriveWineCardMeta } from '../lib/regions.js';
import { loadZip } from '../lib/useIsMobile.js';
import { track } from '../lib/analytics.js';

// "Worth grabbing this week" — the full editorial deals screen (design:
// price-intelligence handoff, Surface 3). Ranked by wine quality × price
// movement; the empty week is a designed, resolved state.
const toPick = d => deriveWineCardMeta({
  wine_id: d.wine_id, name: d.name, price: d.price, retailer: d.retailer,
  region: d.region, varietal: d.varietal, wine_type: d.wine_type,
  image_url: d.image_url, vivino_rating: d.vivino_rating,
  vivino_ratings_count: d.vivino_ratings_count,
  flavor_profile: d.flavor_profile, store_address: d.store_address,
  price_drop: { amount: d.amount, from_price: d.was_price, to_price: d.price },
});

export default function Deals() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const zip = loadZip();

  useEffect(() => {
    getDeals(zip, 40).then(setData).catch(() => setError(true));
  }, [zip]);

  const open = deal => {
    track('deal_opened', { wine_id: deal.wine_id, retailer: deal.retailer });
    navigate(`/wine/${deal.wine_id}`, { state: { pick: toPick(deal) } });
  };

  return (
    <div style={{ overflowY: 'auto', height: '100%', WebkitOverflowScrolling: 'touch' }}>
      <div style={{ maxWidth: 640, margin: '0 auto', padding: '28px 16px 80px' }}>
        <Eyebrow>Worth grabbing{data ? ` · Week of ${data.week_of}` : ''}</Eyebrow>
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 32, lineHeight: 1.08, color: 'var(--ink)', margin: '10px 0 8px' }}>
          Good wine whose price just moved
        </h1>
        <p style={{ fontFamily: 'var(--font-sans)', fontSize: 13.5, lineHeight: 1.6, color: 'var(--ink-2)', margin: '0 0 24px' }}>
          Not a bargain bin. These are bottles I&rsquo;d recommend anyway — they just
          happen to be cheaper near you this week.
        </p>

        {error && (
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)' }}>
            Couldn&rsquo;t load this week&rsquo;s cut — try again in a moment.
          </p>
        )}
        {data && data.deals.length === 0 && (
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 13.5, lineHeight: 1.6, color: 'var(--faded)' }}>
            Nothing worth flagging near you this week — prices are checked every
            Sunday, and I only list bottles I&rsquo;d pour anyway.
          </p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {(data?.deals ?? []).map(d => (
            <WineCard key={d.wine_id} variant="landscape" wine={toPick(d)} onClick={() => open(d)} />
          ))}
        </div>
      </div>
    </div>
  );
}
