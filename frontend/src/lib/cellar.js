// Cellar data access via Supabase RLS (scoped to the signed-in user). Bottles
// may be off-catalog (wine_id null) — they stand on their own via name/vintage.
// The drinking window is computed from varietal+vintage at add time and stored.
import { supabase } from './supabase.js';
import { drinkingWindow } from './drinkingWindow.js';

export async function listCellar(userId, { includeConsumed = false } = {}) {
  if (!supabase || !userId) return [];
  let q = supabase.from('cellar').select('*').eq('user_id', userId).order('created_at', { ascending: false });
  if (!includeConsumed) q = q.eq('status', 'owned');
  const { data, error } = await q;
  return error ? [] : (data || []);
}

// bottle: { wine_id?, name, vintage?, region?, varietal?, wine_type?,
//           quantity?, purchase_date?, price_paid?, drink_from?, drink_to?, notes? }
export async function addBottle(userId, bottle) {
  if (!supabase || !userId || !bottle?.name) return null;
  const win = (bottle.drink_from || bottle.drink_to)
    ? { from: bottle.drink_from ?? null, to: bottle.drink_to ?? null }
    : drinkingWindow(bottle.varietal, bottle.wine_type, bottle.vintage);
  const row = {
    user_id: userId,
    wine_id: bottle.wine_id ?? null,
    name: bottle.name,
    vintage: bottle.vintage ?? null,
    region: bottle.region ?? null,
    quantity: bottle.quantity ?? 1,
    purchase_date: bottle.purchase_date ?? null,
    price_paid: bottle.price_paid ?? null,
    drink_from: win?.from ?? null,
    drink_to: win?.to ?? null,
    notes: bottle.notes ?? null,
  };
  const { data, error } = await supabase.from('cellar').insert(row).select().single();
  return error ? null : data;
}

export async function updateBottle(userId, id, patch) {
  if (!supabase || !userId) return false;
  const { error } = await supabase
    .from('cellar')
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq('id', id).eq('user_id', userId);
  return !error;
}

export async function removeBottle(userId, id) {
  if (!supabase || !userId) return false;
  const { error } = await supabase.from('cellar').delete().eq('id', id).eq('user_id', userId);
  return !error;
}

// "Drank it" — decrement quantity; mark consumed when it hits zero.
export async function drinkBottle(userId, bottle) {
  const remaining = (bottle.quantity ?? 1) - 1;
  return remaining <= 0
    ? updateBottle(userId, bottle.id, { quantity: 0, status: 'consumed' })
    : updateBottle(userId, bottle.id, { quantity: remaining });
}
