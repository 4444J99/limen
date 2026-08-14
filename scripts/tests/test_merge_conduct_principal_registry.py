from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "merge-conduct-principal-registry.py"
SPEC = importlib.util.spec_from_file_location("merge_conduct_principal_registry", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def registry(*principals: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "limen.conduct_principal_registry.v1",
        "principals": list(principals),
    }


def test_adds_narrow_legacy_compatibility_principal() -> None:
    merged = MODULE.merge_registry(registry(), "legacy-bearer-value")

    assert merged["principals"] == [
        {
            "agent": "codex",
            "bearer": "legacy-bearer-value",
            "principal_id": "codex-direct-legacy",
            "roles": ["observer", "conductor", "compatibility"],
            "surface": "direct",
        }
    ]


def test_existing_legacy_principal_is_augmented_idempotently() -> None:
    source = registry(
        {
            "agent": "codex",
            "bearer": "legacy-bearer-value",
            "principal_id": "codex-direct",
            "roles": ["observer", "conductor"],
            "surface": "direct",
        }
    )

    once = MODULE.merge_registry(copy.deepcopy(source), "legacy-bearer-value")
    twice = MODULE.merge_registry(copy.deepcopy(once), "legacy-bearer-value")

    assert once == twice
    assert once["principals"][0]["roles"] == ["compatibility", "conductor", "observer"]
    assert "executor" not in once["principals"][0]["roles"]


def test_rejects_duplicate_legacy_bearer_bindings() -> None:
    source = registry(
        {"bearer": "legacy-bearer-value", "roles": ["observer"]},
        {"bearer": "legacy-bearer-value", "roles": ["conductor"]},
    )

    with pytest.raises(ValueError, match="multiple conduct principals"):
        MODULE.merge_registry(source, "legacy-bearer-value")


def test_requires_a_compatibility_principal() -> None:
    with pytest.raises(ValueError, match="no compatibility principal"):
        MODULE.merge_registry(registry(), "")
