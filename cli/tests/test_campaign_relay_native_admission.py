from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from limen.conduct.campaign_relay_admission import (
    ADMISSION_SCHEMA,
    _monitor_provider_lease,
    run_admission_wrapper,
)
from limen.conduct.campaign_relay_process import (
    _live_relay_lanes,
    _spawn_relay_process,
)

ROOT = Path(__file__).resolve().parents[2]
RELAY_ID = "a" * 64


def _profile(*, transport: str, capabilities: tuple[str, ...]):
    return SimpleNamespace(
        transport=transport,
        capabilities=frozenset(capabilities),
    )


def _vendor(
    name: str,
    *,
    local_checkout: bool,
    transport: str,
    capabilities: tuple[str, ...] = ("execute", "local-worktree"),
):
    return SimpleNamespace(
        name=name,
        binary=name,
        local_checkout=local_checkout,
        execution=_profile(
            transport=transport,
            capabilities=capabilities,
        ),
    )


def test_live_relay_lanes_are_provider_neutral_local_native_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import capacity, census
    import limen.conduct.campaign_relay_process as relay_process

    vendors = {
        "remote-renamed": _vendor(
            "remote-renamed",
            local_checkout=False,
            transport="ianva-stdio",
        ),
        "local-zeta": _vendor(
            "local-zeta",
            local_checkout=True,
            transport="ianva-new",
        ),
        "missing-worktree": _vendor(
            "missing-worktree",
            local_checkout=True,
            transport="native-cli",
            capabilities=("execute",),
        ),
        "local-alpha": _vendor(
            "local-alpha",
            local_checkout=True,
            transport="native-cli",
        ),
        "remote-transport": _vendor(
            "remote-transport",
            local_checkout=True,
            transport="provider-receipt-relay",
        ),
    }
    order = [
        "remote-renamed",
        "local-zeta",
        "missing-worktree",
        "local-alpha",
        "remote-transport",
    ]
    monkeypatch.setattr(capacity, "select_lanes", lambda _selector: list(order))
    monkeypatch.setattr(census, "by_name", vendors.get)
    monkeypatch.setattr(
        relay_process.shutil,
        "which",
        lambda binary: f"/fixture/{binary}" if binary in vendors else None,
    )

    assert _live_relay_lanes(ROOT) == ("local-zeta", "local-alpha")

    order[:] = ["local-alpha", "new-local", "local-zeta"]
    vendors["new-local"] = _vendor(
        "new-local",
        local_checkout=True,
        transport="ianva-future",
    )
    assert _live_relay_lanes(ROOT) == ("local-alpha", "new-local", "local-zeta")


class _WrapperController:
    def __init__(self, decision: dict) -> None:
        self.decision = decision
        self.acquired = 0
        self.released = 0

    def acquire(self, *_args, **_kwargs):
        self.acquired += 1
        return self.decision

    def release(self, **_kwargs):
        self.released += 1
        return {"allowed": True}


