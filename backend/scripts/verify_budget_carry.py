"""Acceptance replay for multi-turn budget state (spoken budget persists + widens).

Drives a LOCAL server over HTTP (not a DB-only replay like verify_referent_carry
or verify_store_filter) because the behavior under test is the SSE `budget` frame
itself — a real Sonnet call has to run for the frame to be emitted and for the
widen re-fetch to actually execute.

Three turns, replaying exactly what the client is expected to send:

  1. "I'm looking for a bottle of red, my budget is $60" with budget_max=10000
     (the ASK-mode wide sentinel — no budget stated yet on the request). A
     `budget` SSE frame must arrive with max == 60.0, and every pick must be
     <= $60.

  2. "Do you carry Overture?" with the carried budget_max=60 (what the client
     echoes next turn) plus turn-1 history. Overture is stocked near 78258 at
     roughly $195-$225 (Opus One's second label) — well outside the $60
     budget. Overture must NOT appear in picks.

     *** THIS IS A DELIBERATE BEHAVIOR REVERSAL, NOT A BUG. *** Before this
     work, turn 2 surfaced Overture despite the stated $60 budget. The
     correct behavior, per the availability oracle (items 39/40), is to
     report it as available-but-out-of-budget ("we carry it, but it runs
     ~$200 — over your $60") rather than either (a) silently recommending a
     $200 bottle against a $60 budget, or (b) denying it exists. If a future
     change makes this assertion fail because Overture is back in picks,
     that is a regression to fix, not a reason to loosen this script.

  3. "actually, let's splurge — up to $250" from a carried budget_max=60. A
     `budget` frame must arrive with max == 250.0, and at least one pick must
     be priced over $60 — proving the widen re-fetch actually pulled in the
     newly-affordable band. Without the re-fetch, the candidate pool is still
     capped at the old $60 ceiling and nothing above it can appear no matter
     what the narrative claims.

Run against a locally running server (NOT prod — this burns real Sonnet calls
and the 15/hr/IP rate limit):

    cd backend
    /usr/bin/python3 -m uvicorn api.main:app --port 8077 &
    /usr/bin/python3 -m scripts.verify_budget_carry
    pkill -f "uvicorn api.main:app --port 8077"
"""
import json
import urllib.request

BASE = "http://127.0.0.1:8077"
ZIP = "78258"


def stream(message, budget_max, history=None, timeout=120):
    """POST to /api/recommend and collect narrative text, final picks, and
    the budget frame (or None if the turn never spoke a budget)."""
    payload = {
        "zip_code": ZIP,
        "budget_min": 10.0,
        "budget_max": float(budget_max),
        "message": message,
    }
    if history:
        payload["conversation_history"] = history
        payload["conversational"] = True
    req = urllib.request.Request(
        f"{BASE}/api/recommend", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    narrative, picks, budget_frame = [], [], None
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
            t = ev.get("type")
            if t == "token":
                narrative.append(ev.get("text", ""))
            elif t == "picks":
                picks = ev.get("picks") or []
            elif t == "budget":
                budget_frame = {"min": ev.get("min"), "max": ev.get("max")}
    return "".join(narrative), picks, budget_frame


def main():
    print(f"=== TURN 1: stated budget $60 (request budget_max=10000, the ASK sentinel) ===")
    narrative1, picks1, budget1 = stream(
        "I'm looking for a bottle of red, my budget is $60", budget_max=10000)
    print(f"BUDGET FRAME | {budget1}")
    for p in picks1:
        print(f"PICK | {p['name'][:50]:50s} ${p['price']}")
    assert budget1 is not None, "expected a `budget` SSE frame on turn 1 (none arrived)"
    assert budget1["max"] == 60.0, f"expected budget frame max == 60.0, got {budget1}"
    over1 = [p for p in picks1 if p["price"] > 60.0]
    assert not over1, f"pick(s) over $60 on turn 1: {[(p['name'], p['price']) for p in over1]}"
    print("OK — budget frame max=60.0, every pick <= $60\n")

    print("=== TURN 2: 'Do you carry Overture?' with carried budget_max=60 ===")
    history = [
        {"role": "user", "content": "I'm looking for a bottle of red, my budget is $60"},
        {"role": "sommelier", "content": narrative1, "picks": picks1},
    ]
    narrative2, picks2, _budget2 = stream(
        "Do you carry Overture?", budget_max=60, history=history)
    print(f"NARRATIVE | {narrative2}")
    for p in picks2:
        print(f"PICK | {p['name'][:50]:50s} ${p['price']}")
    overture_picks = [p for p in picks2 if "overture" in p["name"].lower()]
    assert not overture_picks, (
        f"Overture leaked into picks despite being ~$200 over a $60 budget: "
        f"{[(p['name'], p['price']) for p in overture_picks]}")
    print("OK — Overture withheld from picks (reversal from pre-work behavior)")
    print("     Read the narrative above by hand: it should say Overture IS carried "
          "but runs well over $60 (~$195-$225), not that it doesn't exist.\n")

    print("=== TURN 3: 'let's splurge — up to $250' from carried budget_max=60 ===")
    history2 = history + [
        {"role": "user", "content": "Do you carry Overture?"},
        {"role": "sommelier", "content": narrative2, "picks": picks2},
    ]
    narrative3, picks3, budget3 = stream(
        "actually, let's splurge — up to $250", budget_max=60, history=history2)
    print(f"BUDGET FRAME | {budget3}")
    for p in picks3:
        print(f"PICK | {p['name'][:50]:50s} ${p['price']}")
    assert budget3 is not None, "expected a `budget` SSE frame on turn 3 (none arrived)"
    assert budget3["max"] == 250.0, f"expected budget frame max == 250.0, got {budget3}"
    over60 = [p for p in picks3 if p["price"] > 60.0]
    assert over60, "no pick above $60 on turn 3 — the widen re-fetch did not run"
    print(f"OK — budget frame max=250.0, {len(over60)} pick(s) above $60 "
          f"(proves the widen re-fetch pulled in the new price band)\n")

    print("ALL THREE TURNS PASSED")


if __name__ == "__main__":
    main()
