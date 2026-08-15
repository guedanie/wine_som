"""Report-only detector: wine NAME says one place, region/country fields say another
(roadmap item 42's data-defect follow-up — the Epoch Block B row, fixed by hand in this
same task, is the shape this looks for at scale: 'Epoch Estate Wines Block B Paso Robles
2018' labelled region=Ribeira Sacra/country=Spain).

Per the project's standing conservative-enrichment rule (never auto-correct uncertain
wine data at scale — wrong-and-permanent is the failure mode to avoid), THIS SCRIPT NEVER
WRITES. It only prints a report; a human decides what, if anything, to fix.

Place vocabulary: built from the catalog's own region/sub_region/country columns (a
single pass over `wines`), NOT `recommendation.availability.catalog_terms`. catalog_terms
mixes grape/varietal terms into the same flat set (by design, for its own purpose — free-
text entity matching), and grape words showing up in a wine's own name is normal, not a
place contradiction ("Zinfandel" is not evidence of anything). Restricting the vocabulary
to values that actually appear in region/sub_region/country keeps it place-only, still
catalog-derived (self-updating, no maintenance), and — because both the vocabulary and the
per-row scan come from the same fetched rows — needs only one pass over the table.

Run from backend/ (../.env resolves):
    python3 -m scripts.detect_region_contradictions [--limit N]
"""
import argparse
import os
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Same generic-value stoplist availability.py's catalog_terms uses, so we don't flag a
# name containing a bare "valley"/"other"/"usa"/etc as if it named a real place.
from recommendation.availability import _STOPWORD_TERMS as STOPWORD_TERMS   # noqa: E402
# The grape-name vocabulary (self-updating, same trick as catalog_terms). Needed because
# region/sub_region occasionally holds an extraction error that IS a grape name (e.g. one
# row has sub_region="Aligote" — a grape, not a place); left in, every genuine Aligote-
# named wine downstream gets flagged as a false "region contradiction". Excluding known
# grapes from the place vocabulary is itself catalog/reference-derived, not a hand list.
from enrichment.extraction.reference import KNOWN_GRAPES                    # noqa: E402

# A few wine-classification/quality-tier phrases show up as literal region/sub_region
# column values in this catalog (e.g. region="Burgundy 1er Cru", sub_region="Vieilles
# Vignes") even though they name a quality tier or style, not a place. Left in, they
# flood the report ("1er Cru" alone accounted for ~300 rows) without being genuine
# region/country contradictions. Small and hand-checked against the live data above —
# not a place gazetteer, so it doesn't reintroduce a maintenance burden.
_NON_PLACE_TERMS = {
    "1er cru", "premier cru", "grand cru", "vieilles vignes", "vin de france",
}


def _fold(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def fetch_wines(db, limit: int = 0) -> List[Dict[str, Any]]:
    """All wines, paged by id (same idiom as backfill_wine_type.fetch_null_type_wines)."""
    wines, page, page_size = [], 0, 1000
    while True:
        rows = (db.table("wines")
                .select("id,name,region,sub_region,country")
                .order("id")
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute().data or [])
        wines.extend(rows)
        page += 1
        if len(rows) < page_size or (limit and len(wines) >= limit):
            break
    if limit:
        wines = wines[:limit]
    return wines


def build_place_vocab(wines: List[Dict[str, Any]]) -> set:
    """Folded place terms drawn from the wines' own region/sub_region/country values."""
    terms = set()
    for w in wines:
        for raw in (w.get("region"), w.get("sub_region"), w.get("country")):
            v = _fold(raw)
            if (v and v not in STOPWORD_TERMS and v not in _NON_PLACE_TERMS
                    and v not in KNOWN_GRAPES and len(v) > 2):
                terms.add(v)
    return terms


def own_place_text(w: Dict[str, Any]) -> str:
    """The row's own region/sub_region/country, folded and joined. A name match is
    agreement (not a contradiction) if the term also appears ANYWHERE in this text —
    substring/word-boundary, not exact-value equality, so 'California' inside a
    sub_region of 'Lodi, California' still counts as agreement."""
    return _fold(" ".join(str(w.get(k) or "") for k in ("region", "sub_region", "country")))


def compile_vocab_pattern(vocab: set) -> Optional[re.Pattern]:
    """One alternation regex over the whole vocabulary, longest term first (so 'Paso
    Robles' wins over a shorter overlapping hit) — compiled once, not per row. Naive
    per-term-per-row compilation is O(rows x vocab) and takes minutes at catalog scale;
    this is a single O(rows) scan with a precompiled pattern."""
    if not vocab:
        return None
    alt = "|".join(re.escape(t) for t in sorted(vocab, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alt + r")(?!\w)")


def find_contradiction(w: Dict[str, Any], pattern: re.Pattern) -> Optional[str]:
    """The longest catalog place term found (whole-word, folded) in the wine's NAME that
    is absent from that row's own region/sub_region/country text — or None."""
    name = _fold(w.get("name"))
    if not name:
        return None
    own_text = own_place_text(w)
    for m in pattern.finditer(name):
        t = m.group(0)
        if not re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", own_text):
            return t
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                     help="scan only the first N wines (id order) — for spot-checking")
    args = ap.parse_args()

    from db import get_service_client
    db = get_service_client()

    wines = fetch_wines(db, limit=args.limit)
    print(f"examining {len(wines)} wines", flush=True)

    vocab = build_place_vocab(wines)
    print(f"place vocabulary: {len(vocab)} terms (from region/sub_region/country)", flush=True)
    pattern = compile_vocab_pattern(vocab)

    flagged = []
    if pattern:
        for w in wines:
            place = find_contradiction(w, pattern)
            if place:
                flagged.append((w, place))

    for w, place in sorted(flagged, key=lambda x: (x[1], x[0].get("name") or "")):
        name = (w.get("name") or "")[:60]
        region = w.get("region") or "NULL"
        country = w.get("country") or "NULL"
        print(f"{name} | {region} | {country} | {place}", flush=True)

    print(f"\ntotal contradictions: {len(flagged)} of {len(wines)} wines scanned", flush=True)


if __name__ == "__main__":
    main()
