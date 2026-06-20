import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.merge_duplicate_wines import pick_survivor, merge_fields


def test_pick_survivor_prefers_most_inventory():
    group = [
        {"id": "a", "inventory_count": 1},
        {"id": "b", "inventory_count": 5},
        {"id": "c", "inventory_count": 3},
    ]
    assert pick_survivor(group) == "b"


def test_pick_survivor_tiebreak_lowest_id():
    group = [
        {"id": "z", "inventory_count": 2},
        {"id": "a", "inventory_count": 2},
    ]
    assert pick_survivor(group) == "a"


def test_merge_fields_prefers_specs_name_over_heb():
    survivor = {"id": "s", "name": "Decoy Cabernet Sauvignon California Red Wine",
                "source": "H-E-B", "region": None, "image_url": None}
    losers = [{"id": "l", "name": "Decoy Cabernet", "source": "Spec's",
               "region": "California", "image_url": "http://img"}]
    merged = merge_fields(survivor, losers)
    assert merged["name"] == "Decoy Cabernet"        # Spec's preferred
    assert merged["region"] == "California"           # filled from loser
    assert merged["image_url"] == "http://img"        # first non-null


def test_merge_fields_keeps_survivor_value_when_present():
    survivor = {"id": "s", "name": "A", "source": "Spec's",
                "region": "Napa", "image_url": "http://s"}
    losers = [{"id": "l", "name": "B", "source": "H-E-B",
               "region": "Sonoma", "image_url": "http://l"}]
    merged = merge_fields(survivor, losers)
    assert merged["region"] == "Napa"                 # survivor already had it
    assert merged["image_url"] == "http://s"          # survivor non-null wins
    assert merged["name"] == "A"                       # survivor is Spec's, kept
