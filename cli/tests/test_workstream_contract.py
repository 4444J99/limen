from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

import limen.census as C
import limen.workstream_contract as W
from limen.workstream_contract import (
    AUTHORIZATION,
    IDENTITY_MODULES,
    RECEIPT_MODULES,
    ContractError,
    RunwayExpired,
    admit_contract,
    configure_contract,
    new_contract,
    packet_contract,
    parse_runway,
    read_contract,
    run_bounded,
    sync_identity,
    sync_receipt,
    validate_codex_launch,
    validate_packet_contract,
)


def test_runway_admission_is_idempotent_inherited_and_expires_at_exact_boundary(tmp_path: Path) -> None:
    path = tmp_path / "workstream.json"
    configured, changed = configure_contract(path, "2d")
    assert changed is True
    assert configured["runway"]["duration_seconds"] == 172_800

    admitted, remaining = admit_contract(path, now_epoch=1_000)
    assert remaining == 172_800
    assert admitted["runway"]["deadline_epoch"] == 173_800
    admitted_bytes = path.read_bytes()

    inherited, inherited_remaining = admit_contract(path, now_epoch=1_001)
    assert inherited_remaining == 172_799
    assert inherited["runway"]["started_epoch"] == 1_000
    assert path.read_bytes() == admitted_bytes

    configured_again, changed_again = configure_contract(path)
    assert changed_again is False
    assert configured_again["runway"]["deadline_epoch"] == 173_800
    assert path.read_bytes() == admitted_bytes

    with pytest.raises(ContractError, match="cannot change an admitted runway"):
        configure_contract(path, "3d")
    with pytest.raises(RunwayExpired, match="exhausted"):
        admit_contract(path, now_epoch=173_800)


@pytest.mark.parametrize("raw", ["", "forever", "0h", "14m", "31d", "-1h", "1.5h"])
def test_runway_rejects_malformed_or_unbounded_values(raw: str) -> None:
    with pytest.raises(ContractError):
        parse_runway(raw)


def test_contract_rejects_authorization_drift_and_packet_contract_is_typed(tmp_path: Path) -> None:
    path = tmp_path / "workstream.json"
    configure_contract(path, "8h")
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["authorization"]["approval_mode"] = "ask"
    path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ContractError, match="authorization"):
        read_contract(path)

    timing_path = tmp_path / "timing.json"
    configure_contract(timing_path, "8h")
    admit_contract(timing_path, now_epoch=10_000)
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    timing["runway"]["started_at"] = "2099-01-01T00:00:00+00:00"
    timing_path.write_text(json.dumps(timing), encoding="utf-8")
    with pytest.raises(ContractError, match="timing state"):
        read_contract(timing_path)

    packet = packet_contract("8h", now_epoch=12_345)
    assert packet["runway"]["duration_seconds"] == 28_800
    assert packet["runway"]["started_epoch"] == 12_345
    assert packet["runway"]["deadline_epoch"] == 41_145
    assert packet["authorization"] == AUTHORIZATION
    assert packet["authorization"]["mode"] == "full_non_destructive"
    assert packet["conductor"]["mode"] == "route_bounded_packets"

    tampered_packet = json.loads(json.dumps(packet))
    tampered_packet["runway"]["deadline_epoch"] += 1
    with pytest.raises(ContractError, match="timing"):
        validate_packet_contract(tampered_packet)


def test_contract_instances_cannot_poison_the_validation_baseline() -> None:
    first = new_contract("1d")
    second = new_contract("1d")

    first["authorization"]["retained_gates"].append("fixture")

    assert "fixture" not in second["authorization"]["retained_gates"]
    assert "fixture" not in AUTHORIZATION["retained_gates"]


def test_explicit_codex_launch_contract_is_v2_and_retains_high_risk_gates(tmp_path: Path) -> None:
    path = tmp_path / "workstream.json"
    contract, changed = configure_contract(
        path,
        "8h",
        agent="codex",
        model="fixture-model-renamed-at-runtime",
        reasoning_effort="extreme-fixture",
        sandbox="danger-full-access",
    )

    assert changed is True
    assert contract["schema"] == "limen.workstream.contract.v2"
    assert contract["primary_launch"] == {
        "agent": "codex",
        "model": "fixture-model-renamed-at-runtime",
        "reasoning_effort": "extreme-fixture",
        "selection": "human_explicit",
    }
    assert contract["authorization"]["approval_mode"] == "never"
    assert contract["authorization"]["sandbox"] == "danger-full-access"
    assert contract["authorization"]["retained_gates"] == AUTHORIZATION["retained_gates"]
    assert read_contract(path) == contract

    unchanged, unchanged_flag = configure_contract(
        path,
        "8h",
        agent="codex",
        model="fixture-model-renamed-at-runtime",
        reasoning_effort="extreme-fixture",
        sandbox="danger-full-access",
    )
    assert unchanged_flag is False
    assert unchanged == contract

    with pytest.raises(ContractError, match="emit a successor"):
        configure_contract(
            path,
            "8h",
            agent="codex",
            model="different-live-model",
            reasoning_effort="extreme-fixture",
            sandbox="danger-full-access",
        )


