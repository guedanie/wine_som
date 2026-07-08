// Favorites data access via Supabase RLS — every query is scoped server-side to
// the signed-in user (user_id = auth.uid()), so no cross-user leakage and no
// backend endpoints needed. All calls no-op gracefully if auth isn't configured.
import { supabase } from './supabase.js';

export async function listFavoriteIds(userId) {
  if (!supabase || !userId) return [];
  const { data, error } = await supabase.from('favorites').select('wine_id').eq('user_id', userId);
  return error ? [] : (data || []).map(r => r.wine_id);
}

export async function addFavorite(userId, wineId) {
  if (!supabase || !userId) return false;
  const { error } = await supabase
    .from('favorites')
    .upsert({ user_id: userId, wine_id: wineId }, { onConflict: 'user_id,wine_id' });
  return !error;
}

export async function removeFavorite(userId, wineId) {
  if (!supabase || !userId) return false;
  const { error } = await supabase
    .from('favorites').delete().eq('user_id', userId).eq('wine_id', wineId);
  return !error;
}

// Full rows joined to wines for the Saved view.
export async function listFavorites(userId) {
  if (!supabase || !userId) return [];
  const { data, error } = await supabase
    .from('favorites')
    .select('wine_id, created_at, wines(id, name, brand, varietal, region, country, wine_type, image_url, vivino_rating, vivino_ratings_count)')
    .eq('user_id', userId)
    .order('created_at', { ascending: false });
  return error ? [] : (data || []);
}
