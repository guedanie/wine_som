// Taste profile persistence via Supabase RLS (profiles.taste_profile, scoped to
// the signed-in user). No-ops gracefully if auth isn't configured.
import { supabase } from './supabase.js';

export async function getTasteProfile(userId) {
  if (!supabase || !userId) return null;
  const { data, error } = await supabase
    .from('profiles').select('taste_profile').eq('user_id', userId).maybeSingle();
  return error ? null : (data?.taste_profile ?? null);
}

export async function saveTasteProfile(userId, profile) {
  if (!supabase || !userId) return false;
  const { error } = await supabase.from('profiles').upsert(
    { user_id: userId, taste_profile: profile, updated_at: new Date().toISOString() },
    { onConflict: 'user_id' },
  );
  return !error;
}
