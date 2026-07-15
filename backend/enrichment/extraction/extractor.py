"""
Haiku wine-fact extractor. Reads name + retail description, returns structured
facts (region/sub_region/country/vintage/varietal/grapes/abv/body). Grounded by
the reference cheat sheet; appellation->region is fixed deterministically.
"""
import datetime
import anthropic
from typing import List, Dict, Any, Optional
from config import settings
from enrichment.extraction.reference import (
    APPELLATIONS, CHATEAUX, CORE_GRAPES, FEW_SHOT, parent_region_for,
    canonical_region, canonical_country, canonical_grape, country_for_region,
    gazetteer_hit, region_evidenced, country_evidenced, default_grapes_for,
)

MODEL = "claude-haiku-4-5-20251001"
_anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
_BODY_VALUES = {"light", "medium", "full"}

_TOOL = {
    "name": "extract_facts",
    "description": "Return structured wine facts for each input wine.",
    "input_schema": {
        "type": "object",
        "properties": {
            "wines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "wine_id": {"type": "string"},
                        "region": {"type": ["string", "null"]},
                        "sub_region": {"type": ["string", "null"]},
                        "country": {"type": ["string", "null"]},
                        "vintage_year": {"type": ["integer", "null"]},
                        "varietal": {"type": ["string", "null"]},
                        "grapes": {"type": "array", "items": {"type": "string"}},
                        "abv": {"type": ["number", "null"]},
                        "body": {"type": ["string", "null"]},
                    },
                    "required": ["wine_id"],
                },
            },
        },
        "required": ["wines"],
    },
}


_CHATEAUX_PROMPT_LIMIT = 8   # famous names only — the full list lives in the
                             # deterministic gazetteer matcher (reference.py)


def _chateaux_prompt() -> str:
    return "\n".join(
        f"  {app}: {', '.join(names[:_CHATEAUX_PROMPT_LIMIT])}"
        for app, names in CHATEAUX.items()
    )


def _system_prompt() -> str:
    appellations = "\n".join(
        f"  {region}: {', '.join(apps)}" for region, apps in APPELLATIONS.items() if apps
    )
    grapes = "\n".join(f"  {color}: {', '.join(names)}" for color, names in CORE_GRAPES.items())
    examples = "\n".join(
        f'  name="{n}" desc="{d[:80]}" -> {ex}' for n, d, ex in FEW_SHOT
    )
    return (
        "You extract structured facts about a wine from its name and retail description.\n"
        "Return null for any field the name/description does not determine — NEVER invent a "
        "vintage, region, or grape. `grapes` is the full blend (empty list if unknown); "
        "`varietal` is the single primary grape. `body` is exactly one of light|medium|full. "
        "`region` is the broad region and `sub_region` is the specific appellation if named.\n"
        "`country` — ALWAYS fill it when the region, appellation, or country name makes it "
        "clear (Napa/Sonoma/California -> United States; Tuscany/Chianti/Barolo -> Italy; "
        "Rioja -> Spain; Mendoza -> Argentina; Marlborough -> New Zealand; Bordeaux/Burgundy "
        "-> France). Use full country names ('United States', not 'US').\n"
        "For a classic appellation whose grape is fixed by law, give that grape as `varietal` "
        "even if unstated (Chianti/Brunello -> Sangiovese; Barolo/Barbaresco -> Nebbiolo; "
        "Sancerre/Pouilly-Fumé -> Sauvignon Blanc; Rioja red -> Tempranillo; red Burgundy -> "
        "Pinot Noir; Côtes du Rhône -> Grenache).\n"
        "A grape name alone NEVER determines region or country — 'Merlot' does not mean "
        "Bordeaux; a Chilean Merlot is just as likely. No place evidence -> region null. "
        "Brand words are not wine styles: 'Puerto'/'Porto' in a producer name is not Port "
        "wine; 'Rose' in a producer name is not rosé.\n\n"
        "APPELLATION -> REGION reference (if you see the appellation, the region is the group):\n"
        f"{appellations}\n\n"
        "CHÂTEAU -> APPELLATION reference (a producer name places the wine even when no "
        "appellation is stated; all are Bordeaux, France):\n"
        f"{_chateaux_prompt()}\n\n"
        "CORE GRAPES by color (prefer these spellings; other grapes are allowed):\n"
        f"{grapes}\n\n"
        "EXAMPLES:\n"
        f"{examples}"
    )


