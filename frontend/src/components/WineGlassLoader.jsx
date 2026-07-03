// Swirling wine glass loading state — replaces typing dots while Somm thinks.
// Wave path is two full periods wide (x −80 → 144) so translateX(-50%) loops
// seamlessly. Keyframes (wave-scroll, glass-shimmer, dot-pulse) live in index.css.
export default function WineGlassLoader({ text = 'Thinking about your next bottle' }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center' }} data-testid="wine-glass-loader">
      <svg width="48" height="60" viewBox="8 0 48 76" style={{ flex: 'none' }}>
        <defs>
          <clipPath id="somm-bowl-clip">
            <path d="M15 8 Q11.5 31 23 52 Q27.5 57 32 57.5 Q36.5 57 41 52 Q52.5 31 49 8 Z" />
          </clipPath>
        </defs>

        {/* Wine fill — clipped to bowl */}
        <g clipPath="url(#somm-bowl-clip)">
          <rect x="-10" y="36" width="84" height="30" fill="#6E1023" opacity="0.82" />
          <g style={{ animation: 'wave-scroll 1.8s linear infinite' }}>
            <path
              d="M -80 36 Q -72 31 -64 36 Q -56 41 -48 36 Q -40 31 -32 36 Q -24 41 -16 36 Q -8 31 0 36 Q 8 41 16 36 Q 24 31 32 36 Q 40 41 48 36 Q 56 31 64 36 Q 72 41 80 36 Q 88 31 96 36 Q 104 41 112 36 Q 120 31 128 36 Q 136 41 144 36 L 144 50 L -80 50 Z"
              fill="#6E1023" opacity="0.82"
            />
          </g>
          <rect x="20" y="38" width="5" height="14" rx="2.5" fill="rgba(255,255,255,0.28)"
            style={{ animation: 'glass-shimmer 2.6s ease-in-out infinite' }} />
        </g>

        {/* Glass outline on top of fill */}
        <path d="M15 8 Q11.5 31 23 52 Q27.5 57 32 57.5 Q36.5 57 41 52 Q52.5 31 49 8 Z"
          fill="none" stroke="#1A1A1A" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M16.5 9.5 Q13.5 31 24 51 Q28 56 32 56.5 Q36 56 40 51 Q50.5 31 47.5 9.5"
          fill="none" stroke="#B08D57" strokeWidth="0.75" opacity="0.55" />
        <ellipse cx="32" cy="8" rx="17" ry="3.5" fill="var(--cream-raised)" stroke="#1A1A1A" strokeWidth="1.6" />
        <rect x="30" y="57" width="4" height="13" fill="var(--cream-raised)" stroke="#1A1A1A" strokeWidth="1.5" />
        <rect x="20" y="69" width="24" height="4" rx="1" fill="var(--cream-raised)" stroke="#1A1A1A" strokeWidth="1.5" />
        <circle cx="32" cy="57" r="2.5" fill="#B08D57" />
      </svg>

      <div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--faded)', fontStyle: 'italic', marginBottom: 6 }}>
          {text}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {[0, 0.2, 0.4].map(delay => (
            <span key={delay} style={{
              width: 5, height: 5, borderRadius: '50%', background: 'var(--brass)',
              animation: `dot-pulse 1.2s ease-in-out infinite ${delay}s`,
            }} />
          ))}
        </div>
      </div>
    </div>
  );
}
