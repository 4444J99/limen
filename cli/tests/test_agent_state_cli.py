from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent-state-metabolism.py"


def test_resume_requires_explicit_run_id(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cold-tree",
            "codex-sessions",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--resume",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--resume requires --run-id" in result.stderr


def test_cloud_eviction_requires_both_signed_inputs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--evict",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--evict requires --eviction-authorization and --eviction-signature" in result.stderr


def test_cloud_authorization_plan_requires_principal(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--prepare-eviction-authorization",
            str(tmp_path / "authorization.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "requires --eviction-authorizer" in result.stderr


def test_exact_retention_rejects_age_or_size_heuristics(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cold-tree",
            "opencode-residual",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--retain-relative",
            "opencode.db",
            "--hot-days",
            "0",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--retain-relative cannot be combined" in result.stderr


@pytest.mark.parametrize(
    "selector",
    [
        ("--retain-relative", "keep.txt"),
        ("--hot-days", "0"),
        ("--maximum-hot-gib", "0"),
    ],
)
def test_capture_all_rejects_other_selectors(
    tmp_path: Path,
    selector: tuple[str, str],
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cold-tree",
            "sample-tree",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--capture-all",
            *selector,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--capture-all cannot be combined" in result.stderr


def test_capture_all_selects_every_regular_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "alpha.txt").write_bytes(b"a")
    nested = source / "nested"
    nested.mkdir()
    (nested / "beta.txt").write_bytes(b"bc")
    (source / "alias").symlink_to(source / "alpha.txt")

    spec = importlib.util.spec_from_file_location("agent_state_metabolism_cli_capture_all", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed: dict[str, object] = {}

    def capture(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return SimpleNamespace(
            schema="limen.agent_state_receipt.v1",
            run_id="run",
            atom_count=2,
            duplicate_payloads=0,
            git_commit="payload",
            git_receipt_commit="receipt",
            restorations=(),
            source_retired=False,
        )

    monkeypatch.setattr(module, "run_cold_tree_campaign", capture)
    result = module.main(
        [
            "cold-tree",
            "sample-tree",
            "--root",
            str(source),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--capture-all",
        ]
    )

    assert result == 0
    plan = observed["args"][1]
    assert plan.cold_paths == ("alpha.txt", "nested/beta.txt")
    assert plan.cold_bytes == 3
    assert plan.hot_paths == ()
    assert plan.hot_bytes == 0


def test_cloud_restore_requires_path_free_receipt_pair(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "one item restoration selector and --restore-receipt are required together" in result.stderr


def test_cloud_restore_requires_exactly_one_path_free_selector(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
            "--restore-captured-path-hash",
            "b" * 64,
            "--restore-captured-name-hash",
            "c" * 64,
            "--restore-receipt",
            str(tmp_path / "restore.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "choose exactly one item restoration selector" in result.stderr


def test_cloud_restore_requires_explicit_apply(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
            "--restore-receipt",
            str(tmp_path / "restore.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "item restoration requires explicit --apply" in result.stderr


def test_cloud_restore_apply_invokes_the_bounded_campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = importlib.util.spec_from_file_location("agent_state_metabolism_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed: dict[str, object] = {}

    def restore(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return {"schema": "limen.file_provider_restore_receipt.v1", "status": "already_restored"}

    monkeypatch.setattr(module, "run_restore_cloudkit_item_campaign", restore)
    result = module.main(
        [
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
            "--restore-receipt",
            str(tmp_path / "restore.json"),
            "--apply",
        ]
    )

    assert result == 0
    assert observed["kwargs"] == {
        "run_id": "run",
        "item_hash": "a" * 64,
        "captured_path_hash": None,
        "captured_name_hash": None,
    }
    assert '"status": "already_restored"' in capsys.readouterr().out


def test_cloud_restore_cannot_be_combined_with_eviction(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
            "--restore-receipt",
            str(tmp_path / "restore.json"),
            "--apply",
            "--evict",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "item restoration cannot be combined with eviction operations" in result.stderr
