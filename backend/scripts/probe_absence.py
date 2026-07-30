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
import urllib.request

from db import get_supabase_client
from recommendation.availability import (axes_from_intent, fetch_axis_counts, derive_state,
                                         axis_key, axis_label)
from recommendation.intent import parse_message, merge_intent, intent_from_request
from recommendation.candidate_filters import detect_retailer, detect_store
from utils.geo import find_nearby_store_ids

PROD = "https://winesom-production.up.railway.app"


def stream_narrative(base, message, zip_code, budget_max, wine_type=None, timeout=180):
    """POST to /api/recommend and reassemble the streamed narrative + picks."""
    payload = {"zip_code": zip_code, "budget_min": 10.0, "budget_max": float(budget_max),
               "message": message}
    if wine_type:
        payload["wine_type"] = wine_type
    req = urllib.request.Request(
        f"{base}/api/recommend", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    narrative, picks = [], []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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

    axes = axes_from_intent(resolved, scope_label=scope_label, scope_store_ids=scope_ids)
    counts = fetch_axis_counts(sb, axes, nearby, float(budget_max))
    out = []
    for a in axes:
        c = counts.get(axis_key(a))
        if not c:
            continue
        out.append({"label": axis_label(a),
                    "state": derive_state(c["total"], c["in_budget"], 0),
                    "total": c["total"], "in_budget": c["in_budget"],
                    "min_price": c.get("min_price"), "max_price": c.get("max_price")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--zip", dest="zip_code", default="78209")
    ap.add_argument("--budget", type=float, default=50.0)
    ap.add_argument("--wine-type", default=None)
    ap.add_argument("--base", default=PROD)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

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
