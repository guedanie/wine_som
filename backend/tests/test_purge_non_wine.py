import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.purge_non_wine import rows_to_exclude


def test_rows_to_exclude_filters_and_attaches_reason():
    rows = [
        {"id": "1", "name": "Pacifico Mexican Lager", "varietal": None, "grapes": []},
        {"id": "2", "name": "Chateau Margaux", "varietal": "Cabernet Sauvignon", "grapes": []},
        {"id": "3", "name": "Bota Box Bourbon Barrel Cabernet", "varietal": "Cabernet Sauvignon", "grapes": []},
        {"id": "4", "name": "Del Monte Fruit Cocktail", "varietal": None, "grapes": []},
    ]
    out = rows_to_exclude(rows)
    ids = {r["id"]: r["reason"] for r in out}
    assert set(ids) == {"1", "4"}          # only clear non-wine, no signal
    assert ids["1"] == "lager"
    assert ids["4"] == "cocktail"
