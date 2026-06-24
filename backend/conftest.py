def pytest_configure(config):
    # Registers the `integration` marker (run real queries against the live
    # Supabase schema). Deselect with: pytest -m "not integration".
    config.addinivalue_line(
        "markers",
        "integration: exercises the real Supabase schema; auto-skips if the DB is unreachable",
    )
