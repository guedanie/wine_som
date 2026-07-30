"""Availability oracle — absence as a deterministic computed fact.

The recommendation shortlist is a bounded, ranked, diversity-capped sample; it can
answer "what should I recommend?" but structurally CANNOT answer "what exists nearby?".
This module answers the second question by COUNTING full nearby inventory, bypassing
every stage that narrows the shortlist (limits, budget, staleness, enrichment, type gate).

Bias to OVER-matching: over-counting merely declines to claim absence, while
under-counting reproduces the false-absence bug this exists to eliminate.
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional

NOT_IN_CATALOG = "NOT_IN_CATALOG"
PRESENT_OUT_OF_BUDGET = "PRESENT_OUT_OF_BUDGET"
PRESENT_NOT_SHORTLISTED = "PRESENT_NOT_SHORTLISTED"
PRESENT_SHORTLISTED = "PRESENT_SHORTLISTED"
UNMEASURED = "UNMEASURED"

_MAX_AXES = 6          # bounds latency/cost per request


def _fold(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def derive_state(total: int, in_budget: int, shortlisted_n: int,
                 stale: bool = False) -> str:
    """The five-state vocabulary, in precedence order. `NOT_IN_CATALOG` is the ONLY
    state that licenses an absence sentence in the narrative."""
    if stale:
        return UNMEASURED
    if not total:
        return NOT_IN_CATALOG
    if not in_budget:
        return PRESENT_OUT_OF_BUDGET
    if shortlisted_n > 0:
        return PRESENT_SHORTLISTED
    return PRESENT_NOT_SHORTLISTED


def axes_from_intent(resolved: Dict[str, Any],
                     scope_label: Optional[str] = None,
                     scope_store_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """The constraints the user actually named, as queryable axes. When a retailer or
    store is named, each content axis also gets a scoped copy (so "Barolo at Geraldine's"
    yields both the nearby and the Geraldine's fact); a scope named with no content axis
    yields a scope-only axis. Empty when nothing concrete was named — no axes, no
    queries, no added latency."""
    axes: List[Dict[str, Any]] = []

    def add(kind: str, value: str) -> None:
        if not value:
            return
        axes.append({"kind": kind, "value": str(value), "scope": None, "store_ids": None})

    for r in (resolved.get("regions") or []):
        add("place", r)
    if not (resolved.get("regions") or []) and resolved.get("region"):
        add("place", resolved["region"])
    for g in (resolved.get("grapes") or []):
        add("grape", g)
    if resolved.get("wine_type"):
        add("type", resolved["wine_type"])
    if resolved.get("wine_name"):
        add("name", resolved["wine_name"])

    if scope_label:
        scoped = [dict(a, scope=scope_label, store_ids=scope_store_ids) for a in axes]
        if scoped:
            axes = axes + scoped
        else:
            axes = [{"kind": "scope", "value": scope_label, "scope": scope_label,
                     "store_ids": scope_store_ids}]
    return axes[:_MAX_AXES]


def _cand_text(c: Dict[str, Any]) -> str:
    parts = [c.get("region"), c.get("sub_region"), c.get("country"),
             c.get("varietal"), c.get("name")]
    parts += list(c.get("grapes") or [])
    return " | ".join(_fold(p) for p in parts if p)


def count_shortlisted(axis: Dict[str, Any], top: List[Dict[str, Any]]) -> int:
    """How many of the FINAL candidates satisfy this axis (in-memory, free)."""
    v = _fold(axis.get("value"))
    if not v:
        return 0
    if axis.get("kind") == "type":
        return sum(1 for c in top if _fold(c.get("wine_type")) == v)
    if axis.get("kind") == "scope":
        return sum(1 for c in top if v in _fold(c.get("retailer")))
    scope = _fold(axis.get("scope"))
    n = 0
    for c in top:
        if scope and scope not in _fold(c.get("retailer")):
            continue
        if v in _cand_text(c):
            n += 1
    return n


_SCRIPTS = {
    NOT_IN_CATALOG: "nothing nearby matches this — this is the ONLY axis you may call absent",
    PRESENT_OUT_OF_BUDGET: "exists nearby but nothing within budget — name the count and price range",
    PRESENT_NOT_SHORTLISTED: "exists nearby but none made this shortlist — never call it absent",
    PRESENT_SHORTLISTED: "present in the listings below — must appear in your picks",
    UNMEASURED: "not measurable (stale retailer data or unfilterable attribute) — say you can't confirm",
}


def format_fact_block(facts: List[Dict[str, Any]]) -> str:
    """Render the computed facts for the prompt. Empty string when there are none."""
    if not facts:
        return ""
    lines = []
    for f in facts:
        bits = [f"{f.get('label')}: [{f.get('state')}]"]
        if f.get("total") is not None:
            bits.append(f"{f['total']} nearby")
        if f.get("in_budget") is not None:
            bits.append(f"{f['in_budget']} in budget")
        if f.get("min_price") is not None and f.get("max_price") is not None:
            bits.append(f"${f['min_price']:.0f}-${f['max_price']:.0f}")
        lines.append("- " + ", ".join(bits) + f"  ({_SCRIPTS.get(f.get('state'), '')})")
    return ("\n\n[VERIFIED AVAILABILITY — these are counted facts about full nearby "
            "inventory, not the listings below. They override any impression the listings "
            "give you.]\n" + "\n".join(lines))
