"""LLM structure/sweetness pass (CLAUDE.md item 12).

Two eligibility classes, one qwen2.5:7b pass on the mini:
1. SWEETNESS FILL — a wine has a structure_profile with no `sweetness`. The LLM
   value is MERGED into the existing profile (body/tannins/acidity untouched).
2. UNANCHORED BLEND — a wine has grape data the table can't anchor
   (structure_for -> None) and no profile. The LLM writes the FULL profile.

Run from backend/ on the mini:
    python3 -m scripts.backfill_structure_llm [--dry-run] [--limit N]
"""
import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recommendation.structure_profiles import structure_for               # noqa: E402
from enrichment.extraction.structure_benchmark import _SYSTEM, OLLAMA_URL  # noqa: E402
from scripts.backfill_wine_type import _is_non_wine                        # noqa: E402

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def is_non_wine_row(row) -> bool:
    """True when the row's name marks non-grape-wine catalog noise (sake,
    cocktails, food) that must not receive a structure profile — shares the
    detector with the wine_type backfill."""
    return _is_non_wine((row or {}).get("name"))


def clamp_1_10(v) -> Optional[int]:
    """Integer 1-10 or None (out-of-range / unparseable -> drop, never coerce)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 10 else None


def needs_sweetness(profile: Optional[Dict[str, Any]]) -> bool:
    return bool(profile) and profile.get("sweetness") is None


def needs_full_profile(wine: Dict[str, Any], has_profile: bool) -> bool:
    if has_profile:
        return False
    if not (wine.get("grapes") or wine.get("varietal")):
        return False
    return structure_for(wine.get("varietal"), wine.get("grapes"),
                         wine.get("region")) is None


def merge_sweetness(profile: Dict[str, Any], sweetness: int) -> Dict[str, Any]:
    """Copy the profile with sweetness set; body/tannins/acidity untouched."""
    out = dict(profile)
    out["sweetness"] = sweetness
    if out.get("source") != "llm":
        out["sweetness_source"] = "llm"
    return out


def full_profile_from(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Full llm profile from a raw response row (maps 'tannin' -> 'tannins').
    None if ANY axis is out of range (don't write a partial profile)."""
    body = clamp_1_10(resp.get("body"))
    tannins = clamp_1_10(resp.get("tannin"))
    acidity = clamp_1_10(resp.get("acidity"))
    sweetness = clamp_1_10(resp.get("sweetness"))
    if None in (body, tannins, acidity, sweetness):
        return None
    return {"body": body, "tannins": tannins, "acidity": acidity,
            "sweetness": sweetness, "source": "llm"}


def validate_batch(resp: Dict[str, Any],
                   batch_ids: set) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
    """Return ({wine_id: raw_row}, bad_id_count, bad_value_count). Drops rows
    whose wine_id isn't in the input batch (qwen echo corruption) or whose
    sweetness doesn't clamp."""
    clean, bad_id, bad_val = {}, 0, 0
    for r in resp.get("wines", []):
        wid = str(r.get("wine_id") or "")
        if wid not in batch_ids:
            bad_id += 1
            continue
        if clamp_1_10(r.get("sweetness")) is None:
            bad_val += 1
            continue
        clean[wid] = r
    return clean, bad_id, bad_val


def _call_ollama(wines: List[Dict[str, Any]], timeout: int = 180) -> Dict[str, Any]:
    """One ollama batch call using the benchmark's tuned prompt."""
    listing = "\n".join(
        f'- wine_id={w["id"]} | name="{w.get("name","")}" | type={w.get("wine_type")} '
        f'| grapes="{", ".join(w.get("grapes") or [])}" '
        f'| desc="{(w.get("desc") or "")[:300]}"' for w in wines)
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": "Estimate structure:\n" + listing}],
        "stream": False, "format": "json", "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return json.loads((data.get("message") or {}).get("content") or "{}")


