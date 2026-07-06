"""
Benchmark: Haiku vs local Ollama models on wine-fact extraction.

Runs the same labeled set through each extractor and reports accuracy on the
fields that matter for recommendations (varietal, region, country, body) plus
throughput. Ground truth is hand-verified from the wine names.

  cd backend && python3 -m enrichment.extraction.benchmark [--models haiku,qwen2.5:7b,llama3.1:8b]
"""
import sys
import time
from typing import List, Dict, Any

from enrichment.extraction.extractor import extract_facts
from enrichment.extraction.ollama_extractor import extract_facts_ollama

# Labeled set — (id, name, wine_type, expected {region, country, varietal}).
# region/varietal use our canonical spellings; None means "not determinable
# from the name" (the model should return null, not guess).
LABELED: List[Dict[str, Any]] = [
    # ── easy: region + grape in the name ─────────────────────────
    ("l01", "Altos Las Hormigas Malbec Mendoza", "red", {"region": "Mendoza", "country": "Argentina", "varietal": "Malbec"}),
    ("l02", "Kim Crawford Sauvignon Blanc Marlborough", "white", {"region": "Marlborough", "country": "New Zealand", "varietal": "Sauvignon Blanc"}),
    ("l03", "Josh Cellars Cabernet Sauvignon California", "red", {"region": "California", "country": "United States", "varietal": "Cabernet Sauvignon"}),
    ("l04", "La Marca Prosecco Italy", "sparkling", {"region": "Prosecco", "country": "Italy", "varietal": "Glera"}),
    ("l05", "Oyster Bay Pinot Noir Marlborough", "red", {"region": "Marlborough", "country": "New Zealand", "varietal": "Pinot Noir"}),
    ("l06", "Meiomi Pinot Noir California", "red", {"region": "California", "country": "United States", "varietal": "Pinot Noir"}),
    ("l07", "Whitehaven Sauvignon Blanc New Zealand", "white", {"region": None, "country": "New Zealand", "varietal": "Sauvignon Blanc"}),
    ("l08", "Catena Malbec Argentina", "red", {"region": "Mendoza", "country": "Argentina", "varietal": "Malbec"}),
    ("l09", "Bogle Old Vine Zinfandel California", "red", {"region": "California", "country": "United States", "varietal": "Zinfandel"}),
    ("l10", "Kendall-Jackson Vintner's Reserve Chardonnay California", "white", {"region": "California", "country": "United States", "varietal": "Chardonnay"}),
    # ── medium: appellation implies region + grape ──────────────
    ("l11", "Ruffino Chianti Classico Riserva", "red", {"region": "Tuscany", "country": "Italy", "varietal": "Sangiovese"}),
    ("l12", "Louis Jadot Bourgogne Pinot Noir", "red", {"region": "Burgundy", "country": "France", "varietal": "Pinot Noir"}),
    ("l13", "Bodegas Muga Rioja Reserva", "red", {"region": "Rioja", "country": "Spain", "varietal": "Tempranillo"}),
    ("l14", "Guigal Cotes du Rhone Rouge", "red", {"region": "Rhône", "country": "France", "varietal": "Grenache"}),
    ("l15", "Chateau Ste Michelle Columbia Valley Riesling", "white", {"region": "Columbia Valley", "country": "United States", "varietal": "Riesling"}),
    ("l16", "Marchesi Antinori Chianti Classico", "red", {"region": "Tuscany", "country": "Italy", "varietal": "Sangiovese"}),
    ("l17", "Emmolo Merlot Napa Valley", "red", {"region": "Napa Valley", "country": "United States", "varietal": "Merlot"}),
    ("l18", "Sean Minor Sauvignon Blanc Napa Valley", "white", {"region": "Napa Valley", "country": "United States", "varietal": "Sauvignon Blanc"}),
    ("l19", "Banfi Brunello di Montalcino", "red", {"region": "Tuscany", "country": "Italy", "varietal": "Sangiovese"}),
    ("l20", "Sancerre Domaine Vacheron", "white", {"region": "Loire", "country": "France", "varietal": "Sauvignon Blanc"}),
    ("l21", "Barolo Pio Cesare", "red", {"region": "Piedmont", "country": "Italy", "varietal": "Nebbiolo"}),
    ("l22", "Vietti Barbera d'Asti Tre Vigne", "red", {"region": "Piedmont", "country": "Italy", "varietal": "Barbera"}),
    ("l23", "Weingut Dr Loosen Riesling Mosel", "white", {"region": "Mosel", "country": "Germany", "varietal": "Riesling"}),
    ("l24", "Penfolds Bin 28 Kalimna Shiraz", "red", {"region": "Barossa Valley", "country": "Australia", "varietal": "Shiraz"}),
    # ── hard: producer + brand, less obvious ────────────────────
    ("l25", "Decoy Cabernet Sauvignon", "red", {"region": None, "country": "United States", "varietal": "Cabernet Sauvignon"}),
    ("l26", "Apothic Red Blend California", "red", {"region": "California", "country": "United States", "varietal": None}),
    ("l27", "The Prisoner Red Blend Napa Valley", "red", {"region": "Napa Valley", "country": "United States", "varietal": None}),
    ("l28", "Veuve Clicquot Yellow Label Brut Champagne", "sparkling", {"region": "Champagne", "country": "France", "varietal": None}),
    ("l29", "Cloudy Bay Sauvignon Blanc", "white", {"region": "Marlborough", "country": "New Zealand", "varietal": "Sauvignon Blanc"}),
    ("l30", "Tignanello Antinori Toscana", "red", {"region": "Tuscany", "country": "Italy", "varietal": None}),
    ("l31", "Caymus Cabernet Sauvignon Napa Valley", "red", {"region": "Napa Valley", "country": "United States", "varietal": "Cabernet Sauvignon"}),
    ("l32", "Santa Margherita Pinot Grigio Alto Adige", "white", {"region": "Alto Adige", "country": "Italy", "varietal": "Pinot Grigio"}),
    ("l33", "Duckhorn Vineyards Sauvignon Blanc Napa Valley", "white", {"region": "Napa Valley", "country": "United States", "varietal": "Sauvignon Blanc"}),
    ("l34", "Faust Cabernet Sauvignon Napa Valley", "red", {"region": "Napa Valley", "country": "United States", "varietal": "Cabernet Sauvignon"}),
    ("l35", "Whispering Angel Cotes de Provence Rose", "rose", {"region": "Provence", "country": "France", "varietal": None}),
    ("l36", "Ferrari-Carano Fume Blanc Sonoma County", "white", {"region": "Sonoma", "country": "United States", "varietal": "Sauvignon Blanc"}),
    ("l37", "Mollydooker The Boxer Shiraz South Australia", "red", {"region": None, "country": "Australia", "varietal": "Shiraz"}),
    ("l38", "Chateau Montelena Chardonnay Napa Valley", "white", {"region": "Napa Valley", "country": "United States", "varietal": "Chardonnay"}),
    ("l39", "Frog's Leap Zinfandel Napa Valley", "red", {"region": "Napa Valley", "country": "United States", "varietal": "Zinfandel"}),
    ("l40", "La Crema Pinot Noir Sonoma Coast", "red", {"region": "Sonoma", "country": "United States", "varietal": "Pinot Noir"}),
]


