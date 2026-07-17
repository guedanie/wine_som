import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import run_vivino_sample as runner


def _run(fails, pauses):
    """Run handle_fetch_failure once inside a live loop (py3.9: asyncio.Event
    must be created with a running event loop). Returns (state, aborted, sleep_mock)."""
    async def scenario():
        state = {"consecutive_fails": fails, "pauses": pauses}
        abort = asyncio.Event()
        with patch.object(runner.asyncio, "sleep", new=AsyncMock()) as mock_sleep:
            await runner.handle_fetch_failure(state, abort)
        return state, abort.is_set(), mock_sleep
    return asyncio.run(scenario())


def test_failure_below_threshold_no_pause_no_abort():
    state, aborted, mock_sleep = _run(fails=0, pauses=0)
    assert state["consecutive_fails"] == 1
    assert not aborted
    mock_sleep.assert_not_called()


def test_failure_streak_triggers_pause_and_resets():
    """At ABORT_AFTER consecutive failures with pauses remaining: sleep
    PAUSE_SECONDS, reset the streak, count the pause — do NOT abort."""
    state, aborted, mock_sleep = _run(fails=runner.ABORT_AFTER - 1, pauses=0)
    assert not aborted
    assert state["pauses"] == 1
    assert state["consecutive_fails"] == 0
    mock_sleep.assert_awaited_once_with(runner.PAUSE_SECONDS)


def test_failure_streak_aborts_after_max_pauses():
    state, aborted, mock_sleep = _run(fails=runner.ABORT_AFTER - 1,
                                      pauses=runner.MAX_PAUSES)
    assert aborted
    mock_sleep.assert_not_called()


def test_ci_profile_is_conservative():
    """GITHUB_ACTIONS=true must select the crawl profile — datacenter runner
    IPs get throttled by Vivino far harder than residential ones."""
    import importlib, os
    from unittest.mock import patch as env_patch
    with env_patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
        mod = importlib.reload(runner)
        assert mod.CONCURRENCY == 1
        assert mod.REQ_DELAY >= 2.0
        assert mod.PAUSE_SECONDS >= 300
        assert mod.MAX_PAUSES >= 5
    importlib.reload(runner)  # restore local profile for other tests


def test_local_profile_is_crawl_grade():
    """Vivino began throttling the residential IP ~2026-07-10: every 300-limit
    run aborted after ~40 consecutive fetch failures (~42 wines/day written,
    log-verified 07-10..07-16). The local profile now crawls like CI did —
    slower per-request, but it outlasts the throttle window."""
    import importlib, os
    assert os.environ.get("GITHUB_ACTIONS") != "true"
    mod = importlib.reload(runner)
    assert mod.CONCURRENCY == 1
    assert mod.REQ_DELAY >= 2.0
    assert mod.PAUSE_SECONDS >= 300
    assert mod.MAX_PAUSES >= 5


class _FakeTier:
    """Stands in for a built postgrest query: .limit(n).execute().data"""
    def __init__(self, rows):
        self._rows = rows

    def limit(self, n):
        self._n = n
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self._rows[:self._n])


def _rows(*ids):
    return [{"id": i} for i in ids]


def test_fetch_sample_fills_limit_in_tier_order_with_dedup():
    """Item 13 + item 27: both-null wines (invisible to the recommender) first,
    then un-enriched Bordeaux/Rhône, then the rest. A wine surfacing in two
    tiers must be picked once."""
    tiers = [_FakeTier(_rows("a", "b")),
             _FakeTier(_rows("b", "c")),          # 'b' duplicates tier 1
             _FakeTier(_rows("d", "e", "f"))]
    with patch.object(runner, "_tier_queries", return_value=tiers):
        picked = runner.fetch_sample(db=None, limit=4)
    assert [w["id"] for w in picked] == ["a", "b", "c", "d"]


def test_fetch_sample_stops_at_limit_within_first_tier():
    tiers = [_FakeTier(_rows("a", "b", "c")), _FakeTier(_rows("d")), _FakeTier([])]
    with patch.object(runner, "_tier_queries", return_value=tiers):
        picked = runner.fetch_sample(db=None, limit=2)
    assert [w["id"] for w in picked] == ["a", "b"]


def _facts_wine(**kw):
    base = {"id": "w1", "grapes": [], "abv": 13.5,
            "region": "Bordeaux", "country": "France"}
    base.update(kw)
    return base


def test_write_facts_replaces_appellation_default_blend():
    """Law-book approximations (backfill/extraction defaults) yield to real
    per-wine Vivino data; everything else stays fill-only."""
    from unittest.mock import MagicMock
    db = MagicMock()
    w = _facts_wine(grapes=["Merlot", "Cabernet Franc", "Cabernet Sauvignon"])
    filled = runner.write_facts(db, w, {"grapes": ["Merlot", "Cabernet Franc"]})
    assert "grapes" in filled
    payload = db.table.return_value.update.call_args[0][0]
    assert payload["grapes"] == ["Merlot", "Cabernet Franc"]


def test_write_facts_never_replaces_scraped_or_extracted_grapes():
    from unittest.mock import MagicMock
    db = MagicMock()
    w = _facts_wine(grapes=["Zinfandel"])
    filled = runner.write_facts(db, w, {"grapes": ["Merlot"]})
    assert filled == []
    db.table.return_value.update.assert_not_called()


def test_write_facts_still_fills_empty_grapes():
    from unittest.mock import MagicMock
    db = MagicMock()
    filled = runner.write_facts(db, _facts_wine(), {"grapes": ["Malbec"]})
    assert "grapes" in filled


def test_write_facts_never_replaces_single_grape_even_when_law_default():
    """['Syrah'] is both a law default (Cornas) and a common REAL scraped
    varietal (Washington Syrah) — indistinguishable at rest, so single-grape
    values are never replace-eligible. Only multi-grape law approximations are."""
    from unittest.mock import MagicMock
    db = MagicMock()
    w = _facts_wine(grapes=["Syrah"], region="Rhône")
    filled = runner.write_facts(db, w, {"grapes": ["Syrah", "Viognier"]})
    assert filled == []
    db.table.return_value.update.assert_not_called()