def test_default_contract_remains_byte_compatible_v1(tmp_path: Path) -> None:
    path = tmp_path / "workstream.json"
    contract, _changed = configure_contract(path, "8h")

    assert contract == new_contract("8h")
    assert contract["schema"] == "limen.workstream.contract.v1"
    assert set(contract) == {"schema", "runway", "authorization", "conductor"}
    assert contract["authorization"]["sandbox"] == "workspace-write"


def test_live_codex_catalog_validation_uses_exact_dynamic_ids(tmp_path: Path) -> None:
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        (
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' "
            '\'{"models":[{"slug":"fixture-zeta","supported_reasoning_levels":'
            '[{"effort":"low"},{"effort":"ultra-fixture"}]}]}\'\n'
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    selected = validate_codex_launch(
        str(fake_codex),
        model="fixture-zeta",
        reasoning_effort="ultra-fixture",
    )
    assert selected["slug"] == "fixture-zeta"

    with pytest.raises(ContractError, match="not present"):
        validate_codex_launch(
            str(fake_codex),
            model="fixture-removed",
            reasoning_effort="ultra-fixture",
        )
    with pytest.raises(ContractError, match="does not support"):
        validate_codex_launch(
            str(fake_codex),
            model="fixture-zeta",
            reasoning_effort="renamed-effort",
        )
    with pytest.raises(ContractError, match="sandbox"):
        configure_contract(
            tmp_path / "invalid-sandbox.json",
            "8h",
            agent="codex",
            model="fixture-zeta",
            reasoning_effort="ultra-fixture",
            sandbox="host-everything",
        )


def test_admission_waits_on_the_stable_parent_lock_and_preserves_first_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "workstream.json"
    configure_contract(path, "1d")
    original_flock = fcntl.flock
    holder = os.open(tmp_path, os.O_RDONLY)
    original_flock(holder, fcntl.LOCK_EX)
    attempted = threading.Event()

    def tracked_flock(descriptor: int, operation: int) -> None:
        if threading.current_thread() is not threading.main_thread() and operation & fcntl.LOCK_EX:
            attempted.set()
        original_flock(descriptor, operation)

    monkeypatch.setattr(W.fcntl, "flock", tracked_flock)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(admit_contract, path, now_epoch=1_000)
    try:
        assert attempted.wait(timeout=1)
        assert future.done() is False
        original_flock(holder, fcntl.LOCK_UN)
        admitted, remaining = future.result(timeout=1)
    finally:
        try:
            original_flock(holder, fcntl.LOCK_UN)
        finally:
            os.close(holder)
            executor.shutdown(wait=True)

    inherited, inherited_remaining = admit_contract(path, now_epoch=2_000)
    assert admitted["runway"]["started_epoch"] == 1_000
    assert remaining == 86_400
    assert inherited["runway"]["started_epoch"] == 1_000
    assert inherited_remaining == 85_400


def _receipt_modules(capsule: Path) -> list[tuple[str, Path]]:
    for name in IDENTITY_MODULES:
        path = capsule / name
        if name != "workstream.json":
            path.write_text(f"private {name}\n", encoding="utf-8")
    _sync_receipt_identity(capsule)
    return [(name, capsule / name) for name in RECEIPT_MODULES]


def _sync_receipt_identity(capsule: Path) -> None:
    sync_identity(
        capsule / "capsule.identity",
        invocation_sha256="0" * 64,
        modules=[(name, capsule / name) for name in IDENTITY_MODULES],
    )


def _git_fixture(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def _committed_predecessor(tmp_path: Path, *, explicit_profile: bool = False) -> tuple[Path, bytes, dict[str, object]]:
    repo = tmp_path / "predecessor-repo"
    repo.mkdir()
    _git_fixture("init", "-q", "-b", "work/predecessor", cwd=repo)
    _git_fixture("config", "user.email", "test@example.invalid", cwd=repo)
    _git_fixture("config", "user.name", "Test User", cwd=repo)
    remote = tmp_path / "predecessor-origin.git"
    remote.mkdir()
    _git_fixture("init", "--bare", "-q", cwd=remote)
    _git_fixture("remote", "add", "origin", str(remote), cwd=repo)
    capsule = repo / ".limen-workstream"
    contract_path = capsule / "workstream.json"
    launch = (
        {
            "agent": "codex",
            "model": "fixture-sol",
            "reasoning_effort": "high",
            "sandbox": "danger-full-access",
        }
        if explicit_profile
        else {}
    )
    configure_contract(contract_path, "16d", **launch)
    admitted, _remaining = admit_contract(contract_path, now_epoch=1_754_000_000)
    modules = _receipt_modules(capsule)
    receipt = repo / "docs" / "continuations" / "predecessor" / "workstream.json"
    sync_receipt(
        contract_path,
        receipt,
        slug="predecessor",
        branch="work/predecessor",
        workstream="alpha-omega",
        modules=modules,
    )
    _git_fixture("add", "docs/continuations/predecessor/workstream.json", cwd=repo)
    _git_fixture("commit", "-qm", "docs: preserve predecessor receipt", cwd=repo)
    _git_fixture("push", "-u", "origin", "work/predecessor", cwd=repo)
    return receipt, receipt.read_bytes(), admitted


def test_successor_inherits_exact_admitted_timing_and_records_only_path_free_lineage(tmp_path: Path) -> None:
    predecessor, predecessor_bytes, admitted = _committed_predecessor(tmp_path, explicit_profile=True)
    successor_capsule = tmp_path / "successor" / ".limen-workstream"
    successor_contract_path = successor_capsule / "workstream.json"

    contract, lineage, changed = W.configure_successor_contract(successor_contract_path, predecessor)

    assert changed is True
    assert contract["schema"] == "limen.workstream.contract.v1"
    assert admitted["schema"] == "limen.workstream.contract.v2"
    assert admitted["authorization"]["sandbox"] == "danger-full-access"
    assert contract["runway"] == admitted["runway"]
    assert contract["authorization"] == AUTHORIZATION
    assert contract["conductor"]["provider_and_model"] == "provider_neutral"
    assert lineage == {
        "slug": "predecessor",
        "branch": "work/predecessor",
        "receipt_sha256": hashlib.sha256(predecessor_bytes).hexdigest(),
    }
    modules = _receipt_modules(successor_capsule)
    successor_receipt = tmp_path / "successor" / "docs" / "continuations" / "successor" / "workstream.json"
    value, _receipt_changed = sync_receipt(
        successor_contract_path,
        successor_receipt,
        slug="successor",
        branch="work/successor",
        workstream="alpha-omega",
        modules=modules,
        predecessor_slug=lineage["slug"],
        predecessor_branch=lineage["branch"],
        predecessor_receipt_sha256=lineage["receipt_sha256"],
    )
    serialized = successor_receipt.read_text(encoding="utf-8")
    assert value["predecessor"] == lineage
    assert str(predecessor) not in serialized
    assert predecessor.read_bytes() == predecessor_bytes


def test_successor_renewal_is_distinct_unstarted_and_provider_neutral(tmp_path: Path) -> None:
    predecessor, predecessor_bytes, admitted = _committed_predecessor(tmp_path, explicit_profile=True)

    renewed, lineage = W.successor_contract(predecessor, runway_mode="renew", requested="2d")

    assert admitted["schema"] == "limen.workstream.contract.v2"
    assert admitted["authorization"]["sandbox"] == "danger-full-access"
    assert renewed["schema"] == "limen.workstream.contract.v1"
    assert renewed["runway"]["requested"] == "2d"
    assert renewed["runway"]["duration_seconds"] == 172_800
    assert renewed["runway"]["started_epoch"] is None
    assert renewed["runway"]["deadline_epoch"] is None
    assert "primary_launch" not in renewed
    assert renewed["authorization"] == AUTHORIZATION
    assert renewed["authorization"]["sandbox"] == "workspace-write"
    assert renewed["conductor"]["provider_and_model"] == "provider_neutral"
    assert set(lineage) == {"slug", "branch", "receipt_sha256"}
    assert predecessor.read_bytes() == predecessor_bytes


def test_successor_rejects_mode_drift_and_uncommitted_predecessor_bytes(tmp_path: Path) -> None:
    predecessor, predecessor_bytes, _admitted = _committed_predecessor(tmp_path)

    with pytest.raises(ContractError, match="cannot specify a new runway"):
        W.successor_contract(predecessor, runway_mode="inherit", requested="1d")
    with pytest.raises(ContractError, match="require an explicit runway"):
        W.successor_contract(predecessor, runway_mode="renew")

    predecessor.write_bytes(predecessor_bytes + b"\n")
    with pytest.raises(ContractError, match="committed HEAD bytes"):
        W.successor_contract(predecessor)


def test_predecessor_receipt_growth_during_descriptor_read_hits_the_hard_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor, _predecessor_bytes, _admitted = _committed_predecessor(tmp_path)
    original_read = os.read
    grew = False

    def grow_then_read(descriptor: int, size: int) -> bytes:
        nonlocal grew
        if not grew:
            with predecessor.open("ab") as stream:
                stream.write(b"x" * W.PREDECESSOR_RECEIPT_CEILING)
            grew = True
        return original_read(descriptor, size)

    monkeypatch.setattr(W.os, "read", grow_then_read)

    with pytest.raises(ContractError, match="exceeds its bounded size"):
        W.predecessor_custody(predecessor)
    assert grew is True


def test_predecessor_receipt_fifo_without_a_writer_is_rejected_without_blocking(tmp_path: Path) -> None:
    predecessor = tmp_path / "receipt-fifo"
    os.mkfifo(predecessor)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "from pathlib import Path\n"
                "from limen.workstream_contract import ContractError, predecessor_custody\n"
                "try:\n"
                "    predecessor_custody(Path(sys.argv[1]))\n"
                "except ContractError as exc:\n"
                "    raise SystemExit(0 if str(exc) == 'predecessor receipt must be a real file' else 2)\n"
                "raise SystemExit(1)\n"
            ),
            str(predecessor),
        ],
        check=False,
        timeout=2,
    )

    assert probe.returncode == 0


