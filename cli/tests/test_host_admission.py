from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import stat
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

import limen.host_admission as host_admission
from limen.host_admission import (
    AdmissionDenied,
    AdmissionController,
    AdmissionStateError,
    hold_lease,
    parse_iostat_mib_samples,
    worktree_scope,
)
from limen.models import Task

ROOT = Path(__file__).resolve().parents[2]


def healthy_pressure(
    *,
    observed_epoch: float = 100.0,
    backblaze_cpu: float = 0.0,
    backblaze_rss: int = 0,
    swap_used: int = 0,
    memory_bytes: int = 16 * 1024**3,
    disk: list[float] | None = None,
    vitals: str = "ok",
    errors: list[str] | None = None,
) -> dict[str, object]:
    return {
        "observed_epoch": observed_epoch,
        "backblaze_cpu_percent": backblaze_cpu,
        "backblaze_rss_bytes": backblaze_rss,
        "swap_used_bytes": swap_used,
        "memory_bytes": memory_bytes,
        "disk_mib_per_second_samples": [0.0, 0.0] if disk is None else disk,
        "vitals_action": vitals,
        "sensor_errors": [] if errors is None else errors,
    }


def controller(
    root: Path,
    *,
    now: list[float] | None = None,
    alive=None,
    identity=None,
    process_cwd_probe=None,
    descendant=None,
    pressure=None,
) -> AdmissionController:
    now = now or [100.0]
    return AdmissionController(
        root,
        clock=lambda: now[0],
        alive=alive or (lambda pid: pid > 0),
        identity=identity or (lambda pid: f"start-{pid}"),
        process_cwd_probe=process_cwd_probe or (lambda _pid: None),
        descendant=descendant or (lambda _pid, _ancestor: False),
        pressure_probe=pressure or (lambda: healthy_pressure(observed_epoch=now[0])),
        thresholds={
            "backblaze_cpu_percent": 50,
            "backblaze_rss_bytes": 1024**3,
            "swap_fraction": 0.25,
            "swap_growth_bytes_per_minute": 512 * 1024**2,
            "disk_mib_per_second": 100,
        },
    )


def make_linked_worktrees(tmp_path: Path) -> tuple[Path, Path, Path]:
    main = tmp_path / "repo"
    first = tmp_path / "first"
    second = tmp_path / "second"
    main.mkdir()
    for command in (
        ["git", "init", "-q", "-b", "main", str(main)],
        ["git", "-C", str(main), "config", "user.email", "test@example.com"],
        ["git", "-C", str(main), "config", "user.name", "Test"],
    ):
        subprocess.run(command, check=True)
    (main / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(main), "commit", "-qm", "fixture"], check=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-qb", "first", str(first)], check=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-qb", "second", str(second)], check=True)
    return main, first, second


def test_iostat_parser_sums_each_disk_triplet() -> None:
    raw = """\
          disk0               disk2
    KB/t  xfrs   MB/s   KB/t  xfrs   MB/s
   20.00  10.0   1.25   10.00  20.0   2.75
   40.00  20.0 101.00   50.00  10.0   4.00
   10.00  20.0  90.00   20.00  10.0  12.00
"""
    assert parse_iostat_mib_samples(raw) == [4.0, 105.0, 102.0]


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin libproc integration")
def test_process_identity_uses_libproc_when_ps_is_unavailable(monkeypatch) -> None:
    def denied_ps(*_args, **_kwargs):
        raise OSError("sandbox denied ps")

    monkeypatch.setattr(host_admission.subprocess, "run", denied_ps)

    first = host_admission.process_identity(os.getpid())
    second = host_admission.process_identity(os.getpid())

    assert first is not None
    assert first.startswith("darwin-proc-start:")
    assert first == second


