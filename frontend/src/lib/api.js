// frontend/src/lib/api.js
const BASE = import.meta.env?.VITE_API_URL ?? 'http://localhost:8000';

export async function* streamRecommend(req) {
  const res = await fetch(`${BASE}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop();
    for (const part of parts) {
      if (!part.startsWith('data: ')) continue;
      const text = part.slice(6).trim();
      if (text === '[DONE]') return;
      yield JSON.parse(text);
    }
  }
}

export async function getWine(id, zip) {
  const url = zip
    ? `${BASE}/api/wines/${id}?zip=${encodeURIComponent(zip)}`
    : `${BASE}/api/wines/${id}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getRegionWines(region, zip) {
  const res = await fetch(`${BASE}/api/region/${encodeURIComponent(region)}?zip=${encodeURIComponent(zip)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export function postFeedback(payload) {
  fetch(`${BASE}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => {});
}

export async function* streamSomm({ wine, message, history }) {
  let resp;
  try {
    resp = await fetch(`${BASE}/api/somm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wine, message, history }),
    });
  } catch {
    yield { type: 'error', message: 'Connection failed' };
    return;
  }
  if (!resp.ok) { yield { type: 'error', message: 'Somm unavailable' }; return; }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data:')) continue;
      const raw = line.slice(5).trim();
      if (raw === '[DONE]') return;
      try { yield JSON.parse(raw); } catch {}
    }
  }
}
