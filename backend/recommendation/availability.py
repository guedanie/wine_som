"""Availability oracle — absence as a deterministic computed fact.

The recommendation shortlist is a bounded, ranked, diversity-capped sample; it can
answer "what should I recommend?" but structurally CANNOT answer "what exists nearby?".
This module answers the second question by COUNTING full nearby inventory, bypassing
every stage that narrows the shortlist (limits, budget, staleness, enrichment, type gate).

Bias to OVER-matching: over-counting merely declines to claim absence, while
under-counting reproduces the false-absence bug this exists to eliminate.
"""
import logging
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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
                     scope_store_ids: Optional[List[str]] = None,
                     fallback_terms: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """The constraints the user actually named, as queryable axes. When a retailer or
    store is named, each content axis also gets a scoped copy (so "Barolo at Geraldine's"
    yields both the nearby and the Geraldine's fact); a scope named with no content axis
    yields a scope-only axis. Empty when nothing concrete was named — no axes, no
    queries, no added latency.

    `fallback_terms` (catalog terms found in the raw message) is a deterministic FLOOR:
    consulted only when the LLM parse produced no content axis, never overriding a
    successful parse."""
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

    # Deterministic floor: when the LLM parse named nothing, fall back to catalog terms
    # actually present in the message. Negative/rhetorical framings ("nothing from
    # Mendoza right?") defeat the parser, and an axis-less turn silently bypasses the
    # oracle entirely — the precondition of the original false-absence incidents.
    if not axes and fallback_terms:
        for t in fallback_terms:
            add("place", t)

    if scope_label:
        scoped = [dict(a, scope=scope_label, store_ids=scope_store_ids) for a in axes]
        if scoped:
            axes = axes + scoped
        else:
            axes = [{"kind": "scope", "value": scope_label, "scope": scope_label,
                     "store_ids": scope_store_ids}]

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for a in axes:
        if (a.get("scope") and a.get("kind") != "scope"
                and _fold(a.get("value")) == _fold(a.get("scope"))):
            continue                      # "H-E-B at H-E-B" is not a second axis
        k = (a.get("kind"), _fold(a.get("value")), a.get("scope"))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(a)
    return deduped[:_MAX_AXES]


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


def _axis_or_clause(axis: Dict[str, Any]) -> Optional[str]:
    """The postgrest `or_` predicate for an axis, deliberately BROAD (over-matching is
    safe; under-matching causes false absence). None => no wines-level filter."""
    v = (axis.get("value") or "").replace(",", " ").strip()
    if not v:
        return None
    kind = axis.get("kind")
    if kind == "scope":
        return None                      # store_ids alone scope this axis
    if kind == "type":
        # intent enum says 'rose'; the column stores 'rosé' (1,017 rows vs 0) — match both
        vals = {v, v.replace("rose", "rosé")} if v.startswith("rose") else {v}
        return ",".join(f"wine_type.eq.{t}" for t in sorted(vals))
    if kind == "grape":
        return (f"varietal.ilike.%{v}%,name.ilike.%{v}%,"
                f'grapes.cs.["{v.title()}"],grapes.cs.["{v}"]')
    # place / name: the full union, INCLUDING sub_region (never queried elsewhere today)
    return (f"region.ilike.%{v}%,sub_region.ilike.%{v}%,country.ilike.%{v}%,"
            f"varietal.ilike.%{v}%,name.ilike.%{v}%")


