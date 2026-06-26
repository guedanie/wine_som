// Screen 3 — Wine detail framed by its region (the "dossier").
function RegionDossier({ wine, region, wines, onBack, onOpenWine }) {
  const stores = [
    { name: "Spec's", addr: "Alamo Heights · 78209", dist: "4.2 mi", price: wine.price, best: true },
    { name: "Total Wine & More", addr: "Quarry Market · 78209", dist: "6.0 mi", price: wine.price + 4 },
    { name: "H-E-B Central Market", addr: "Broadway · 78209", dist: "5.1 mi", price: wine.price + 7 },
  ];
  const more = wines.filter((w) => w.region === region.id && w.id !== wine.id);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 32px 72px" }}>
      <button onClick={onBack} style={{ cursor: "pointer", background: "none", border: "none", fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--faded)", padding: 0, marginBottom: 22 }}>← Back to recommendations</button>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 44, alignItems: "start" }}>
        <Poster src={region.poster} region={region.region} />
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Eyebrow style={{ whiteSpace: "nowrap" }}>{region.region}</Eyebrow>
            <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
            <span className="t-coord" style={{ whiteSpace: "nowrap" }}>{region.coord}</span>
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: 46, lineHeight: 1.0, color: "var(--ink)", margin: "12px 0 0" }}>{wine.name}</h1>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 10 }}>
            <span style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--ink-2)", whiteSpace: "nowrap" }}>{wine.producer} · {wine.vintage}</span>
            <span style={{ fontFamily: "var(--font-serif)", fontSize: 24, color: "var(--bordeaux)" }}>${wine.price}</span>
          </div>
          <p className="t-body" style={{ marginTop: 16, maxWidth: 540 }}>{wine.note}</p>
          <div style={{ display: "flex", gap: 7, marginTop: 14, flexWrap: "wrap" }}>
            {wine.tags.map((t) => <Tag key={t}>{t}</Tag>)}
          </div>

          <div style={{ marginTop: 26, maxWidth: 540 }}>
            <Eyebrow style={{ display: "block", marginBottom: 12 }}>Structure</Eyebrow>
            <StructureBars items={wine.structure} />
          </div>

          <div style={{ position: "relative", height: 40, margin: "26px 0 8px", overflow: "hidden" }}>
            <Contours w={540} h={40} color="var(--brass)" cfg={{ cx: 270, cy: 20, r0: 5, step: 5, count: 7, wob: 4, seed: 1.4, sx: 5 }} />
          </div>

          <Eyebrow style={{ display: "block", marginBottom: 10 }}>Available near you</Eyebrow>
          <div style={{ border: "1.5px solid var(--ink)", background: "var(--cream)", maxWidth: 540 }}>
            {stores.map((s, i) => (
              <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", borderTop: i ? "1px solid var(--border)" : "none" }}>
                <div style={{ width: 26, height: 26, borderRadius: "50%", border: "1px solid var(--brass)", position: "relative", overflow: "hidden", flex: "none" }}>
                  <Contours w={26} h={26} color="var(--brass)" cfg={{ cx: 13, cy: 13, r0: 3, step: 3, count: 4, wob: 2, seed: i + 1, sx: 1.4 }} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{s.name} {s.best && <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", color: "var(--sage)", marginLeft: 6 }}>BEST PRICE</span>}</div>
                  <div style={{ fontSize: 11.5, color: "var(--faded)" }}>{s.addr} · {s.dist}</div>
                </div>
                <div style={{ fontFamily: "var(--font-serif)", fontSize: 19, color: "var(--bordeaux)" }}>${s.price}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 12, marginTop: 18 }}>
            <Btn>Get directions <span style={{ fontSize: 15 }}>→</span></Btn>
            <Btn variant="ghost">Save to cellar</Btn>
          </div>
        </div>
      </div>

      {more.length > 0 && (
        <div style={{ marginTop: 52 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
            <span style={{ fontFamily: "var(--font-serif)", fontSize: 24, color: "var(--ink)" }}>More from {region.region}</span>
            <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 18, maxWidth: 760 }}>
            {more.map((w) => <WineCard key={w.id} wine={w} onOpen={() => onOpenWine(w)} />)}
          </div>
        </div>
      )}
    </div>
  );
}
Object.assign(window, { RegionDossier });
