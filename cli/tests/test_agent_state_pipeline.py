from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest
from limen.agent_state import pipeline
from limen.agent_state.atomize import sha256_file, stat_identity
from limen.agent_state.models import MetabolismReceipt, ReceiptError, RestoreProof, SourceProof
from limen.agent_state.pipeline import (
    GitVault,
    PipelineError,
    capture_opencode,
    partition_git_paths,
    require_mounted_external,
    retire_opencode,
)


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=17")
        connection.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        connection.execute("CREATE INDEX session_title ON session(title)")
        connection.execute("INSERT INTO session VALUES ('s1', 'private title')")


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _interrupted_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    remote_has_local_head: bool,
) -> tuple[GitVault, Path, list[Path]]:
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    root = tmp_path / "vault"
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "Limen Test")
    _git(root, "config", "user.email", "limen@example.test")
    _git(root, "remote", "add", "origin", str(remote))
    (root / "README.md").write_text("private ciphertext vault\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initialize vault")
    _git(root, "push", "-u", "origin", "main")

    relative = Path("agent-state") / "icloud-drive" / "run"
    payload = root / relative
    payload.mkdir(parents=True)
    expected = [relative / "atoms-00000.bin", relative / "atoms-00001.bin", relative / "manifest.json"]
    for path, content in zip(expected, (b"aaaa", b"bbbb", b"ccc"), strict=True):
        (root / path).write_bytes(content)
    _git(root, "add", str(expected[0]))
    _git(root, "commit", "-m", "agent-state: seal icloud-drive run (1/3)")
    if remote_has_local_head:
        _git(root, "push", "origin", "HEAD:main")

    real_run = pipeline._run

    def declared_private(arguments: list[str], *, cwd: Path | None = None) -> str:
        if arguments[:3] == ["git", "remote", "get-url"]:
            return "https://github.com/organvm/arca.git"
        if arguments[:3] == ["gh", "repo", "view"]:
            return "PRIVATE"
        return real_run(arguments, cwd=cwd)

    monkeypatch.setattr(pipeline, "_run", declared_private)
    return GitVault(root), relative, expected


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


