"""Bottle-scan spike: label-read parsing + catalog-match classification.

Pure logic only — no Anthropic calls, no DB. The vision round-trip lives in
enrichment/label_scan.py (parse tested here); classification in
recommendation/label_match.py.
"""
from enrichment.label_scan import parse_label_read
from recommendation.label_match import classify_scan


# ---------------------------------------------------------------- parse

def test_parse_label_read_extracts_json_from_prose():
    text = ('Here is the label info:\n'
            '{"producer": "Tablas Creek", "wine_name": "Esprit de Tablas", '
            '"vintage": "2019", "appellation": "Paso Robles", '
            '"varietal": null, "confidence": 0.9, "is_wine": true}')
    read = parse_label_read(text)
    assert read is not None
    assert read["producer"] == "Tablas Creek"
    assert read["wine_name"] == "Esprit de Tablas"
    assert read["vintage"] == "2019"
    assert read["confidence"] == 0.9
    assert read["is_wine"] is True


def test_parse_label_read_garbage_returns_none():
    assert parse_label_read("I cannot read this label, sorry.") is None
    assert parse_label_read("") is None
    assert parse_label_read(None) is None


def test_parse_label_read_normalizes_int_vintage_and_missing_fields():
    read = parse_label_read('{"producer": "Caymus", "wine_name": "Cabernet Sauvignon", '
                            '"vintage": 2021, "confidence": 0.8}')
    assert read["vintage"] == "2021"
    assert read["is_wine"] is True  # defaults true when omitted


# ---------------------------------------------------------------- classify

def _cand(id, name, brand=None, vintage_year=None):
    return {"id": id, "name": name, "brand": brand, "vintage_year": vintage_year}


READ_TABLAS = {"producer": "Tablas Creek", "wine_name": "Esprit de Tablas",
               "vintage": "2019", "confidence": 0.9, "is_wine": True}


def test_classify_exact_single_clear_winner():
    cands = [
        _cand("w1", "Tablas Creek Esprit de Tablas", "Tablas Creek", 2019),
        _cand("w2", "Justin Cabernet Sauvignon", "Justin", 2021),
    ]
    res = classify_scan(READ_TABLAS, cands)
    assert res["status"] == "exact"
    assert res["wine"]["id"] == "w1"


def test_classify_vintage_mismatch_same_wine_different_year():
    cands = [_cand("w1", "Tablas Creek Esprit de Tablas", "Tablas Creek", 2021)]
    res = classify_scan(READ_TABLAS, cands)
    assert res["status"] == "vintage_mismatch"
    assert res["wine"]["id"] == "w1"
    assert res["read_vintage"] == "2019"


def test_classify_candidates_same_producer_close_scores():
    cands = [
        _cand("w1", "Tablas Creek Esprit de Tablas", "Tablas Creek", 2019),
        _cand("w2", "Tablas Creek Esprit de Tablas Blanc", "Tablas Creek", 2019),
        _cand("w3", "Tablas Creek Cotes de Tablas", "Tablas Creek", 2020),
    ]
    read = {"producer": "Tablas Creek", "wine_name": "Tablas", "vintage": None,
            "confidence": 0.6, "is_wine": True}
    res = classify_scan(read, cands)
    assert res["status"] == "candidates"
    assert 2 <= len(res["candidates"]) <= 4


def test_classify_unstocked_confident_read_no_match():
    cands = [_cand("w1", "Apothic Red Blend", "Apothic", 2022)]
    read = {"producer": "Clos Rougeard", "wine_name": "Le Bourg",
            "vintage": "2018", "confidence": 0.85, "is_wine": True}
    res = classify_scan(read, cands)
    assert res["status"] == "unstocked"


def test_classify_unreadable_when_read_empty():
    assert classify_scan(None, [])["status"] == "unreadable"
    empty = {"producer": None, "wine_name": None, "vintage": None,
             "confidence": 0.1, "is_wine": True}
    assert classify_scan(empty, [])["status"] == "unreadable"


def test_classify_not_wine_declines():
    read = {"producer": "Pacifico", "wine_name": "Mexican Lager",
            "vintage": None, "confidence": 0.9, "is_wine": False}
    assert classify_scan(read, [])["status"] == "not_wine"


def test_classify_dedupes_inventory_rows_by_wine_id():
    # same wine at two stores must not read as a 2-candidate disambiguation
    cands = [
        _cand("w1", "Tablas Creek Esprit de Tablas", "Tablas Creek", 2019),
        _cand("w1", "Tablas Creek Esprit de Tablas", "Tablas Creek", 2019),
    ]
    res = classify_scan(READ_TABLAS, cands)
    assert res["status"] == "exact"
