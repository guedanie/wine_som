"""Vision match-rate spike harness (bottle-scan, item 26 pre-build).

Measures the two-stage pipeline photo -> Claude vision read -> catalog fuzzy
match, graded against ground truth. Two modes:

  Smoke test (catalog images — clean-studio ceiling, validates prompt+matcher):
    python3 -m scripts.spike_vision_match --smoke 10

  Real photos (the honest number; see PHOTO-GUIDELINES.md for the test set):
    python3 -m scripts.spike_vision_match --photos ../data/exploration/bottle-scan-photos

  --model haiku|sonnet|both (default haiku). --seed for a reproducible smoke sample.

Outcomes per item: TOP1 (right wine, exact/vintage state), TOP4 (right wine in
candidates), WRONG-CONF (confident exact on the WRONG wine — the bad UX case),
MISS (unstocked/unreadable on a stocked bottle), DECLINE (not_wine / unstocked
as expected). Summary prints rates + latency + token spend per model.
"""
import argparse
import csv
import random
import ssl
import urllib.request
from pathlib import Path

from db import get_supabase_client
from enrichment.label_scan import HAIKU, SONNET, media_type_for, read_label
from recommendation.candidate_filters import significant_name_tokens
from recommendation.label_match import classify_scan

MODELS = {"haiku": HAIKU, "sonnet": SONNET}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch_candidates(sb, read):
    """Catalog-wide token search (name OR brand ilike per token) — the spike
    measures identification; zip-scoping happens in the real endpoint."""
    tokens = significant_name_tokens(
        " ".join(filter(None, [read.get("producer"), read.get("wine_name")])))
    if not tokens:
        return []
    conds = []
    for t in tokens[:6]:
        conds.append(f"name.ilike.%{t}%")
        conds.append(f"brand.ilike.%{t}%")
    rows = (sb.table("wines")
            .select("id, name, brand, vintage_year, region, varietal")
            .is_("excluded_at", "null")
            .or_(",".join(conds)).limit(120).execute().data or [])
    return rows


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return r.read(), r.headers.get_content_type() or "image/jpeg"


def grade(result, expected_id=None, expected_name=None, in_catalog=True):
    """Map a scan result + ground truth to an outcome bucket."""
    status = result["status"]
    if not in_catalog:
        return "DECLINE" if status in ("unstocked", "not_wine", "unreadable") else "WRONG-CONF"

    def is_expected(wine):
        if wine is None:
            return False
        if expected_id is not None:
            return wine.get("id") == expected_id
        want = set(significant_name_tokens(expected_name or ""))
        have = " ".join(filter(None, [wine.get("name"), wine.get("brand")])).lower()
        return bool(want) and all(t in have for t in want)

    if status in ("exact", "vintage_mismatch"):
        return "TOP1" if is_expected(result.get("wine")) else "WRONG-CONF"
    if status == "candidates":
        return "TOP4" if any(is_expected(c) for c in result["candidates"]) else "MISS"
    return "MISS"  # unstocked/unreadable/not_wine on a stocked bottle


def run_item(sb, model_id, image_bytes, media_type, expected_id=None,
             expected_name=None, in_catalog=True, label=""):
    read, meta = read_label(image_bytes, media_type, model=model_id)
    result = classify_scan(read, fetch_candidates(sb, read) if read else [])
    outcome = grade(result, expected_id, expected_name, in_catalog)
    got = (result.get("wine") or {}).get("name") if result.get("wine") else \
        f"{len(result.get('candidates', []))} candidates" if result["status"] == "candidates" else "-"
    read_str = " / ".join(filter(None, [(read or {}).get("producer"),
                                        (read or {}).get("wine_name"),
                                        (read or {}).get("vintage")])) or "(no read)"
    print(f"  [{outcome:10s}] {result['status']:16s} {meta['latency_s']:5.1f}s"
          f"  {label[:38]:38s} read: {read_str[:44]:44s} -> {got}")
    return outcome, meta


def summarize(model, outcomes, metas):
    n = len(outcomes)
    if not n:
        return
    counts = {k: outcomes.count(k) for k in ("TOP1", "TOP4", "WRONG-CONF", "MISS", "DECLINE")}
    lat = sorted(m["latency_s"] for m in metas)
    tok_in = sum(m["input_tokens"] for m in metas)
    tok_out = sum(m["output_tokens"] for m in metas)
    print(f"\n== {model} over {n} items ==")
    for k, v in counts.items():
        if v:
            print(f"  {k:10s} {v:3d}  ({v / n:.0%})")
    print(f"  latency median {lat[len(lat) // 2]:.1f}s  max {lat[-1]:.1f}s"
          f"  tokens in/out {tok_in}/{tok_out}")


def smoke_items(sb, n, seed):
    """Sample enriched wines that have a Vivino image — expected id is the wine
    itself. Overfetch then sample so reruns vary unless seeded."""
    rows = (sb.table("wines")
            .select("id, name, brand, vintage_year, image_url")
            .is_("excluded_at", "null")
            .not_.is_("image_url", "null")
            .not_.is_("vivino_rating", "null")
            .limit(400).execute().data or [])
    rows = [r for r in rows if (r.get("image_url") or "").startswith("http")]
    random.Random(seed).shuffle(rows)
    return rows[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=int, nargs="?", const=10, default=None,
                    metavar="N", help="run against N catalog (Vivino) images")
    ap.add_argument("--photos", type=str, default=None,
                    metavar="DIR", help="run against real photos + ground_truth.csv")
    ap.add_argument("--model", choices=["haiku", "sonnet", "both"], default="haiku")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if args.smoke is None and args.photos is None:
        ap.error("pick --smoke [N] or --photos DIR")

    sb = get_supabase_client()
    model_ids = [MODELS[m] for m in (["haiku", "sonnet"] if args.model == "both" else [args.model])]

    items = []  # (label, bytes, media_type, expected_id, expected_name, in_catalog)
    if args.smoke is not None:
        for w in smoke_items(sb, args.smoke, args.seed):
            try:
                data, mt = download(w["image_url"])
            except Exception as e:
                print(f"  skip (image fetch failed): {w['name'][:50]} — {e}")
                continue
            items.append((w["name"], data, mt, w["id"], None, True))
    else:
        photo_dir = Path(args.photos)
        gt = photo_dir / "ground_truth.csv"
        assert gt.exists(), f"missing {gt} — see PHOTO-GUIDELINES.md for the format"
        with open(gt, newline="") as f:
            for row in csv.DictReader(f):
                p = photo_dir / row["filename"]
                if not p.exists():
                    print(f"  skip (no file): {row['filename']}")
                    continue
                in_cat = (row.get("in_catalog") or "yes").strip().lower() in ("yes", "y", "true", "1")
                items.append((f"{row['filename']} [{row.get('difficulty', '?')}]",
                              p.read_bytes(), media_type_for(str(p)),
                              None, row.get("expected_wine"), in_cat))

    print(f"{len(items)} items, models: {', '.join(model_ids)}\n")
    for model_id in model_ids:
        print(f"--- {model_id} ---")
        outcomes, metas = [], []
        for label, data, mt, eid, ename, in_cat in items:
            o, m = run_item(sb, model_id, data, mt, eid, ename, in_cat, label)
            outcomes.append(o)
            metas.append(m)
        summarize(model_id, outcomes, metas)


if __name__ == "__main__":
    main()
