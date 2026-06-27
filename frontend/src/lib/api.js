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

export async function getWine(id) {
  const res = await fetch(`${BASE}/api/wines/${id}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