def test_darwin_process_identity_changes_with_start_time_and_rejects_failures() -> None:
    pid = 4242

    def proc_result(seconds: int, microseconds: int, *, result_pid: int = pid, returned: int | None = None):
        def fake_proc_pidinfo(_pid, flavor, arg, buffer, size):
            assert (_pid, flavor, arg) == (pid, host_admission._PROC_PIDTBSDINFO, 0)
            info = ctypes.cast(buffer, ctypes.POINTER(host_admission._ProcBsdInfo)).contents
            info.pbi_pid = result_pid
            info.pbi_start_tvsec = seconds
            info.pbi_start_tvusec = microseconds
            return size if returned is None else returned

        return fake_proc_pidinfo

    first = host_admission._darwin_process_identity(
        pid,
        proc_pidinfo=proc_result(1_700_000_000, 123_456),
    )
    reused = host_admission._darwin_process_identity(
        pid,
        proc_pidinfo=proc_result(1_700_000_000, 123_457),
    )

    assert first == "darwin-proc-start:1700000000:123456"
    assert reused == "darwin-proc-start:1700000000:123457"
    assert reused != first
    assert (
        host_admission._darwin_process_identity(
            pid,
            proc_pidinfo=proc_result(1_700_000_000, 123_456, result_pid=pid + 1),
        )
        is None
    )
    assert (
        host_admission._darwin_process_identity(
            pid,
            proc_pidinfo=proc_result(1_700_000_000, 123_456, returned=1),
        )
        is None
    )

    def failed_proc_pidinfo(*_args):
        raise OSError("libproc unavailable")

    assert host_admission._darwin_process_identity(pid, proc_pidinfo=failed_proc_pidinfo) is None


def test_execution_lease_does_not_run_heavy_pressure_probe(tmp_path: Path) -> None:
    def should_not_run() -> dict[str, object]:
        raise AssertionError("execution admission must remain lightweight")

    service = controller(tmp_path / "state", pressure=should_not_run)
    decision = service.acquire("execution", owner="codex-a", surface="turn", pid=101)
    assert decision["allowed"] is True
    assert decision["pressure"] is None


def test_same_owner_is_idempotent_and_other_root_is_denied(tmp_path: Path) -> None:
    now = [100.0]
    first = controller(tmp_path / "state", now=now)
    second = controller(tmp_path / "state", now=now)
    acquired = first.acquire("execution", owner="codex-a", surface="turn", pid=101)
    now[0] = 110.0
    refreshed = second.acquire("execution", owner="codex-a", surface="turn", pid=101)
    denied = second.acquire("execution", owner="codex-b", surface="turn", pid=202)

    assert refreshed["allowed"] is True
    assert refreshed["lease"]["lease_id"] == acquired["lease"]["lease_id"]
    assert refreshed["lease"]["expires_epoch"] == pytest.approx(1010.0)
    assert denied["allowed"] is False
    assert denied["reasons"] == ["execution-lease-held"]


def test_current_owner_legacy_execution_is_upgraded_in_place(tmp_path: Path) -> None:
    _main, first, _second = make_linked_worktrees(tmp_path)
    service = controller(tmp_path / "state")
    legacy = service.acquire("execution", owner="codex-a", surface="turn", pid=101)
    scope = worktree_scope(first)
    upgraded = service.acquire(scope.lease_kind, owner="codex-a", surface="write", pid=101)

    assert upgraded["allowed"] is True
    assert upgraded["lease"]["lease_id"] == legacy["lease"]["lease_id"]
    assert upgraded["lease"]["kind"] == scope.lease_kind
    assert len(upgraded["leases"]) == 1
    state_text = service.state_path.read_text(encoding="utf-8")
    assert str(first) not in state_text
    assert str(scope.common_dir) not in state_text


def test_live_peer_legacy_scope_is_resolved_without_blocking_disjoint_worktree(tmp_path: Path) -> None:
    _main, first, second = make_linked_worktrees(tmp_path)
    process_cwds = {101: first, 202: second}
    service = controller(
        tmp_path / "state",
        process_cwd_probe=lambda pid: process_cwds.get(pid),
    )
    service.acquire("execution", owner="codex-a", surface="turn", pid=101)
    admitted = service.acquire(
        worktree_scope(second).lease_kind,
        owner="codex-b",
        surface="write",
        pid=202,
    )

    assert admitted["allowed"] is True
    assert len(admitted["leases"]) == 2
    assert {lease["kind"] for lease in admitted["leases"]} == {
        worktree_scope(first).lease_kind,
        worktree_scope(second).lease_kind,
    }


