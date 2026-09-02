"""Pure candidate-shaping helpers for the recommend endpoint: NULL wine_type
resolution + hard type gate, fuzzy store detection, and candidate merge/dedup.
Kept free of I/O so they unit-test without a DB (the router wires them)."""
import difflib
import re
import unicodedata
from typing import Any, Dict, List, Optional

from utils import infer_wine_type

# Generic wine words that don't identify a specific bottle — dropped when
# tokenizing a wine name for name search / narrative reconcile.
_GENERIC_WINE_WORDS = {
    "cabernet", "sauvignon", "merlot", "pinot", "noir", "gris", "grigio", "chardonnay",
    "syrah", "shiraz", "zinfandel", "malbec", "tempranillo", "sangiovese", "nebbiolo",
    "grenache", "mourvedre", "carignan", "riesling", "blanc", "chenin", "viognier",
    "barbera", "tannat", "red", "white", "rose", "wine", "blend", "reserve", "reserva",
    "vineyard", "vineyards", "valley", "county", "napa", "sonoma", "paso", "robles",
    "california", "italian", "the", "and", "estate", "old", "vine", "vines", "cuvee",
}


def significant_name_tokens(name: Optional[str]) -> List[str]:
    """Lowercased 3+ char tokens of a wine name, minus generic varietal/geo words —
    the distinctive producer/bottle tokens to search or reconcile on."""
    return [t for t in re.findall(r"[a-z0-9é]{3,}", (name or "").lower())
            if t not in _GENERIC_WINE_WORDS]


def rank_name_matches(candidates: List[Dict[str, Any]],
                      tokens: List[str]) -> List[Dict[str, Any]]:
    """Keep candidates whose name contains at least one search token, ordered by
    how many tokens matched (all-token matches first). Empty tokens → []."""
    if not tokens:
        return []
    scored = []
    for c in candidates:
        name = (c.get("name") or "").lower()
        hits = sum(1 for t in tokens if t in name)
        if hits:
            scored.append((hits, c))
    scored.sort(key=lambda hc: hc[0], reverse=True)
    return [c for _, c in scored]


def _cand_grapes(c: Dict[str, Any]) -> set:
    g = {str(x).lower() for x in (c.get("grapes") or [])}
    if c.get("varietal"):
        g.add(str(c["varietal"]).lower())
    return g


def deep_fetch_reason(intent: Dict[str, Any],
                      top: List[Dict[str, Any]]) -> Optional[str]:
    """Return "named" if the user named a specific bottle, else "weak" if the
    user expressed a concrete constraint (grape/region/wine_type) that NONE of the
    selected top candidates satisfies, else None. Named always wins."""
    names = intent.get("wine_names") or (
        [intent["wine_name"]] if intent.get("wine_name") else [])
    if any(significant_name_tokens(n) for n in names):
        return "named"

    want_grapes = {str(g).lower() for g in (intent.get("grapes") or [])}
    want_region = (intent.get("region") or "").strip().lower()
    want_type = intent.get("wine_type")
    if not want_grapes and not want_region and not want_type:
        return None

    for c in top:
        if want_grapes and (want_grapes & _cand_grapes(c)):
            return None
        region = (c.get("region") or "").lower()
        if want_region and region and (want_region in region or region in want_region):
            return None
        if want_type and c.get("wine_type") == want_type:
            return None
    return "weak"


def pin_named_matches(top: List[Dict[str, Any]],
                      named: List[Dict[str, Any]],
                      cap: int = 3) -> List[Dict[str, Any]]:
    """Put named-bottle matches at the front of `top`, deduped by wine_id (keeping
    the cheapest row per wine), capped at `cap`. Scored candidates follow, minus any
    now pinned. `named` is assumed already relevance-ordered (rank_name_matches)."""
    if not named:
        return top
    best_by_wine: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for c in named:
        wid = c.get("wine_id")
        prev = best_by_wine.get(wid)
        if prev is None:
            best_by_wine[wid] = c
            order.append(wid)
        elif (c.get("price") or float("inf")) < (prev.get("price") or float("inf")):
            best_by_wine[wid] = c
    pinned = [best_by_wine[w] for w in order][:cap]
    pinned_ids = {w.get("wine_id") for w in pinned}
    rest = [w for w in top if w.get("wine_id") not in pinned_ids]
    return pinned + rest


