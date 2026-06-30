import { useState, useEffect, useMemo } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import WineCard from '../components/WineCard.jsx';
import Btn from '../components/Btn.jsx';
import { getRegionWines } from '../lib/api.js';
import { DISCOVERY_REGIONS, deriveWineCardMeta, buildApiReq } from '../lib/regions.js';

const PRICE_BANDS = [
  { label: 'Under $20',  min: 0,   max: 20 },
  { label: '$20 – $40',  min: 20,  max: 40 },
  { label: '$40 – $75',  min: 40,  max: 75 },
  { label: '$75+',       min: 75,  max: Infinity },
];

function Chip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        cursor: 'pointer',
        fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 500,
        padding: '5px 13px', borderRadius: 999,
        border: active ? '1.5px solid var(--bordeaux)' : '1.5px solid var(--border)',
        background: active ? 'var(--bordeaux)' : 'var(--cream-raised)',
        color: active ? 'var(--cream)' : 'var(--ink)',
        transition: 'all .15s',
      }}>
      {label}
    </button>
  );
}

export default function RegionBrowse() {
  const { slug }   = useParams();
  const { state }  = useLocation();
  const navigate   = useNavigate();

  const regionName = decodeURIComponent(slug);
  const regionMeta = DISCOVERY_REGIONS.find(r => r.name === regionName) ?? { coord: null };

  const [zip,       setZip]       = useState(state?.zip ?? '78209');
  const [zipInput,  setZipInput]  = useState(state?.zip ?? '78209');
  const [retailers, setRetailers] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  // Filter state
  const [activeGrapes,    setActiveGrapes]    = useState([]);
  const [activeRetailers, setActiveRetailers] = useState([]);

  async function fetchWines(z) {
    setLoading(true);
    setError(null);
    setActiveGrapes([]);
    setActiveRetailers([]);
    try {
      const data = await getRegionWines(regionName, z);
      setRetailers(data.retailers ?? []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchWines(zip); }, [zip]);

  function handleZipSubmit(e) {
    e.preventDefault();
    if (zipInput.length === 5) setZip(zipInput);
  }

  // Flatten all wines from all retailers, dedup by wine_id keeping lowest price.
  const allWines = useMemo(() => {
    const seen = new Map();
    retailers.forEach(section => {
      section.wines.forEach(w => {
        const existing = seen.get(w.wine_id);
        if (!existing || w.price < existing.price) {
          seen.set(w.wine_id, w);
        }
      });
    });
    return [...seen.values()];
  }, [retailers]);

  const availableGrapes = useMemo(() => {
    const seen = new Set();
    allWines.forEach(w => { if (w.varietal) seen.add(w.varietal); });
    return [...seen].sort();
  }, [allWines]);

  const availableRetailers = useMemo(() => retailers.map(s => s.retailer), [retailers]);

  const filteredWines = useMemo(() => {
    return allWines.filter(w => {
      if (activeRetailers.length > 0 && !activeRetailers.includes(w.retailer)) return false;
      if (activeGrapes.length > 0 && !activeGrapes.includes(w.varietal)) return false;
      return true;
    });
  }, [allWines, activeRetailers, activeGrapes]);

  const byPriceBand = useMemo(() => {
    return PRICE_BANDS.map(band => ({
      ...band,
      wines: filteredWines
        .filter(w => w.price >= band.min && w.price < band.max)
        .sort((a, b) => a.price - b.price),
    })).filter(band => band.wines.length > 0);
  }, [filteredWines]);

  const totalVisible = filteredWines.length;
  const hasFilters   = activeGrapes.length > 0 || activeRetailers.length > 0;

  function toggleGrape(g) {
    setActiveGrapes(p => p.includes(g) ? p.filter(x => x !== g) : [...p, g]);
  }
  function toggleRetailer(r) {
    setActiveRetailers(p => p.includes(r) ? p.filter(x => x !== r) : [...p, r]);
  }

  function handleAskSommelier() {
    const freeText = [
      `Wines from ${regionName}`,
      ...(activeGrapes.length ? [`Grape: ${activeGrapes.join(', ')}`] : []),
    ].join(' · ');
    const prefs = { zip, budget: 100, styles: [], occasion: 'Tonight', wineTypes: [], grapes: activeGrapes, freeText };
    navigate('/recommend', { state: { prefs, apiReq: buildApiReq(prefs) } });
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px 80px' }}>
      <button
        onClick={() => navigate('/discover')}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 22 }}>
        ← Back to Discover
      </button>

      {/* Hero row */}
      <div style={{ display: 'flex', gap: 40, alignItems: 'flex-start', marginBottom: 32 }}>
        <div style={{ flex: 1 }}>
          <Eyebrow>Discover</Eyebrow>
          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 56, lineHeight: 1.0, color: 'var(--ink)', margin: '10px 0 0' }}>
            {regionName}
          </h1>
          {regionMeta.coord && (
            <div style={{ fontSize: 12, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 6 }}>{regionMeta.coord}</div>
          )}
          <form onSubmit={handleZipSubmit} style={{ marginTop: 24, display: 'flex', gap: 10, alignItems: 'center' }}>
            <label style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>Near</label>
            <input
              value={zipInput}
              onChange={e => setZipInput(e.target.value.replace(/\D/g, '').slice(0, 5))}
              maxLength={5}
              placeholder="78209"
              style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink)', background: 'var(--cream-raised)', border: '1.5px solid var(--ink)', padding: '8px 11px', width: 90, borderRadius: 0, outline: 'none' }}
            />
            {zipInput.length === 5 && zipInput !== zip && (
              <Btn type="submit" variant="ghost">Update</Btn>
            )}
          </form>
        </div>
        <div style={{ width: 160, flex: 'none' }}>
          <Poster region={regionName} />
        </div>
      </div>

      {/* Filter bar */}
      {!loading && !error && allWines.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', padding: '14px 0', marginBottom: 32, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {availableGrapes.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', width: 52 }}>Grape</span>
              {availableGrapes.map(g => (
                <Chip key={g} label={g} active={activeGrapes.includes(g)} onClick={() => toggleGrape(g)} />
              ))}
            </div>
          )}
          {availableRetailers.length > 1 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', width: 52 }}>Retailer</span>
              {availableRetailers.map(r => (
                <Chip key={r} label={r} active={activeRetailers.includes(r)} onClick={() => toggleRetailer(r)} />
              ))}
            </div>
          )}
          {hasFilters && (
            <div>
              <button onClick={() => { setActiveGrapes([]); setActiveRetailers([]); }}
                style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', padding: 0, textDecoration: 'underline' }}>
                Clear filters
              </button>
            </div>
          )}
        </div>
      )}

      {loading && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', padding: '40px 0' }}>
          Loading wines from {regionName}…
        </div>
      )}
      {error && !loading && (
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--bordeaux)', padding: '40px 0' }}>{error}</div>
      )}

      {/* Empty state after filtering */}
      {!loading && !error && totalVisible === 0 && allWines.length > 0 && (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', marginBottom: 10 }}>No matches</div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', marginBottom: 20 }}>
            No wines in {regionName} match your current filters near {zip}.
          </div>
          <Btn onClick={handleAskSommelier}>Ask the sommelier →</Btn>
        </div>
      )}

      {/* Price band sections */}
      {!loading && !error && byPriceBand.map(band => (
        <div key={band.label} style={{ marginBottom: 56 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
            <Eyebrow>{band.label}</Eyebrow>
            <span style={{ flex: 1, height: '1px', background: 'var(--border)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
              {band.wines.length} wine{band.wines.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 18 }}>
            {band.wines.map(w => {
              const meta = { ...deriveWineCardMeta(w), store_address: null };
              return (
                <WineCard
                  key={w.wine_id}
                  wine={meta}
                  onClick={() => navigate(`/wine/${w.wine_id}`, {
                    state: { pick: meta, chatState: null },
                  })}
                />
              );
            })}
          </div>
        </div>
      ))}

      {/* Ask sommelier CTA */}
      {!loading && !error && totalVisible > 0 && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 32, display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)' }}>
            {totalVisible} wine{totalVisible !== 1 ? 's' : ''} available near {zip}
          </span>
          <span style={{ flex: 1 }} />
          <Btn onClick={handleAskSommelier}>Get a recommendation →</Btn>
        </div>
      )}
    </div>
  );
}