def test_live_peer_legacy_scope_denies_same_worktree(tmp_path: Path) -> None:
    _main, first, _second = make_linked_worktrees(tmp_path)
    service = controller(
        tmp_path / "state",
        process_cwd_probe=lambda pid: first if pid == 101 else None,
    )
    service.acquire("execution", owner="codex-a", surface="turn", pid=101)
    denied = service.acquire(
        worktree_scope(first).lease_kind,
        owner="codex-b",
        surface="write",
        pid=202,
    )

    assert denied["allowed"] is False
    assert denied["reasons"] == ["workspace-writer-lease-held"]


def test_unprovable_live_legacy_scope_fails_only_attempted_mutation(tmp_path: Path) -> None:
    _main, _first, second = make_linked_worktrees(tmp_path)
    service = controller(tmp_path / "state", process_cwd_probe=lambda _pid: None)
    legacy = service.acquire("execution", owner="codex-a", surface="turn", pid=101)
    denied = service.acquire(
        worktree_scope(second).lease_kind,
        owner="codex-b",
        surface="write",
        pid=202,
    )

    assert denied["allowed"] is False
    assert denied["reasons"] == ["legacy-execution-scope-unproven"]
    assert denied["lease"]["lease_id"] == legacy["lease"]["lease_id"]
    assert service.status(probe=False)["leases"][0]["kind"] == "execution"


def test_nested_process_inherits_parent_heavy_lease_without_releasing_it(tmp_path: Path) -> None:
    service = controller(
        tmp_path / "state",
        descendant=lambda pid, ancestor: (pid, ancestor) == (202, 101),
    )
    parent = service.acquire("heavy", owner="worker", surface="dispatch", pid=101)
    child = service.acquire("heavy", owner="verify", surface="verify-scoped", pid=202)

    assert parent["allowed"] is True
    assert child["allowed"] is True
    assert child["inherited"] is True
    assert child["lease"]["lease_id"] == parent["lease"]["lease_id"]
    assert len(child["leases"]) == 1


@pytest.mark.parametrize(
    ("pressure", "reason"),
    [
        (healthy_pressure(backblaze_cpu=50.001), "backblaze-cpu"),
        (healthy_pressure(backblaze_rss=1024**3 + 1), "backblaze-rss"),
        (healthy_pressure(swap_used=4 * 1024**3 + 1), "swap-fraction"),
        (healthy_pressure(disk=[100.001, 100.001]), "disk-throughput"),
        (healthy_pressure(vitals="shed"), "vitals-shed"),
    ],
)
def test_new_heavy_lease_denies_each_pressure_axis(
    tmp_path: Path,
    pressure: dict[str, object],
    reason: str,
) -> None:
    service = controller(tmp_path / reason, pressure=lambda: pressure)
    decision = service.acquire("heavy", owner="worker", surface="test", pid=101)
    assert decision["allowed"] is False
    assert reason in decision["reasons"]
    assert decision["leases"] == []


def test_pressure_boundaries_are_strictly_greater_than(tmp_path: Path) -> None:
    pressure = healthy_pressure(
        backblaze_cpu=50,
        backblaze_rss=1024**3,
        swap_used=4 * 1024**3,
        disk=[100, 100],
    )
    service = controller(tmp_path / "state", pressure=lambda: pressure)
    assert service.acquire("heavy", owner="worker", surface="test", pid=101)["allowed"] is True


def test_disk_requires_two_hot_interval_samples(tmp_path: Path) -> None:
    pressure = healthy_pressure(disk=[100.001, 99.999])
    service = controller(tmp_path / "state", pressure=lambda: pressure)
    assert service.acquire("heavy", owner="worker", surface="test", pid=101)["allowed"] is True


def test_swap_growth_uses_two_recent_samples(tmp_path: Path) -> None:
    now = [100.0]
    samples = [
        healthy_pressure(observed_epoch=100.0, swap_used=1024**3),
        healthy_pressure(observed_epoch=160.0, swap_used=1024**3 + 512 * 1024**2 + 1),
    ]
    service = controller(tmp_path / "state", now=now, pressure=lambda: samples.pop(0))
    service.status()
    now[0] = 160.0
    decision = service.acquire("heavy", owner="worker", surface="test", pid=101)
    assert decision["allowed"] is False
    assert decision["reasons"] == ["swap-growth"]


