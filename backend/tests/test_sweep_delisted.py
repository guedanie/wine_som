import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from unittest.mock import MagicMock, call
from scripts.sweep_delisted import eligible_runs, sweep_run


def _run(retailer="H-E-B", status="success", updated=34703,
         started="2026-07-12T09:49:00+00:00"):
    return {"retailer_name": retailer, "status": status,
            "records_updated": updated, "started_at": started}


def test_only_successful_nonzero_runs_are_swept():
    """A failed or silent-zero run must NEVER trigger a sweep — otherwise a
    broken scraper would flip its whole retailer to out-of-stock."""
    runs = [
        _run(status="success", updated=34703),
        _run(retailer="Spec's", status="success", updated=0),
        _run(retailer="Kroger (multi-banner)", status="failed", updated=0),
        _run(retailer="Twin Liquors", status="partial", updated=500),
        _run(retailer="Pogo's Wine & Spirits", status="running", updated=None),
    ]
    assert [r["retailer_name"] for r in eligible_runs(runs)] == ["H-E-B"]


def _sb(store_ids, participating):
    """Mock supabase: stores lookup returns store_ids; the per-store
    participation probe returns a row only for stores in `participating`."""
    sb = MagicMock()

    def table(name):
        qb = MagicMock()
        qb.select.return_value = qb
        qb.update.return_value = qb
        qb.eq.return_value = qb
        qb.in_.return_value = qb
        qb.gte.return_value = qb
        qb.lt.return_value = qb
        qb.limit.return_value = qb
        if name == "stores":
            qb.execute.return_value = MagicMock(data=[{"id": s} for s in store_ids])
        else:
            # participation probe: qb.in_ was called with ([store_id],) per store
            def exec_side_effect():
                probed = qb.in_.call_args[0][1]
                hit = probed and probed[0] in participating
                return MagicMock(data=[{"id": "x"}] if hit else [])
            qb.execute.side_effect = lambda: exec_side_effect()
        table.calls.setdefault(name, []).append(qb)
        return qb

    table.calls = {}
    sb.table.side_effect = table
    sb._calls = table.calls
    return sb


def test_sweep_only_touches_participating_stores():
    """A store with no fresh rows this run (subset run, new store, etc.) is
    left alone — sweeping it would delist inventory that was never scraped."""
    sb = _sb(store_ids=["s1", "s2"], participating=["s1"])
    swept = sweep_run(sb, _run())
    update_qbs = [q for q in sb._calls.get("retail_inventory", [])
                  if q.update.called]
    assert len(update_qbs) == 1
    qb = update_qbs[0]
    assert qb.update.call_args[0][0] == {"in_stock": False}
    assert qb.in_.call_args_list[-1] == call("store_ref", ["s1"])   # not s2
    assert qb.lt.call_args == call("last_scraped_at", "2026-07-12T09:49:00+00:00")
    assert qb.eq.call_args_list[-1] == call("in_stock", True)


def test_sweep_skips_when_no_store_participated():
    sb = _sb(store_ids=["s1", "s2"], participating=[])
    sweep_run(sb, _run())
    update_qbs = [q for q in sb._calls.get("retail_inventory", [])
                  if q.update.called]
    assert update_qbs == []


def test_multi_banner_run_name_maps_to_store_retailer_names():
    """scraper_runs says 'Kroger (multi-banner)' but the stores rows say
    'Kroger' and 'Harris Teeter' — the sweep must look up both, not the
    literal run name (which matches nothing and silently skips the sweep)."""
    sb = _sb(store_ids=["s1"], participating=["s1"])
    sweep_run(sb, _run(retailer="Kroger (multi-banner)"))
    stores_qb = sb._calls["stores"][0]
    assert stores_qb.in_.call_args == call(
        "retailer_name", ["Kroger", "Harris Teeter"])
