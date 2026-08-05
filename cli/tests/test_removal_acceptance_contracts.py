from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-removal-acceptance.py"
REAP_ACCEPTANCE = ROOT / "scripts" / "reap_acceptance.py"


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_registered_removal_surfaces_are_canonical() -> None:
    module = load_script(REAP_ACCEPTANCE, "reap_acceptance_contract_under_test")

    assert module.removal_acceptance_surface_names() == (
        "branch",
        "clone",
        "remote_branch",
        "worktree",
        "antigravity_scratch",
    )
    assert module.REQUIRED_ACCEPTANCE_PROOF_FIELDS == ("accepted_at", "archive_proof", "redaction_proof")


def test_removal_acceptance_contracts_pass_for_repo() -> None:
    module = load_script(SCRIPT, "check_removal_acceptance_under_test")

    assert module.check_all(ROOT) == []


def test_surface_check_rejects_doc_missing_required_proof(tmp_path: Path) -> None:
    module = load_script(SCRIPT, "check_removal_acceptance_missing_doc_under_test")
    surface = {
        "name": "example",
        "script": "scripts/example-reap.py",
        "doc": "docs/example-reap.md",
        "ledger": "docs/example-reap.jsonl",
        "destructive_action": "remove example",
    }
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / surface["script"]).write_text(
        "from reap_acceptance import has_required_acceptance_proof\nLEDGER = 'example-reap.jsonl'\n",
        encoding="utf-8",
    )
    (tmp_path / surface["doc"]).write_text(
        "docs/example-reap.jsonl\nDo not create that JSONL as a cleanup shortcut\n`accepted_at`\n`redaction_proof`\n",
        encoding="utf-8",
    )

    errors = module.check_surface(tmp_path, surface)

    assert "example: doc does not require proof field archive_proof" in errors


def test_direct_removal_bans_reject_guarded_tokens(tmp_path: Path) -> None:
    module = load_script(SCRIPT, "check_removal_acceptance_direct_bans_under_test")
    guarded = tmp_path / "scripts" / "unsafe.sh"
    guarded.parent.mkdir()
    guarded.write_text("git worktree remove --force /tmp/example\n", encoding="utf-8")

    errors = module.check_direct_removal_bans(
        tmp_path,
        {"scripts/unsafe.sh": ("worktree remove",)},
    )

    assert errors == [
        "direct-removal-ban: scripts/unsafe.sh contains forbidden token 'worktree remove'",
    ]