def test_predecessor_receipt_growth_during_git_custody_fails_without_a_second_path_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor, _predecessor_bytes, _admitted = _committed_predecessor(tmp_path)
    original_git_control = W._git_control
    replaced = False

    def replace_then_probe(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            predecessor.write_bytes(b"x" * (W.PREDECESSOR_RECEIPT_CEILING + 1))
            replaced = True
        return original_git_control(*args, **kwargs)

    monkeypatch.setattr(W, "_git_control", replace_then_probe)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _path: pytest.fail("predecessor custody must not reopen the path for an unbounded read"),
    )

    with pytest.raises(ContractError, match="changed during bounded capture"):
        W.predecessor_custody(predecessor)
    assert replaced is True


def test_predecessor_receipt_change_during_final_remote_probe_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor, _predecessor_bytes, _admitted = _committed_predecessor(tmp_path)
    original_git_control = W._git_control
    changed = False

    def change_after_remote_probe(*args, **kwargs):
        nonlocal changed
        result = original_git_control(*args, **kwargs)
        if len(args) > 1 and args[1] == "ls-remote" and not changed:
            with predecessor.open("ab") as stream:
                stream.write(b"\n")
            changed = True
        return result

    monkeypatch.setattr(W, "_git_control", change_after_remote_probe)

    with pytest.raises(ContractError, match="changed during bounded capture"):
        W.predecessor_custody(predecessor)
    assert changed is True


