function tRing(cx, cy, R, wob, seed, sx, pts = 80) {
  let d = '';
  for (let j = 0; j <= pts; j++) {
    const t = (j / pts) * Math.PI * 2;
    const rr = R + Math.sin(t * 3 + seed) * wob * (0.6 + 0.4 * Math.sin(t * 2 + seed));
    d += (j === 0 ? 'M' : 'L') +
      (cx + Math.cos(t) * rr * sx).toFixed(1) + ' ' +
      (cy + Math.sin(t) * rr).toFixed(1);
  }
  return d + 'Z';
}

export default function Contours({ w = 600, h = 120, color = '#B08D57', cfg }) {
  const c = cfg ?? { cx: w / 2, cy: h / 2, r0: 10, step: 9, count: 9, wob: 7, seed: 1.4, sx: 1.6 };
  const paths = [];
  for (let i = 0; i < c.count; i++) {
    paths.push(tRing(c.cx, c.cy, c.r0 + i * c.step, c.wob, c.seed + i * 0.5, c.sx));
  }
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid slice"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
      {paths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={color}
          strokeWidth={i === c.count - 1 ? 1.6 : 1}
          opacity={0.3 + (i / c.count) * 0.6} />
      ))}
      <circle cx={c.cx} cy={c.cy} r="3" fill={color} />
    </svg>
  );
}