def _fetch_eligible(db, limit: int) -> Tuple[List[dict], List[dict]]:
    """Return (sweetness_rows, blend_rows), each row {id,name,desc,wine_type,
    varietal,grapes,region,profile}. Paged; filtered client-side."""
    sweetness, blends, page = [], [], 0
    while True:
        rows = (db.table("wines")
                .select("id,name,varietal,region,grapes,wine_type,"
                        "wine_details(structure_profile,tasting_notes)")
                .order("id").range(page * 1000, (page + 1) * 1000 - 1).execute().data)
        if not rows:
            break
        for w in rows:
            wd = w.get("wine_details") or {}
            wd = wd[0] if isinstance(wd, list) else wd
            profile = wd.get("structure_profile")
            base = {"id": w["id"], "name": w.get("name"),
                    "desc": wd.get("tasting_notes"), "wine_type": w.get("wine_type"),
                    "varietal": w.get("varietal"), "grapes": w.get("grapes") or [],
                    "region": w.get("region"), "profile": profile}
            if is_non_wine_row(base):
                continue
            if needs_sweetness(profile):
                sweetness.append(base)
            elif needs_full_profile(w, has_profile=bool(profile)):
                blends.append(base)
        page += 1
        if limit and (len(sweetness) + len(blends)) >= limit:
            break
    if limit:
        merged = (blends + sweetness)[:limit]
        s_ids = {r["id"] for r in sweetness}
        sweetness = [r for r in merged if r["id"] in s_ids]
        blends = [r for r in merged if r["id"] not in s_ids]
    return sweetness, blends


def _notify_slack(text: str) -> None:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"slack notify failed: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    from db import get_service_client
    import uuid
    from datetime import datetime, timezone
    db = get_service_client()

    run_id = str(uuid.uuid4())
    if not args.dry_run:
        db.table("scraper_runs").insert({
            "id": run_id, "retailer_name": "Structure LLM (local qwen)",
            "status": "running"}).execute()

    sweetness, blends, filled_s, filled_b, bad = [], [], 0, 0, 0
    try:
        sweetness, blends = _fetch_eligible(db, args.limit)
        print(f"eligible: {len(sweetness)} sweetness-fill, {len(blends)} unanchored blends", flush=True)

        def _run(rows, is_full):
            nonlocal filled_s, filled_b, bad
            for i in range(0, len(rows), args.batch):
                chunk = rows[i:i + args.batch]
                ids = {r["id"] for r in chunk}
                try:
                    resp = _call_ollama(chunk)
                except Exception as e:
                    print(f"  batch {i // args.batch} call failed: {e}", flush=True)
                    continue
                clean, bad_id, bad_val = validate_batch(resp, ids)
                bad += bad_id + bad_val
                by_id = {r["id"]: r for r in chunk}
                for wid, row in clean.items():
                    if is_full:
                        prof = full_profile_from(row)
                        if prof is None:
                            bad += 1
                            continue
                    else:
                        prof = merge_sweetness(by_id[wid]["profile"],
                                               clamp_1_10(row["sweetness"]))
                    if not args.dry_run:
                        db.table("wine_details").upsert(
                            {"wine_id": wid, "structure_profile": prof},
                            on_conflict="wine_id").execute()
                    if is_full:
                        filled_b += 1
                    else:
                        filled_s += 1
                print(f"  {('blend' if is_full else 'sweetness')} {i + len(chunk)}/{len(rows)} "
                      f"| filled s={filled_s} b={filled_b} bad={bad}", flush=True)

        _run(blends, is_full=True)
        _run(sweetness, is_full=False)

        summary = (f"Structure LLM{' (dry run)' if args.dry_run else ''}: "
                   f"{filled_s} sweetness filled, {filled_b} blends profiled, "
                   f"{bad} dropped (bad id/value)")
        print(summary, flush=True)
        if not args.dry_run:
            db.table("scraper_runs").update({
                "status": "success", "records_updated": filled_s + filled_b,
                "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
            _notify_slack(f":test_tube: {summary}")
    except Exception as e:
        if not args.dry_run:
            db.table("scraper_runs").update({
                "status": "failed", "error_message": str(e)[:500],
                "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", run_id).execute()
        raise


if __name__ == "__main__":
    main()
