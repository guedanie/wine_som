// Price-watch data access via Supabase RLS — same shape as favorites.js:
// every query is server-side scoped to the signed-in user (user_id =
// auth.uid()), no backend endpoint. No-ops gracefully when auth isn't
// configured. The notifier that acts on these ships later (Phase D designs
// the affordance; delivery is roadmap item 16's tail).
import { supabase } from './supabase.js';

export async function listWatchIds(userId) {
  if (!supabase || !userId) return [];
  const { data, error } = await supabase.from('price_watches').select('wine_id').eq('user_id', userId);
  return error ? [] : (data || []).map(r => r.wine_id);
}

export async function addWatch(userId, wineId) {
  if (!supabase || !userId) return false;
  const { error } = await supabase
    .from('price_watches')
    .upsert({ user_id: userId, wine_id: wineId }, { onConflict: 'user_id,wine_id' });
  return !error;
}

export async function removeWatch(userId, wineId) {
  if (!supabase || !userId) return false;
  const { error } = await supabase
    .from('price_watches').delete().eq('user_id', userId).eq('wine_id', wineId);
  return !error;
}