def test_metabolism_receipt_write_uses_private_modes(tmp_path: Path) -> None:
    source = tmp_path / "opencode.db"
    _database(source)
    receipt = _receipt(source)
    private_parent = tmp_path / "private"
    nested_parent = private_parent / "nested"
    path = nested_parent / "receipt.json"

    previous_umask = os.umask(0)
    try:
        receipt.write(path)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(private_parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(nested_parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    path.chmod(0o644)
    receipt.write(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_unmounted_external_custody_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="mounted /Volumes"):
        require_mounted_external(tmp_path / "not-external")


def test_git_custody_batches_stay_below_push_limit(tmp_path: Path) -> None:
    paths = []
    for name, size in (("alpha", 4), ("beta", 5), ("gamma", 7)):
        path = tmp_path / name
        path.write_bytes(b"x" * size)
        paths.append(path)

    batches = partition_git_paths(paths, byte_limit=10)

    assert [[path.name for path in batch] for batch in batches] == [
        ["alpha", "beta"],
        ["gamma"],
    ]
    assert all(sum(path.stat().st_size for path in batch) <= 10 for batch in batches)
    with pytest.raises(PipelineError, match="single Git custody file"):
        partition_git_paths(paths, byte_limit=6)


@pytest.mark.parametrize("remote_has_local_head", [False, True])
def test_interrupted_git_custody_resumes_from_valid_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remote_has_local_head: bool,
) -> None:
    vault, relative, expected = _interrupted_vault(
        tmp_path,
        monkeypatch,
        remote_has_local_head=remote_has_local_head,
    )

    head = vault.resume_and_push_payload(
        relative,
        expected,
        "agent-state: seal icloud-drive run",
        byte_limit=6,
    )

    assert head == _git(vault.root, "rev-parse", "HEAD")
    assert _git(vault.root, "status", "--porcelain=v1") == ""
    assert _git(vault.root, "ls-remote", "origin", "refs/heads/main").split()[0] == head
    assert _git(vault.root, "log", "-3", "--format=%s").splitlines() == [
        "agent-state: seal icloud-drive run (3/3)",
        "agent-state: seal icloud-drive run (2/3)",
        "agent-state: seal icloud-drive run (1/3)",
    ]


def test_interrupted_git_custody_rejects_unrelated_dirty_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, relative, expected = _interrupted_vault(
        tmp_path,
        monkeypatch,
        remote_has_local_head=False,
    )
    (vault.root / "unrelated.txt").write_text("not part of the run\n", encoding="utf-8")

    with pytest.raises(PipelineError, match="unrelated or missing dirty state"):
        vault.resume_and_push_payload(
            relative,
            expected,
            "agent-state: seal icloud-drive run",
            byte_limit=6,
        )


def test_interrupted_git_custody_rejects_missing_ciphertext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, relative, expected = _interrupted_vault(
        tmp_path,
        monkeypatch,
        remote_has_local_head=False,
    )
    (vault.root / expected[-1]).unlink()

    with pytest.raises(PipelineError, match="missing an expected file"):
        vault.resume_and_push_payload(
            relative,
            expected,
            "agent-state: seal icloud-drive run",
            byte_limit=6,
        )


def test_completed_remote_receipt_ignores_dirty_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, relative, expected = _interrupted_vault(
        tmp_path,
        monkeypatch,
        remote_has_local_head=False,
    )
    _git(vault.root, "add", *(str(path) for path in expected[1:]))
    _git(vault.root, "commit", "-m", "agent-state: seal icloud-drive run")
    payload_commit = _git(vault.root, "rev-parse", "HEAD")
    receipt_path = vault.root / relative / "receipt.json"
    receipt_path.write_text('{"schema":"test"}\n', encoding="utf-8")
    _git(vault.root, "add", str(receipt_path.relative_to(vault.root)))
    _git(vault.root, "commit", "-m", "agent-state: receipt icloud-drive run")
    receipt_commit = _git(vault.root, "rev-parse", "HEAD")
    _git(vault.root, "push", "origin", "HEAD:main")
    (vault.root / "README.md").unlink()
    advance = tmp_path / "advance"
    subprocess.run(
        ["git", "clone", str(tmp_path / "remote.git"), str(advance)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(advance, "config", "user.name", "Limen Test")
    _git(advance, "config", "user.email", "limen@example.test")
    (advance / "unrelated.txt").write_text("later remote state\n", encoding="utf-8")
    _git(advance, "add", "unrelated.txt")
    _git(advance, "commit", "-m", "unrelated later custody")
    _git(advance, "push", "origin", "main")

    observed_payload, observed_receipt, receipt = vault.completed_receipt_at_remote(
        relative,
        "agent-state: receipt icloud-drive run",
    )

    assert observed_payload == payload_commit
    assert observed_receipt == receipt_commit
    assert receipt == '{"schema":"test"}'
    assert _git(vault.root, "status", "--porcelain=v1")


def test_remote_payload_restoration_reads_fetched_commit_not_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, relative, expected = _interrupted_vault(
        tmp_path,
        monkeypatch,
        remote_has_local_head=False,
    )
    _git(vault.root, "add", *(str(path) for path in expected[1:]))
    _git(vault.root, "commit", "-m", "agent-state: seal icloud-drive run")
    payload_commit = _git(vault.root, "rev-parse", "HEAD")
    _git(vault.root, "push", "origin", "HEAD:main")
    (vault.root / expected[0]).write_bytes(b"local-only")
    destination = tmp_path / "restored"

    vault.materialize_remote_payload(
        relative,
        payload_commit,
        [Path(path.name) for path in expected],
        destination,
    )

    assert (destination / expected[0].name).read_bytes() == b"aaaa"
    assert (destination / expected[1].name).read_bytes() == b"bbbb"
    assert (destination / expected[2].name).read_bytes() == b"ccc"
    assert (vault.root / expected[0]).read_bytes() == b"local-only"


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
