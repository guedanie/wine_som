import { useState, useEffect } from 'react';

const QUERY = '(max-width: 640px)';

// jsdom has no matchMedia — tests always take the desktop path unless they
// mock window.matchMedia explicitly.
function matches() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(QUERY).matches;
}

export default function useIsMobile() {
  const [isMobile, setIsMobile] = useState(matches);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const mql = window.matchMedia(QUERY);
    const onChange = e => setIsMobile(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}

// Shared zip persistence — TopBar pill + screens read the last-used zip.
export function loadZip() {
  try { return localStorage.getItem('somm_zip') || '78209'; } catch { return '78209'; }
}
export function saveZip(zip) {
  try { localStorage.setItem('somm_zip', zip); } catch { /* private mode */ }
}
