from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reap_acceptance.py"


def load_reap_acceptance():
    spec = importlib.util.spec_from_file_location("reap_acceptance_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_required_acceptance_proof_fields_are_shared() -> None:
    module = load_reap_acceptance()

    assert module.REQUIRED_ACCEPTANCE_PROOF_FIELDS == ("accepted_at", "archive_proof", "redaction_proof")
    assert module.removal_acceptance_surface_names() == (
        "branch",
        "clone",
        "remote_branch",
        "worktree",
        "antigravity_scratch",
    )


def test_required_acceptance_proof_rejects_blank_fields() -> None:
    module = load_reap_acceptance()
    event = {
        "accepted_at": "2026-07-06T06:00:00Z",
        "archive_proof": "",
        "redaction_proof": "clean remote mirror",
    }

    assert module.has_required_acceptance_proof(event) is False
    assert module.missing_required_acceptance_proof_fields(event) == ("archive_proof",)
