// Brand mark — "The Pin": map location pin, wine glass cut into the eye.
// Full mark (ink ring + cardinal ticks) renders as a standalone SVG.
// reversed=true wraps a cream pin in a bordeaux circle — for chat avatar, FAB, dark surfaces.
export default function Stamp({ size = 32, reversed = false }) {
  if (reversed) {
    // Bordeaux circle + cream pin body + bordeaux glass inside
    const inner = Math.round(size * 0.58);
    return (
      <div
        aria-hidden="true"
        style={{
          width: size, height: size, borderRadius: '50%', background: 'var(--bordeaux)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none',
        }}
      >
        <svg width={inner} height={inner} viewBox="0 0 100 100" fill="none">
          <path d="M50 20 C40 20 32 28 32 38 C32 50 50 74 50 74 C50 74 68 50 68 38 C68 28 60 20 50 20Z" fill="#EFE6D4"/>
          <path d="M42 30 C41 35 42 41 47 42 L50 43 L53 42 C58 41 59 35 58 30 Z" fill="#6E1023"/>
          <rect x="49.2" y="43" width="1.6" height="6" fill="#6E1023"/>
          <rect x="45.5" y="49" width="9" height="1.4" rx="0.7" fill="#6E1023"/>
        </svg>
      </div>
    );
  }

  // Full mark — ink outer ring, brass inner ring, cardinal ticks (≥36px), bordeaux pin, cream glass
  const ticks = size >= 36;
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      style={{ flex: 'none', display: 'block' }}
    >
      <circle cx="50" cy="50" r="47" stroke="#1A1A1A" strokeWidth="1.8"/>
      <circle cx="50" cy="50" r="43.5" stroke="#B08D57" strokeWidth="0.7"/>
      {ticks && (
        <>
          <line x1="50" y1="3"  x2="50" y2="8"  stroke="#1A1A1A" strokeWidth="1.2"/>
          <line x1="50" y1="97" x2="50" y2="92" stroke="#1A1A1A" strokeWidth="1.2"/>
          <line x1="3"  y1="50" x2="8"  y2="50" stroke="#1A1A1A" strokeWidth="1.2"/>
          <line x1="97" y1="50" x2="92" y2="50" stroke="#1A1A1A" strokeWidth="1.2"/>
        </>
      )}
      <path d="M50 20 C40 20 32 28 32 38 C32 50 50 74 50 74 C50 74 68 50 68 38 C68 28 60 20 50 20Z" fill="#6E1023"/>
      <path d="M42 30 C41 35 42 41 47 42 L50 43 L53 42 C58 41 59 35 58 30 Z" fill="#EFE6D4"/>
      <rect x="49.2" y="43" width="1.6" height="6" fill="#EFE6D4"/>
      <rect x="45.5" y="49" width="9" height="1.4" rx="0.7" fill="#EFE6D4"/>
    </svg>
  );
}
