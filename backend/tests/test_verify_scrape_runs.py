import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import MagicMock
from datetime import datetime
from scripts.verify_scrape_runs import classify_runs, flip_silent_zeroes, SILENT_ZERO_MSG


def _dt(iso):
    return datetime.fromisoformat(iso)


def _run(retailer="Spec's", status="success", updated=0, run_id="run-1"):
    return {"id": run_id, "retailer_name": retailer, "status": status,
            "records_updated": updated, "started_at": "2026-07-12T10:28:00Z",
            "error_message": None}


def test_success_with_zero_records_is_flagged():
    """The Spec's failure mode: process exits clean, writes nothing, status
    says success — the exact shape that hid a 3.5-week outage."""
    issues = classify_runs([_run(status="success", updated=0)])
    assert len(issues) == 1
    assert issues[0]["kind"] == "silent_zero"


def test_success_with_none_records_is_flagged():
    issues = classify_runs([_run(status="success", updated=None)])
    assert [i["kind"] for i in issues] == ["silent_zero"]


def test_healthy_run_is_not_flagged():
    assert classify_runs([_run(status="success", updated=34703)]) == []


def test_failed_and_partial_runs_are_reported():
    rows = [_run(status="failed", updated=0, run_id="a"),
            _run(retailer="Kroger (multi-banner)", status="partial", updated=900, run_id="b")]
    kinds = [i["kind"] for i in classify_runs(rows)]
    assert kinds == ["failed", "partial"]


def test_running_rows_are_ignored():
    """An in-flight run (mini job still going) isn't an issue yet.

    Anchored to a `now` near the fixture's start_at. Before the stuck check
    existed this passed against wall-clock time, which meant it was only ever
    asserting "running is exempt forever" — the very gap that let Kroger sit at
    `running` for two weeks.
    """
    assert classify_runs([_run(status="running", updated=0)],
                         now=_dt("2026-07-12T10:45:00+00:00")) == []


def test_flip_silent_zeroes_marks_failed_in_db():
    sb = MagicMock()
    issues = classify_runs([_run(status="success", updated=0, run_id="run-9")])
    flip_silent_zeroes(sb, issues)
    sb.table.assert_called_with("scraper_runs")
    update_arg = sb.table.return_value.update.call_args[0][0]
    assert update_arg["status"] == "failed"
    assert update_arg["error_message"] == SILENT_ZERO_MSG
    sb.table.return_value.update.return_value.eq.assert_called_with("id", "run-9")


def test_flip_leaves_failed_and_partial_alone():
    """failed/partial rows already tell the truth — only silent zeroes flip."""
    sb = MagicMock()
    issues = classify_runs([_run(status="failed", run_id="a"),
                            _run(status="partial", updated=5, run_id="b")])
    flip_silent_zeroes(sb, issues)
    sb.table.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# 2026-09-06: Kroger's run row sat at `running` for two weeks and nothing
# complained. kroger.py wrote status="partial", which violates the
# scraper_runs status CHECK enum, so the terminal update raised; the workflow's
# continue-on-error swallowed it, `running` was treated as in-flight here, and
# sweep_delisted skipped the retailer entirely (781 stale in-stock rows).
# ---------------------------------------------------------------------------

def test_a_run_stuck_in_running_is_an_issue():
    """`running` means in-flight, but only for a while. A row that never
    reaches a terminal status is exactly how a broken completion path hides —
    no failure, no silent zero, just silence."""
    rows = [{"id": "1", "retailer_name": "Kroger (multi-banner)", "status": "running",
             "records_updated": 0, "started_at": "2026-09-06T11:59:00+00:00"}]
    issues = classify_runs(rows, now=_dt("2026-09-07T06:00:00+00:00"))
    assert [i["kind"] for i in issues] == ["stuck"]


def test_a_recently_started_run_is_still_in_flight():
    """Long scrapes are normal — Spec's takes ~30 min, extraction hours. Only
    flag a run that has blown past any plausible duration."""
    rows = [{"id": "1", "retailer_name": "Spec's", "status": "running",
             "records_updated": 0, "started_at": "2026-09-06T11:59:00+00:00"}]
    assert classify_runs(rows, now=_dt("2026-09-06T12:20:00+00:00")) == []


def test_a_long_running_job_can_be_excluded_rather_than_raising_the_threshold():
    """The local-LLM extraction chain legitimately runs ~13h. Excluding it from
    a caller that does not own it beats raising the threshold above a day and
    blinding the check for everything else."""
    rows = [{"id": "1", "retailer_name": "Extraction (local qwen)", "status": "running",
             "records_updated": 0, "started_at": "2026-09-06T08:00:00+00:00"}]
    now = _dt("2026-09-06T20:00:00+00:00")
    assert [i["kind"] for i in classify_runs(rows, now=now)] == ["stuck"]
    assert classify_runs(rows, now=now, exclude={"Extraction (local qwen)"}) == []


def test_excluded_retailers_are_not_this_callers_problem():
    """GitHub and the mini both verify by time window, so each sees the other's
    runs. GitHub went red for an H-E-B failure it neither ran nor can fix —
    noise that teaches people to ignore a red build."""
    rows = [
        {"id": "1", "retailer_name": "H-E-B", "status": "failed",
         "records_updated": 51920, "started_at": "2026-09-06T10:30:00+00:00"},
        {"id": "2", "retailer_name": "Pogo's Wine & Spirits", "status": "failed",
         "records_updated": 0, "started_at": "2026-09-06T11:59:00+00:00"},
    ]
    issues = classify_runs(rows, now=_dt("2026-09-06T12:10:00+00:00"),
                           exclude={"H-E-B"})
    assert [i["run"]["retailer_name"] for i in issues] == ["Pogo's Wine & Spirits"]