def test_successor_rejects_receipt_branch_that_does_not_match_checkout(tmp_path: Path) -> None:
    predecessor, _predecessor_bytes, _admitted = _committed_predecessor(tmp_path)
    repo = predecessor.parents[3]
    value = json.loads(predecessor.read_text(encoding="utf-8"))
    value["branch"] = "work/different-predecessor"
    predecessor.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git_fixture("add", str(predecessor.relative_to(repo)), cwd=repo)
    _git_fixture("commit", "-qm", "test: mismatch predecessor branch", cwd=repo)

    with pytest.raises(ContractError, match="does not match its checkout branch"):
        W.successor_contract(predecessor)


def test_successor_rejects_predecessor_head_without_exact_remote_custody(tmp_path: Path) -> None:
    predecessor, _predecessor_bytes, _admitted = _committed_predecessor(tmp_path)
    repo = predecessor.parents[3]
    (repo / "unpushed.txt").write_text("not remotely custodied\n", encoding="utf-8")
    _git_fixture("add", "unpushed.txt", cwd=repo)
    _git_fixture("commit", "-qm", "test: leave predecessor head local", cwd=repo)

    with pytest.raises(ContractError, match="not the exact origin branch head"):
        W.successor_contract(predecessor)


@pytest.mark.parametrize(
    ("stream", "ceiling"),
    [
        ("stdout", W.GIT_CONTROL_STDOUT_CEILING),
        ("stderr", W.GIT_CONTROL_STDERR_CEILING),
    ],
)
def test_predecessor_git_probes_fail_at_hard_output_ceilings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stream: str,
    ceiling: int,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        (f'#!/usr/bin/env python3\nimport sys\nsys.{stream}.buffer.write(b"x" * {ceiling + 1})\n'),
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    with pytest.raises(ContractError, match="output ceiling"):
        W._git_control(tmp_path, "rev-parse", "--show-toplevel")


@pytest.mark.parametrize(("field", "invalid"), [("slug", 1), ("branch", 1), ("workstream", 1)])
def test_predecessor_receipt_rejects_non_string_metadata(field: str, invalid: object, tmp_path: Path) -> None:
    predecessor, _predecessor_bytes, _admitted = _committed_predecessor(tmp_path)
    value = json.loads(predecessor.read_text(encoding="utf-8"))
    value[field] = invalid

    with pytest.raises(ContractError, match="metadata types"):
        W.validate_workstream_receipt(value)


def test_redacted_receipt_is_idempotent_and_contains_no_private_paths_or_bodies(tmp_path: Path) -> None:
    capsule = tmp_path / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = tmp_path / "docs" / "continuations" / "demo" / "workstream.json"
    configure_contract(contract, "8h")
    modules = _receipt_modules(capsule)

    value, changed = sync_receipt(
        contract,
        receipt,
        slug="demo",
        branch="work/demo",
        workstream="",
        modules=modules,
    )
    receipt_bytes = receipt.read_bytes()
    receipt_mtime = receipt.stat().st_mtime_ns
    repeated, repeated_changed = sync_receipt(
        contract,
        receipt,
        slug="demo",
        branch="work/demo",
        workstream=None,
        modules=modules,
    )

    assert changed is True
    assert repeated_changed is False
    assert repeated == value
    assert receipt.read_bytes() == receipt_bytes
    assert receipt.stat().st_mtime_ns == receipt_mtime
    assert value["schema"] == "limen.workstream.receipt.v1"
    assert value["workstream"] is None
    assert value["contract"] == read_contract(contract)
    assert value["private_capsule"] == {
        "content": "redacted",
        "modules": list(RECEIPT_MODULES),
    }
    rendered = receipt.read_text(encoding="utf-8")
    assert str(tmp_path) not in rendered
    assert "private intent.md" not in rendered
    assert not __import__("re").search(r'"[0-9a-f]{64}"', rendered)


@pytest.mark.parametrize(
    ("branch", "workstream"),
    [
        ("work/demo", "private/path"),
        ("work/demo", "private prose"),
        ("work/demo", "private\npayload"),
        ("../private", "demo"),
        ("work/demo lock", "demo"),
        ("work//demo", "demo"),
        ("work/demo.lock", "demo"),
    ],
)
def test_redacted_receipt_rejects_unsafe_identity_strings(
    tmp_path: Path,
    branch: str,
    workstream: str,
) -> None:
    capsule = tmp_path / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = tmp_path / "docs" / "continuations" / "demo" / "workstream.json"
    configure_contract(contract, "8h")
    modules = _receipt_modules(capsule)

    with pytest.raises(ContractError, match="branch|workstream"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch=branch,
            workstream=workstream,
            modules=modules,
        )
    assert not receipt.exists()


