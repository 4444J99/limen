from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from limen.estate_audit_custody import (
    GENERATED_ROOT_RE,
    CustodyPlan,
    EstateAuditCustodyError,
    apply_plan,
    discover_plan,
    preflight_plan,
    public_receipt,
    verify_failed_checkout_content,
    verify_receipt,
)
from limen.worktree_roots import WorktreeTarget

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "estate-audit-custody.py"


def git(cwd: Path, *arguments: str) -> str:
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def make_remote(tmp_path: Path) -> tuple[Path, str, str]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--quiet", "--initial-branch=main")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test")
    (source / "README.md").write_text("custody fixture\n", encoding="utf-8")
    executable = source / "scripts" / "run.sh"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    git(source, "add", ".")
    git(source, "commit", "--quiet", "-m", "fixture")
    head = git(source, "rev-parse", "HEAD")
    tree = git(source, "rev-parse", "HEAD^{tree}")
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "--quiet", "--bare", str(source), str(remote))
    return remote, head, tree


def make_failed_checkout(
    tmp_path: Path,
    remote: Path,
    *,
    stamp: str,
    empty_index: bool = True,
) -> tuple[Path, WorktreeTarget]:
    root = tmp_path / f"estate-audit-example-{stamp}"
    git(tmp_path, "clone", "--quiet", str(remote), str(root))
    git(root, "remote", "set-url", "origin", "https://github.com/organvm/example.git")
    if empty_index:
        git(root, "read-tree", "--empty")
    return root, WorktreeTarget(path=root, min_age_h=0, source="test-inventory")


def error_code(callable_) -> str:
    with pytest.raises(EstateAuditCustodyError) as raised:
        callable_()
    return raised.value.code


def test_generated_name_is_strict_and_plan_is_dynamic_and_public_safe(tmp_path: Path) -> None:
    remote, head, _tree = make_remote(tmp_path)
    first, first_target = make_failed_checkout(tmp_path, remote, stamp="20260727010101")
    second, second_target = make_failed_checkout(tmp_path, remote, stamp="20260727010202")
    non_generated = WorktreeTarget(
        path=tmp_path / "estate-audit-custody-20260727",
        min_age_h=0,
        source="test-inventory",
    )

    plan = discover_plan(tmp_path, targets=[first_target, non_generated, second_target])
    public = plan.public_payload()
    encoded = json.dumps(public, sort_keys=True)

    assert GENERATED_ROOT_RE.fullmatch(first.name)
    assert not GENERATED_ROOT_RE.fullmatch(non_generated.path.name)
    assert public["root_count"] == 2
    assert public["repository_count"] == 1
    assert public["head_count"] == 1
    assert public["empty_index_root_count"] == 2
    assert public["indexed_root_count"] == 0
    assert str(first) not in encoded
    assert str(second) not in encoded
    assert "organvm/example" not in encoded
    assert head not in encoded


def test_discovery_fails_closed_for_empty_scope_and_limits_but_keeps_indexed_roots(tmp_path: Path) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _root, target = make_failed_checkout(
        tmp_path,
        remote,
        stamp="20260727010303",
        empty_index=False,
    )

    assert error_code(lambda: discover_plan(tmp_path, targets=[])) == "no-generated-roots"
    indexed = discover_plan(tmp_path, targets=[target])
    assert indexed.indexed_root_count == 1
    assert indexed.empty_index_root_count == 0
    assert error_code(lambda: discover_plan(tmp_path, targets=[target], max_roots=1001)) == "invalid-root-limit"


