import { listFavorites } from './favorites.js';
import { listCellar } from './cellar.js';
import { getTasteProfile } from './profile.js';
import { supabase } from './supabase.js';

// Gather the user's liked/owned wines into a compact taste context the
// recommendation engine uses to personalize + cite ("close to X you saved").
// Signals: 👍 upvoted picks (strongest) + saved + cellar → liked; 👎 downvoted
// → disliked (scorer penalizes resemblance). Capped so the prompt stays lean.

// Pure: split feedback votes into liked/disliked wine objects (hydrated).
export function _mapVotedWines(votes, winesById) {
  const up = [], down = [], seenUp = new Set(), seenDown = new Set();
  for (const v of votes || []) {
    const w = winesById[v.entity_id];
    if (!w) continue;
    const wine = { name: w.name, wine_id: w.id, varietal: w.varietal ?? null, region: w.region ?? null, grapes: w.grapes ?? null };
    if (v.vote === 'up' && !seenUp.has(w.id)) { seenUp.add(w.id); up.push({ ...wine, source: 'upvoted' }); }
    if (v.vote === 'down' && !seenDown.has(w.id)) { seenDown.add(w.id); down.push({ ...wine, source: 'downvoted' }); }
  }
  return { up, down };
}

async function fetchVotedWines() {
  if (!supabase) return { up: [], down: [] };
  // RLS scopes feedback rows to the signed-in user.
  const { data: votes, error } = await supabase
    .from('feedback').select('entity_id, vote').eq('type', 'wine_card').not('vote', 'is', null);
  if (error || !votes?.length) return { up: [], down: [] };
  const ids = [...new Set(votes.map(v => v.entity_id))];
  const { data: wines } = await supabase
    .from('wines').select('id, name, varietal, region, grapes').in('id', ids);
  const byId = Object.fromEntries((wines || []).map(w => [w.id, w]));
  return _mapVotedWines(votes, byId);
}

function dedupeCap(wines, cap) {
  const seen = new Set(), out = [];
  for (const lw of wines) {
    const key = lw.wine_id || lw.name;
    if (!key || seen.has(key)) continue;
    seen.add(key); out.push(lw);
    if (out.length >= cap) break;
  }
  return out;
}

export async function buildTasteContext(userId, { cap = 12 } = {}) {
  if (!userId) return null;
  const [saved, cellar, voted, profile] = await Promise.all([
    listFavorites(userId), listCellar(userId), fetchVotedWines(), getTasteProfile(userId),
  ]);

  const likedRaw = [
    ...voted.up,                                                   // 👍 strongest — keep first
    ...(saved || []).map(f => {
      const w = f.wines || {};
      return { name: w.name, wine_id: w.id ?? f.wine_id, varietal: w.varietal ?? null, region: w.region ?? null, grapes: w.grapes ?? null, source: 'saved' };
    }),
    ...(cellar || []).map(b => ({ name: b.name, wine_id: b.wine_id ?? null, varietal: null, region: b.region ?? null, grapes: null, source: 'cellar' })),
  ];

  const liked_wines = dedupeCap(likedRaw, cap);
  const disliked_wines = dedupeCap(voted.down, 8);
  const p = profile?.completed_at ? profile : null;

  return (liked_wines.length || disliked_wines.length || p) ? { liked_wines, disliked_wines, profile: p } : null;
}
