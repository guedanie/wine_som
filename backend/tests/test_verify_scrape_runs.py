import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import MagicMock
from scripts.verify_scrape_runs import classify_runs, flip_silent_zeroes, SILENT_ZERO_MSG


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
    """An in-flight run (mini job still going) isn't an issue yet."""
    assert classify_runs([_run(status="running", updated=0)]) == []


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
