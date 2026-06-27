"""
Latency + consistency benchmark for /api/recommend.
Usage: python3 scripts/benchmark_recommend.py [--runs N] [--url URL]
"""
import argparse
import json
import time
import urllib.request
import urllib.error
from collections import Counter

PAYLOAD = {
    "zip_code": "78209",
    "budget_min": 15,
    "budget_max": 60,
    "style_preferences": ["bold", "tannic"],
    "wine_types": ["Red"],
    "grapes": [],
    "avoid": [],
    "message": "Recommend wines based on my preferences",
}

def call(url: str) -> tuple:
    """Return (elapsed_ms, picks_list) or raise."""
    body = json.dumps(PAYLOAD).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    elapsed = (time.perf_counter() - t0) * 1000
    picks = [p["wine_id"] for p in data.get("picks", [])]
    return elapsed, picks, data.get("picks", [])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--url", default="http://localhost:8000/api/recommend")
    args = parser.parse_args()

    print(f"Benchmarking {args.url}  ({args.runs} runs)\n")
    print(f"Request payload: Red wine · $15-60 · bold+tannic · zip 78209\n")
    print("-" * 60)

    latencies = []
    all_picks = []   # list of frozenset per run
    pick_names = []  # list of name lists per run

    for i in range(args.runs):
        try:
            ms, picks, raw_picks = call(args.url)
            latencies.append(ms)
            all_picks.append(frozenset(picks))
            pick_names.append([p["name"] for p in raw_picks])
            print(f"Run {i+1:2d}: {ms:7.0f} ms  |  {len(picks)} picks  |  {', '.join(p['name'][:28] for p in raw_picks)}")
        except Exception as e:
            print(f"Run {i+1:2d}: ERROR — {e}")

    if not latencies:
        print("\nNo successful runs.")
        return

    print("\n" + "=" * 60)
    print("LATENCY")
    print(f"  Min  : {min(latencies):.0f} ms")
    print(f"  Max  : {max(latencies):.0f} ms")
    print(f"  Avg  : {sum(latencies)/len(latencies):.0f} ms")
    med = sorted(latencies)[len(latencies)//2]
    print(f"  Median: {med:.0f} ms")

    print("\nCONSISTENCY")
    # Overlap: what fraction of wines appear in >50% of runs?
    wine_counter = Counter()
    for s in all_picks:
        for wid in s:
            wine_counter[wid] += 1
    threshold = len(latencies) / 2
    stable = {wid for wid, cnt in wine_counter.items() if cnt > threshold}
    total_unique = len(wine_counter)
    print(f"  Unique wines seen across all runs: {total_unique}")
    print(f"  Wines appearing in >50% of runs  : {len(stable)}")
    if all_picks:
        avg_set = sum(len(s) for s in all_picks) / len(all_picks)
        avg_overlap = sum(len(s & all_picks[0]) for s in all_picks[1:]) / max(len(all_picks)-1,1)
        print(f"  Avg picks per run               : {avg_set:.1f}")
        print(f"  Avg overlap with run 1          : {avg_overlap:.1f} wines")

    # Show per-run name lists for qualitative comparison
    print("\nPICK NAMES PER RUN")
    for i, names in enumerate(pick_names, 1):
        print(f"  Run {i}: {', '.join(names)}")

if __name__ == "__main__":
    main()
