from __future__ import annotations

import hashlib
import json
import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import limen.estate_audit_custody as custody_module
import pytest
from limen.estate_audit_custody import (
    GENERATED_ROOT_RE,
    CustodyPlan,
    EstateAuditCustodyError,
    apply_plan,
    assert_custody_target_identity,
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


def test_git_environment_keeps_auth_explicit_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = tmp_path / "gh"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o700)
    monkeypatch.setattr(custody_module, "GH", str(helper))
    monkeypatch.setenv("GH_TOKEN", "must-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "99")
    monkeypatch.setenv("GIT_CONFIG_KEY_98", "credential.helper")
    monkeypatch.setenv("GIT_CONFIG_VALUE_98", "hostile")

    neutral = custody_module._git_environment()
    authenticated = custody_module._git_environment(github_auth=True)

    assert "GH_TOKEN" not in neutral
    assert "GITHUB_TOKEN" not in neutral
    assert "GIT_CONFIG_COUNT" not in neutral
    assert "GIT_CONFIG_KEY_98" not in neutral
    assert "GIT_CONFIG_VALUE_98" not in neutral
    assert authenticated["GIT_CONFIG_COUNT"] == "1"
    assert authenticated["GIT_CONFIG_KEY_0"] == "credential.https://github.com.helper"
    assert authenticated["GIT_CONFIG_VALUE_0"] == f"!{helper} auth git-credential"
    assert set(authenticated) - set(neutral) == {
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    }

    monkeypatch.setattr(custody_module, "GH", None)
    assert (
        error_code(lambda: custody_module._git_environment(github_auth=True)) == "github-credential-helper-unavailable"
    )


def test_deadline_git_timeout_is_fractional_and_fails_before_subsecond_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_timeouts: list[float] = []

    def fake_run(_arguments, **kwargs):
        observed_timeouts.append(kwargs["timeout"])
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(custody_module.subprocess, "run", fake_run)
    custody_module._run_git(tmp_path, ["status"], timeout=0.25)
    assert observed_timeouts == [0.25]

    monkeypatch.setattr(custody_module.time, "monotonic", lambda: 100.5)
    assert error_code(lambda: custody_module._scan_timeout(101.0)) == "campaign-time-limit-exceeded"
    assert observed_timeouts == [0.25]


def test_github_hydration_requires_the_explicit_credential_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010000")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"
    monkeypatch.setattr(custody_module, "GH", None)

    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256=plan.plan_sha256,
                revalidate=lambda: plan,
                remote_url_for=lambda _repository: "https://github.com/organvm/example.git",
                max_seconds=60,
                require_volume=False,
            )
        )
        == "github-credential-helper-unavailable"
    )
    assert not (custody / "receipts" / f"{plan.plan_sha256}.json").exists()


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
    assert len(public["working_payload_manifest_sha256"]) == 64
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


def test_live_payload_drift_rotates_receipt_and_reaches_a_fixed_point(tmp_path: Path) -> None:
    remote, head, _tree = make_remote(tmp_path)
    root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010506")
    (root / "README.md").write_text("captured state\n", encoding="utf-8")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"

    receipt, _changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: discover_plan(tmp_path, targets=[target]),
        remote_url_for=lambda _repository: str(remote),
        max_seconds=60,
        require_volume=False,
    )
    receipt_path = custody / "receipts" / f"{plan.plan_sha256}.json"
    original = receipt_path.read_bytes()
    root_identity = root.stat()
    index = git(root, "ls-files", "-s")

    (root / "README.md").write_text("stale payload!\n", encoding="utf-8")

    current = root.stat()
    assert git(root, "rev-parse", "HEAD") == head
    assert git(root, "ls-files", "-s") == index
    assert (current.st_dev, current.st_ino, current.st_mtime_ns) == (
        root_identity.st_dev,
        root_identity.st_ino,
        root_identity.st_mtime_ns,
    )
    assert discover_plan(tmp_path, targets=[target]).plan_sha256 == plan.plan_sha256
    assert (
        receipt["failed_checkout_states"][0]["payloads"][0]["payload_sha256"]
        != hashlib.sha256((root / "README.md").read_bytes()).hexdigest()
    )
    version_path = custody / "receipts" / f"{plan.plan_sha256}.{receipt['content_sha256']}.json"
    archive_deadline = custody_module.time.monotonic() + 60
    assert (
        custody_module._preserve_canonical_receipt(
            custody,
            plan.plan_sha256,
            receipt,
            deadline=archive_deadline,
        )
        is True
    )
    assert (
        custody_module._preserve_canonical_receipt(
            custody,
            plan.plan_sha256,
            receipt,
            deadline=archive_deadline,
        )
        is False
    )
    rotated, rotated_changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: discover_plan(tmp_path, targets=[target]),
        remote_url_for=lambda _repository: pytest.fail("existing receipt must not re-hydrate"),
        max_seconds=60,
        require_volume=False,
    )
    current_payload = (root / "README.md").read_bytes()
    current_payload_sha256 = hashlib.sha256(current_payload).hexdigest()
    rotated_payload = rotated["failed_checkout_states"][0]["payloads"][0]

    assert rotated_changed is True
    assert version_path.read_bytes() == original
    assert stat.S_IMODE(version_path.stat().st_mode) == 0o600
    assert receipt_path.read_bytes() != original
    assert rotated["content_sha256"] != receipt["content_sha256"]
    assert rotated_payload["payload_sha256"] == current_payload_sha256
    assert (custody / rotated_payload["store"]).read_bytes() == current_payload

    canonical = receipt_path.read_bytes()
    fixed_point, fixed_point_changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: pytest.fail("fixed-point receipt must not re-discover the plan"),
        remote_url_for=lambda _repository: pytest.fail("fixed-point receipt must not re-hydrate"),
        max_seconds=60,
        require_volume=False,
    )
    assert fixed_point_changed is False
    assert fixed_point == rotated
    assert receipt_path.read_bytes() == canonical
    assert version_path.read_bytes() == original
    assert sorted(path.name for path in (custody / "receipts").iterdir()) == sorted(
        [receipt_path.name, version_path.name]
    )


