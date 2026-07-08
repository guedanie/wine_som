import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import importlib


def _get_extractor(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("EXTRACTOR_BACKEND", raising=False)
    else:
        monkeypatch.setenv("EXTRACTOR_BACKEND", value)
    mod = importlib.import_module("enrichment.extraction.run_extraction")
    return mod.get_extractor()


def test_default_backend_is_haiku(monkeypatch):
    from enrichment.extraction.extractor import extract_facts
    assert _get_extractor(monkeypatch, None) is extract_facts


def test_ollama_backend_selected_by_env(monkeypatch):
    from enrichment.extraction.ollama_extractor import extract_facts_ollama
    assert _get_extractor(monkeypatch, "ollama") is extract_facts_ollama


def test_backend_is_case_insensitive(monkeypatch):
    from enrichment.extraction.ollama_extractor import extract_facts_ollama
    assert _get_extractor(monkeypatch, "OLLAMA") is extract_facts_ollama


def test_unknown_backend_falls_back_to_haiku(monkeypatch):
    from enrichment.extraction.extractor import extract_facts
    assert _get_extractor(monkeypatch, "gpt5") is extract_facts
