import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import {
  DISCOVERY_REGIONS, REGION_POSTERS, STYLE_WINE_TYPE, VARIETAL_OPTS, regionSlug,
} from '../lib/regions.js';
import { searchWines } from '../lib/api.js';
import useIsMobile, { loadZip } from '../lib/useIsMobile.js';

const STRIPE_BG = 'repeating-linear-gradient(135deg, var(--paper), var(--paper) 11px, #E6DAC2 11px, #E6DAC2 22px)';

const STYLES = Object.keys(STYLE_WINE_TYPE);
const RETAILERS = [
  "H-E-B", "Spec's", "Central Market", "Geraldine's Natural Wines",
  "AOC Selections", "US Natural Wine", "Antonelli's Cheese Shop",
];

function Chip({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: 'var(--font-sans)', fontSize: 11, padding: '5px 10px',
        margin: '0 4px 5px 0', display: 'inline-block', cursor: 'pointer',
        border: `1px solid ${active ? 'var(--bordeaux)' : 'var(--border)'}`,
        background: active ? 'var(--bordeaux)' : 'none',
        color: active ? 'var(--cream)' : 'var(--ink-2)',
        transition: 'all 0.12s var(--ease)',
      }}
    >
      {label}
    </button>
  );
}

function FilterSection({ label, children, last }) {
  return (
    <div style={{
      marginBottom: last ? 0 : 24, paddingBottom: last ? 0 : 24,
      borderBottom: last ? 'none' : '1px solid var(--border)',
    }}>
      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', display: 'block', marginBottom: 11 }}>
        {label}
      </span>
      {children}
    </div>
  );
}

function BottleThumb({ src, alt }) {
  const [failed, setFailed] = useState(false);
  return (
    <div style={{
      width: 40, height: 53, flex: 'none', background: STRIPE_BG,
      display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
    }}>
      {src && !failed ? (
        <img src={src} alt={alt} onError={() => setFailed(true)}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
      ) : (
        <svg width="14" height="36" viewBox="0 0 14 36" style={{ opacity: 0.3 }}>
          <path d="M5 0h4v10c0 2 5 4 5 8v16a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V18c0-4 5-6 5-8V0z" fill="var(--brass)" />
        </svg>
      )}
    </div>
  );
}

