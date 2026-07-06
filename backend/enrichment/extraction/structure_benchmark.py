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
    """Vivino-structured wines with a description + extracted grape/region."""
    rows = (db.table("wine_details")
            .select("wine_id,structure_profile,description,description_long,"
                    "wines!inner(name,wine_type,varietal,region,grapes)")
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
                      "wine_type": w.get("wine_type"), "desc": desc,
                      "varietal": w.get("varietal"), "region": w.get("region"),
                      "grapes": w.get("grapes") or []})
        truth[r["wine_id"]] = {"body": sp["body"], "tannin": sp["tannins"],
                               "acidity": sp["acidity"], "sweetness": sp["sweetness"]}
        if len(wines) >= n:
            break
    return wines, truth


_ANCHOR_SYSTEM = (
    "You refine a wine's structural estimate. Each wine has a grape-based "
    "baseline (body/tannin/acidity, 1-10) that is usually accurate. KEEP the "
    "baseline unless the name or description clearly signals otherwise:\n"
    "  - explicitly oaky / rich / concentrated / reserve / big → +1-2 body\n"
    "  - delicate / light / fresh → −1-2 body\n"
    "  - crisp / racy / bright / high-acid / cool-climate / mountain → +1-2 acidity\n"
    "  - round / soft / low-acid / warm / jammy → −1-2 acidity\n"
    "If a wine has NO baseline (a blend with no single grape), estimate all "
    "three from the style/name. Never move a value more than 2 from the baseline.\n"
    'Respond ONLY with JSON: {"wines":[{"wine_id":"...","body":N,"tannin":N,'
    '"acidity":N}]}. Integers 1-10, every wine_id once.'
)


def _infer_with_table(wines, table_pred, model, batch=8, timeout=180):
    """LLM refinement anchored on the table's grape-based baseline."""
    out = {}
    for i in range(0, len(wines), batch):
        chunk = wines[i:i + batch]
        lines = []
        for w in chunk:
            t = table_pred.get(str(w["id"]))
            base = (f'baseline body={t["body"]} tannin={t["tannin"]} acidity={t["acidity"]}'
                    if t else "baseline=NONE (blend — estimate)")
            lines.append(f'- wine_id={w["id"]} | name="{w["name"]}" | type={w.get("wine_type")} '
                         f'| {base} | desc="{(w.get("desc") or "")[:280]}"')
        body = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": _ANCHOR_SYSTEM},
                         {"role": "user", "content": "Refine:\n" + "\n".join(lines)}],
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
            print(f"  hybrid batch {i//batch} failed: {e}")
    return out


def _table_predict(wines):
    """Deterministic grape+region table prediction (no tannin>white=1 etc.)."""
    from recommendation.structure_profiles import structure_for
    out = {}
    for w in wines:
        s = structure_for(w.get("varietal"), w.get("grapes"), w.get("region"))
        if s:
            # table has no sweetness; leave it out of scoring for the table
            out[str(w["id"])] = {"body": s["body"], "tannin": s["tannins"],
                                 "acidity": s["acidity"]}
    return out


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

    def score(pred, axes):
        err = {a: [] for a in axes}
        n_scored = 0
        for wid, gt in truth.items():
            p = pred.get(wid)
            if not p:
                continue
            n_scored += 1
            for a in axes:
                try:
                    err[a].append(abs(float(p[a]) - float(gt[a])))
                except (KeyError, TypeError, ValueError):
                    pass
        return err, n_scored

    def report(label, err, n_scored, axes, dt=None):
        t = f" | {dt:.0f}s" if dt is not None else ""
        print(f"\n=== {label} | scored {n_scored}/{len(wines)}{t}")
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

    # Deterministic table (body/tannin/acidity; no sweetness)
    tbl = _table_predict(wines)
    terr, tn = score(tbl, ["body", "tannin", "acidity"])
    report(f"TABLE (grape+region)", terr, tn, ["body", "tannin", "acidity"])

    # LLM inference (all four axes)
    t0 = time.time()
    pred = _infer(wines, model)
    dt = time.time() - t0
    lerr, ln = score(pred, ["body", "tannin", "acidity", "sweetness"])
    report(f"LLM {model}", lerr, ln, ["body", "tannin", "acidity", "sweetness"], dt)

    # Hybrid: LLM refining the table's baseline
    t0 = time.time()
    hyb = _infer_with_table(wines, tbl, model)
    dth = time.time() - t0
    herr, hn = score(hyb, ["body", "tannin", "acidity"])
    report(f"HYBRID (table→LLM {model})", herr, hn, ["body", "tannin", "acidity"], dth)

    # head-to-head sample
    print("\nsample (name | table / hybrid / Vivino — body/tan/acid):")
    for w in wines[:8]:
        gt, t, h = truth.get(w["id"]), tbl.get(str(w["id"])), hyb.get(str(w["id"]))
        if not gt:
            continue
        ts = "/".join(str(t.get(a, "?")) for a in ("body", "tannin", "acidity")) if t else "—(blend)"
        hs = "/".join(str(h.get(a, "?")) for a in ("body", "tannin", "acidity")) if h else "—"
        gs = "/".join(str(gt.get(a, "?")) for a in ("body", "tannin", "acidity"))
        print(f"  {w['name'][:38]:38} tbl {ts:10} hyb {hs:10} viv {gs}")


if __name__ == "__main__":
    main()
