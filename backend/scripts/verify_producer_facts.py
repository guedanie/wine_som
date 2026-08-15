"""Acceptance check for the producer-facts lookup (roadmap item 42, Task 2's
`recommendation/producer_facts.py`), run against the live catalog:

  1. "close to epoch in style" resolves to a Paso Robles fact, NOT Texas Hill Country
     — this is the exact hallucination repro from the roadmap item.
  2. "Caymus" resolves to Napa Valley.
  3. A generic message with no producer-shaped token yields no facts.

Prints PASS/FAIL per case and exits non-zero on any failure.

Run from backend/ (../.env resolves):
    python3 -m scripts.verify_producer_facts
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_service_client                       # noqa: E402
from recommendation.producer_facts import fetch_producer_facts  # noqa: E402


def _regions(facts):
    out = set()
    for f in facts:
        for r, _n in (f.get("regions") or []):
            out.add(r)
    return out


def main() -> None:
    db = get_service_client()
    failures = 0

    # Case 1: the actual repro message from the roadmap item.
    msg = "Looking for something from willow creek - close to epoch in style"
    facts = fetch_producer_facts(db, msg)
    regions = _regions(facts)
    print(f"[epoch] message={msg!r}")
    print(f"[epoch] facts={facts}")
    ok = ("Paso Robles" in regions) and not any("Texas" in r for r in regions)
    print(f"[epoch] {'PASS' if ok else 'FAIL'} — expected Paso Robles, not Texas Hill Country")
    failures += 0 if ok else 1

    # Case 2: Caymus -> Napa Valley.
    msg2 = "Do you have anything from Caymus?"
    facts2 = fetch_producer_facts(db, msg2)
    regions2 = _regions(facts2)
    print(f"\n[caymus] message={msg2!r}")
    print(f"[caymus] facts={facts2}")
    ok2 = "Napa Valley" in regions2
    print(f"[caymus] {'PASS' if ok2 else 'FAIL'} — expected Napa Valley")
    failures += 0 if ok2 else 1

    # Case 3: a generic message shouldn't produce a bogus producer fact.
    msg3 = "I'd like something bold and fruity for a weeknight dinner, nothing too expensive."
    facts3 = fetch_producer_facts(db, msg3)
    print(f"\n[generic] message={msg3!r}")
    print(f"[generic] facts={facts3}")
    ok3 = facts3 == []
    print(f"[generic] {'PASS' if ok3 else 'FAIL'} — expected no facts")
    failures += 0 if ok3 else 1

    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
