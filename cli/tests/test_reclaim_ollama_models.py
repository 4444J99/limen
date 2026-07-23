from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclaim-ollama-models.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_ollama_list_extracts_model_names():
    mod = _load("reclaim_ollama_models_parse_uut")
    text = """NAME        ID              SIZE      MODIFIED
llava:7b    8dd30f6b0cb1    4.7 GB    13 hours ago
qwen3:8b    500a1f067a9f    5.2 GB    24 hours ago
"""

    rows = mod.parse_ollama_list(text)

    assert [row["name"] for row in rows] == ["llava:7b", "qwen3:8b"]
    assert rows[0]["size"] == "4.7 GB"


def test_loaded_models_skips_header_and_empty_rows():
    mod = _load("reclaim_ollama_models_loaded_uut")
    text = """NAME    ID    SIZE    PROCESSOR    CONTEXT    UNTIL

qwen3:8b    500a    5.2 GB    100% GPU    4096    4 minutes
"""

    assert mod.loaded_models(text) == ["qwen3:8b"]
