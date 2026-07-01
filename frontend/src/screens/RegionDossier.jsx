import { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Eyebrow from '../components/Eyebrow.jsx';
import Btn from '../components/Btn.jsx';
import Poster from '../components/Poster.jsx';
import Contours from '../components/Contours.jsx';
import Tag from '../components/Tag.jsx';
import StructureBars from '../components/StructureBars.jsx';
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

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px 72px' }}>
      <button onClick={() => {
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
        style={{ cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', padding: 0, marginBottom: 22 }}>
        ← Back to recommendations
      </button>

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 44, alignItems: 'start' }}>
        <Poster region={region} />

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Eyebrow style={{ whiteSpace: 'nowrap' }}>{region}</Eyebrow>
            <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            {pick.coord && <span className="t-coord" style={{ whiteSpace: 'nowrap' }}>{pick.coord}</span>}
          </div>

          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 46, lineHeight: 1.0, color: 'var(--ink)', margin: '12px 0 0' }}>
            {wine.name ?? pick.name}
          </h1>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 10 }}>
            {subtitle && <span style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--ink-2)' }}>{subtitle}</span>}
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--bordeaux)' }}>${pick.price}</span>
          </div>

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
            <div style={{ marginTop: 26, maxWidth: 540 }}>
              <Eyebrow style={{ display: 'block', marginBottom: 12 }}>Structure</Eyebrow>
              <StructureBars items={bars} />
            </div>
          )}

          {detail && (
            <>
              {/* Contour divider — only on the dossier page */}
              <div style={{ position: 'relative', height: 40, margin: '26px 0 8px', overflow: 'hidden' }}>
                <Contours w={540} h={40} color="var(--brass)"
                  cfg={{ cx: 270, cy: 20, r0: 5, step: 5, count: 7, wob: 4, seed: 1.4, sx: 5 }} />
              </div>

              <Eyebrow style={{ display: 'block', marginBottom: 10 }}>Available near you</Eyebrow>
              <div style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', maxWidth: 540 }}>
                {(wine.availability?.length > 0 ? wine.availability : pick.retailer ? [{ retailer: pick.retailer, address: pick.store_address, price: pick.price }] : []).map((loc, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px',
                    borderTop: i > 0 ? '1px solid var(--border)' : 'none',
                  }}>
                    <div style={{ width: 26, height: 26, borderRadius: '50%', border: '1px solid var(--brass)', position: 'relative', overflow: 'hidden', flex: 'none' }}>
                      <Contours w={26} h={26} color="var(--brass)"
                        cfg={{ cx: 13, cy: 13, r0: 3, step: 3, count: 4, wob: 2, seed: i + 1, sx: 1.4 }} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
                        {loc.retailer}
                      </div>
                      {loc.address && (
                        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)', marginTop: 2 }}>
                          {loc.address}
                        </div>
                      )}
                    </div>
                    <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, color: 'var(--bordeaux)' }}>${loc.price}</div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div style={{ marginTop: 18 }}>
            <Btn variant="ghost" onClick={() => navigate('/discover')}>More from this region</Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
