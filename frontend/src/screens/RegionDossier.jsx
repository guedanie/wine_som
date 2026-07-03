import { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Btn from '../components/Btn.jsx';
import Contours from '../components/Contours.jsx';
import Tag from '../components/Tag.jsx';
import StructureBars from '../components/StructureBars.jsx';
import SommOverlay from '../components/SommOverlay.jsx';
import { REGION_POSTERS, REGION_META, REGION_DETAILS, regionSlug } from '../lib/regions.js';
import { getWine } from '../lib/api.js';

function structureToBars(sp) {
  if (!sp) return [];
  return [
    ['Body',    'Body',    (sp.body    ?? 0) / 10],
    ['Tannin',  'Tannin',  (sp.tannins ?? 0) / 10],
    ['Acidity', 'Acidity', (sp.acidity ?? 0) / 10],
    ['Finish',  'Finish',  (sp.finish  ?? 0) / 10],
  ].filter(([,, v]) => v > 0);
}

function shopifyHiRes(url) {
  if (!url || !url.includes('cdn.shopify.com')) return url;
  // Shopify CDN: insert _1200x before the extension to request larger size.
  // Guard: skip if a size suffix is already present.
  return /(_\d+x\d*)\.[a-z]+(\?|$)/i.test(url)
    ? url
    : url.replace(/(\.[a-z]{3,4})(\?|$)/i, '_1200x$1$2');
}

function BottleFrame({ src, alt }) {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = src && !imgFailed;
  const hiResSrc  = showImage ? shopifyHiRes(src) : null;

  return (
    <div style={{
      background: 'var(--cream-raised)',
      padding: 10,
      border: '1.5px solid var(--ink)',
      boxShadow: '0 18px 40px -22px rgba(0,0,0,0.50)',
    }}>
      <div style={{ border: '0.75px solid var(--brass)' }}>
        <div style={{
          aspectRatio: '372/494',
          // Stripe only shows through when there is NO image — clean cream behind a bottle shot
          background: showImage
            ? 'var(--cream-raised)'
            : 'repeating-linear-gradient(135deg, #EFE6D4, #EFE6D4 11px, #E6DAC2 11px, #E6DAC2 22px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          position: 'relative',
          padding: showImage ? '12px 8%' : 0,
        }}>
          {showImage && (
            <img
              src={hiResSrc}
              alt={alt}
              onError={() => setImgFailed(true)}
              style={{
                display: 'block',
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                imageRendering: 'high-quality',
              }}
            />
          )}
          {!showImage && (
            <div style={{
              fontFamily: 'var(--font-sans)',
              fontSize: 10,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--faded)',
              textAlign: 'center',
              lineHeight: 1.7,
            }}>
              Wine bottle<br />image
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RegionThumbnail({ region, meta, posterSrc, onExplore }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginTop: 14 }}>
      {/* Mini poster frame */}
      <div style={{ flex: 'none', width: 88 }}>
        <div style={{ padding: 6, border: '1.5px solid var(--ink)' }}>
          <div style={{ border: '0.75px solid var(--brass)' }}>
            {posterSrc ? (
              <img
                src={posterSrc}
                alt={region}
                style={{ display: 'block', width: '100%', aspectRatio: '88/118', objectFit: 'cover' }}
              />
            ) : (
              <div style={{
                aspectRatio: '88/118',
                background: 'repeating-linear-gradient(135deg, #EFE6D4, #EFE6D4 11px, #E6DAC2 11px, #E6DAC2 22px)',
              }} />
            )}
          </div>
        </div>
      </div>

      {/* Region text */}
      <div style={{ paddingTop: 4 }}>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 9, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faded)', marginBottom: 4 }}>
          Region
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink)', lineHeight: 1.1 }}>
          {region}
        </div>
        {meta?.country && (
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--faded)', marginTop: 4 }}>
            {meta.country}
          </div>
        )}
        {meta?.coord && (
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, letterSpacing: '0.12em', color: 'var(--faded)', marginTop: 6 }}>
            {meta.coord}
          </div>
        )}
        <button
          onClick={onExplore}
          style={{ marginTop: 10, fontFamily: 'var(--font-sans)', fontSize: 11, letterSpacing: '0.06em', color: 'var(--bordeaux)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
        >
          Explore region →
        </button>
      </div>
    </div>
  );
}

