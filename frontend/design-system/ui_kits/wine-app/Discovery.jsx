// Screen 4 — Discover: browse by place.
function Discovery({ regions, onOpenRegion }) {
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "44px 32px 80px" }}>
      <Eyebrow>Discover</Eyebrow>
      <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 56, lineHeight: 1.0, color: "var(--ink)", margin: "12px 0 0" }}>Browse by place</h1>
      <p className="t-body" style={{ marginTop: 12, maxWidth: 520 }}>
        Every region is a poster; every poster is a map. Start somewhere and follow the wine home.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 24, marginTop: 36 }}>
        {regions.map((r) => (
          <Poster key={r.id} src={r.poster} region={r.region} place={r.place} count={r.count} onOpen={() => onOpenRegion(r)} />
        ))}
      </div>
    </div>
  );
}
Object.assign(window, { Discovery });
