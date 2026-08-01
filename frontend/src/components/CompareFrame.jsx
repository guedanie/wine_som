// frontend/src/components/CompareFrame.jsx
// The signature aisle moment (design handoff): the two-bottle comparison's
// DATA half. Sharp 1.5px ink frame — data is sharp, conversation is soft.
// The verdict lives in the somm's bubble; the winning column is column 0
// (the model's first pick) washed bordeaux-tint with a MINE flag.
// Axes are 0-10, the same scale structureToBars (dossier) divides by 10.
const bodyLabel = v => (v == null ? null : v <= 3 ? 'Light' : v <= 6 ? 'Medium' : 'Full');
const tanninLabel = v => (v == null ? null : v <= 3 ? 'Soft' : v <= 6 ? 'Medium' : 'Firm');

export default function CompareFrame({ picks }) {
  if (!picks || picks.length < 2) return null;
  const [a, b] = picks;
  const sp = p => p.structure_profile || {};
  const rows = [
    ['PRICE', p => (p.price != null ? `$${Number(p.price).toFixed(0)}` : null)],
    ['BODY', p => bodyLabel(sp(p).body)],
    ['TANNIN', p => tanninLabel(sp(p).tannins)],
  ].filter(([, get]) => get(a) != null || get(b) != null);
  if (!rows.length) return null;

  const col = (p, mine) => (
    <div style={{ flex: 1, background: mine ? 'var(--bordeaux-tint)' : 'transparent', minWidth: 0 }}>
      <div style={{ padding: '10px 12px 8px', borderBottom: '0.75px solid var(--brass)' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, lineHeight: 1.15, color: 'var(--ink)' }}>{p.name}</div>
        {mine && <span className="t-eyebrow" style={{ color: 'var(--bordeaux)', marginTop: 3, display: 'inline-block' }}>MINE</span>}
      </div>
      {rows.map(([label, get]) => (
        <div key={label} style={{ padding: '7px 12px', borderBottom: '0.75px solid var(--border)' }}>
          <span className="t-eyebrow" style={{ display: 'block' }}>{label}</span>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--ink-2)' }}>{get(p) ?? '—'}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ display: 'flex', border: '1.5px solid var(--ink)', background: 'var(--cream-raised)', marginBottom: 14, marginLeft: 43 }}>
      {col(a, true)}
      <div style={{ width: 1, background: 'var(--ink)' }} />
      {col(b, false)}
    </div>
  );
}