def test_existing_heavy_owner_can_refresh_under_new_pressure(tmp_path: Path) -> None:
    samples = [
        healthy_pressure(),
        healthy_pressure(backblaze_cpu=99),
    ]
    service = controller(tmp_path / "state", pressure=lambda: samples.pop(0))
    first = service.acquire("heavy", owner="worker", surface="test", pid=101)
    second = service.acquire("heavy", owner="worker", surface="test", pid=101)
    assert first["allowed"] is True
    assert second["allowed"] is True
    assert second["lease"]["lease_id"] == first["lease"]["lease_id"]
    assert second["pressure"]["backblaze_cpu_percent"] == 99


def test_stale_dead_and_reused_pid_leases_are_reaped(tmp_path: Path) -> None:
    now = [100.0]
    identities = {101: "start-101", 202: "start-202", 303: "start-303"}
    live = {101, 202, 303}
    service = controller(
        tmp_path / "state",
        now=now,
        alive=lambda pid: pid in live,
        identity=lambda pid: identities.get(pid),
    )

    stale = service.acquire(
        "execution",
        owner="stale",
        surface="turn",
        pid=101,
        ttl_seconds=30,
    )
    now[0] = 131.0
    replacement = service.acquire("execution", owner="replacement", surface="turn", pid=202)
    assert replacement["allowed"] is True
    assert stale["lease"]["lease_id"] in {item["lease_id"] for item in replacement["reaped"]}
    assert replacement["reaped"][0]["reason"] == "stale-ttl"

    service.release(
        lease_id=replacement["lease"]["lease_id"],
        owner="replacement",
        pid=202,
    )
    dead = service.acquire("execution", owner="dead", surface="turn", pid=202)
    live.remove(202)
    after_dead = service.acquire("execution", owner="next", surface="turn", pid=303)
    assert dead["lease"]["lease_id"] in {item["lease_id"] for item in after_dead["reaped"]}
    assert after_dead["reaped"][0]["reason"] == "dead-pid"

    service.release(lease_id=after_dead["lease"]["lease_id"], owner="next", pid=303)
    reused = service.acquire("execution", owner="reused", surface="turn", pid=101)
    identities[101] = "different-start"
    after_reuse = service.acquire("execution", owner="final", surface="turn", pid=303)
    assert reused["lease"]["lease_id"] in {item["lease_id"] for item in after_reuse["reaped"]}
    assert after_reuse["reaped"][0]["reason"] == "pid-reused"


def test_refresh_and_release_require_exact_owner_pid_and_start_identity(tmp_path: Path) -> None:
    identities = {101: "start-101", 202: "start-202"}
    service = controller(tmp_path / "state", identity=lambda pid: identities.get(pid))
    acquired = service.acquire("execution", owner="codex", surface="turn", pid=101)
    lease_id = acquired["lease"]["lease_id"]

    assert service.refresh(lease_id=lease_id, owner="other", pid=101)["allowed"] is False
    assert service.release(lease_id=lease_id, owner="codex", pid=202)["allowed"] is False
    assert service.release(lease_id=lease_id, owner="codex", pid=101)["allowed"] is True
    # Release is idempotent once exact custody has already disappeared.
    assert service.release(lease_id=lease_id, owner="codex", pid=101)["allowed"] is True


def test_release_owned_is_atomic_and_does_not_release_another_owner(tmp_path: Path) -> None:
    service = controller(tmp_path / "state")
    service.acquire("execution", owner="codex", surface="turn", pid=101)

    assert service.release_owned("execution", owner="other", pid=202)["allowed"] is True
    assert len(service.status(probe=False)["leases"]) == 1
    assert service.release_owned("execution", owner="codex", pid=101)["allowed"] is True
    assert service.status(probe=False)["leases"] == []
    assert service.release_owned("execution", owner="codex", pid=101)["allowed"] is True


