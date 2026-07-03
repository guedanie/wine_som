import { Link, NavLink, useNavigate } from 'react-router-dom';
import Stamp from './Stamp.jsx';

export default function NavBar() {
  const navigate = useNavigate();
  return (
    <nav style={{
      display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center',
      padding: '0 32px', height: 56,
      borderBottom: '1.5px solid var(--ink)', background: 'var(--cream)',
      position: 'sticky', top: 0, zIndex: 10,
    }}>
      {/* Brand — left */}
      <Link to="/" aria-label="Somm" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', justifySelf: 'start' }}>
        <Stamp size={36} />
        <div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 22, color: 'var(--ink)', lineHeight: 1 }}>Somm</div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 8.5, letterSpacing: '0.26em', textTransform: 'uppercase', color: 'var(--faded)' }}>Wine Atlas</div>
        </div>
      </Link>

      {/* Links — centered */}
      <div style={{ display: 'flex', gap: 2, alignItems: 'center', justifyContent: 'center' }}>
        {[['Recommend', '/'], ['Discover', '/discover']].map(([label, to]) => (
          <NavLink key={to} to={to} end
            style={({ isActive }) => ({
              fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 500,
              textDecoration: 'none', padding: '6px 13px',
              color: isActive ? 'var(--ink)' : 'var(--faded)',
              boxShadow: isActive ? 'inset 0 -2px 0 var(--bordeaux)' : 'none',
            })}>
            {label}
          </NavLink>
        ))}
      </div>

      {/* Search — right */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
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