def pin_comparison_matches(top: List[Dict[str, Any]],
                           named_lists: List[List[Dict[str, Any]]],
                           cap_per_name: int = 2) -> List[Dict[str, Any]]:
    """Pin each compared bottle's best matches to the front, first-named bottle
    first — a two-bottle comparison must surface BOTH. Reuses pin_named_matches,
    applied in reverse so earlier names land ahead of later ones."""
    out = top
    for named in reversed([nl for nl in named_lists if nl]):
        out = pin_named_matches(out, named, cap=cap_per_name)
    return out


def resolve_wine_type(wine: Dict[str, Any]) -> Optional[str]:
    """Return the wine's type, inferring from varietal -> name -> first grape
    when the stored wine_type is NULL. None only when nothing resolves."""
    if wine.get("wine_type"):
        return wine["wine_type"]
    for text in (wine.get("varietal"), wine.get("name"),
                 (wine.get("grapes") or [None])[0]):
        if text:
            t = infer_wine_type(text)
            if t:
                return t
    return None


def apply_type_gate(candidates: List[Dict[str, Any]],
                    requested_types: set) -> List[Dict[str, Any]]:
    """Resolve each candidate's NULL wine_type (written back in place), then, when
    the user requested one or more types, drop candidates whose resolved type is
    KNOWN and not requested. Unresolvable (None) types are kept — benefit of the
    doubt. Fails open (returns the input) if the gate would empty the pool."""
    for c in candidates:
        if not c.get("wine_type"):
            c["wine_type"] = resolve_wine_type(c)
    if not requested_types:
        return candidates
    kept = [c for c in candidates
            if c.get("wine_type") is None or c["wine_type"] in requested_types]
    return kept or candidates


def requested_types_from(chip_types: Optional[List[str]],
                         parsed_type: Optional[str]) -> set:
    """The set of wine types the user explicitly asked for — UI chips plus the
    parsed message intent. 'dessert' also accepts 'fortified' (the intent enum
    has no fortified value, so Port/Sherry — typed fortified — surface under a
    dessert/after-dinner ask). One-directional."""
    types = set(t for t in (chip_types or []) if t)
    if parsed_type:
        types.add(parsed_type)
    if "dessert" in types:
        types.add("fortified")
    return types


# Generic tokens that don't distinguish one store from another.
_STORE_STOPWORDS = {
    "the", "and", "wine", "wines", "market", "shop", "store", "plus",
    "natural", "heb", "h-e-b", "heb's", "central",
    # geographic / descriptor words that also appear in wine names & regions —
    # too generic to distinguish a store, and prone to false fuzzy matches
    "heights", "oak", "oaks", "valley", "park", "hill", "hills", "creek",
    "ridge", "coast", "river", "springs", "grove", "lake", "mountain",
    "village", "canyon", "vista", "view",
}


def _store_tokens(s: str) -> List[str]:
    words = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()
    return [w for w in words if len(w) > 2 and w not in _STORE_STOPWORDS]


# 0.80 let ordinary words impersonate store tokens: 'ave'~'have' scores .857,
# 'san'~'an'/'four'~'for'/'lovers'~'over'/'monroe'~'more' all score .800. On the
# live catalog that made 12 of 145 stores reachable by a word like "an" or
# "have". Measured on real store names, every false positive sits at or below
# .857 while genuine matches — including the 'lincon'→'lincoln' typo this
# tolerance exists for (.923) — sit at or above .923, so .90 separates them.
_STORE_MATCH_CUTOFF = 0.90

# Ordinary conversation and wine vocabulary. Dropped from the MESSAGE side only:
# a store name may legitimately contain one of these ("W.W. White H-E-B"), but a
# user typing it is almost never naming a store, and an EXACT collision survives
# the cutoff above. Same remedy as item 42's producer-token stopwords, which hit
# this class when "close" matched the producer "Closerie".
_CHAT_STOPWORDS = {
    "any", "anything", "some", "something", "have", "has", "had", "get", "got",
    "carry", "carries", "stock", "want", "need", "like", "likes", "looking",
    "look", "find", "show", "tell", "give", "recommend", "suggest", "about",
    "more", "most", "over", "under", "for", "but", "this", "that", "these",
    "those", "there", "here", "what", "which", "who", "when", "where", "why",
    "how", "does", "did", "was", "were", "are", "been", "with", "from", "into",
    "than", "then", "they", "them", "your", "you", "mine", "one", "two", "all",
    "can", "could", "would", "should", "will", "just", "only", "also", "very",
    "really", "good", "best", "better", "nice", "please", "thanks", "bottle",
    "red", "white", "rose", "price", "budget", "cheap", "expensive", "pair",
    "pairs", "goes", "buy", "drink", "open", "night", "dinner",
}


