"""
Integration tests that run the app's REAL PostgREST queries against the live
Supabase schema — no mocks. These catch the class of bug the mocked unit tests
cannot: a query that names a column the schema doesn't have (PostgREST 42703).

A historical example: the recommend query selected `stores.store_name`, which
does not exist (the column is `name`). Every mocked test passed while the
endpoint 500'd against the real DB. This file guards that seam.

Auto-skips when Supabase is unreachable (e.g. CI without secrets), so it never
fails for environment reasons — it either validates the schema or skips.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import pytest
from postgrest.exceptions import APIError

from db import get_service_client
from api.routers.recommend import INVENTORY_SELECT


def _db_or_skip():
    """Return a working service client, or skip the test if the DB is unreachable."""
    try:
        db = get_service_client()
        db.table("wines").select("id").limit(1).execute()
        return db
    except Exception as exc:  # noqa: BLE001 - any connection/auth failure means "skip"
        pytest.skip(f"Supabase unreachable; skipping integration test ({exc})")


@pytest.mark.integration
def test_recommend_inventory_projection_matches_real_schema():
    """The recommend candidate query projection must reference only real columns.
    Runs the EXACT projection the router uses; a bad column raises PostgREST 42703."""
    db = _db_or_skip()
    try:
        db.table("retail_inventory").select(INVENTORY_SELECT).limit(1).execute()
    except APIError as exc:
        pytest.fail(f"INVENTORY_SELECT names a column not in the schema: {exc}")


@pytest.mark.integration
def test_wines_table_has_extracted_and_dedup_columns():
    """Columns the recommender/scorer and dedup rely on must exist on `wines`.
    Guards against a dropped/renamed extraction or canonical-UPC column."""
    db = _db_or_skip()
    cols = "id, name, varietal, region, sub_region, country, wine_type, grapes, abv, body, upc, upc_canonical, image_url"
    try:
        db.table("wines").select(cols).limit(1).execute()
    except APIError as exc:
        pytest.fail(f"`wines` is missing a column the app reads: {exc}")


@pytest.mark.integration
def test_stores_table_has_columns_the_app_reads():
    """Columns the scrapers/geo/recommend read from `stores` must exist."""
    db = _db_or_skip()
    cols = "id, retailer_name, store_id, name, address, city, state, zip_code, latitude, longitude"
    try:
        db.table("stores").select(cols).limit(1).execute()
    except APIError as exc:
        pytest.fail(f"`stores` is missing a column the app reads: {exc}")