def test_failed_checkout_content_requires_exact_paths_modes_and_blobs(tmp_path: Path) -> None:
    remote, head, tree = make_remote(tmp_path)
    root, _target = make_failed_checkout(tmp_path, remote, stamp="20260727010404")

    exact = verify_failed_checkout_content(root, expected_head=head, expected_tree=tree)
    assert exact.exact is True
    assert exact.reason == "exact-head-content"
    assert exact.file_count == 2

    (root / "README.md").write_text("drift\n", encoding="utf-8")
    changed = verify_failed_checkout_content(root, expected_head=head, expected_tree=tree)
    assert changed.exact is False
    assert changed.reason == "blob-mismatch"

    (root / "README.md").write_text("custody fixture\n", encoding="utf-8")
    (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    extra = verify_failed_checkout_content(root, expected_head=head, expected_tree=tree)
    assert extra.exact is False
    assert extra.reason == "path-outside-head"

    (root / "extra.txt").unlink()
    (root / "README.md").unlink()
    subset = verify_failed_checkout_content(root, expected_head=head, expected_tree=tree)
    assert subset.exact is True
    assert subset.reason == "exact-head-content-subset"
    assert subset.file_count == 1


def test_apply_restores_fresh_receipt_is_private_and_second_apply_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010505")
    (root / "README.md").write_text("materialized payload\n", encoding="utf-8")
    plan = discover_plan(tmp_path, targets=[target])
    preflight = preflight_plan(plan, max_seconds=60)
    custody = tmp_path / "custody"
    hostile_config = tmp_path / "hostile.gitconfig"
    hostile_config.write_text(
        f'[url "file:///definitely-missing"]\n\tinsteadOf = {remote}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile_config))

    receipt, changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: discover_plan(tmp_path, targets=[target]),
        remote_url_for=lambda _repository: str(remote),
        max_seconds=60,
        require_volume=False,
    )
    public = public_receipt(receipt, changed=changed)
    receipt_path = custody / "receipts" / f"{plan.plan_sha256}.json"
    original = receipt_path.read_bytes()
    encoded = json.dumps(public, sort_keys=True)

    assert changed is True
    assert preflight["content_preflight_ok"] is True
    assert preflight["working_payload_count"] == 1
    assert preflight["working_payload_unique_count"] == 1
    assert receipt["restoration_passed"] is True
    assert public["status"] == "restored"
    assert public["root_count"] == 1
    assert public["empty_index_root_count"] == 1
    assert public["indexed_root_count"] == 0
    assert public["working_payload_count"] == 1
    assert public["working_payload_unique_count"] == 1
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert str(root) not in encoded
    assert "organvm/example" not in encoded
    assert receipt["roots"][0]["head"] not in encoded
    payload = receipt["failed_checkout_states"][0]["payloads"][0]
    payload_path = custody / payload["store"]
    assert stat.S_IMODE(payload_path.stat().st_mode) == 0o600

    second, second_changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: pytest.fail("idempotent receipt must not re-scan source roots"),
        remote_url_for=lambda _repository: pytest.fail("idempotent receipt must not re-hydrate"),
        max_seconds=60,
        require_volume=False,
    )
    assert second_changed is False
    assert second == receipt
    assert receipt_path.read_bytes() == original

    verified = verify_receipt(
        custody,
        plan.plan_sha256,
        full_restore=True,
        max_seconds=60,
        require_volume=False,
    )
    assert verified == receipt

    payload_path.write_text("corrupt\n", encoding="utf-8")
    payload_path.chmod(0o600)
    assert (
        error_code(
            lambda: verify_receipt(
                custody,
                plan.plan_sha256,
                full_restore=True,
                max_seconds=60,
                require_volume=False,
            )
        )
        == "payload-store-content-mismatch"
    )


def test_apply_requires_exact_plan_and_revalidation_before_receipt(tmp_path: Path) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _first, first_target = make_failed_checkout(tmp_path, remote, stamp="20260727010606")
    _second, second_target = make_failed_checkout(tmp_path, remote, stamp="20260727010707")
    plan = discover_plan(tmp_path, targets=[first_target])
    custody = tmp_path / "custody"

    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256="0" * 64,
                revalidate=lambda: plan,
                remote_url_for=lambda _repository: str(remote),
                require_volume=False,
            )
        )
        == "plan-sha-mismatch"
    )
    assert not custody.exists()

    expanded = discover_plan(tmp_path, targets=[first_target, second_target])
    assert isinstance(expanded, CustodyPlan)
    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256=plan.plan_sha256,
                revalidate=lambda: expanded,
                remote_url_for=lambda _repository: str(remote),
                max_seconds=60,
                require_volume=False,
            )
        )
        == "plan-changed-before-receipt"
    )
    assert not (custody / "receipts" / f"{plan.plan_sha256}.json").exists()


def test_receipt_mode_is_part_of_verification(tmp_path: Path) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010808")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"
    apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: plan,
        remote_url_for=lambda _repository: str(remote),
        max_seconds=60,
        require_volume=False,
    )
    receipt_path = custody / "receipts" / f"{plan.plan_sha256}.json"
    receipt_path.chmod(0o644)

    assert (
        error_code(
            lambda: verify_receipt(
                custody,
                plan.plan_sha256,
                max_seconds=60,
                require_volume=False,
            )
        )
        == "custody-receipt-mode-invalid"
    )


def test_cli_check_emits_only_public_dynamic_preflight(tmp_path: Path) -> None:
    remote, head, _tree = make_remote(tmp_path)
    root, _target = make_failed_checkout(tmp_path, remote, stamp="20260727010909")
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LIMEN_WORKTREE_ROOT": str(tmp_path),
    }

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--json",
            "--limen-root",
            str(tmp_path),
            "--max-seconds",
            "60",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["root_count"] == 1
    assert payload["content_preflight_ok"] is True
    assert payload["failed_checkout_root_count"] == 1
    assert str(root) not in encoded
    assert "organvm/example" not in encoded
    assert head not in encoded