def _norm(s):
    return (s or "").strip().lower().replace("é", "e").replace("ô", "o")


def _region_match(pred, gold):
    """Region matches on containment either way (Napa ~ Napa Valley)."""
    if gold is None:
        return pred is None or pred == ""   # should not have guessed
    p, g = _norm(pred), _norm(gold)
    return bool(p) and (p in g or g in p)


def _exact(pred, gold):
    if gold is None:
        return not pred
    return _norm(pred) == _norm(gold)


def _score(records_by_id):
    fields = {"region": 0, "country": 0, "varietal": 0}
    # only score region/varietal where gold is not None (guessability)
    counts = {"region": 0, "country": 0, "varietal": 0}
    for _id, name, wtype, gold in LABELED:
        rec = records_by_id.get(_id, {})
        for f in fields:
            g = gold.get(f)
            counts[f] += 1
            match = _region_match(rec.get(f), g) if f == "region" else _exact(rec.get(f), g)
            if match:
                fields[f] += 1
    return {f: (fields[f], counts[f]) for f in fields}


def run(model_name: str):
    wines = [{"id": i, "name": n, "wine_type": t, "description": ""} for i, n, t, _ in LABELED]
    t0 = time.time()
    if model_name == "haiku":
        recs = extract_facts(wines, batch_size=15)
    else:
        recs = extract_facts_ollama(wines, batch_size=10, model=model_name)
    dt = time.time() - t0
    by_id = {r["wine_id"]: r for r in recs}
    return _score(by_id), dt, len(by_id), by_id


def main():
    models = ["haiku", "qwen2.5:7b", "llama3.1:8b"]
    if "--models" in sys.argv:
        models = sys.argv[sys.argv.index("--models") + 1].split(",")

    print(f"Labeled wines: {len(LABELED)}\n")
    print(f"{'model':16} {'varietal':>12} {'region':>12} {'country':>12} {'returned':>9} {'time':>8}")
    detail = {}
    for m in models:
        try:
            score, dt, n, by_id = run(m)
            detail[m] = by_id
            def pct(f): a, b = score[f]; return f"{a}/{b} {100*a//b}%"
            print(f"{m:16} {pct('varietal'):>12} {pct('region'):>12} {pct('country'):>12} {n:>9} {dt:>7.1f}s")
        except Exception as e:
            print(f"{m:16} ERROR: {str(e)[:60]}")

    # per-wine disagreements vs Haiku (for the winning local model)
    if "haiku" in detail:
        for m in models:
            if m == "haiku" or m not in detail:
                continue
            print(f"\n=== {m} misses (vs ground truth) ===")
            for _id, name, wtype, gold in LABELED:
                r = detail[m].get(_id, {})
                probs = []
                if not _exact(r.get("varietal"), gold.get("varietal")):
                    probs.append(f"varietal: got {r.get('varietal')!r} want {gold.get('varietal')!r}")
                if not _region_match(r.get("region"), gold.get("region")):
                    probs.append(f"region: got {r.get('region')!r} want {gold.get('region')!r}")
                if probs:
                    print(f"  {name[:42]:42} {' | '.join(probs)}")


if __name__ == "__main__":
    main()
