-- User accounts (optional, anonymous-first) — Phase 0 profiles + Phase 1 favorites.
--
-- Accounts are never mandatory: the anonymous flow is unchanged. These tables
-- hold data only for users who choose to sign in (Supabase Auth). RLS scopes
-- every row to its owner (user_id = auth.uid()), so the frontend can read/write
-- a user's own data directly via supabase-js with the public anon key — no
-- backend endpoints, no cross-user leakage. See docs/user-accounts-roadmap.md.

-- profiles: one row per authenticated user. Saved preferences now; taste
-- profile (Phase 3, the Somm interview) lands in taste_profile later.
CREATE TABLE IF NOT EXISTS profiles (
    user_id        UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    zip            TEXT,
    default_budget NUMERIC(8,2),
    styles         JSONB NOT NULL DEFAULT '[]'::jsonb,
    taste_profile  JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own profile" ON profiles
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
GRANT ALL ON profiles TO authenticated;
GRANT ALL ON profiles TO service_role;

-- favorites: wines a user saved.
CREATE TABLE IF NOT EXISTS favorites (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    wine_id    UUID NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, wine_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites (user_id, created_at DESC);

ALTER TABLE favorites ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users manage own favorites" ON favorites
  FOR ALL TO authenticated
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
GRANT ALL ON favorites TO authenticated;
GRANT ALL ON favorites TO service_role;