def test_expired_deadline_cannot_rotate_a_drifted_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010507")
    (root / "README.md").write_text("captured state\n", encoding="utf-8")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"
    receipt, _changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: discover_plan(tmp_path, targets=[target]),
        remote_url_for=lambda _repository: str(remote),
        max_seconds=60,
        require_volume=False,
    )
    receipt_path = custody / "receipts" / f"{plan.plan_sha256}.json"
    original = receipt_path.read_bytes()
    original_names = sorted(path.name for path in (custody / "receipts").iterdir())
    (root / "README.md").write_text("changed after capture\n", encoding="utf-8")

    now = [100.0]
    deadline = 200.0
    original_verify_live = custody_module._verify_live_failed_checkout_states

    def expire_after_drift(
        current_receipt: dict[str, object],
        *,
        deadline: float,
    ) -> None:
        try:
            original_verify_live(current_receipt, deadline=deadline)
        except EstateAuditCustodyError as exc:
            assert exc.code == "failed-checkout-content-drift"
            now[0] = deadline
            raise

    monkeypatch.setattr(custody_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        custody_module,
        "_verify_live_failed_checkout_states",
        expire_after_drift,
    )
    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256=plan.plan_sha256,
                revalidate=lambda: pytest.fail("expired rotation must not re-discover"),
                remote_url_for=lambda _repository: pytest.fail("expired rotation must not re-hydrate"),
                max_seconds=60,
                require_volume=False,
                deadline=deadline,
            )
        )
        == "campaign-time-limit-exceeded"
    )
    assert receipt_path.read_bytes() == original
    assert sorted(path.name for path in (custody / "receipts").iterdir()) == original_names
    assert receipt["content_sha256"] in original.decode("utf-8")


def test_receipt_rotation_refuses_a_conflicting_historical_name(
    tmp_path: Path,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010508")
    (root / "README.md").write_text("captured state\n", encoding="utf-8")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"
    receipt, _changed = apply_plan(
        plan,
        custody,
        expected_plan_sha256=plan.plan_sha256,
        revalidate=lambda: discover_plan(tmp_path, targets=[target]),
        remote_url_for=lambda _repository: str(remote),
        max_seconds=60,
        require_volume=False,
    )
    canonical = custody / "receipts" / f"{plan.plan_sha256}.json"
    original = canonical.read_bytes()
    version = custody / "receipts" / f"{plan.plan_sha256}.{receipt['content_sha256']}.json"
    version.write_bytes(b"conflicting fixture\n")
    version.chmod(0o600)
    (root / "README.md").write_text("changed after capture\n", encoding="utf-8")

    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256=plan.plan_sha256,
                revalidate=lambda: pytest.fail("conflict must block before revalidation"),
                remote_url_for=lambda _repository: pytest.fail("conflict must not re-hydrate"),
                max_seconds=60,
                require_volume=False,
            )
        )
        == "custody-receipt-version-conflict"
    )
    assert canonical.read_bytes() == original
    assert version.read_bytes() == b"conflicting fixture\n"


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


def test_receipt_read_rejects_limit_plus_one_without_exposing_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custody = tmp_path / "custody"
    receipt_directory = custody / "receipts"
    receipt_directory.mkdir(parents=True)
    receipt = receipt_directory / f"{'a' * 64}.json"
    receipt.write_bytes(b"x" * 65)
    receipt.chmod(0o600)
    monkeypatch.setattr(custody_module, "MAX_CUSTODY_RECEIPT_BYTES", 64)

    with pytest.raises(EstateAuditCustodyError) as raised:
        verify_receipt(
            custody,
            "a" * 64,
            max_seconds=60,
            require_volume=False,
        )
    assert raised.value.code == "custody-receipt-size-limit"
    assert str(tmp_path) not in str(raised.value)


