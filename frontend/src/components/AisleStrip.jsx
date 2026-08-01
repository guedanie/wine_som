// frontend/src/components/AisleStrip.jsx
// Door 2 (aisle-mode handoff): a tab says *there is another view*; this strip
// says *here is when you'd want it*. Tapping is a declaration — "I'm here,
// now" — so it also opens the store picker.
import { useNavigate } from 'react-router-dom';

export default function AisleStrip() {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate('/recommend', { state: { mode: 'ask', openStorePicker: true } })}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%',
        background: 'var(--bordeaux-tint)', border: 'none',
        borderTop: '0.75px solid var(--brass)', cursor: 'pointer',
        padding: '11px 16px', flexShrink: 0, textAlign: 'left',
      }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--bordeaux)" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
      </svg>
      <span style={{ flex: 1, fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--bordeaux)', fontWeight: 500 }}>
        In a store right now? Just ask me instead.
      </span>
      <span style={{ color: 'var(--bordeaux)', fontSize: 15 }}>›</span>
    </button>
  );
}