@pytest.mark.parametrize("branch", ["work/demo", "fix/capsule-integrity", "feature/v2"])
def test_redacted_receipt_allows_bounded_git_branch_refs(tmp_path: Path, branch: str) -> None:
    capsule = tmp_path / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = tmp_path / "docs" / "continuations" / "demo" / "workstream.json"
    configure_contract(contract, "8h")
    modules = _receipt_modules(capsule)

    value, _changed = sync_receipt(
        contract,
        receipt,
        slug="demo",
        branch=branch,
        workstream="capsule-integrity",
        modules=modules,
    )

    assert value["branch"] == branch
    assert value["workstream"] == "capsule-integrity"


def test_receipt_sync_rejects_module_drift_from_private_identity(tmp_path: Path) -> None:
    capsule = tmp_path / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = tmp_path / "docs" / "continuations" / "demo" / "workstream.json"
    configure_contract(contract, "8h")
    modules = _receipt_modules(capsule)
    (capsule / "intent.md").write_text("drifted private intent\n", encoding="utf-8")

    with pytest.raises(ContractError, match="module bytes changed"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream="capsule-integrity",
            modules=modules,
        )
    assert not receipt.exists()


def test_receipt_snapshot_and_admission_share_one_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = tmp_path / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = tmp_path / "docs" / "continuations" / "demo" / "workstream.json"
    configure_contract(contract, "8h")
    modules = _receipt_modules(capsule)
    original_read = W.read_contract
    stale_snapshot_loaded = threading.Event()
    release_snapshot = threading.Event()

    def delayed_first_thread_read(path: Path) -> dict[str, object]:
        value = original_read(path)
        if threading.current_thread() is not threading.main_thread() and not stale_snapshot_loaded.is_set():
            stale_snapshot_loaded.set()
            assert release_snapshot.wait(timeout=2)
        return value

    def admit_and_sync() -> dict[str, object]:
        admitted, _remaining = admit_contract(contract, now_epoch=1_000)
        _sync_receipt_identity(capsule)
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream=None,
            modules=modules,
        )
        return admitted

    monkeypatch.setattr(W, "read_contract", delayed_first_thread_read)
    executor = ThreadPoolExecutor(max_workers=2)
    stale_write = executor.submit(
        sync_receipt,
        contract,
        receipt,
        slug="demo",
        branch="work/demo",
        workstream=None,
        modules=modules,
    )
    try:
        assert stale_snapshot_loaded.wait(timeout=1)
        launch_write = executor.submit(admit_and_sync)
        assert launch_write.done() is False
        release_snapshot.set()
        stale_write.result(timeout=2)
        admitted = launch_write.result(timeout=2)
    finally:
        release_snapshot.set()
        executor.shutdown(wait=True)

    durable = json.loads(receipt.read_text(encoding="utf-8"))
    assert durable["contract"] == admitted
    assert durable["contract"]["runway"]["started_epoch"] == 1_000


def test_redacted_receipt_rejects_duplicate_external_missing_and_symlinked_modules(tmp_path: Path) -> None:
    capsule = tmp_path / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = tmp_path / "docs" / "continuations" / "demo" / "workstream.json"
    configure_contract(contract, "8h")
    modules = _receipt_modules(capsule)

    with pytest.raises(ContractError, match="unique"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream=None,
            modules=[*modules, modules[0]],
        )

    external = tmp_path / "external"
    external.mkdir()
    external_intent = external / "intent.md"
    external_intent.write_text("outside\n", encoding="utf-8")
    outside_modules = [(name, external_intent if name == "intent.md" else path) for name, path in modules]
    with pytest.raises(ContractError, match="outside"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream=None,
            modules=outside_modules,
        )

    missing_modules = [(name, capsule / "missing.md" if name == "intent.md" else path) for name, path in modules]
    with pytest.raises(ContractError, match="unsafe"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream=None,
            modules=missing_modules,
        )

    runtime = capsule / "runtime.md"
    runtime.unlink()
    external_runtime = external / "runtime.md"
    external_runtime.write_text("outside\n", encoding="utf-8")
    runtime.symlink_to(external_runtime)
    with pytest.raises(ContractError, match="unsafe"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream=None,
            modules=modules,
        )

    runtime.unlink()
    runtime.write_text("private runtime.md\n", encoding="utf-8")
    outside_receipts = tmp_path / "outside-receipts"
    outside_receipts.mkdir()
    (tmp_path / "docs").symlink_to(outside_receipts, target_is_directory=True)
    with pytest.raises(ContractError, match="custody home"):
        sync_receipt(
            contract,
            receipt,
            slug="demo",
            branch="work/demo",
            workstream=None,
            modules=modules,
        )


def test_bounded_runner_terminates_a_slow_process_group() -> None:
    started = time.monotonic()

    result = run_bounded(["/bin/sh", "-c", "sleep 30"], 1)

    assert result == 124
    assert time.monotonic() - started < 4


