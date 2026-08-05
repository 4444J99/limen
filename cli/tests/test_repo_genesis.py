from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repo-genesis.py"
SPEC = importlib.util.spec_from_file_location("repo_genesis", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_estate(path: Path, *, override: bool = True) -> None:
    data = {
        "classes": {
            "operation_private": {"match": []},
            "shelf_public": {"match": ["organvm-iii-ergon/**"]},
            "contrib_fork": {"match": ["**"]},
        },
        "repo_overrides": {},
    }
    if override:
        data["repo_overrides"]["organvm-iii-ergon/collaboration-operations-platform"] = {
            "class": "operation_private",
            "why": "project-neutral operation",
        }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_explicit_override_wins_before_broad_class_globs(tmp_path: Path, monkeypatch) -> None:
    estate = tmp_path / "estate.yaml"
    write_estate(estate)
    monkeypatch.setattr(MODULE, "ESTATE", estate)

    passed, detail = MODULE.gate_class("organvm-iii-ergon/collaboration-operations-platform", "operation_private")

    assert passed is True
    assert "explicit override" in detail
    assert "operation_private" in detail


def test_expected_class_rejects_a_glob_fallback(tmp_path: Path, monkeypatch) -> None:
    estate = tmp_path / "estate.yaml"
    write_estate(estate, override=False)
    monkeypatch.setattr(MODULE, "ESTATE", estate)

    passed, detail = MODULE.gate_class("organvm-iii-ergon/collaboration-operations-platform", "operation_private")

    assert passed is False
    assert "resolves to 'shelf_public', expected 'operation_private'" in detail