def test_expected_volume_and_stable_physical_identity_are_both_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_uuid = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
    expected_physical = "device_" + "1" * 32
    volume = tmp_path / "Fixture"
    custody = volume / "limen-private" / "custody"
    custody.mkdir(parents=True)

    def fake_run(arguments, **_kwargs):
        assert arguments[-1] == str(custody)
        return SimpleNamespace(
            returncode=0,
            stdout=plistlib.dumps(
                {
                    "MountPoint": str(volume),
                    "VolumeUUID": expected_uuid,
                }
            ),
        )

    monkeypatch.setattr(custody_module.subprocess, "run", fake_run)
    observed_mounts: list[Path] = []

    def device_identity(mount: Path) -> str:
        observed_mounts.append(mount)
        return expected_physical

    monkeypatch.setattr(custody_module, "_device_identity", device_identity)
    assert_custody_target_identity(
        custody,
        expected_volume_uuid=expected_uuid,
        expected_physical_identity=expected_physical,
    )
    assert observed_mounts == [volume]

    monkeypatch.setattr(custody_module, "_device_identity", lambda _mount: "device_" + "2" * 32)
    assert (
        error_code(
            lambda: assert_custody_target_identity(
                custody,
                expected_volume_uuid=expected_uuid,
                expected_physical_identity=expected_physical,
            )
        )
        == "custody-target-identity-mismatch"
    )


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        ("ancestor", "custody-target-path-indirection"),
        ("final", "custody-target-path-indirection"),
        ("loop", "custody-target-path-indirection"),
        ("traversal", "custody-target-path-indirection"),
    ],
)
def test_custody_path_indirection_fails_before_identity_probe_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape: str,
    expected: str,
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    if shape == "ancestor":
        alias = tmp_path / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        custody = alias / "custody"
    elif shape == "final":
        target = actual / "target"
        target.mkdir()
        custody = actual / "custody"
        custody.symlink_to(target, target_is_directory=True)
    elif shape == "loop":
        left = tmp_path / "left"
        right = tmp_path / "right"
        left.symlink_to(right)
        right.symlink_to(left)
        custody = left / "custody"
    else:
        custody = actual / ".." / "actual" / "custody"

    def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("identity probe must not run for an indirect path")

    monkeypatch.setattr(custody_module.subprocess, "run", unexpected_probe)
    assert (
        error_code(
            lambda: assert_custody_target_identity(
                custody,
                expected_volume_uuid="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
                expected_physical_identity="device_" + "1" * 32,
            )
        )
        == expected
    )
    assert not (actual / "custody" / "receipts" / f"{'a' * 64}.json").exists()


def test_identity_swap_at_apply_mutation_boundary_fails_before_receipt(
    tmp_path: Path,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010809")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"
    calls = 0

    def identity_guard(resolved_root: Path) -> None:
        nonlocal calls
        assert resolved_root == custody.resolve()
        calls += 1
        if calls == 4:
            raise EstateAuditCustodyError("custody-target-identity-mismatch")

    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256=plan.plan_sha256,
                revalidate=lambda: plan,
                remote_url_for=lambda _repository: str(remote),
                max_seconds=60,
                require_volume=False,
                identity_guard=identity_guard,
            )
        )
        == "custody-target-identity-mismatch"
    )
    assert calls == 4
    assert custody.is_dir()
    assert not (custody / "receipts" / f"{plan.plan_sha256}.json").exists()


def test_identity_swap_after_full_restore_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010810")
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
    swapped = False
    original_restore = custody_module._restore_repository

    def swapping_restore(*args, **kwargs):
        nonlocal swapped
        result = original_restore(*args, **kwargs)
        swapped = True
        return result

    def identity_guard(resolved_root: Path) -> None:
        assert resolved_root == custody.resolve()
        if swapped:
            raise EstateAuditCustodyError("custody-target-identity-mismatch")

    monkeypatch.setattr(custody_module, "_restore_repository", swapping_restore)
    assert (
        error_code(
            lambda: verify_receipt(
                custody,
                plan.plan_sha256,
                max_seconds=60,
                require_volume=False,
                identity_guard=identity_guard,
            )
        )
        == "custody-target-identity-mismatch"
    )


def test_late_revalidation_cannot_write_a_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote, _head, _tree = make_remote(tmp_path)
    _root, target = make_failed_checkout(tmp_path, remote, stamp="20260727010811")
    plan = discover_plan(tmp_path, targets=[target])
    custody = tmp_path / "custody"
    now = [100.0]
    deadline = 200.0
    monkeypatch.setattr(custody_module.time, "monotonic", lambda: now[0])

    def late_revalidate() -> CustodyPlan:
        now[0] = deadline
        return plan

    assert (
        error_code(
            lambda: apply_plan(
                plan,
                custody,
                expected_plan_sha256=plan.plan_sha256,
                revalidate=late_revalidate,
                remote_url_for=lambda _repository: str(remote),
                max_seconds=60,
                require_volume=False,
                deadline=deadline,
            )
        )
        == "campaign-time-limit-exceeded"
    )
    assert not (custody / "receipts" / f"{plan.plan_sha256}.json").exists()


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


def test_cli_rejects_incomplete_expected_device_contract_before_discovery(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--json",
            "--limen-root",
            str(tmp_path),
            "--expected-volume-uuid",
            "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["error"] == "expected-custody-identity-incomplete"
    assert str(tmp_path) not in json.dumps(payload, sort_keys=True)
