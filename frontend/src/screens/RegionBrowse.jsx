import { useState, useEffect, useMemo } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Poster from '../components/Poster.jsx';
import WineCard from '../components/WineCard.jsx';
import Btn from '../components/Btn.jsx';
import { getRegionWines } from '../lib/api.js';
import { DISCOVERY_REGIONS, deriveWineCardMeta, buildApiReq } from '../lib/regions.js';

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
  const [priceMin,        setPriceMin]        = useState(0);
  const [priceMax,        setPriceMax]        = useState(999);
  const [boundsSet,       setBoundsSet]       = useState(false);

  async function fetchWines(z) {
    setLoading(true);
    setError(null);
    setActiveGrapes([]);
    setActiveRetailers([]);
    setBoundsSet(false);
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

  // Set price bounds once after first load
  useEffect(() => {
    if (boundsSet || retailers.length === 0) return;
    const all = retailers.flatMap(s => s.wines.map(w => w.price));
    if (!all.length) return;
    setPriceMin(Math.floor(Math.min(...all)));
    setPriceMax(Math.ceil(Math.max(...all)));
    setBoundsSet(true);
  }, [retailers, boundsSet]);

  function handleZipSubmit(e) {
    e.preventDefault();
    if (zipInput.length === 5) setZip(zipInput);
  }

  const availableGrapes = useMemo(() => {
    const seen = new Set();
    retailers.forEach(s => s.wines.forEach(w => { if (w.varietal) seen.add(w.varietal); }));
    return [...seen].sort();
  }, [retailers]);

  const availableRetailers = useMemo(() => retailers.map(s => s.retailer), [retailers]);

  const filteredRetailers = useMemo(() => {
    return retailers.map(section => {
      if (activeRetailers.length > 0 && !activeRetailers.includes(section.retailer)) {
        return { ...section, wines: [] };
      }
      const wines = section.wines.filter(w => {
        if (activeGrapes.length > 0 && !activeGrapes.includes(w.varietal)) return false;
        if (w.price < priceMin || w.price > priceMax) return false;
        return true;
      });
      return { ...section, wines };
    }).filter(s => s.wines.length > 0);
  }, [retailers, activeGrapes, activeRetailers, priceMin, priceMax]);

  const totalVisible = filteredRetailers.reduce((n, s) => n + s.wines.length, 0);
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
    const prefs = { zip, budget: priceMax || 100, styles: [], occasion: 'Tonight', wineTypes: [], grapes: activeGrapes, freeText };
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
      {!loading && !error && retailers.length > 0 && (
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
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', width: 52 }}>Price</span>
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--ink)' }}>$</span>
            <input type="number" value={priceMin} min={0} onChange={e => setPriceMin(+e.target.value)}
              style={{ fontFamily: 'var(--font-sans)', fontSize: 13, width: 60, border: '1.5px solid var(--border)', background: 'var(--cream-raised)', padding: '4px 8px', borderRadius: 0, outline: 'none', color: 'var(--ink)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)' }}>–</span>
            <input type="number" value={priceMax} min={0} onChange={e => setPriceMax(+e.target.value)}
              style={{ fontFamily: 'var(--font-sans)', fontSize: 13, width: 60, border: '1.5px solid var(--border)', background: 'var(--cream-raised)', padding: '4px 8px', borderRadius: 0, outline: 'none', color: 'var(--ink)' }} />
            {hasFilters && (
              <button onClick={() => { setActiveGrapes([]); setActiveRetailers([]); }}
                style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', padding: '0 4px', textDecoration: 'underline' }}>
                Clear
              </button>
            )}
          </div>
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
      {!loading && !error && totalVisible === 0 && retailers.length > 0 && (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--ink)', marginBottom: 10 }}>No matches</div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--faded)', marginBottom: 20 }}>
            No wines in {regionName} match your current filters near {zip}.
          </div>
          <Btn onClick={handleAskSommelier}>Ask the sommelier →</Btn>
        </div>
      )}

      {/* Retailer sections */}
      {!loading && !error && filteredRetailers.map(section => (
        <div key={section.retailer} style={{ marginBottom: 48 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
            <Eyebrow>{section.retailer}</Eyebrow>
            <span style={{ flex: 1, height: '1px', background: 'var(--border)' }} />
            <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
              {section.wines.length} wine{section.wines.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 18 }}>
            {section.wines.map(w => {
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
    </div>
  );
}
