import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from recommendation.availability import (
    axes_from_intent, derive_state, count_shortlisted, format_fact_block,
    NOT_IN_CATALOG, PRESENT_OUT_OF_BUDGET, PRESENT_SHORTLISTED,
    PRESENT_NOT_SHORTLISTED, UNMEASURED,
)


def _res(**kw):
    base = {"regions": [], "grapes": [], "wine_type": None, "wine_name": None}
    base.update(kw)
    return base


# --- derive_state precedence ---
def test_state_unmeasured_beats_everything():
    assert derive_state(0, 0, 0, stale=True) == UNMEASURED
    assert derive_state(9, 9, 9, stale=True) == UNMEASURED


def test_state_not_in_catalog_only_when_total_zero():
    assert derive_state(0, 0, 0, stale=False) == NOT_IN_CATALOG


def test_state_out_of_budget():
    assert derive_state(3, 0, 0, stale=False) == PRESENT_OUT_OF_BUDGET


def test_state_shortlisted_and_not_shortlisted():
    assert derive_state(10, 8, 2, stale=False) == PRESENT_SHORTLISTED
    assert derive_state(10, 8, 0, stale=False) == PRESENT_NOT_SHORTLISTED


# --- axes_from_intent ---
def test_axes_each_named_kind():
    axes = axes_from_intent(_res(regions=["Barolo"], grapes=["Nebbiolo"], wine_type="red"))
    kinds = {(a["kind"], a["value"]) for a in axes}
    assert ("place", "Barolo") in kinds
    assert ("grape", "Nebbiolo") in kinds
    assert ("type", "red") in kinds
    assert all(a["scope"] is None for a in axes)


def test_axes_empty_when_nothing_named():
    assert axes_from_intent(_res()) == []


def test_axes_compound_adds_scoped_copy():
    axes = axes_from_intent(_res(regions=["Barolo"]), scope_label="Geraldine's",
                            scope_store_ids=["s1"])
    scoped = [a for a in axes if a["scope"] == "Geraldine's"]
    unscoped = [a for a in axes if a["scope"] is None]
    assert len(scoped) == 1 and scoped[0]["store_ids"] == ["s1"]
    assert len(unscoped) == 1            # both the nearby and the scoped fact


def test_axes_scope_only_when_no_content_axis():
    axes = axes_from_intent(_res(), scope_label="H-E-B", scope_store_ids=["s1"])
    assert len(axes) == 1
    assert axes[0]["kind"] == "scope" and axes[0]["scope"] == "H-E-B"


def test_axes_are_capped():
    axes = axes_from_intent(_res(regions=[f"R{i}" for i in range(10)]))
    assert len(axes) <= 6


# --- count_shortlisted ---
def test_count_shortlisted_matches_subregion_and_accent():
    top = [{"region": "Bordeaux", "sub_region": "Pauillac", "name": "X"},
           {"region": "Rhône", "name": "Y"}]
    assert count_shortlisted({"kind": "place", "value": "Pauillac"}, top) == 1
    assert count_shortlisted({"kind": "place", "value": "Rhone"}, top) == 1   # accent-folded


def test_count_shortlisted_grape_and_name():
    top = [{"varietal": "Nebbiolo", "grapes": ["Nebbiolo"], "name": "Barolo DOCG"}]
    assert count_shortlisted({"kind": "grape", "value": "Nebbiolo"}, top) == 1
    assert count_shortlisted({"kind": "name", "value": "Barolo"}, top) == 1


# --- format_fact_block ---
def test_format_empty_is_blank():
    assert format_fact_block([]) == ""


def test_format_renders_state_and_prices():
    block = format_fact_block([
        {"label": "Barolo x Geraldine's", "state": PRESENT_OUT_OF_BUDGET,
         "total": 3, "in_budget": 0, "min_price": 59, "max_price": 110},
    ])
    assert "Barolo x Geraldine's" in block
    assert "3" in block and "59" in block and "110" in block
    assert PRESENT_OUT_OF_BUDGET in block


def test_format_not_in_catalog_is_the_only_absence():
    block = format_fact_block([{"label": "Muscadet", "state": NOT_IN_CATALOG,
                                "total": 0, "in_budget": 0}])
    assert NOT_IN_CATALOG in block
