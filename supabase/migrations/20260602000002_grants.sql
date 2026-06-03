-- Grant table access to Supabase roles
-- service_role: full access for backend scripts (bypasses RLS)
-- authenticated: read on catalog tables for logged-in users
-- anon: read on catalog tables for public/unauthenticated access

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

GRANT SELECT ON wines, wine_details, retail_inventory TO anon, authenticated;
GRANT ALL ON user_preferences, recommendation_sessions, user_saved_wines TO authenticated;
GRANT ALL ON scraper_runs TO service_role;
