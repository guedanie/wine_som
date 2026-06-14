"""
Effectiveness eval — step 2: read the labeled CSV, compute metrics, write a report.

  cd backend && python3 -m enrichment.matching.eval.run_eval

Reads  enrichment/matching/eval/eval_candidates.csv  (with `correct` filled)
Writes enrichment/matching/eval/eval_report.md
"""
import csv
from collections import defaultdict
from pathlib import Path
from typing import List, Dict

OUT_DIR = Path(__file__).parent


def _bucket(conf: float) -> str:
    if conf >= 0.8:
        return ">=0.8"
    if conf >= 0.5:
        return "0.5-0.8"
    return "<0.5"


def compute_metrics(rows: List[Dict]) -> dict:
    """Aggregate labeled candidate rows into coverage / precision@1 / recall / calibration."""
    by_wine = defaultdict(list)
    for r in rows:
        by_wine[r["wine_id"]].append(r)

    def _is_true(v):
        return str(v).strip() == "1"

    def _is_primary(v):
        return str(v).strip().lower() in ("true", "1")

    def metrics_for(wine_ids):
        n = len(wine_ids)
        covered = p1_hits = recall_hits = 0
        buckets = defaultdict(lambda: [0, 0])  # bucket -> [hits, total]
        for wid in wine_ids:
            cands = by_wine[wid]
            correct_rows = [c for c in cands if _is_true(c.get("correct"))]
            primary = next((c for c in cands if _is_primary(c.get("is_primary"))), None)
            if correct_rows:
                covered += 1
                if any(_is_primary(c.get("is_primary")) for c in correct_rows):
                    p1_hits += 1
                recall_hits += 1
            if primary and primary.get("confidence"):
                b = _bucket(float(primary["confidence"]))
                buckets[b][1] += 1
                if any(_is_primary(c.get("is_primary")) for c in correct_rows):
                    buckets[b][0] += 1
        return {
            "n_wines": n,
            "coverage": round(covered / n, 3) if n else 0.0,
            "precision_at_1": round(p1_hits / covered, 3) if covered else 0.0,
            "top3_recall": round(recall_hits / covered, 3) if covered else 0.0,
            "calibration": {b: {"correct": h, "total": t, "rate": round(h / t, 3) if t else 0.0}
                            for b, (h, t) in sorted(buckets.items())},
        }

    all_ids = list(by_wine.keys())
    result = {"overall": metrics_for(all_ids)}
    by_source = defaultdict(list)
    for wid, cands in by_wine.items():
        by_source[cands[0].get("source", "?")].append(wid)
    result["by_retailer"] = {src: metrics_for(ids) for src, ids in by_source.items()}
    return result


def _format_report(m: dict) -> str:
    lines = ["# GrapeMinds Matching — Effectiveness Report", ""]
    for scope, data in [("Overall", m["overall"])] + list(m["by_retailer"].items()):
        lines.append(f"## {scope}")
        lines.append(f"- wines: {data['n_wines']}")
        lines.append(f"- coverage: {data['coverage']}")
        lines.append(f"- precision@1: {data['precision_at_1']}")
        lines.append(f"- top-3 recall: {data['top3_recall']}")
        lines.append("- calibration (primary confidence bucket -> correctness):")
        for b, c in data["calibration"].items():
            lines.append(f"    {b}: {c['correct']}/{c['total']} = {c['rate']}")
        lines.append("")
    return "\n".join(lines)


def main():
    csv_path = OUT_DIR / "eval_candidates.csv"
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    m = compute_metrics(rows)
    (OUT_DIR / "eval_report.md").write_text(_format_report(m))
    print(_format_report(m))


if __name__ == "__main__":
    main()
