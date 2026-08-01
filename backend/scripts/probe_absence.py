"""Probe a live Somm deployment for FALSE ABSENCE claims.

Sends a message to /api/recommend, collects the streamed narrative, then independently
computes the availability oracle's facts from the database. A false absence is:
the narrative tells the user something isn't available while the counted fact says it IS.

This is the mechanical half of the capability suite (audit plan item #1) — it gathers
evidence; semantic judgement of the narrative is done by the caller.

Run from backend/:
    /usr/bin/python3 -m scripts.probe_absence --zip 78209 --budget 50 \
        --message "so there are no barolos at Geraldine?"
    /usr/bin/python3 -m scripts.probe_absence --json ...     # machine-readable
"""
import argparse
import json
import time
import urllib.error
import urllib.request

from db import get_supabase_client
from recommendation.availability import (axes_from_intent, catalog_terms, derive_state,
                                         fetch_axis_counts, terms_in_message,
                                         axis_key, axis_label)
from recommendation.intent import parse_message, merge_intent, intent_from_request
from recommendation.candidate_filters import detect_retailer, detect_store
from utils.geo import find_nearby_store_ids

PROD = "https://winesom-production.up.railway.app"


def stream_narrative(base, message, zip_code, budget_max, wine_type=None, timeout=180,
                     retries=4, history=None):
    """POST to /api/recommend and reassemble the streamed narrative + picks.

    Retries on 429/5xx with exponential backoff — an unhandled 429 cost 9 of 23 probes
    in the first production sweep, silently shrinking the evidence base."""
    payload = {"zip_code": zip_code, "budget_min": 10.0, "budget_max": float(budget_max),
               "message": message}
    if wine_type:
        payload["wine_type"] = wine_type
    if history:
        payload["conversation_history"] = history
        payload["conversational"] = True
    req = urllib.request.Request(
        f"{base}/api/recommend", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    narrative, picks = [], []
    for attempt in range(retries):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(5 * (2 ** attempt))
                continue
            raise
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                ev = json.loads(body)
            except Exception:
                continue
            if ev.get("type") == "token":
                narrative.append(ev.get("text", ""))
            elif ev.get("type") == "picks":
                picks = ev.get("picks") or []
    return "".join(narrative), picks


def local_facts(message, zip_code, budget_max):
    """Independently compute what the oracle SHOULD know — ground truth."""
    sb = get_supabase_client()
    nearby = find_nearby_store_ids(zip_code, sb)
    if not nearby:
        return []
    meta = sb.table("stores").select("id,retailer_name,name").in_("id", nearby).execute().data or []
    r2s = {}
    for s in meta:
        if s.get("retailer_name"):
            r2s.setdefault(s["retailer_name"], []).append(s["id"])

    resolved = merge_intent(parse_message(message), intent_from_request(
        wine_type=None, style_preferences=[], avoid=[], budget_min=10.0,
        budget_max=float(budget_max)))
    store = detect_store(message, meta)
    retailer = detect_retailer(message, list(r2s))
    scope_label = (store or {}).get("name") if store else retailer
    scope_ids = ([store["id"]] if store else r2s.get(retailer) if retailer else None)

    # Must mirror production exactly: the endpoint passes catalog fallback terms, so a
    # harness without them computes an EMPTY ground truth for negative framings and
    # grades the very fail-open it exists to detect as a PASS.
    fallback = terms_in_message(message, catalog_terms(sb))
    axes = axes_from_intent(resolved, scope_label=scope_label, scope_store_ids=scope_ids,
                            fallback_terms=fallback)
    counts = fetch_axis_counts(sb, axes, nearby, float(budget_max))
    out = []
    for a in axes:
        c = counts.get(axis_key(a))
        if not c:
            continue
        out.append({"label": axis_label(a),
                    # shortlisted_n is unknowable from outside (we don't see prod's final
                    # `top`), so this is the INVENTORY state: PRESENT_SHORTLISTED can never
                    # appear here and a PRESENT_NOT_SHORTLISTED label must NOT be read as
                    # "prod mislabeled it". Production computes the real state.
                    "state": derive_state(c["total"], c["in_budget"], 0),
                    "state_note": "inventory-state only; shortlist membership not observable",
                    "total": c["total"], "in_budget": c["in_budget"],
                    "min_price": c.get("min_price"), "max_price": c.get("max_price")})
    return out


def probe_followup(base, message, followup, zip_code, budget_max):
    """Multi-turn referential probe (item 41): turn 1 produces picks; turn 2 sends a
    referential follow-up WITH the picks in history (the production payload shape).
    A false absence here is the turn-2 narrative denying a turn-1 pick — every
    pick was, by construction, in stock one turn ago."""
    from api.routers.recommend import _false_absence_suspects
    narrative1, picks1 = stream_narrative(base, message, zip_code, budget_max)
    if not picks1:
        return {"skipped": "turn 1 produced no picks", "narrative1": narrative1}
    history = [
        {"role": "user", "content": message},
        {"role": "sommelier", "content": narrative1,
         "picks": [{"wine_id": p.get("wine_id"), "name": p.get("name")} for p in picks1]},
    ]
    narrative2, picks2 = stream_narrative(base, followup, zip_code, budget_max,
                                          history=history)
    pseudo_facts = [{"label": p.get("name") or "", "state": "PRESENT_PRIOR_PICK"}
                    for p in picks1]
    suspects = _false_absence_suspects(narrative2, pseudo_facts)
    return {"turn1_picks": [p.get("name") for p in picks1],
            "turn2_picks": [p.get("name") for p in picks2],
            "turn2_narrative": narrative2,
            "denied_prior_picks": [s["label"] for s in suspects],
            "verdict": "FAIL — denied a wine it recommended one turn ago"
                       if suspects else "PASS"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--followup", default=None,
                    help="multi-turn referential probe: send this as turn 2 with turn 1's picks in history (item 41)")
    ap.add_argument("--zip", dest="zip_code", default="78209")
    ap.add_argument("--budget", type=float, default=50.0)
    ap.add_argument("--wine-type", default=None)
    ap.add_argument("--base", default=PROD)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.followup:
        result = probe_followup(args.base, args.message, args.followup,
                                args.zip_code, args.budget)
        print(json.dumps(result, indent=2))
        return

    narrative, picks = stream_narrative(args.base, args.message, args.zip_code,
                                        args.budget, args.wine_type)
    facts = local_facts(args.message, args.zip_code, args.budget)
    result = {"message": args.message, "zip": args.zip_code, "budget": args.budget,
              "narrative": narrative, "pick_count": len(picks),
              "picks": [p.get("name") for p in picks], "facts": facts}
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"MESSAGE : {args.message}")
    print(f"PICKS   : {len(picks)} — {[p.get('name', '')[:40] for p in picks]}")
    print("FACTS   :")
    for f in facts:
        print(f"  - {f['label']}: {f['state']} total={f['total']} in_budget={f['in_budget']}"
              f" range={f.get('min_price')}-{f.get('max_price')}")
    print(f"NARRATIVE:\n{narrative}")


if __name__ == "__main__":
    main()
