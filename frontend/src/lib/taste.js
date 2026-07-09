import { listFavorites } from './favorites.js';
import { listCellar } from './cellar.js';

// Gather the user's liked/owned wines into a compact taste context the
// recommendation engine uses to personalize + cite ("close to X you saved").
// Saved (rich: varietal/grapes/region) + cellar (name/region) for now; feedback
// thumbs later. Capped so the prompt stays lean.
export async function buildTasteContext(userId, { cap = 12 } = {}) {
  if (!userId) return null;
  const [saved, cellar] = await Promise.all([listFavorites(userId), listCellar(userId)]);

  const liked = [];
  for (const f of saved || []) {
    const w = f.wines || {};
    liked.push({ name: w.name, wine_id: w.id ?? f.wine_id, varietal: w.varietal ?? null, region: w.region ?? null, grapes: w.grapes ?? null, source: 'saved' });
  }
  for (const b of cellar || []) {
    liked.push({ name: b.name, wine_id: b.wine_id ?? null, varietal: null, region: b.region ?? null, grapes: null, source: 'cellar' });
  }

  const seen = new Set();
  const out = [];
  for (const lw of liked) {
    const key = lw.wine_id || lw.name;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(lw);
    if (out.length >= cap) break;
  }
  return out.length ? { liked_wines: out } : null;
}