export default function SearchScreen() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const { state } = useLocation();
  const [params, setParams] = useSearchParams();

  const zip = state?.zip ?? loadZip();
  const [input, setInput]       = useState(params.get('q') ?? '');
  const [query, setQuery]       = useState(params.get('q') ?? '');
  const [styles, setStyles]     = useState(state?.prefs?.styles ?? []);
  const [maxPrice, setMaxPrice] = useState(state?.prefs?.budget ?? 200);
  const [inStock, setInStock]   = useState(true);
  const [retailers, setRetailers] = useState([]);
  const [varietals, setVarietals] = useState([]);

  const [wines, setWines]     = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const inputRef = useRef(null);

  async function runSearch(q) {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await searchWines({
        q, zip,
        maxPrice: maxPrice < 200 ? maxPrice : null,
        retailers, varietals,
      });
      setWines(data.wines);
    } catch (e) {
      setError(e.message);
      setWines([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (query) runSearch(query); }, [query, maxPrice, retailers, varietals]);

  function submit() {
    const q = input.trim();
    if (!q) return;
    setQuery(q);
    setParams({ q });
  }

  const toggle = (list, setList, v) =>
    setList(list.includes(v) ? list.filter(x => x !== v) : [...list, v]);

  // Style chips → wine_type filter (client-side)
  const wantedTypes = new Set(styles.map(s => STYLE_WINE_TYPE[s]).filter(Boolean));
  const visibleWines = wantedTypes.size > 0
    ? wines.filter(w => !w.wine_type || wantedTypes.has(w.wine_type))
    : wines;

  // Places — match query against curated regions
  const ql = query.trim().toLowerCase();
  const places = ql ? DISCOVERY_REGIONS.filter(r =>
    r.name.toLowerCase().includes(ql) ||
    r.country.toLowerCase().includes(ql) ||
    r.subregion.toLowerCase().includes(ql)
  ) : [];

  const activeFilterCount = styles.length + retailers.length + varietals.length + (inStock ? 1 : 0);

  const wineRow = w => (
    <div
      key={w.wine_id}
      onClick={() => navigate(`/wine/${w.wine_id}`, {
        state: { pick: { wine_id: w.wine_id, name: w.name, price: w.price, retailer: w.retailer, region: w.region }, zip },
      })}
      style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
    >
      <BottleThumb src={w.image_url} alt={w.name} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink)', lineHeight: 1.15 }}>{w.name}</div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginTop: 2 }}>
          {[w.brand, w.vintage_year, w.region].filter(Boolean).join(' · ')}
        </div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--sage)', marginTop: 2 }}>
          {w.retailer}{w.distance_miles != null ? ` · ${w.distance_miles} mi` : ''}
        </div>
      </div>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--bordeaux)', flexShrink: 0 }}>${w.price}</div>
    </div>
  );

  const DrawerChip = ({ label, active, onClick }) => (
    <button onClick={onClick} style={{
      cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 12,
      padding: '7px 12px', border: '1px solid',
      borderColor: active ? 'var(--bordeaux)' : 'var(--border)',
      background: active ? 'var(--bordeaux)' : 'none',
      color: active ? 'var(--cream)' : 'var(--ink-2)',
      borderRadius: 0, minHeight: 36, transition: 'all .12s', marginRight: 6, marginBottom: 6,
    }}>{label}</button>
  );

  if (isMobile) {
    return (
      <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Search bar */}
        <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid var(--border)', background: 'var(--cream)', flexShrink: 0 }}>
          <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)' }}>
            <svg style={{ margin: 'auto 12px', flexShrink: 0, color: 'var(--faded)' }} width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submit(); }}
              placeholder="Wine, producer, or region…"
              aria-label="Search wines and regions"
              style={{ flex: 1, border: 'none', background: 'transparent', outline: 'none', fontFamily: 'var(--font-serif)', fontSize: 18, color: 'var(--ink)', padding: '11px 4px', minWidth: 0 }}
            />
            {input && (
              <button onClick={() => { setInput(''); inputRef.current?.focus(); }} aria-label="Clear search"
                style={{ border: 'none', background: 'none', color: 'var(--faded)', padding: '0 12px', cursor: 'pointer', fontSize: 18, minWidth: 44, minHeight: 44 }}>×</button>
            )}
            <button onClick={submit} aria-label="Submit search"
              style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', padding: '0 16px', fontSize: 18, cursor: 'pointer', minWidth: 48 }}>→</button>
          </div>
        </div>

        {/* Active filter strip */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderBottom: '1px solid var(--border)', background: 'var(--cream-raised)', flexShrink: 0, overflowX: 'auto' }}>
          <button onClick={() => setDrawerOpen(true)} style={{
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600,
            color: activeFilterCount > 0 ? 'var(--cream)' : 'var(--ink-2)',
            background: activeFilterCount > 0 ? 'var(--bordeaux)' : 'none',
            border: '1px solid', borderColor: activeFilterCount > 0 ? 'var(--bordeaux)' : 'var(--border)',
            padding: '7px 12px', flexShrink: 0, minHeight: 36,
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="4" y1="6" x2="20" y2="6" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="11" y1="18" x2="13" y2="18" />
            </svg>
            Filters{activeFilterCount > 0 && ` · ${activeFilterCount}`}
          </button>
          <div style={{ flexShrink: 0, fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--ink-2)', border: '1px solid var(--border)', padding: '5px 10px', whiteSpace: 'nowrap' }}>
            Up to <span style={{ fontFamily: 'var(--font-serif)', color: 'var(--bordeaux)', fontSize: 14 }}>{maxPrice >= 200 ? '$200+' : `$${maxPrice}`}</span>
          </div>
          {styles.map(s => (
            <button key={s} onClick={() => toggle(styles, setStyles, s)} style={{ flexShrink: 0, cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--bordeaux)', background: 'var(--bordeaux-tint)', border: '1px solid var(--bordeaux)', padding: '5px 10px', display: 'flex', alignItems: 'center', gap: 5, minHeight: 36 }}>
              {s} <span style={{ fontSize: 14, lineHeight: 1 }}>×</span>
            </button>
          ))}
          {inStock && (
            <div style={{ flexShrink: 0, fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--sage)', border: '1px solid var(--sage)', padding: '5px 10px', whiteSpace: 'nowrap' }}>In stock</div>
          )}
        </div>

        {/* Results */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 14px 20px', WebkitOverflowScrolling: 'touch' }}>
          {query && !loading && (
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginBottom: 14 }}>
              {visibleWines.length} wine{visibleWines.length !== 1 ? 's' : ''} for “{query}”
            </div>
          )}
          {loading && <div className="t-body" style={{ padding: '16px 0' }}>Searching…</div>}
          {error && <div className="t-body" style={{ padding: '16px 0', color: 'var(--bordeaux)' }}>{error}</div>}
          {visibleWines.map(wineRow)}

          {places.length > 0 && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '20px 0 4px' }}>
                <span style={{ fontFamily: 'var(--font-sans)', fontSize: 9, fontWeight: 600, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', whiteSpace: 'nowrap' }}>Places</span>
                <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              </div>
              {places.map(r => (
                <div key={r.name} onClick={() => navigate(`/regions/${regionSlug(r.name)}`)}
                  style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}>
                  <div style={{ width: 40, height: 53, flexShrink: 0, background: STRIPE_BG, overflow: 'hidden' }}>
                    {REGION_POSTERS[r.name] && (
                      <img src={REGION_POSTERS[r.name]} alt={r.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink)' }}>{r.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--faded)', marginTop: 2 }}>{r.country} · {r.subregion}</div>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--bordeaux)', flexShrink: 0 }}>Explore →</span>
                </div>
              ))}
            </>
          )}
          {query && !loading && !error && visibleWines.length === 0 && places.length === 0 && (
            <div className="t-body" style={{ padding: '16px 0' }}>
              Nothing found for “{query}”. Try a grape, a region, or a producer name.
            </div>
          )}
          {!query && !loading && (
            <div style={{ paddingTop: 48, textAlign: 'center', color: 'var(--faded)', fontFamily: 'var(--font-sans)', fontSize: 14 }}>
              Search wines, producers, or regions.
            </div>
          )}
        </div>

        {/* Drawer dim */}
        <div onClick={() => setDrawerOpen(false)} style={{
          position: 'absolute', inset: 0, background: 'rgba(26,26,26,0.45)', zIndex: 20,
          opacity: drawerOpen ? 1 : 0, pointerEvents: drawerOpen ? 'auto' : 'none', transition: 'opacity 0.25s',
        }} />

        {/* Filter drawer */}
        <div data-testid="filter-drawer" style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 21,
          height: '82%', background: 'var(--cream)', borderTop: '1.5px solid var(--ink)',
          transform: drawerOpen ? 'translateY(0)' : 'translateY(100%)',
          transition: 'transform 0.3s cubic-bezier(0.2, 0.7, 0.3, 1)',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, position: 'relative' }}>
            <div style={{ width: 36, height: 3, background: 'var(--border)', borderRadius: 2, position: 'absolute', left: '50%', transform: 'translateX(-50%)', top: 6 }} />
            <span className="t-eyebrow">Filter wines</span>
            <button onClick={() => setDrawerOpen(false)} aria-label="Close filters"
              style={{ cursor: 'pointer', border: 'none', background: 'none', fontSize: 20, color: 'var(--faded)', minWidth: 44, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>×</button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px 16px 24px' }}>
            <div style={{ marginBottom: 24, paddingBottom: 24, borderBottom: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
                <span className="t-eyebrow">Max price</span>
                <span style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--bordeaux)' }}>{maxPrice >= 200 ? '$200+' : `$${maxPrice}`}</span>
              </div>
              <input type="range" min={15} max={200} step={5} value={maxPrice} aria-label="Max price"
                onChange={e => setMaxPrice(Number(e.target.value))} style={{ width: '100%', height: 4 }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--faded)', marginTop: 6 }}><span>$15</span><span>$200</span></div>
            </div>

            <div style={{ marginBottom: 24, paddingBottom: 24, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <span className="t-eyebrow">In stock near me</span>
                <div style={{ fontSize: 11, color: 'var(--faded)', marginTop: 3 }}>{zip} · within 10 mi</div>
              </div>
              <button onClick={() => setInStock(p => !p)} role="switch" aria-checked={inStock} aria-label="In stock near me"
                style={{ width: 44, height: 26, borderRadius: 13, background: inStock ? 'var(--bordeaux)' : 'var(--border)', border: 'none', position: 'relative', cursor: 'pointer', padding: 0, transition: 'background .15s', flexShrink: 0 }}>
                <span style={{ position: 'absolute', top: 5, left: inStock ? 22 : 4, width: 16, height: 16, borderRadius: '50%', background: '#fff', transition: 'left .15s' }} />
              </button>
            </div>

            <div style={{ marginBottom: 24, paddingBottom: 24, borderBottom: '1px solid var(--border)' }}>
              <span className="t-eyebrow" style={{ display: 'block', marginBottom: 12 }}>Style</span>
              <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                {STYLES.map(o => <DrawerChip key={o} label={o} active={styles.includes(o)} onClick={() => toggle(styles, setStyles, o)} />)}
              </div>
            </div>

            <div style={{ marginBottom: 24, paddingBottom: 24, borderBottom: '1px solid var(--border)' }}>
              <span className="t-eyebrow" style={{ display: 'block', marginBottom: 12 }}>Retailer</span>
              <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                {RETAILERS.map(r => <DrawerChip key={r} label={r.replace(' Natural Wines', '').replace(' Cheese Shop', '')} active={retailers.includes(r)} onClick={() => toggle(retailers, setRetailers, r)} />)}
              </div>
            </div>

            <div>
              <span className="t-eyebrow" style={{ display: 'block', marginBottom: 12 }}>Grape varietal</span>
              <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                {VARIETAL_OPTS.map(v => <DrawerChip key={v} label={v} active={varietals.includes(v)} onClick={() => toggle(varietals, setVarietals, v)} />)}
              </div>
            </div>
          </div>
          <div style={{ padding: '12px 16px 20px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
            <button onClick={() => setDrawerOpen(false)} style={{
              width: '100%', minHeight: 48, cursor: 'pointer', border: 'none', borderRadius: 0,
              background: 'var(--bordeaux)', color: 'var(--cream)',
              fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600, letterSpacing: '0.04em',
            }}>
              Show results
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 32px 0' }}>
      <button onClick={() => navigate(-1)}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 18 }}>
        ← Back
      </button>

      {/* Search bar */}
      <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)', maxWidth: 680, marginBottom: 28 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--faded)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" style={{ margin: 'auto 14px' }}>
          <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
        </svg>
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit(); }}
          placeholder="Search wines & regions…"
          aria-label="Search wines and regions"
          style={{
            flex: 1, fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--ink)',
            padding: '12px 8px', border: 'none', background: 'transparent', outline: 'none',
          }}
        />
        {input && (
          <button onClick={() => { setInput(''); inputRef.current?.focus(); }}
            aria-label="Clear search"
            style={{ background: 'none', border: 'none', color: 'var(--faded)', padding: '0 12px', cursor: 'pointer', fontSize: 16 }}>
            ×
          </button>
        )}
        <button onClick={submit} aria-label="Submit search"
          style={{ background: 'var(--bordeaux)', color: 'var(--cream)', border: 'none', padding: '0 20px', fontSize: 18, cursor: 'pointer' }}>
          →
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', margin: '0 -32px' }}>
        {/* Filter sidebar */}
        <aside style={{ borderRight: '1.5px solid var(--ink)', borderTop: '1.5px solid var(--ink)', padding: '24px 20px 40px', background: 'var(--cream-raised)' }}>
          <FilterSection label="Style">
            {STYLES.map(s => (
              <Chip key={s} label={s} active={styles.includes(s)}
                onClick={() => toggle(styles, setStyles, s)} />
            ))}
          </FilterSection>

          <FilterSection label="Max price">
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>$15</span>
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 18, color: 'var(--bordeaux)' }}>
                {maxPrice >= 200 ? '$200+' : `$${maxPrice}`}
              </span>
            </div>
            <input type="range" min={15} max={200} step={5} value={maxPrice}
              aria-label="Max price"
              onChange={e => setMaxPrice(Number(e.target.value))}
              style={{ width: '100%' }} />
          </FilterSection>

          <FilterSection label="In stock near me">
            <button
              onClick={() => setInStock(!inStock)}
              role="switch" aria-checked={inStock} aria-label="In stock near me"
              style={{
                width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
                background: inStock ? 'var(--bordeaux)' : 'var(--border)',
                position: 'relative', transition: 'background 0.15s var(--ease)',
              }}
            >
              <span style={{
                position: 'absolute', top: 4, left: inStock ? 20 : 4,
                width: 12, height: 12, borderRadius: '50%', background: '#fff',
                transition: 'left 0.15s var(--ease)',
              }} />
            </button>
          </FilterSection>

          <FilterSection label="Retailer">
            {RETAILERS.map(r => (
              <Chip key={r} label={r.replace(' Natural Wines', '').replace(' Cheese Shop', '')}
                active={retailers.includes(r)}
                onClick={() => toggle(retailers, setRetailers, r)} />
            ))}
          </FilterSection>

          <FilterSection label="Grape varietal" last>
            {VARIETAL_OPTS.map(v => (
              <Chip key={v} label={v} active={varietals.includes(v)}
                onClick={() => toggle(varietals, setVarietals, v)} />
            ))}
          </FilterSection>
        </aside>

        {/* Results */}
        <main style={{ padding: '28px 32px 60px', borderTop: '1.5px solid var(--ink)' }}>
          {query && !loading && (
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)', marginBottom: 4 }}>
              {visibleWines.length} wine{visibleWines.length !== 1 ? 's' : ''} for “{query}”
            </div>
          )}
          {loading && (
            <div className="t-body" style={{ padding: '20px 0' }}>Searching…</div>
          )}
          {error && (
            <div className="t-body" style={{ padding: '20px 0', color: 'var(--bordeaux)' }}>{error}</div>
          )}

          {visibleWines.map(w => (
            <div
              key={w.wine_id}
              onClick={() => navigate(`/wine/${w.wine_id}`, {
                state: {
                  pick: {
                    wine_id: w.wine_id, name: w.name, price: w.price,
                    retailer: w.retailer, region: w.region,
                  },
                  zip,
                },
              })}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--paper)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
              style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
            >
              <BottleThumb src={w.image_url} alt={w.name} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, color: 'var(--ink)', lineHeight: 1.1 }}>
                  {w.name}
                </div>
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 3 }}>
                  {[w.brand, w.vintage_year, w.region].filter(Boolean).join(' · ')}
                </div>
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--sage)', marginTop: 3 }}>
                  {w.retailer}{w.distance_miles != null ? ` · ${w.distance_miles} mi` : ''}
                </div>
              </div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--bordeaux)', flex: 'none' }}>
                ${w.price}
              </div>
            </div>
          ))}

          {/* Places */}
          {places.length > 0 && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '28px 0 4px' }}>
                <span style={{ fontFamily: 'var(--font-sans)', fontSize: 9, fontWeight: 600, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--faded)', whiteSpace: 'nowrap' }}>
                  Places
                </span>
                <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              </div>
              {places.map(r => (
                <div
                  key={r.name}
                  onClick={() => navigate(`/regions/${regionSlug(r.name)}`)}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--paper)'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                  style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
                >
                  <div style={{ width: 40, height: 53, flex: 'none', background: STRIPE_BG, overflow: 'hidden' }}>
                    {REGION_POSTERS[r.name] && (
                      <img src={REGION_POSTERS[r.name]} alt={r.name}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, color: 'var(--ink)', lineHeight: 1.1 }}>
                      {r.name}
                    </div>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 3 }}>
                      {r.country} · {r.subregion}
                    </div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--bordeaux)', whiteSpace: 'nowrap' }}>
                    Explore →
                  </span>
                </div>
              ))}
            </>
          )}

          {query && !loading && !error && visibleWines.length === 0 && places.length === 0 && (
            <div className="t-body" style={{ padding: '20px 0' }}>
              Nothing found for “{query}”. Try a grape, a region, or a producer name.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
