import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Parse "43.5° N · 11.3° E" → [43.5, 11.3] (negative for S/W)
export function parseCoord(coord) {
  const m = (coord || '').match(/([\d.]+)°\s*([NS])\s*·\s*([\d.]+)°\s*([EW])/);
  if (!m) return null;
  const lat = parseFloat(m[1]) * (m[2] === 'S' ? -1 : 1);
  const lng = parseFloat(m[3]) * (m[4] === 'W' ? -1 : 1);
  return [lat, lng];
}

export default function RegionMap({ latlng, zoom = 8, subregions = [] }) {
  const el = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (!el.current || mapRef.current) return;

    const map = L.map(el.current, {
      center: latlng,
      zoom,
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: false,
    });
    mapRef.current = map;

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors © CARTO',
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    const centerIcon = L.divIcon({
      html: '<div style="width:14px;height:14px;border-radius:50%;background:#B08D57;border:2px solid #1A1A1A;box-shadow:0 1px 4px rgba(0,0,0,.35);"></div>',
      iconSize: [14, 14], iconAnchor: [7, 7], className: '',
    });
    L.marker(latlng, { icon: centerIcon }).addTo(map);

    subregions.forEach(s => {
      const pos = parseCoord(s.coord);
      if (!pos) return;
      const subIcon = L.divIcon({
        html: `<div title="${s.name}" style="width:8px;height:8px;border-radius:50%;background:#EFE6D4;border:1.5px solid #B08D57;"></div>`,
        iconSize: [8, 8], iconAnchor: [4, 4], className: '',
      });
      L.marker(pos, { icon: subIcon }).addTo(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div style={{ border: '1.5px solid var(--ink)', boxShadow: '0 8px 24px -12px rgba(0,0,0,.4)' }}>
      <div style={{ border: '0.75px solid var(--brass)' }}>
        <div ref={el} style={{ height: 260, width: '100%' }} />
      </div>
    </div>
  );
}
