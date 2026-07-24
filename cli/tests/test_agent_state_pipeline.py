from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from limen.agent_state.atomize import sha256_file, stat_identity
from limen.agent_state.models import MetabolismReceipt, ReceiptError, RestoreProof, SourceProof
from limen.agent_state.pipeline import (
    PipelineError,
    capture_opencode,
    require_mounted_external,
    retire_opencode,
)


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=17")
        connection.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        connection.execute("CREATE INDEX session_title ON session(title)")
        connection.execute("INSERT INTO session VALUES ('s1', 'private title')")


def _receipt(source: Path, *, external_passed: bool = True) -> MetabolismReceipt:
    identity = stat_identity(source)
    return MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run",
        source=SourceProof(
            path=str(source),
            kind="opencode-sqlite",
            bytes=identity[0],
            sha256=sha256_file(source),
            stat_before=identity,
            stat_after=identity,
        ),
        atom_count=1,
        logical_sha256="a" * 64,
        git_remote="organvm/arca",
        git_commit="b" * 40,
        git_receipt_commit="c" * 40,
        external_chunks=[],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=external_passed),
        ],
    )


def test_unmounted_external_custody_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="mounted /Volumes"):
        require_mounted_external(tmp_path / "not-external")


def test_active_vendor_denies_capture_before_writes(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    vault = tmp_path / "vault"
    external = tmp_path / "external"
    with pytest.raises(PipelineError, match="OpenCode is active"):
        capture_opencode(
            source,
            vault,
            external,
            tmp_path / "receipt.json",
            process_probe=lambda: True,
            require_external_mount=False,
        )
    assert not external.exists()


def test_failed_restoration_cannot_retire_source(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    receipt = _receipt(source, external_passed=False)
    receipt.external_chunks.append(object())  # only the non-empty custody predicate matters here

    with pytest.raises(ReceiptError, match="restoration gates missing"):
        retire_opencode(receipt, process_probe=lambda: False)
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT count(*) FROM session").fetchone()[0] == 1


def test_verified_source_is_replaced_by_clean_current_schema(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    receipt = _receipt(source)
    receipt.external_chunks.append(object())

    retired = retire_opencode(receipt, process_probe=lambda: False)

    assert retired.source_retired
    assert retired.retirement_proof.startswith("deleted-source-sha256:")
    assert not list(tmp_path.glob("*.retiring"))
    with sqlite3.connect(source) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 17
        assert connection.execute("SELECT count(*) FROM session").fetchone()[0] == 0
        indexes = connection.execute(
            "SELECT count(*) FROM sqlite_schema WHERE type='index' AND name='session_title'"
        ).fetchone()[0]
        assert indexes == 1


def test_source_mutation_after_capture_denies_retirement(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    receipt = _receipt(source)
    receipt.external_chunks.append(object())
    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO session VALUES ('s2', 'later')")

    with pytest.raises(PipelineError, match="changed after custody"):
        retire_opencode(receipt, process_probe=lambda: False)
