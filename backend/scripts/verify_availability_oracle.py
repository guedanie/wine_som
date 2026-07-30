"""Acceptance for the availability oracle. Run from backend/:
    /usr/bin/python3 -m scripts.verify_availability_oracle"""
from db import get_supabase_client
from utils.geo import find_nearby_store_ids
from recommendation.availability import (axes_from_intent, fetch_axis_counts, derive_state,
                                         axis_key, axis_label, NOT_IN_CATALOG,
                                         PRESENT_OUT_OF_BUDGET)

ZIP = "78209"


def facts_for(sb, nearby, resolved, scope_label=None, scope_ids=None, budget=50.0,
              fallback_terms=None):
    axes = axes_from_intent(resolved, scope_label=scope_label, scope_store_ids=scope_ids,
                            fallback_terms=fallback_terms)
    counts = fetch_axis_counts(sb, axes, nearby, budget)
    out = []
    for a in axes:
        c = counts.get(axis_key(a))
        if c:
            out.append((axis_label(a), derive_state(c["total"], c["in_budget"], 0), c))
    return out


def main():
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(ZIP, sb)
    meta = sb.table("stores").select("id,retailer_name").in_("id", nearby).execute().data
    ger = [s["id"] for s in meta if "Geraldine" in (s.get("retailer_name") or "")]

    print("— Barolo x Geraldine's (the bug-#6 case) —")
    got = facts_for(sb, nearby, {"regions": ["Barolo"]}, "Geraldine's", ger)
    for label, state, c in got:
        print(f"  {label}: {state} total={c['total']} in_budget={c['in_budget']} "
              f"range={c.get('min_price')}-{c.get('max_price')}")
    scoped = [g for g in got if "Geraldine" in g[0]]
    assert scoped, "expected a Geraldine's-scoped fact"
    assert scoped[0][1] == PRESENT_OUT_OF_BUDGET, f"expected out-of-budget, got {scoped[0][1]}"

    print("— a genuinely absent axis —")
    absent = facts_for(sb, nearby, {"regions": ["Ktimalandia Nowhere"]})
    print(f"  {absent}")
    assert absent and absent[0][1] == NOT_IN_CATALOG

    print("— negative framing must still emit an axis (the silent fail-open) —")
    from recommendation.availability import catalog_terms, terms_in_message
    terms = terms_in_message("nothing from Mendoza right?", catalog_terms(sb))
    print(f"  fallback terms: {terms}")
    assert terms, "expected the catalog fallback to find 'mendoza'"
    got = facts_for(sb, nearby, {"regions": [], "grapes": [], "wine_type": None,
                                 "wine_name": None}, fallback_terms=terms)
    for label, state, c in got:
        print(f"  {label}: {state} total={c['total']} in_budget={c['in_budget']}")
    assert got and got[0][1].startswith("PRESENT_"), "expected a PRESENT_* Mendoza fact"

    print("— the two red-team false-absence cases now produce a correct line —")
    from recommendation.availability import availability_lines
    terms = terms_in_message("nothing from Mendoza right?", catalog_terms(sb))
    mendoza = facts_for(sb, nearby, {"regions": [], "grapes": [], "wine_type": None,
                                     "wine_name": None}, fallback_terms=terms)
    m_facts = [{"label": l, "state": s, "total": c["total"], "in_budget": c["in_budget"],
                "min_price": c.get("min_price"), "max_price": c.get("max_price"),
                "axis": {"kind": "place", "value": l, "scope": None}}
               for l, s, c in mendoza]
    m_lines = availability_lines(m_facts, [], 50.0)
    print(f"  mendoza -> {m_lines}")
    assert m_lines and "in budget" in m_lines[0], "expected a Mendoza availability line"

    bru = facts_for(sb, nearby, {"regions": ["Brunello di Montalcino"], "grapes": [],
                                 "wine_type": None, "wine_name": None})
    b_facts = [{"label": l, "state": s, "total": c["total"], "in_budget": c["in_budget"],
                "min_price": c.get("min_price"), "max_price": c.get("max_price"),
                "axis": {"kind": "place", "value": l, "scope": None}}
               for l, s, c in bru]
    b_lines = availability_lines(b_facts, [], 50.0)
    print(f"  brunello -> {b_lines}")
    assert b_lines, "expected a Brunello availability line"
    assert any("brunello" in l.lower() for l in b_lines), "must name the axis the user asked for"

    print("OK — oracle states verified against live inventory")


if __name__ == "__main__":
    main()