def _post_process(rec: Dict[str, Any], source_text: Optional[str] = None) -> Dict[str, Any]:
    out = dict(rec)
    # 0. gazetteer + evidence gate (only when the caller passes the wine's
    #    name+description). A producer/château hit fixes the place outright;
    #    otherwise a region/sub_region the source doesn't support is NULLED —
    #    the model free-associates grape→region (Merlot → "Bordeaux"), and an
    #    honest NULL beats a confident hallucination (Vivino can fill it later).
    if source_text:
        hit = gazetteer_hit(source_text)
        if hit:
            if hit["sub_region"]:
                out["sub_region"] = hit["sub_region"]
            elif out.get("sub_region") and \
                    parent_region_for(out["sub_region"]) != hit["region"]:
                # a stale sub_region from another region would drag the
                # region back via the parent lookup below
                out["sub_region"] = None
            out["region"] = hit["region"]
            out["country"] = hit["country"]
        else:
            if out.get("sub_region") and not region_evidenced(out["sub_region"], source_text):
                out["sub_region"] = None
            region_ok = out.get("region") and (
                region_evidenced(out["region"], source_text)
                or (out.get("sub_region")
                    and parent_region_for(out["sub_region"]) == canonical_region(out["region"]))
            )
            if out.get("region") and not region_ok:
                out["region"] = None
            if out.get("country") and not out.get("region") \
                    and not country_evidenced(out["country"], source_text):
                out["country"] = None
    # 1. appellation -> parent region (deterministic, overrides the model)
    parent = parent_region_for(out.get("sub_region"))
    if parent:
        out["region"] = parent
    # 2. region name canonicalization (Toscana -> Tuscany, etc.)
    out["region"] = canonical_region(out.get("region"))
    # 3. grape synonyms -> canonical spelling (Fume Blanc -> Sauvignon Blanc)
    out["varietal"] = canonical_grape(out.get("varietal"))
    out["grapes"] = [canonical_grape(g) for g in (out.get("grapes") or [])]
    # 3b. appellation law -> default blend when the model gave no grapes
    #     (left bank Cab-led, right bank Merlot-led, S. Rhône GSM, Sauternes
    #     Sémillon). Never overwrites model-supplied grapes.
    if not out.get("grapes"):
        blend = default_grapes_for(out.get("sub_region"))
        if blend:
            out["grapes"] = list(blend)
    # 4. country: canonicalize what the model gave, else derive from region
    country = canonical_country(out.get("country"))
    if not country:
        country = country_for_region(out.get("region"))
    out["country"] = country
    # 5. body normalization
    body = (out.get("body") or "").strip().lower()
    out["body"] = body if body in _BODY_VALUES else None
    # 6. vintage range
    vy = out.get("vintage_year")
    next_year = datetime.date.today().year + 1
    if not (isinstance(vy, int) and 1900 <= vy <= next_year):
        out["vintage_year"] = None
    # 7. abv range
    abv = out.get("abv")
    try:
        abv = float(abv)
        out["abv"] = abv if 0 < abv <= 25 else None
    except (TypeError, ValueError):
        out["abv"] = None
    # 8. varietal defaults to first grape
    grapes = out.get("grapes")
    if not out.get("varietal") and grapes:
        out["varietal"] = grapes[0]
    return out


def extract_facts(wines: List[Dict[str, Any]], batch_size: int = 15) -> List[Dict[str, Any]]:
    """Extract structured facts for a list of wine rows. Returns post-processed records."""
    system = _system_prompt()
    results = []
    for i in range(0, len(wines), batch_size):
        batch = wines[i:i + batch_size]
        listing = "\n".join(
            f'- wine_id={w["id"]} | name="{w.get("name","")}" | type={w.get("wine_type")} '
            f'| desc="{(w.get("description") or w.get("description_long") or "")[:400]}"'
            for w in batch
        )
        sources = {w["id"]: f'{w.get("name","")} {w.get("description") or w.get("description_long") or ""}'
                   for w in batch}
        try:
            resp = _anthropic_client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content":
                           "Extract facts for these wines:\n" + listing}],
                tools=[_TOOL],
                tool_choice={"type": "tool", "name": "extract_facts"},
                timeout=60.0,
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            if not block:
                continue
            for rec in block.input.get("wines", []):
                if rec.get("wine_id"):
                    results.append(_post_process(rec, source_text=sources.get(rec["wine_id"])))
        except Exception as e:
            print(f"  extraction batch {i // batch_size} failed: {e}")
    return results
