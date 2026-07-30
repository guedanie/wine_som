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


from recommendation.availability import (terms_in_message, _STOPWORD_TERMS, axis_key,
                                         fetch_axis_counts)

_AX_TERMS = {"mendoza", "barolo", "montalcino", "brunello di montalcino", "rhone",
             "chablis", "nebbiolo", "red", "wine", "valley"}


def test_terms_longest_match_wins():
    found = terms_in_message("any brunello di montalcino under $50?", _AX_TERMS)
    assert "brunello di montalcino" in found
    assert "montalcino" not in found


def test_terms_whole_word_only():
    assert terms_in_message("a barolotto please", {"barolo"}) == []


def test_terms_accent_folded():
    assert "rhone" in terms_in_message("anything from the Rhône?", _AX_TERMS)


def test_terms_stopwords_never_match():
    assert terms_in_message("just a red wine from the valley", _AX_TERMS) == []


def test_terms_negative_framing_still_found():
    assert "mendoza" in terms_in_message("nothing from Mendoza right?", _AX_TERMS)


def test_terms_empty_vocab_is_safe():
    assert terms_in_message("anything from Mendoza?", set()) == []


def test_stopwords_cover_generic_catalog_values():
    for w in ("red", "white", "wine", "valley", "other", "blend"):
        assert w in _STOPWORD_TERMS


def test_fallback_used_only_when_no_content_axis():
    axes = axes_from_intent({"regions": [], "grapes": [], "wine_type": None,
                             "wine_name": None}, fallback_terms=["mendoza"])
    assert [(a["kind"], a["value"]) for a in axes] == [("place", "mendoza")]


def test_fallback_ignored_when_parse_succeeded():
    axes = axes_from_intent({"regions": ["Rioja"], "grapes": [], "wine_type": None,
                             "wine_name": None}, fallback_terms=["mendoza"])
    vals = {a["value"] for a in axes}
    assert "Rioja" in vals and "mendoza" not in vals


def test_axes_are_deduped():
    axes = axes_from_intent({"regions": ["Champagne"], "grapes": [], "wine_type": None,
                             "wine_name": "Champagne"})
    keys = [(a["kind"], a["value"].lower(), a["scope"]) for a in axes]
    assert len(keys) == len(set(keys))


def test_scoped_copy_skipped_when_value_equals_scope():
    axes = axes_from_intent({"regions": [], "grapes": [], "wine_type": None,
                             "wine_name": "H-E-B"},
                            scope_label="H-E-B", scope_store_ids=["s1"])
    assert not any(a["value"].lower() == "h-e-b" and a["scope"] == "H-E-B"
                   and a["kind"] != "scope" for a in axes)


def test_one_failing_axis_does_not_void_the_others():
    """A single transient DB error must not collapse every axis to no-fact — that
    silently voids the whole safety net (observed in production verification)."""
    class _FlakyDB:
        def table(self, _n): return self
        def select(self, *a, **k): return self
        def in_(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def lte(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def or_(self, clause, **k):
            if "boom" in clause:
                raise RuntimeError("simulated transient error")
            return self
        def execute(self):
            class R:
                count = 7
                data = [{"price": 20.0}]
            return R()

    axes = [{"kind": "place", "value": "boom", "scope": None, "store_ids": None},
            {"kind": "place", "value": "rioja", "scope": None, "store_ids": None}]
    counts = fetch_axis_counts(_FlakyDB(), axes, ["s1"], 50.0)
    assert axis_key(axes[0]) not in counts
    assert counts[axis_key(axes[1])]["total"] == 7
