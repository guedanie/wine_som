from supabase import create_client, Client
from config import settings


def get_supabase_client() -> Client:
    """Anon client — respects RLS. Use for public reads and authenticated user requests."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_service_client() -> Client:
    """Service role client — bypasses RLS. Use only in backend scripts and scrapers."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
