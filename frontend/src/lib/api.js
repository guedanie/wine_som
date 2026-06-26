// frontend/src/lib/api.js
const BASE = import.meta.env?.VITE_API_URL ?? 'http://localhost:8000';

export async function recommend(req) {
  const res = await fetch(`${BASE}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getWine(id) {
  const res = await fetch(`${BASE}/api/wines/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
