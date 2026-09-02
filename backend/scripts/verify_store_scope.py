"""Acceptance: no LIVE store name is reachable by an ordinary chat word.

The unit tests pin the mechanism; this pins the DATA, which the mechanism can't
see. detect_store fuzzy-matches against whatever store names the catalog holds
today, so a newly scraped store ("Four Points", "Lovers Lane", "W.W. White")
can reintroduce the 2026-09-01 Overture bug without a line of code changing:
an ordinary word in a question silently scopes the whole recommendation to one
store, and every answer after that looks perfectly plausible.

Run from backend/:  python3 scripts/verify_store_scope.py
"""
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_supabase_client  # noqa: E402
from recommendation.candidate_filters import (
    _message_tokens, _store_tokens, _STORE_MATCH_CUTOFF, detect_store)

# Ordinary sommelier-chat vocabulary. None of these is anyone naming a store.
CHAT_WORDS = """
do you have carry stock any got the a an is it what that this does want like
with from some good wine red white best under over about tell me more which one
two both please thanks looking bottle budget for and near open tonight dinner
pair goes drink cheap expensive nice better
""".split()


def main() -> int:
    sb = get_supabase_client()
    stores = sb.table("stores").select("name").limit(5000).execute().data or []
    msg_tokens = _message_tokens(" ".join(CHAT_WORDS))

    collisions = {}
    for st in stores:
        for nt in _store_tokens(st.get("name") or ""):
            hit = difflib.get_close_matches(
                nt, msg_tokens, n=1, cutoff=_STORE_MATCH_CUTOFF)
            if hit:
                collisions.setdefault((nt, hit[0]), set()).add(st["name"])

    print(f"scanned {len(stores)} live stores against {len(CHAT_WORDS)} chat words "
          f"(cutoff={_STORE_MATCH_CUTOFF})")
    if collisions:
        print("\nFAIL — ordinary words can scope a real store:")
        for (nt, word), names in sorted(collisions.items(), key=lambda kv: -len(kv[1])):
            print(f"  store token {nt!r} ~ chat word {word!r} → {len(names)} store(s)")
            for n in sorted(names)[:4]:
                print(f"      {n}")
        print("\nFix: add the word to _CHAT_STOPWORDS, or raise _STORE_MATCH_CUTOFF.")
        return 1
    print("OK — no store is reachable by an ordinary chat word")

    # Recall guard: the precision fix must not make stores undetectable. A
    # distinctive token from each store's own name still has to resolve it.
    #
    # One store is knowingly given up: every token of "W.W. White H-E-B" is
    # either too short ('w.w.') or an ordinary wine word ('white'), so keeping
    # it text-detectable would mean letting "a nice white under $20" scope every
    # answer to that shop. It stays reachable through the store picker, which is
    # the reliable path anyway — and since text detection is now only a ranking
    # boost, losing it costs ordering, not inventory.
    ACCEPTED_UNDETECTABLE = {"W.W. White H-E-B"}

    checked = missed = 0
    unexpected = []
    for st in stores:
        toks = [t for t in _store_tokens(st.get("name") or "")
                if t not in _message_tokens(" ".join(CHAT_WORDS))]
        if not toks:
            continue
        checked += 1
        if detect_store(f"anything at {' '.join(toks)}", stores) is None:
            missed += 1
            if st["name"] not in ACCEPTED_UNDETECTABLE:
                unexpected.append((st["name"], toks))
    print(f"{checked - missed}/{checked} stores resolve from their own name "
          f"({len(ACCEPTED_UNDETECTABLE & {s['name'] for s in stores})} knowingly given up)")
    if unexpected:
        print("\nFAIL — precision fix cost recall on stores we did not sign up for:")
        for name, toks in unexpected:
            print(f"  {name!r} unreachable by its own tokens {toks}")
        return 1
    print("OK — no unexpected recall loss")
    return 0


if __name__ == "__main__":
    sys.exit(main())