def fetch_axis_counts(supabase, axes: List[Dict[str, Any]], nearby_store_ids: List[str],
                      budget_max: float) -> Dict[str, Dict[str, Any]]:
    """Count each axis against FULL nearby inventory — no limit, no staleness, no
    enrichment gate, no type gate. Returns {axis_key: {total, in_budget, min_price,
    max_price}}. Fails open to {} on any error (never breaks a recommendation)."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(axis: Dict[str, Any]) -> Any:
      # Isolated per axis: one flaky query must not void every OTHER axis's fact —
      # a single transient error previously collapsed the entire safety net silently.
      try:
        store_ids = axis.get("store_ids") or nearby_store_ids
        clause = _axis_or_clause(axis)

        def _q(with_budget: bool):
            # `wines!inner(id)` is required for the `reference_table="wines"` or_ filter
            # (postgrest PGRST108: the embedded resource must appear in the select).
            q = (supabase.table("retail_inventory")
                 .select("price, wines!inner(id)", count="exact")
                 .in_("store_ref", store_ids).eq("in_stock", True))
            if clause:
                q = q.or_(clause, reference_table="wines")
            if with_budget:
                q = q.lte("price", budget_max)
            return q.limit(1).execute()

        total = _q(False).count or 0
        in_budget = (_q(True).count or 0) if total else 0
        out = {"total": total, "in_budget": in_budget,
               "min_price": None, "max_price": None}
        # Price bounds on EVERY present axis, not just out-of-budget ones: production
        # verification found min/max null on nearly all PRESENT_NOT_SHORTLISTED facts, so
        # half the sanctioned script was unrenderable the moment an axis changed state.
        if total:
            def _edge(desc: bool):
                q = (supabase.table("retail_inventory").select("price, wines!inner(id)")
                     .in_("store_ref", store_ids).eq("in_stock", True))
                if clause:
                    q = q.or_(clause, reference_table="wines")
                return q.order("price", desc=desc).limit(1).execute().data or []
            lo, hi = _edge(False), _edge(True)
            if lo:
                out["min_price"] = lo[0]["price"]
            if hi:
                out["max_price"] = hi[0]["price"]
        return out
      except Exception:
        logger.exception("AVAILABILITY | axis failed: %s", axis_key(axis))
        return None

    if not axes:
        return {}
    try:
        with ThreadPoolExecutor(max_workers=min(6, len(axes))) as ex:
            results = list(ex.map(_one, axes))
        return {axis_key(a): r for a, r in zip(axes, results) if r is not None}
    except Exception:
        # Fail open so a broken oracle never breaks a recommendation — but NEVER
        # silently: a query-shape error here (e.g. PGRST108 from an un-embedded
        # reference_table) would otherwise make the whole safety net a permanent
        # no-op with no signal, which is the exact failure class the oracle exists
        # to eliminate.
        logger.exception("AVAILABILITY | count fetch failed — no facts this turn")
        return {}


def axis_key(axis: Dict[str, Any]) -> str:
    return f"{axis.get('kind')}:{axis.get('value')}:{axis.get('scope') or ''}"


def axis_label(axis: Dict[str, Any]) -> str:
    base = axis.get("value")
    return f"{base} at {axis['scope']}" if axis.get("scope") else str(base)


# Generic catalog values that must never be treated as a user constraint.
_STOPWORD_TERMS = {
    "red", "white", "rose", "rosé", "wine", "wines", "red wine", "white wine",
    "rose wine", "sparkling", "dessert", "fortified", "orange", "blend", "red blend",
    "white blend", "valley", "other", "unknown", "n/a", "none", "misc", "assorted",
    "table wine", "usa", "us",
}

_CATALOG_TTL_SECONDS = 3600
_catalog_cache = {"terms": None, "at": 0.0}


def catalog_terms(supabase, ttl: int = _CATALOG_TTL_SECONDS) -> set:
    """Normalized place/grape vocabulary drawn from the catalog itself.

    Complete by construction — if a wine is in inventory, the term describing it is
    matchable. A curated gazetteer measured 146 terms and missed 6 of 11 probe terms
    (Barolo, Chablis, Sancerre, Pauillac, Brunello di Montalcino, Vinho Verde); the
    catalog yields ~2,300 and missed none. Cached per process; fails open to empty."""
    now = time.time()
    if _catalog_cache["terms"] is not None and (now - _catalog_cache["at"]) < ttl:
        return _catalog_cache["terms"]
    terms = set()
    try:
        page = 0
        while True:
            rows = (supabase.table("wines")
                    .select("region,sub_region,country,varietal,grapes")
                    .order("id").range(page * 1000, page * 1000 + 999)
                    .execute().data or [])
            if not rows:
                break
            for w in rows:
                vals = [w.get(k) for k in ("region", "sub_region", "country", "varietal")]
                vals += list(w.get("grapes") or [])
                for raw in vals:
                    v = _fold(raw)
                    if v and v not in _STOPWORD_TERMS and len(v) > 2:
                        terms.add(v)
            page += 1
    except Exception:
        logger.exception("AVAILABILITY | catalog vocabulary fetch failed — fallback disabled")
        return _catalog_cache["terms"] or set()
    _catalog_cache["terms"], _catalog_cache["at"] = terms, now
    return terms


def terms_in_message(message: str, terms: set, cap: int = 4) -> List[str]:
    """Catalog terms named in the message — whole-word, accent-folded, longest first
    (so "Brunello di Montalcino" wins over "Montalcino"). Claimed spans are not
    re-matched. Deterministic: no LLM involved, so a negative or rhetorical framing
    ("nothing from Mendoza right?") still yields the entity."""
    low = _fold(message)
    if not low or not terms:
        return []
    found: List[str] = []
    claimed: List[tuple] = []
    for t in sorted(terms, key=len, reverse=True):
        if len(found) >= cap:
            break
        if t in _STOPWORD_TERMS:
            continue
        for m in re.finditer(r"(?<!\w)" + re.escape(t) + r"(?!\w)", low):
            if any(m.start() < ce and cs < m.end() for cs, ce in claimed):
                continue
            claimed.append((m.start(), m.end()))
            found.append(t)
            break
    return found
