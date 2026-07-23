from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import limen.workstream_contract as W
import pytest
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
