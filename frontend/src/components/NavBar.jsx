import { Link, NavLink } from 'react-router-dom';
import Stamp from './Stamp.jsx';

export default function NavBar() {
  return (
    <nav style={{ borderBottom: '1.5px solid var(--ink)', background: 'var(--cream)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', height: 56 }}>
      <Link to="/" aria-label="Terroir" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
        <Stamp size={28} />
        <span style={{ fontFamily: 'var(--font-serif)', fontSize: 20, color: 'var(--ink)' }}>Terroir</span>
      </Link>
      <div style={{ display: 'flex', gap: 28 }}>
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
      </div>
    </nav>
  );
}