@pytest.mark.parametrize("interrupt_signal", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_bounded_runner_cleans_process_group_when_wrapper_is_interrupted(
    tmp_path: Path,
    interrupt_signal: int,
) -> None:
    process_group_path = tmp_path / f"interrupted-{interrupt_signal}.pgid"
    child_source = "\n".join(
        [
            "import os, pathlib, time",
            f"pathlib.Path({str(process_group_path)!r}).write_text(str(os.getpgrp()))",
            "time.sleep(30)",
        ]
    )
    cli_src = Path(__file__).resolve().parents[1] / "src"
    wrapper_source = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(cli_src)!r})",
            "from limen.workstream_contract import run_bounded",
            f"raise SystemExit(run_bounded([{sys.executable!r}, '-c', {child_source!r}], 30))",
        ]
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", wrapper_source],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process_group_id: int | None = None

    try:
        deadline = time.monotonic() + 5
        process_group_text = ""
        while wrapper.poll() is None and time.monotonic() < deadline:
            try:
                process_group_text = process_group_path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                pass
            if process_group_text:
                break
            time.sleep(0.01)
        assert process_group_text, f"bounded child did not publish its process group; wrapper status={wrapper.poll()}"
        process_group_id = int(process_group_text)

        wrapper.send_signal(interrupt_signal)
        wrapper_returncode = wrapper.wait(timeout=7)

        assert wrapper_returncode != 0
        with pytest.raises(ProcessLookupError):
            os.killpg(process_group_id, 0)
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=2)
        if process_group_id is None and process_group_path.exists():
            process_group_text = process_group_path.read_text(encoding="utf-8").strip()
            if process_group_text:
                process_group_id = int(process_group_text)
        if process_group_id is not None:
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_bounded_runner_replays_wrapper_signal_received_during_cleanup(tmp_path: Path) -> None:
    process_group_path = tmp_path / "cleanup-interrupted.pgid"
    cleanup_started_path = tmp_path / "cleanup-started.txt"
    child_source = "\n".join(
        [
            "import os, pathlib, signal, time",
            f"cleanup_started_path = pathlib.Path({str(cleanup_started_path)!r})",
            "def record_cleanup(_signum, _frame):",
            "    cleanup_started_path.write_text('term')",
            "signal.signal(signal.SIGTERM, record_cleanup)",
            f"pathlib.Path({str(process_group_path)!r}).write_text(str(os.getpgrp()))",
            "time.sleep(30)",
        ]
    )
    leader_source = "\n".join(
        [
            "import pathlib, subprocess, sys, time",
            f"subprocess.Popen([sys.executable, '-c', {child_source!r}])",
            f"process_group_path = pathlib.Path({str(process_group_path)!r})",
            "deadline = time.monotonic() + 5",
            "while not process_group_path.exists() and time.monotonic() < deadline:",
            "    time.sleep(0.01)",
            "if not process_group_path.exists():",
            "    raise RuntimeError('descendant did not become ready')",
        ]
    )
    cli_src = Path(__file__).resolve().parents[1] / "src"
    wrapper_source = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(cli_src)!r})",
            "from limen.workstream_contract import run_bounded",
            f"raise SystemExit(run_bounded([{sys.executable!r}, '-c', {leader_source!r}], 30))",
        ]
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", wrapper_source],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process_group_id: int | None = None

    try:
        deadline = time.monotonic() + 5
        while not cleanup_started_path.exists() and wrapper.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cleanup_started_path.exists(), f"bounded cleanup did not start; wrapper status={wrapper.poll()}"
        process_group_id = int(process_group_path.read_text(encoding="utf-8"))

        wrapper.send_signal(signal.SIGTERM)
        wrapper_returncode = wrapper.wait(timeout=7)

        assert wrapper_returncode == -signal.SIGTERM
        with pytest.raises(ProcessLookupError):
            os.killpg(process_group_id, 0)
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=2)
        if process_group_id is None and process_group_path.exists():
            process_group_id = int(process_group_path.read_text(encoding="utf-8"))
        if process_group_id is not None:
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_bounded_runner_cleans_resistant_descendant_after_leader_exits_normally(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "normal-child.pid"
    process_group_path = tmp_path / "normal-process-group.pid"
    child_source = "\n".join(
        [
            "import os, pathlib, signal, time",
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
            f"pathlib.Path({str(child_pid_path)!r}).write_text(str(os.getpid()))",
            "time.sleep(30)",
        ]
    )
    leader_source = "\n".join(
        [
            "import os, pathlib, subprocess, sys, time",
            f"subprocess.Popen([sys.executable, '-c', {child_source!r}])",
            f"child_pid_path = pathlib.Path({str(child_pid_path)!r})",
            "deadline = time.monotonic() + 5",
            "while not child_pid_path.exists() and time.monotonic() < deadline:",
            "    time.sleep(0.01)",
            "if not child_pid_path.exists():",
            "    raise RuntimeError('descendant did not become ready')",
            f"pathlib.Path({str(process_group_path)!r}).write_text(str(os.getpgrp()))",
        ]
    )
    process_group_id: int | None = None

    try:
        result = run_bounded([sys.executable, "-c", leader_source], 5)
        process_group_id = int(process_group_path.read_text(encoding="utf-8"))

        assert result == 0
        with pytest.raises(ProcessLookupError):
            os.killpg(process_group_id, 0)
    finally:
        if process_group_id is None and process_group_path.exists():
            process_group_id = int(process_group_path.read_text(encoding="utf-8"))
        if process_group_id is not None:
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_bounded_runner_kills_resistant_descendant_after_leader_exits(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    process_group_path = tmp_path / "process-group.pid"
    leader_exit_path = tmp_path / "leader-exit.txt"
    child_source = "\n".join(
        [
            "import os, pathlib, signal, time",
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
            f"pathlib.Path({str(child_pid_path)!r}).write_text(str(os.getpid()))",
            "time.sleep(30)",
        ]
    )
    leader_source = "\n".join(
        [
            "import os, pathlib, signal, subprocess, sys, time",
            f"exit_path = pathlib.Path({str(leader_exit_path)!r})",
            "def exit_on_term(_signum, _frame):",
            "    exit_path.write_text('term')",
            "    raise SystemExit(0)",
            "signal.signal(signal.SIGTERM, exit_on_term)",
            f"subprocess.Popen([sys.executable, '-c', {child_source!r}])",
            f"child_pid_path = pathlib.Path({str(child_pid_path)!r})",
            "deadline = time.monotonic() + 5",
            "while not child_pid_path.exists() and time.monotonic() < deadline:",
            "    time.sleep(0.01)",
            "if not child_pid_path.exists():",
            "    raise RuntimeError('descendant did not become ready')",
            f"pathlib.Path({str(process_group_path)!r}).write_text(str(os.getpgrp()))",
            "time.sleep(30)",
        ]
    )
    process_group_id: int | None = None

    try:
        result = run_bounded([sys.executable, "-c", leader_source], 1)
        process_group_id = int(process_group_path.read_text(encoding="utf-8"))

        assert result == 124
        assert leader_exit_path.read_text(encoding="utf-8") == "term"
        with pytest.raises(ProcessLookupError):
            os.killpg(process_group_id, 0)
    finally:
        if process_group_id is None and process_group_path.exists():
            process_group_id = int(process_group_path.read_text(encoding="utf-8"))
        if process_group_id is not None:
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass


# ── lane tier pin (s9-lane-tier-pin) ────────────────────────────────────────────
#
# A bare `--model` pins the launched non-Codex lane's model. It is threaded OUTSIDE the v2 launch
# contract on purpose: `_primary_launch` models a launch profile as strictly Codex and demands a
# reasoning effort, so reusing `launch_model` for a bare pin raises ContractError at render. These
# tests hold that separation, and hold the pin to "refuse, never silently ignore".

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPSULE_LIB = REPO_ROOT / "scripts" / "lib" / "workstream-capsule.sh"
LAUNCHER = REPO_ROOT / "scripts" / "start-worktree-session.sh"


def _fake_lane_binary(tmp_path: Path) -> Path:
    """A stand-in CLI that records its argv instead of starting a model."""
    binary = tmp_path / "fake-lane"
    binary.write_text('#!/usr/bin/env bash\nprintf "ARGV:"; printf " [%s]" "$@"; printf "\\n"\n')
    binary.chmod(0o755)
    return binary


def _launch_argv(tmp_path: Path, provider: C.Vendor, pin: str) -> subprocess.CompletedProcess[str]:
    binary = _fake_lane_binary(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("capsule prompt body")
    env = dict(os.environ)
    env.update(
        {
            "LIMEN_CAPSULE_ID": "argv-contract",
            "LIMEN_WORKTREE": str(tmp_path),
            "LIMEN_SESSION_ID": "argv-contract-session",
        }
    )
    env[f"LIMEN_{provider.name.upper().replace('-', '_')}_BIN"] = str(binary)
    script = (
        f'source "{CAPSULE_LIB}"\n'
        f'workstream_launch_native_agent "{provider.name}" "{binary}" 1 "{readme}" 0 '
        f'"" "" "" "" "{pin}" "{provider.execution.workstream_adapter}" '
        f'"{int(provider.execution.workstream_model_flag)}"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=60,
        check=False,
    )


PIN_CAPABLE_PROVIDERS = tuple(provider for provider in C.VENDORS if provider.execution.workstream_model_flag)


@pytest.mark.parametrize("provider", PIN_CAPABLE_PROVIDERS, ids=lambda provider: provider.name)
def test_lane_tier_pin_reaches_the_launched_argv(tmp_path: Path, provider: C.Vendor) -> None:
    """The pin must arrive as a real `--model <value>` pair in the exec'd argv, not be dropped."""
    result = _launch_argv(tmp_path, provider, "opus")
    assert "ARGV: [--model] [opus]" in result.stdout, result.stdout or result.stderr


def test_unpinned_launch_argv_is_unchanged(tmp_path: Path) -> None:
    """No pin must add NO argument — not an empty string, which would break a strict lane parser."""
    provider = next(item for item in C.VENDORS if item.execution.workstream_adapter == "positional")
    result = _launch_argv(tmp_path, provider, "")
    assert "ARGV: [This session is already admitted; read the modules and continue." in result.stdout
    assert "capsule prompt body]" in result.stdout, result.stdout or result.stderr
    assert "--model" not in result.stdout


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (
            next(item for item in C.VENDORS if item.execution.workstream_adapter == "codex"),
            "requires the validated --model/--reasoning-effort/--sandbox profile",
        ),
        (
            next(item for item in C.VENDORS if item.execution.workstream_adapter == "jules"),
            "no verified --model flag form",
        ),
    ],
    ids=lambda value: value.name if isinstance(value, C.Vendor) else str(value),
)
def test_lane_tier_pin_is_refused_never_ignored(
    tmp_path: Path,
    provider: C.Vendor,
    expected: str,
) -> None:
    """A lane that cannot honour a pin must FAIL. Silently launching unpinned is the bug itself:
    the lane would run on the inherited default while the operator believes it is pinned."""
    result = _launch_argv(tmp_path, provider, "opus")
    assert result.returncode == 2, result.stdout
    assert expected in result.stderr, result.stderr
    assert "ARGV:" not in result.stdout


def test_registry_profile_survives_provider_rename_catalog_add_remove_and_reorder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Launch behavior follows the stable registry profile, never a frozen provider-name allowlist."""

    source = next(item for item in C.VENDORS if item.execution.workstream_adapter == "prompt-flag")
    renamed = replace(
        source,
        name="fixture-provider-renamed-arbitrarily",
        aliases=(),
        binary="fixture-provider-cli",
    )
    addition = replace(
        source,
        name="fixture-catalog-addition",
        aliases=(),
        binary="fixture-addition-cli",
        execution=replace(source.execution, workstream_adapter="positional"),
    )
    catalogs = (
        (renamed,),  # the old ID was removed
        (addition, renamed),  # unrelated addition before the selected lane
        (renamed, addition),  # arbitrary reorder
    )

    for catalog in catalogs:
        monkeypatch.setattr(C, "VENDORS", catalog)
        monkeypatch.setattr(C, "_BY_NAME", {item.name: item for item in catalog})
        selected = C.by_name(C.canonical(renamed.name))
        assert selected is renamed
        assert C.by_name(source.name) is None
        result = _launch_argv(tmp_path, selected, "fixture-model")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ARGV: [--model] [fixture-model] [--prompt]" in result.stdout


def test_renamed_jules_adapter_records_the_registry_provider_id(tmp_path: Path) -> None:
    provider = replace(
        next(item for item in C.VENDORS if item.execution.workstream_adapter == "jules"),
        name="fixture-jules-renamed",
        aliases=(),
    )
    receipt = tmp_path / "docs" / "continuations" / "fixture" / "workstream.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"schema":"limen.workstream.receipt.v1"}\n', encoding="utf-8")
    session_id = "12345678901234567890"
    session_url = f"https://jules.google.com/session/{session_id}"
    script = (
        f'source "{CAPSULE_LIB}"\n'
        f'workstream_jules_sync_receipt "{receipt}" "{session_id}" "{session_url}" "{provider.name}"\n'
        f'workstream_jules_provider_run_id "{receipt}" "{provider.name}"\n'
    )

    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "LIMEN_WORKTREE": str(tmp_path)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [session_id]
    assert json.loads(receipt.read_text(encoding="utf-8"))["provider_run"]["provider"] == provider.name


def _launcher(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(LAUNCHER), *args, "limen", "zz-lane-pin-never-created"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
        check=False,
    )


def test_bare_pin_requires_a_launch_and_partial_codex_profile_still_rejected() -> None:
    """A pin with no --agent has no consumer; a two-of-three Codex profile is still invalid."""
    no_agent = _launcher("--model", "opus")
    assert no_agent.returncode == 2
    assert "requires --agent" in no_agent.stderr, no_agent.stderr

    partial = _launcher("--model", "opus", "--sandbox", "workspace-write")
    assert partial.returncode == 2
    assert "must be supplied together" in partial.stderr, partial.stderr


def test_codex_lane_still_demands_its_triple_and_never_accepts_a_bare_pin() -> None:
    """The Codex launch profile is untouched: exactly one way to launch it explicitly.

    Both refusals must be ENVIRONMENT-INDEPENDENT, and each needed its own ordering fix:
      * the bare pin is refused before the generic binary probe;
      * an invalid --sandbox is rejected by the STATIC `validate-codex-sandbox` helper before that
        same probe, because `validate-codex-launch` needs a resolved --binary and so cannot run
        until codex is known to exist.
    An argument is invalid regardless of what happens to be installed, so CI (no codex binary) must
    reach the same verdict as a workstation that has one. Without either fix this exits 127 on CI
    and 2 locally — the same assertion passing or failing on environment alone.
    """
    bare = _launcher("--model", "opus", "--agent", "codex")
    assert bare.returncode == 2
    assert "lane tier pin refused" in bare.stderr, bare.stderr

    bad_sandbox = _launcher("--agent", "codex", "--model", "x", "--reasoning-effort", "high", "--sandbox", "nope")
    assert bad_sandbox.returncode != 0
    assert "Codex sandbox must be one of" in (bad_sandbox.stderr + bad_sandbox.stdout)


def test_bare_pin_never_builds_a_v2_launch_contract() -> None:
    """The regression that made this its own domain: a bare pin routed through the Codex launch
    profile raises, because a v2 contract requires an effort and a sandbox it does not have."""
    # Sandbox is validated first, so that is the message a bare pin actually hits here.
    with pytest.raises(ContractError, match="Codex sandbox must be one of"):
        W.new_contract_v2("8h", agent="claude", model="opus", reasoning_effort="", sandbox="")
    # And the lane itself is rejected independently, which is why the pin routes around this path
    # entirely rather than extending it.
    with pytest.raises(ContractError, match="require the Codex native lane"):
        W._primary_launch(agent="claude", model="opus", reasoning_effort="high")