@pytest.mark.parametrize("reason", ["heavy-lease-held", "vitals-shed"])
def test_admission_denial_precedes_provider_exec(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    monkeypatch.setenv("LIMEN_CAMPAIGN_RELAY_ID", RELAY_ID)
    controller = _WrapperController(
        {
            "allowed": False,
            "inherited": False,
            "lease": None,
            "reasons": [reason],
        }
    )
    reader, writer = os.pipe()
    exec_calls: list[tuple] = []
    result = run_admission_wrapper(
        ("/provider",),
        handshake_descriptor=writer,
        controller=controller,  # type: ignore[arg-type]
        provider_pid=os.getpid(),
        execvpe=lambda *args: exec_calls.append(args),
    )
    payload = json.loads(os.read(reader, 2_048))
    os.close(reader)

    assert result == 75
    assert controller.acquired == 1
    assert exec_calls == []
    assert payload == {
        "allowed": False,
        "reasons": [reason],
        "schema": ADMISSION_SCHEMA,
    }


def test_inherited_finite_controller_lease_fails_closed_before_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIMEN_CAMPAIGN_RELAY_ID", RELAY_ID)
    controller = _WrapperController(
        {
            "allowed": True,
            "inherited": True,
            "lease": {"lease_id": "ancestor"},
            "reasons": [],
        }
    )
    reader, writer = os.pipe()
    result = run_admission_wrapper(
        ("/provider",),
        handshake_descriptor=writer,
        controller=controller,  # type: ignore[arg-type]
        provider_pid=os.getpid(),
        execvpe=lambda *_args: pytest.fail("provider must not execute"),
    )
    payload = json.loads(os.read(reader, 2_048))
    os.close(reader)

    assert result == 75
    assert payload["reasons"] == ["inherited-heavy-lease"]
    assert controller.released == 0


def test_exec_failure_releases_the_exact_admitted_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIMEN_CAMPAIGN_RELAY_ID", RELAY_ID)
    controller = _WrapperController(
        {
            "allowed": True,
            "inherited": False,
            "lease": {
                "lease_id": "relay-lease",
                "process_identity": "start-provider",
            },
            "reasons": [],
        }
    )
    reader, writer = os.pipe()

    def fail_exec(*_args):
        raise OSError("fixture exec failure")

    result = run_admission_wrapper(
        ("/provider",),
        handshake_descriptor=writer,
        controller=controller,  # type: ignore[arg-type]
        provider_pid=os.getpid(),
        start_monitor=lambda *_args, **_kwargs: 202,
        execvpe=fail_exec,
    )
    payload = json.loads(os.read(reader, 2_048))
    os.close(reader)

    assert result == 126
    assert payload == {
        "allowed": True,
        "reasons": [],
        "schema": ADMISSION_SCHEMA,
    }
    assert controller.released == 1


class _HandshakeProcess:
    payload: bytes = b""
    command: list[str] = []

    def __init__(self, command, **kwargs) -> None:
        type(self).command = list(command)
        os.write(kwargs["pass_fds"][-1], type(self).payload)
        self.pid = 404
        self.stdout = BytesIO()
        self.stderr = BytesIO()

    def poll(self):
        return 0


def _relay_descriptors() -> list[tuple[int, int]]:
    return [os.pipe() for _index in range(3)]


def _close_descriptors(pipes: list[tuple[int, int]]) -> None:
    for pair in pipes:
        for descriptor in pair:
            try:
                os.close(descriptor)
            except OSError:
                pass


def test_spawn_returns_only_after_the_wrapper_admits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import limen.conduct.campaign_relay_process as relay_process

    _HandshakeProcess.payload = (
        json.dumps(
            {
                "allowed": True,
                "reasons": [],
                "schema": ADMISSION_SCHEMA,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    monkeypatch.setattr(relay_process.subprocess, "Popen", _HandshakeProcess)
    pipes = _relay_descriptors()
    try:
        process = _spawn_relay_process(
            ["/provider", "--bounded"],
            root=ROOT,
            env={"LIMEN_CAMPAIGN_RELAY_ID": RELAY_ID},
            ack_descriptor=pipes[0][0],
            control_descriptor=pipes[1][1],
            exec_descriptor=pipes[2][1],
        )
    finally:
        _close_descriptors(pipes)

    assert process.pid == 404
    assert _HandshakeProcess.command[-2:] == ["/provider", "--bounded"]
    assert _HandshakeProcess.command[1].endswith("campaign_relay_admission.py")


def test_denied_spawn_records_the_exact_host_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import limen.conduct.campaign_relay_process as relay_process

    _HandshakeProcess.payload = (
        json.dumps(
            {
                "allowed": False,
                "reasons": ["vitals-shed"],
                "schema": ADMISSION_SCHEMA,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    recorded: list[tuple[str, ...]] = []
    monkeypatch.setattr(relay_process.subprocess, "Popen", _HandshakeProcess)
    monkeypatch.setattr(
        relay_process,
        "_record_admission_denial",
        lambda _root, _env, reasons: recorded.append(reasons),
    )
    pipes = _relay_descriptors()
    try:
        with pytest.raises(OSError, match="vitals-shed"):
            _spawn_relay_process(
                ["/provider"],
                root=ROOT,
                env={"LIMEN_CAMPAIGN_RELAY_ID": RELAY_ID},
                ack_descriptor=pipes[0][0],
                control_descriptor=pipes[1][1],
                exec_descriptor=pipes[2][1],
            )
    finally:
        _close_descriptors(pipes)

    assert recorded == [("vitals-shed",)]


class _MonitorController:
    def __init__(self, clock) -> None:
        self.clock = clock
        self.refreshes: list[float] = []
        self.releases: list[float] = []

    def refresh(self, **_kwargs):
        self.refreshes.append(self.clock())
        return {"allowed": True}

    def release(self, **_kwargs):
        self.releases.append(self.clock())
        return {"allowed": True}


def test_monitor_refreshes_beyond_ttl_and_releases_on_exit() -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    controller = _MonitorController(clock)
    _monitor_provider_lease(
        controller,  # type: ignore[arg-type]
        lease_id="lease",
        owner="relay",
        provider_pid=101,
        provider_identity="start-101",
        ttl_seconds=30,
        alive=lambda _pid: clock() < 65,
        identity=lambda _pid: "start-101",
        monotonic=clock,
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert controller.refreshes[0] == 0
    assert max(controller.refreshes) >= 60
    assert controller.releases == [65]


def test_monitor_releases_a_reused_provider_identity() -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    controller = _MonitorController(clock)
    _monitor_provider_lease(
        controller,  # type: ignore[arg-type]
        lease_id="lease",
        owner="relay",
        provider_pid=101,
        provider_identity="start-101",
        ttl_seconds=30,
        alive=lambda _pid: True,
        identity=lambda _pid: "start-101" if clock() < 3 else "start-reused",
        monotonic=clock,
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert controller.releases == [3]
