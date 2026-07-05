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


def test_local_profile_unchanged():
    import importlib, os
    assert os.environ.get("GITHUB_ACTIONS") != "true"
    mod = importlib.reload(runner)
    assert mod.CONCURRENCY == 2
    assert mod.REQ_DELAY == 1.0
    assert mod.PAUSE_SECONDS == 90
    assert mod.MAX_PAUSES == 3