export default function RegionDossier() {
  const { id }     = useParams();
  const { state }  = useLocation();
  const navigate   = useNavigate();
  const pick      = state?.pick ?? {};
  const chatState = state?.pick?.chatState ?? state?.chatState ?? null;
  const zip       = state?.zip ?? chatState?.prefs?.zip ?? pick?.chatState?.prefs?.zip ?? null;

  const [detail, setDetail] = useState(null);

  async function fetchDetail() {
    try { setDetail(await getWine(id, zip)); } catch {}
  }

  useEffect(() => { fetchDetail(); }, [id]);

  const wine    = detail ?? {};
  const rawDetails = wine.wine_details;
  const details = Array.isArray(rawDetails) ? (rawDetails[0] ?? {}) : (rawDetails ?? {});
  const flavors = details.flavor_profile ?? [];
  const bars    = structureToBars(details.structure_profile);
  const region  = wine.region ?? pick.region;
  const subtitle = [wine.brand, wine.vintage_year, pick.retailer].filter(Boolean).join(' · ');
  const meta     = REGION_META[region] ?? null;
  const posterSrc = REGION_POSTERS[region] ?? null;

  const sommWine = {
    wine_name:             wine.name ?? pick.name,
    producer:              wine.brand        ?? null,
    vintage:               wine.vintage_year ?? null,
    price:                 pick.price        ?? null,
    store:                 pick.retailer     ?? null,
    tags:                  flavors,
    region:                region            ?? null,
    wine_type:             wine.wine_type    ?? null,
    vivino_rating:         wine.vivino_rating         ?? null,
    vivino_ratings_count:  wine.vivino_ratings_count  ?? null,
  };

  return (
    <div style={{ maxWidth: 1060, margin: '0 auto', padding: '32px 36px 100px' }}>
      <button
        onClick={() => {
          if (chatState) {
            navigate('/recommend', {
              state: {
                prefs:     chatState.prefs,
                apiReq:    chatState.apiReq,
                _restored: chatState,
              },
            });
          } else {
            navigate(-1);
          }
        }}
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 26 }}
      >
        ← Back to recommendations
      </button>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 48, alignItems: 'start' }}>
        {/* Left column — bottle image + region thumbnail */}
        <div>
          <BottleFrame
            src={wine.image_url ?? null}
            alt={[wine.name ?? pick.name, wine.vintage_year].filter(Boolean).join(' ')}
          />
          {region && (
            <RegionThumbnail
              region={region}
              meta={meta}
              posterSrc={posterSrc}
              onExplore={() => REGION_DETAILS[region]
                ? navigate(`/regions/${regionSlug(region)}`)
                : navigate('/discover')}
            />
          )}
        </div>

        {/* Right column — wine detail */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Eyebrow style={{ whiteSpace: 'nowrap' }}>{region}</Eyebrow>
            <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            {pick.coord && <span className="t-coord" style={{ whiteSpace: 'nowrap' }}>{pick.coord}</span>}
          </div>

          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 48, lineHeight: 1.0, color: 'var(--ink)', margin: '12px 0 0' }}>
            {wine.name ?? pick.name}
          </h1>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 10 }}>
            {subtitle && <span style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink-2)' }}>{subtitle}</span>}
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--bordeaux)' }}>${pick.price}</span>
          </div>

          {wine.vivino_rating && wine.vivino_ratings_count > 0 && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--ink-2)', fontWeight: 500 }}>
                {wine.vivino_rating.toFixed(1)} ★
              </span>
              <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--faded)' }}>
                {wine.vivino_ratings_count >= 1000
                  ? `${Math.round(wine.vivino_ratings_count / 1000)}k`
                  : wine.vivino_ratings_count} ratings on Vivino
              </span>
            </div>
          )}

          {details.tasting_notes && (
            <p className="t-body" style={{ marginTop: 16, maxWidth: 540 }}>{details.tasting_notes}</p>
          )}

          {details.description && (
            <p className="t-body" style={{ marginTop: 14, maxWidth: 540, color: 'var(--ink-2)' }}>
              {details.description}
            </p>
          )}

          {flavors.length > 0 && (
            <div style={{ display: 'flex', gap: 7, marginTop: 14, flexWrap: 'wrap' }}>
              {flavors.map(t => <Tag key={t}>{t}</Tag>)}
            </div>
          )}

          {bars.length > 0 && (
            <div style={{ marginTop: 26, maxWidth: 520 }}>
              <Eyebrow style={{ display: 'block', marginBottom: 12 }}>Structure</Eyebrow>
              <StructureBars items={bars} />
            </div>
          )}

          {detail && (
            <>
              <div style={{ position: 'relative', height: 36, margin: '28px 0 10px', maxWidth: 520, overflow: 'hidden' }}>
                <Contours w={520} h={36} color="var(--brass)"
                  cfg={{ cx: 260, cy: 18, r0: 5, step: 5, count: 7, wob: 4, seed: 1.4, sx: 5 }} />
              </div>

              <Eyebrow style={{ display: 'block', marginBottom: 10 }}>Available near you</Eyebrow>
              <div style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', maxWidth: 520 }}>
                {(wine.availability?.length > 0
                  ? wine.availability
                  : pick.retailer
                    ? [{ retailer: pick.retailer, address: pick.store_address, price: pick.price }]
                    : []
                ).map((loc, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px',
                    borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                  }}>
                    <div style={{
                      width: 26, height: 26, borderRadius: '50%',
                      border: i === 0 ? '1px solid var(--brass)' : '1px solid var(--brass)',
                      background: i === 0 ? 'var(--bordeaux-tint)' : 'var(--paper)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none',
                    }}>
                      <svg width="10" height="10" viewBox="0 0 10 10">
                        <circle cx="5" cy="5" r="2" fill={i === 0 ? 'var(--bordeaux)' : 'var(--brass)'} />
                      </svg>
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
                        {loc.retailer}
                        {i === 0 && (
                          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', color: 'var(--sage)', marginLeft: 6 }}>
                            BEST PRICE
                          </span>
                        )}
                      </div>
                      {loc.address && (
                        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11.5, color: 'var(--faded)', marginTop: 2 }}>
                          {loc.address}
                        </div>
                      )}
                    </div>
                    <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--bordeaux)' }}>${loc.price}</div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
            <Btn onClick={() => navigate('/discover')}>More from this region</Btn>
            <Btn variant="ghost" onClick={() => navigate('/discover')}>Save to cellar</Btn>
          </div>
        </div>
      </div>

      <SommOverlay wine={sommWine} />
    </div>
  );
}