def _message_tokens(s: str) -> List[str]:
    """Store-name tokens minus ordinary chat words — the message side of the
    match, where an everyday word must never stand in for a store token."""
    return [w for w in _store_tokens(s) if w not in _CHAT_STOPWORDS]


def detect_store(message: str, nearby_stores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Fuzzy-match a store named in the message against the nearby stores.
    Tolerates typos ('lincon'); returns None when no distinctive store token
    matches (e.g. only the retailer word 'heb' appears)."""
    msg = _message_tokens(message)
    if not msg:
        return None
    best, best_score = None, 0
    for st in nearby_stores:
        name_toks = _store_tokens(st.get("name", ""))
        score = sum(1 for nt in name_toks
                    if difflib.get_close_matches(nt, msg, n=1, cutoff=_STORE_MATCH_CUTOFF))
        # strict > keeps the first (nearest, since nearby_stores is distance-ordered) on ties
        if score > best_score:
            best, best_score = st, score
    return best if best_score >= 1 else None


# item 41: a follow-up like "compare these two" names nothing the parser can
# extract — the referents live in the conversation's own prior picks. These
# helpers carry them: extract from history, detect the anaphora, pin.

def prior_picks_from_history(history) -> List[Dict[str, Any]]:
    """Ordered, deduped {wine_id, name} from the picks attached to sommelier
    turns in conversation_history. Empty when the client sent prose-only."""
    seen, out = set(), []
    for turn in history or []:
        for p in turn.get("picks") or []:
            wid = p.get("wine_id")
            if wid and wid not in seen:
                seen.add(wid)
                out.append({"wine_id": wid, "name": p.get("name")})
    return out


# Conservative on purpose: a false positive pins wines the user didn't mean
# (mild — they were just shown), a false negative reproduces bug 41.
_REFERENTIAL_PAT = re.compile(
    r"\b(these|those|them|both|either|neither|that one|"
    r"(the )?(first|second|third|last) one|"
    r"which (one|of th|of the|do you|would you))\b", re.I)


def is_referential(message: Optional[str]) -> bool:
    """True when the message points back at previously shown wines
    ("these two", "the first one") rather than naming anything."""
    return bool(_REFERENTIAL_PAT.search(message or ""))


def pin_prior_picks(top: List[Dict[str, Any]], prior_cands: List[Dict[str, Any]],
                    ordered_ids: List[str], cap: int = 4) -> List[Dict[str, Any]]:
    """Pin previously recommended wines to the shortlist front, in the order
    they appeared in the conversation (cheapest row per wine). A comparison
    must never lose its subjects."""
    by_id: Dict[Any, List[Dict[str, Any]]] = {}
    for c in prior_cands:
        by_id.setdefault(c.get("wine_id"), []).append(c)
    ordered = [c for wid in ordered_ids for c in by_id.get(wid, [])]
    return pin_named_matches(top, ordered, cap=cap)


def resolve_store_scope(store_ref: Optional[str],
                        stores: List[Dict[str, Any]],
                        message: Optional[str]):
    """Split the store scope into (standing, mentioned) — two different claims
    that used to be one value, which is how a fuzzy guess inherited a hard
    filter's authority.

    standing: a structured store_ref from the aisle store picker. The user is
        physically in that building, which is what licenses item 44's HARD
        filter — a bottle on another store's shelf is useless to them.
    mentioned: a store name recovered from free text. This is a GUESS. It may
        scope a targeted fetch and boost ranking, but it must never delete the
        rest of the catalog: when detect_store misfired on 'have'~'Ave' the
        hard filter turned that into a confident "we don't carry Overture"
        while six bottles sat in nearby stores.

    A store_ref that isn't among the NEARBY stores is a stale pick carried over
    from another zip — ignored, then free text gets its turn.
    """
    if store_ref:
        for st in stores:
            if st.get("id") == store_ref:
                return st, None
    return None, detect_store(message or "", stores)


def filter_to_store(candidates: List[Dict[str, Any]],
                    store_id: Optional[str]) -> List[Dict[str, Any]]:
    """Keep only rows on the given store's shelves — the aisle-mode HARD filter
    (item 44). A wine exclusive to another store must never surface to someone
    standing in this one. No-op on a falsy store_id. An empty result is the
    honest 'this store has nothing' signal — the caller must NOT silently widen."""
    if not store_id:
        return candidates
    return [c for c in candidates if c.get("store_ref") == store_id]


def merge_candidates(breadth: List[Dict[str, Any]],
                     targeted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Union breadth + targeted candidate dicts, deduped by (wine_id, store_ref)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in list(breadth) + list(targeted):
        key = (c.get("wine_id"), c.get("store_ref"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _norm_place(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def _cand_in_place(cand: Dict[str, Any], nr: str) -> bool:
    reg = _norm_place(cand.get("region"))
    ctry = _norm_place(cand.get("country"))
    return bool((reg and (nr in reg or reg in nr)) or (ctry and (nr in ctry or ctry in nr)))


def ensure_region_representation(top: List[Dict[str, Any]], scored: List[Dict[str, Any]],
                                 regions: List[str], max_candidates: int) -> List[Dict[str, Any]]:
    """For a 2+ place comparison, guarantee `top` contains >=1 candidate per named place.
    Pins each missing place's best-scoring candidate from `scored` (score-sorted desc);
    pinned candidates survive the `max_candidates` cap, the rest fill by score. No-op for
    <2 regions."""
    norm_regions = [_norm_place(r) for r in regions if r]
    if len(norm_regions) < 2:
        return top

    def key(c):
        return (c.get("wine_id"), c.get("store_ref"))

    present_ids = {key(c) for c in top}
    pinned: List[Dict[str, Any]] = []
    for nr in norm_regions:
        if any(_cand_in_place(c, nr) for c in top) or any(_cand_in_place(p, nr) for p in pinned):
            continue
        best = next((c for c in scored
                     if _cand_in_place(c, nr) and key(c) not in present_ids), None)
        if best is not None:
            pinned.append(best)
            present_ids.add(key(best))
    if not pinned:
        return top

    pinned_ids = {key(p) for p in pinned}
    others = [c for c in top if key(c) not in pinned_ids]
    others.sort(key=lambda c: c.get("_score", 0), reverse=True)
    return (pinned + others)[:max_candidates]


# Retailer shorthands → canonical name. Keyed on the fully-normalized token
# (lowercase, punctuation stripped) so 'heb'/'HEB'/'h-e-b'/'h.e.b' all become 'heb'.
# Only applied when the canonical target is actually nearby. The alias map is
# REQUIRED for H-E-B: its name tokenizes to h/e/b, which no fuzzy match can catch.
_RETAILER_ALIASES = {
    "heb": "H-E-B", "specs": "Spec's", "spec": "Spec's",
    "cm": "Central Market", "twin": "Twin Liquors", "ht": "Harris Teeter",
    "geraldines": "Geraldine's", "geraldine": "Geraldine's", "pogos": "Pogo's",
}
# Generic words dropped from a retailer NAME's distinctive tokens.
_RETAILER_GENERIC = {"the", "wine", "wines", "market", "shop", "store", "liquors",
                     "liquor", "selections", "natural", "co", "company", "and"}


def _norm_retailer(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _retailer_name_tokens(name: str) -> List[str]:
    """Distinctive normalized tokens of a retailer name (generic words dropped)."""
    raw = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    return [_norm_retailer(t) for t in raw if t not in _RETAILER_GENERIC and _norm_retailer(t)]


def detect_retailer(message: str, nearby_retailers: List[str]) -> Optional[str]:
    """Return the canonical nearby retailer named in the message, or None. Matches
    case/punctuation-insensitively (heb/HEB/h-e-b/h.e.b → H-E-B) via an alias map,
    then falls back to fuzzy token match against the nearby retailer names. Only ever
    returns a retailer present in `nearby_retailers`."""
    if not message or not nearby_retailers:
        return None
    nearby_set = set(nearby_retailers)
    msg_tokens = [t for t in (_norm_retailer(w) for w in message.split()) if t]
    if not msg_tokens:
        return None
    # 1) alias hit (whole-token match; only if the target is nearby)
    for t in msg_tokens:
        target = _RETAILER_ALIASES.get(t)
        if target and target in nearby_set:
            return target
    # 2) fuzzy match distinctive tokens of each nearby retailer name
    best, best_score = None, 0
    for r in nearby_retailers:
        name_toks = _retailer_name_tokens(r)
        if not name_toks:
            continue
        score = sum(1 for nt in name_toks
                    if difflib.get_close_matches(nt, msg_tokens, n=1, cutoff=0.8))
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 1 else None
