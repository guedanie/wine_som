"""Acceptance for the off-catalog-bottle web search gate. Run from backend/:
    /usr/bin/python3 -m scripts.verify_web_search_gate

Live end-to-end: a real named bottle this catalog doesn't carry, run through
the actual availability oracle against live inventory, then through the gate
and the user-message builder -- confirming the directive appears and the tool
would be attached, without spending an actual Anthropic API call.
"""
import sys
from db import get_supabase_client
from utils.geo import find_nearby_store_ids
from recommendation.availability import axes_from_intent, fetch_axis_counts, derive_state, axis_key
from recommendation.web_search import off_catalog_bottles, off_catalog_directive, WEB_SEARCH_TOOL
from recommendation.claude_client import _build_user_message

ZIP = "78209"
# A specific, real, small-production bottle overwhelmingly unlikely to be in
# any of this app's scraped retailers -- the live equivalent of the "genuinely
# absent axis" case in verify_availability_oracle.py.
OFF_CATALOG_BOTTLE = "Domaine de la Romanee-Conti Montrachet 2018"


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)

    resolved = {"regions": [], "grapes": [], "wine_type": None,
                "wine_name": OFF_CATALOG_BOTTLE}
    axes = axes_from_intent(resolved)
    assert axes and axes[0]["kind"] == "name", "expected a single name axis"

    counts = fetch_axis_counts(sb, axes, nearby, 50.0)
    c = counts.get(axis_key(axes[0]))
    assert c is not None, "axis count fetch failed -- cannot verify live"
    state = derive_state(c["total"], c["in_budget"], 0)
    print(f"— {OFF_CATALOG_BOTTLE}: state={state} total={c['total']} —")

    facts = [{"label": OFF_CATALOG_BOTTLE, "state": state, "axis": axes[0]}]
    bottles = off_catalog_bottles(facts)

    if state == "NOT_IN_CATALOG":
        assert bottles == [OFF_CATALOG_BOTTLE], "gate should fire for a confirmed-absent bottle"
        directive = off_catalog_directive(bottles)
        assert "OFF-CATALOG BOTTLE" in directive and OFF_CATALOG_BOTTLE in directive
        msg = _build_user_message([], {**resolved, "flavors": [], "avoid": [],
                                       "budget_min": 10.0, "budget_max": 50.0,
                                       "availability_facts": facts})
        assert "OFF-CATALOG BOTTLE" in msg, "directive did not reach the built user message"
        print(f"  gate fired — web_search tool would be attached "
              f"(allowed_domains={WEB_SEARCH_TOOL['allowed_domains']})")
    else:
        # If this specific bottle is ever actually stocked, the test's premise
        # went stale -- fail loudly (not the gate being broken) rather than
        # silently exiting 0 having never exercised the branch this script
        # exists to test. A future dev should pick a new OFF_CATALOG_BOTTLE.
        assert bottles == []
        print(f"  PREMISE STALE: bottle resolved {state}, not NOT_IN_CATALOG -- the gate "
              f"correctly did NOT fire for it, but this script's core assertions never ran. "
              f"Pick a different OFF_CATALOG_BOTTLE (a real bottle genuinely absent from the "
              f"catalog) and re-run.")
        sys.exit(1)

    print("OK — off-catalog web search gate verified against live inventory")


if __name__ == "__main__":
    main()
