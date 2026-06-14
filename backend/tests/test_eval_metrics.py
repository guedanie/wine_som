import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from enrichment.matching.eval.run_eval import compute_metrics


def _row(wine_id, source, rank, is_primary, confidence, correct):
    return {"wine_id": wine_id, "source": source, "rank": str(rank),
            "is_primary": str(is_primary), "confidence": str(confidence), "correct": correct}


def test_compute_metrics_precision_recall_coverage():
    rows = [
        # wine A: correct == primary  -> covered, p@1 hit, recall hit
        _row("A", "H-E-B", 1, True, 0.92, "1"),
        _row("A", "H-E-B", 2, False, 0.80, ""),
        # wine B: correct is rank 2   -> covered, p@1 MISS, recall hit
        _row("B", "H-E-B", 1, True, 0.70, ""),
        _row("B", "H-E-B", 2, False, 0.55, "1"),
        # wine C: no correct           -> not covered
        _row("C", "Geraldine's Natural Wines", 1, True, 0.30, ""),
    ]
    m = compute_metrics(rows)
    assert m["overall"]["n_wines"] == 3
    assert m["overall"]["coverage"] == round(2/3, 3)
    assert m["overall"]["precision_at_1"] == 0.5     # A hit, B miss
    assert m["overall"]["top3_recall"] == 1.0        # A and B both found
