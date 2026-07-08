import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import socket
from unittest.mock import patch, MagicMock
import json as _json
from enrichment.extraction import ollama_extractor as oe


class _Resp:
    def __init__(self, payload): self._p = payload
    def read(self): return _json.dumps(self._p).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


_OK = {"message": {"content": '{"wines": []}'}}


def test_retries_on_timeout_then_succeeds():
    calls = {"n": 0}
    def flaky(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise socket.timeout("timed out")
        return _Resp(_OK)
    with patch("urllib.request.urlopen", side_effect=flaky), patch("time.sleep"):
        out = oe._call_ollama("sys", "user", "qwen2.5:7b")
    assert out == {"wines": []}
    assert calls["n"] == 3          # failed twice, succeeded on the third


def test_raises_after_exhausting_retries():
    with patch("urllib.request.urlopen", side_effect=socket.timeout("nope")), patch("time.sleep"):
        try:
            oe._call_ollama("sys", "user", "qwen2.5:7b")
            assert False, "should have raised"
        except Exception:
            pass
