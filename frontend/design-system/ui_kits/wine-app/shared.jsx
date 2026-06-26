// Terroir wine-app — shared UI primitives.
// Exported to window for the screen components.

const TASSET = "../../assets/";

// procedural contour band/field (the topo motif)
function tRing(cx, cy, R, wob, seed, sx, pts = 80) {
  let d = "";
  for (let j = 0; j <= pts; j++) {
    const t = (j / pts) * Math.PI * 2;
    const rr = R + Math.sin(t * 3 + seed) * wob * (0.6 + 0.4 * Math.sin(t * 2 + seed));
    d += (j === 0 ? "M" : "L") + (cx + Math.cos(t) * rr * sx).toFixed(1) + " " + (cy + Math.sin(t) * rr).toFixed(1);
  }
  return d + "Z";
}
function Contours({ w = 600, h = 120, color = "#B08D57", cfg }) {
  const c = cfg || { cx: w / 2, cy: h / 2, r0: 10, step: 9, count: 9, wob: 7, seed: 1.4, sx: 1.6 };
  const paths = [];
  for (let i = 0; i < c.count; i++) paths.push(tRing(c.cx, c.cy, c.r0 + i * c.step, c.wob, c.seed + i * 0.5, c.sx));
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid slice" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
      {paths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={color} strokeWidth={i === c.count - 1 ? 1.6 : 1} opacity={0.3 + (i / c.count) * 0.6} />
      ))}
      <circle cx={c.cx} cy={c.cy} r="3" fill={color} />
    </svg>
  );
}

const Stamp = ({ size = 32, reversed }) => (
  <img src={TASSET + (reversed ? "mark-terroir-reversed.svg" : "mark-terroir.svg")} width={size} height={size} alt="Terroir" style={{ display: "block" }} />
);

const Eyebrow = ({ children, style }) => (
  <span className="t-eyebrow" style={style}>{children}</span>
);

const Coord = ({ children }) => <span className="t-coord">{children}</span>;

const Tag = ({ children }) => <span className="t-tag">{children}</span>;

function Btn({ children, variant, onClick, style }) {
  const cls = "t-btn" + (variant === "ghost" ? " t-btn--ghost" : "");
  return <button className={cls} style={style} onClick={onClick}>{children}</button>;
}

function StructureBars({ items, compact }) {
  return (
    <div style={{ display: "flex", gap: compact ? 12 : 20 }}>
      {items.map(([k, label, v]) => (
        <div key={k} style={{ flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--faded)", marginBottom: 5 }}>
            <span>{k}</span>{!compact && <span style={{ color: "var(--ink-2)" }}>{label}</span>}
          </div>
          <div style={{ height: 5, borderRadius: 3, background: "var(--paper)" }}>
            <div style={{ width: `${v * 100}%`, height: "100%", borderRadius: 3, background: "var(--brass)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// Framed wine card — editorial header (tagline + coordinates + brass keyline).
// No contour map here; that's reserved for the dossier page.
function WineCard({ wine, onOpen }) {
  return (
    <div
      onClick={onOpen}
      style={{ border: "1.5px solid var(--ink)", background: "var(--cream)", cursor: onOpen ? "pointer" : "default", transition: "transform .18s var(--ease), box-shadow .18s var(--ease)" }}
      onMouseEnter={(e) => { if (onOpen) { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-card)"; } }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "none"; }}
    >
      <div style={{ padding: "13px 14px", borderBottom: "0.75px solid var(--brass)", display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 9.5, letterSpacing: "0.24em", textTransform: "uppercase", color: "var(--faded)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{wine.tagline}</div>
          <div style={{ fontSize: 10, letterSpacing: "0.16em", color: "var(--sage)", marginTop: 4 }}>{wine.coord}</div>
        </div>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 24, color: "var(--bordeaux)", flex: "none" }}>${wine.price}</div>
      </div>
      <div style={{ padding: "13px 14px 14px" }}>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 21, lineHeight: 1.05, color: "var(--ink)" }}>{wine.name}</div>
        <div style={{ fontSize: 11.5, color: "var(--ink-2)", marginTop: 3 }}>{wine.producer} · {wine.vintage} · {wine.store}</div>
        <div style={{ display: "flex", gap: 6, marginTop: 11, flexWrap: "wrap" }}>
          {wine.tags.map((t) => <Tag key={t}>{t}</Tag>)}
        </div>
      </div>
    </div>
  );
}

// Matted poster (real image or placeholder)
function Poster({ src, region, place, count, onOpen, w }) {
  return (
    <div style={{ width: w || "100%", cursor: onOpen ? "pointer" : "default" }} onClick={onOpen}>
      <div style={{ background: "var(--cream)", padding: 10, border: "1.5px solid var(--ink)", boxShadow: "var(--shadow-print)" }}>
        <div style={{ border: "0.75px solid var(--brass)", padding: 4 }}>
          {src ? (
            <img src={src} alt={region} style={{ display: "block", width: "100%", aspectRatio: "372/494", objectFit: "cover" }} />
          ) : (
            <div style={{ aspectRatio: "372/494", background: "repeating-linear-gradient(135deg,var(--paper),var(--paper) 11px,#E6DAC2 11px,#E6DAC2 22px)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9.5, letterSpacing: "0.22em", color: "var(--faded)" }}>REGION POSTER</span>
              <span style={{ fontFamily: "var(--font-serif)", fontSize: 24, color: "var(--faded-2)" }}>{region}</span>
            </div>
          )}
        </div>
      </div>
      {count != null && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 10 }}>
          <div>
            <div style={{ fontFamily: "var(--font-serif)", fontSize: 19, color: "var(--ink)", lineHeight: 1 }}>{region}</div>
            <div style={{ fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--faded)", marginTop: 3 }}>{place}</div>
          </div>
          <div style={{ fontSize: 11, color: "var(--bordeaux)" }}>{count} wines</div>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { Contours, Stamp, Eyebrow, Coord, Tag, Btn, StructureBars, WineCard, Poster, TASSET });