def test_corrupt_state_is_preserved_and_blocks_acquire(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    state = root / "state.json"
    state.write_text("{not-json", encoding="utf-8")
    service = controller(root)

    with pytest.raises(AdmissionStateError, match="corrupt"):
        service.acquire("execution", owner="codex", surface="turn", pid=101)
    assert state.read_text(encoding="utf-8") == "{not-json"


def test_symlink_or_open_permissions_state_root_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(AdmissionStateError, match="real directory"):
        controller(link).status(probe=False)

    open_root = tmp_path / "open"
    open_root.mkdir(mode=0o755)
    assert stat.S_IMODE(open_root.stat().st_mode) == 0o755
    with pytest.raises(AdmissionStateError, match="0700"):
        controller(open_root).status(probe=False)


def test_hold_lease_releases_on_exception(tmp_path: Path) -> None:
    service = controller(tmp_path / "state")
    with pytest.raises(RuntimeError, match="boom"):
        with hold_lease(
            "execution",
            owner="codex",
            surface="turn",
            pid=101,
            controller=service,
        ):
            raise RuntimeError("boom")
    assert service.status(probe=False)["leases"] == []


def _concurrent_acquire(root: str, owner: str, ready, start, results) -> None:
    service = AdmissionController(
        Path(root),
        clock=lambda: 100.0,
        alive=lambda pid: True,
        identity=lambda pid: f"start-{pid}",
        descendant=lambda _pid, _ancestor: False,
        pressure_probe=lambda: healthy_pressure(),
    )
    ready.put(owner)
    start.wait(timeout=5)
    decision = service.acquire("execution", owner=owner, surface="turn", pid=os.getpid())
    results.put((owner, decision["allowed"]))


def test_concurrent_roots_admit_only_one_execution_owner(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    ready = context.Queue()
    results = context.Queue()
    start = context.Event()
    root = tmp_path / "state"
    processes = [
        context.Process(target=_concurrent_acquire, args=(str(root), owner, ready, start, results))
        for owner in ("root-a", "root-b")
    ]
    for process in processes:
        process.start()
    assert {ready.get(timeout=5), ready.get(timeout=5)} == {"root-a", "root-b"}
    start.set()
    outcomes = [results.get(timeout=5), results.get(timeout=5)]
    for process in processes:
        process.join(timeout=5)
        assert process.exitcode == 0
    assert sum(1 for _owner, allowed in outcomes if allowed) == 1


def test_state_file_is_private_and_versioned(tmp_path: Path) -> None:
    service = controller(tmp_path / "state")
    service.acquire("execution", owner="codex", surface="turn", pid=101)
    payload = json.loads(service.state_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "limen.host_admission_state.v1"
    assert stat.S_IMODE(service.state_path.stat().st_mode) == 0o600


def test_json_cli_status_is_report_only_and_release_is_exact(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "host-work-admission.py"
    root = tmp_path / "state"
    common = [sys.executable, str(script), "--state-root", str(root)]
    acquired = subprocess.run(
        [
            *common,
            "acquire",
            "--kind",
            "execution",
            "--owner",
            "test-cli",
            "--surface",
            "unit",
            "--pid",
            str(os.getpid()),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lease_id = json.loads(acquired.stdout)["lease"]["lease_id"]
    status = subprocess.run(
        [*common, "status", "--no-probe"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert status.returncode == 0
    assert json.loads(status.stdout)["allowed"] is False  # pressure is unknown, but status remains report-only
    released = subprocess.run(
        [
            *common,
            "release",
            "--lease-id",
            lease_id,
            "--owner",
            "test-cli",
            "--pid",
            str(os.getpid()),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(released.stdout)["leases"] == []


def test_public_limen_host_admission_scoped_cli(tmp_path: Path, monkeypatch) -> None:
    from limen.cli import main

    _main, first, _second = make_linked_worktrees(tmp_path)
    state_root = tmp_path / "state"
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", str(state_root))
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_OWNER", "cli-test-owner")
    runner = CliRunner()

    acquired = runner.invoke(
        main,
        ["host-admission", "acquire", "execution", "--cwd", str(first), "--json"],
    )
    assert acquired.exit_code == 0, acquired.output
    payload = json.loads(acquired.output)
    assert payload["lease"]["kind"] == worktree_scope(first).lease_kind

    status = runner.invoke(
        main,
        ["host-admission", "status", "--cwd", str(first), "--json"],
    )
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["scope"]["writer_held"] is True

    released = runner.invoke(
        main,
        ["host-admission", "release", "execution", "--cwd", str(first), "--json"],
    )
    assert released.exit_code == 0, released.output
    assert json.loads(released.output)["leases"] == []


def test_local_codex_dispatch_holds_only_the_machine_heavy_lease(monkeypatch) -> None:
    from limen import dispatch

    task = Task(
        id="HOST-ADMISSION-1",
        title="bounded local dispatch",
        repo="organvm/limen",
        target_agent="codex",
        created=date(2026, 7, 17),
    )
    held: list[tuple[str, str]] = []

    @contextmanager
    def fake_hold(kind: str, *, owner: str, surface: str):
        held.append((kind, surface))
        yield {"allowed": True, "lease": {"owner": owner}}

    monkeypatch.delenv("LIMEN_DISPATCH_CMD", raising=False)
    monkeypatch.setattr(dispatch, "hold_lease", fake_hold)
    monkeypatch.setattr(dispatch, "_call_local_agent", lambda *_args: "local-result")

    assert dispatch.call_agent_dispatch("codex", task, dry_run=False) == "local-result"
    assert held == [("heavy", "limen-codex-dispatch")]


def test_local_dispatch_returns_owner_routed_blocker_when_host_denies(monkeypatch) -> None:
    from limen import dispatch

    task = Task(
        id="HOST-ADMISSION-2",
        title="blocked local dispatch",
        repo="organvm/limen",
        target_agent="claude",
        created=date(2026, 7, 17),
    )

    @contextmanager
    def denied(*_args, **_kwargs):
        raise AdmissionDenied({"allowed": False, "reasons": ["backblaze-rss"]})
        yield  # pragma: no cover

    monkeypatch.delenv("LIMEN_DISPATCH_CMD", raising=False)
    monkeypatch.setattr(dispatch, "hold_lease", denied)
    result = dispatch.call_agent_dispatch("claude", task, dry_run=False)
    assert dispatch._is_blocked_result(result)
    assert "backblaze-rss" in result


def test_shell_helper_acquires_refreshes_and_releases_exact_lease(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    commands = {
        "iostat": """#!/usr/bin/env bash
printf 'disk0\\nKB/t xfrs MB/s\\n1 1 0\\n1 1 0\\n1 1 0\\n'
""",
        "ps": """#!/usr/bin/env bash
if [[ "${1:-}" == "-axo" ]]; then exit 0; fi
exec /bin/ps "$@"
""",
        "sysctl": """#!/usr/bin/env bash
if [[ "$*" == *"vm.swapusage hw.memsize"* ]]; then
  printf 'total = 0.00M  used = 0.00M  free = 0.00M\\n17179869184\\n'
  exit 0
fi
case "${*: -1}" in
  vm.swapusage) printf 'total = 0.00M  used = 0.00M  free = 0.00M\\n' ;;
  hw.memsize) printf '17179869184\\n' ;;
  kern.memorystatus_vm_pressure_level) printf '1\\n' ;;
  *) exit 1 ;;
esac
""",
    }
    for name, body in commands.items():
        path = fake_bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    state_root = tmp_path / "state"
    shell = f"""
set -euo pipefail
export PATH={fake_bin!s}:$PATH
export LIMEN_HOST_ADMISSION_ROOT={state_root!s}
source {ROOT / "scripts" / "lib" / "host-admission.sh"}
host_admission_acquire fixture {ROOT!s}
[[ -n "$HOST_ADMISSION_LEASE_ID" ]]
host_admission_release
"""
    result = subprocess.run(
        ["bash", "-c", shell],
        capture_output=True,
        text=True,
        # The helper spawns several python3 interpreters; on a CI host saturated
        # by xdist siblings each spawn can take seconds, so the budget covers a
        # loaded host while still bounding a hung refresh child.
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads((state_root / "state.json").read_text(encoding="utf-8"))
    assert state["leases"] == []
