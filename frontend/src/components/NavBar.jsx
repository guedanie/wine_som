import { Link, NavLink, useNavigate } from 'react-router-dom';
import Stamp from './Stamp.jsx';

export default function NavBar() {
  const navigate = useNavigate();
  return (
    <nav style={{ borderBottom: '1.5px solid var(--ink)', background: 'var(--cream)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', height: 56 }}>
      <Link to="/" aria-label="Terroir" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
        <Stamp size={28} />
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--ink)' }}>Terroir</span>
      </Link>
      <div style={{ display: 'flex', gap: 28, alignItems: 'center' }}>
        {[['Recommend', '/'], ['Discover', '/discover']].map(([label, to]) => (
          <NavLink key={to} to={to} end
            style={({ isActive }) => ({
              fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 600,
              textDecoration: 'none', letterSpacing: '0.04em',
              color: isActive ? 'var(--bordeaux)' : 'var(--faded)',
              borderBottom: isActive ? '1.5px solid var(--bordeaux)' : 'none',
              paddingBottom: 2,
            })}>
            {label}
          </NavLink>
        ))}
        <button
          onClick={() => navigate('/search')}
          style={{
            display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer',
            fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--faded)',
            border: '1px solid var(--border)', background: 'none', padding: '7px 12px',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--ink)'; e.currentTarget.style.color = 'var(--ink)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--faded)'; }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
          </svg>
          Search wines & regions
        </button>
      </div>
    </nav>
  );
}
