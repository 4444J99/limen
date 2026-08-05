"""Deterministic source-union tests for the biography resolver."""

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "resolve-biography.py"
    spec = importlib.util.spec_from_file_location("resolve_biography", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_union_keeps_old_and_new_review_histories(tmp_path):
    module = _module()
    registry = tmp_path / "biography.yaml"
    (tmp_path / "docs" / "reviews").mkdir(parents=True)
    older = "docs/reviews/full-history-excavation-2026-06-08--2026-07-08.md"
    newer = "docs/reviews/deep-history-2022-2026.md"
    for relative in (older, newer):
        path = tmp_path / relative
        path.write_text(relative, encoding="utf-8")
    registry.write_text(
        f"facts:\n  biography.narrative.cited:\n    source_documents:\n      - {older}\n      - {newer}\n",
        encoding="utf-8",
    )

    result = module.resolve_biography(tmp_path, registry)
    paths = [row["path"] for row in result["sources"]]
    assert paths == sorted([older, newer])
    assert result["unavailable"] == []


def test_missing_current_source_is_explicitly_unavailable(tmp_path):
    module = _module()
    registry = tmp_path / "biography.yaml"
    registry.write_text(
        "facts:\n  biography.narrative.cited:\n    source_documents:\n      - docs/reviews/current.md\n",
        encoding="utf-8",
    )

    result = module.resolve_biography(tmp_path, registry)
    assert result["source_count"] == 0
    assert result["unavailable"] == ["docs/reviews/current.md"]
