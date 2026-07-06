"""
Structure-inference benchmark: can a local LLM estimate a wine's structure
(body / tannin / acidity / sweetness) from name + description alone?

Ground truth = Vivino's real crowd-measured baseline_structure (already in
wine_details.structure_profile, source='vivino', 1-10 scale). We hide it, ask
qwen to infer the same four axes, and compare per-axis.

  cd backend && python3 -m enrichment.extraction.structure_benchmark [--n 80] [--model qwen2.5:7b]
"""
import sys
import json
import time
import urllib.request

from db import get_service_client

OLLAMA_URL = "http://localhost:11434/api/chat"

# NOTE (2026-07-05 benchmark): qwen2.5:7b infers sweetness well (86% within ±1)
# and body decently (65%), but tannin/acidity are unreliable and — critically —
# HEAVIER calibration anchoring made it WORSE (the 7B model ignores detailed
# scale guidance and gets erratic). Conclusion: don't ask a small local model
# to QUANTIFY structure. Better path = deterministic grape->structure table
# (grape is LLM-extracted at ~80%, then mapped), LLM only for sweetness. This
# simpler prompt is the better-scoring baseline kept for future model tests.
_SYSTEM = (
    "You are a wine expert. From a wine's name and description, estimate its "
    "structural profile on a 1-10 integer scale:\n"
    "  body      1=very light (e.g. Muscadet)      10=very full (e.g. Napa Cab, Amarone)\n"
    "  tannin    1=none (whites, most rosé)         10=very grippy (young Nebbiolo, Cab, Tannat)\n"
    "  acidity   1=soft/flabby                      10=very high (Sancerre, Champagne, Riesling)\n"
    "  sweetness 1=bone dry (most reds/whites)      10=very sweet (Sauternes, Moscato, Port)\n"
    "Anchor on grape + region + style: Cabernet/Syrah/Nebbiolo = full body + high tannin, dry. "
    "Sauvignon Blanc/Riesling(dry) = light-med body, no tannin, high acidity, dry. "
    "Moscato/late-harvest/Port = high sweetness. Champagne/sparkling = high acidity. "
    "Pinot Noir = light-med body, low-med tannin, high acidity. Chardonnay(oaked) = full body, "
    "med acidity, no tannin, dry.\n"
    'Respond ONLY with JSON: {"wines":[{"wine_id":"...","body":N,"tannin":N,"acidity":N,'
    '"sweetness":N}]}. Integers 1-10. Every wine_id exactly once.'
)


def _infer(wines, model, batch=8, timeout=180):
    out = {}
    for i in range(0, len(wines), batch):
        chunk = wines[i:i + batch]
        listing = "\n".join(
            f'- wine_id={w["id"]} | name="{w["name"]}" | type={w.get("wine_type")} '
            f'| desc="{(w.get("desc") or "")[:300]}"' for w in chunk
        )
        body = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": "Estimate structure:\n" + listing}],
            "stream": False, "format": "json", "options": {"temperature": 0},
        }).encode()
        req = urllib.request.Request(OLLAMA_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            parsed = json.loads((data.get("message") or {}).get("content") or "{}")
            for r in parsed.get("wines", []):
                if r.get("wine_id"):
                    out[str(r["wine_id"])] = r
        except Exception as e:
            print(f"  batch {i//batch} failed: {e}")
    return out


def _fetch_ground_truth(db, n):
    """Vivino-structured wines with a description to reason from."""
    rows = (db.table("wine_details")
            .select("wine_id,structure_profile,description,description_long,"
                    "wines!inner(name,wine_type)")
            .eq("structure_profile->>source", "vivino")
            .limit(n * 3).execute().data)
    wines, truth = [], {}
    for r in rows:
        sp = r.get("structure_profile") or {}
        # need all four axes present in the Vivino data to score fairly
        if not all(sp.get(k) is not None for k in ("body", "tannins", "acidity", "sweetness")):
            continue
        w = r.get("wines") or {}
        desc = r.get("description") or r.get("description_long") or ""
        wines.append({"id": r["wine_id"], "name": w.get("name", ""),
                      "wine_type": w.get("wine_type"), "desc": desc})
        truth[r["wine_id"]] = {"body": sp["body"], "tannin": sp["tannins"],
                               "acidity": sp["acidity"], "sweetness": sp["sweetness"]}
        if len(wines) >= n:
            break
    return wines, truth


def main():
    n = 80
    model = "qwen2.5:7b"
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    db = get_service_client()
    wines, truth = _fetch_ground_truth(db, n)
    print(f"Ground-truth wines (Vivino structure + description): {len(wines)}\n")
    if not wines:
        print("none found — run Vivino facts backfill first")
        return

    t0 = time.time()
    pred = _infer(wines, model)
    dt = time.time() - t0

    axes = ["body", "tannin", "acidity", "sweetness"]
    err = {a: [] for a in axes}
    scored = 0
    for wid, gt in truth.items():
        p = pred.get(wid)
        if not p:
            continue
        scored += 1
        for a in axes:
            try:
                err[a].append(abs(float(p[a]) - float(gt[a])))
            except (KeyError, TypeError, ValueError):
                pass

    print(f"model={model} | scored {scored}/{len(wines)} | {dt:.0f}s\n")
    print(f"{'axis':10} {'MAE':>6} {'within±1':>9} {'within±2':>9}  (0-10 scale)")
    for a in axes:
        e = err[a]
        if not e:
            print(f"{a:10} {'—':>6}")
            continue
        mae = sum(e) / len(e)
        w1 = 100 * sum(1 for x in e if x <= 1) / len(e)
        w2 = 100 * sum(1 for x in e if x <= 2) / len(e)
        print(f"{a:10} {mae:>6.2f} {w1:>8.0f}% {w2:>8.0f}%")

    # a few concrete comparisons
    print("\nsample (name → predicted vs Vivino):")
    for w in wines[:6]:
        p, gt = pred.get(w["id"]), truth.get(w["id"])
        if p and gt:
            ps = "/".join(str(p.get(a, "?")) for a in axes)
            gs = "/".join(str(gt.get(a, "?")) for a in axes)
            print(f"  {w['name'][:44]:44} pred {ps:12} vivino {gs}  (body/tan/acid/sweet)")


if __name__ == "__main__":
    main()
