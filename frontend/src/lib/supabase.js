// Supabase browser client for optional auth + user data (favorites, profile).
// Guarded: if the env isn't set, the client is null and auth features no-op —
// the app stays fully usable anonymously.
import { createClient } from '@supabase/supabase-js';

const url = import.meta.env?.VITE_SUPABASE_URL;
const anonKey = import.meta.env?.VITE_SUPABASE_ANON_KEY;

export const isAuthConfigured = () => Boolean(url && anonKey);

export const supabase = isAuthConfigured()
  ? createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,   // handle the magic-link callback
      },
    })
  : null;
