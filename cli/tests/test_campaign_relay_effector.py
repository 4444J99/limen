from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import limen.conduct.campaign_relay as relay_core
import limen.conduct.campaign_relay_process as relay_process
import limen.conduct.campaign_relay_protocol as relay_protocol
import limen.conduct.campaign_relay_publication as relay_publication
import pytest
from limen.bounded_subprocess import BoundedSubprocessError
from limen.conduct.campaign_relay import (
    CampaignRelayError,
    _git_bytes,
    discover_ready_relay,
    launch_reserved_relay,
    reserve_relay,
)
from limen.conduct.campaign_relay_process import _bounded_registration, _spawn_relay_process
from limen.conduct.campaign_relay_state import _read_relay, _replace_relay
from limen.conduct.models import CampaignRelayReceiptV1
from limen.workstream_contract import RECEIPT_MODULES, new_contract

ROOT = Path(__file__).resolve().parents[2]


def _agent_resolution_source() -> str:
    source = (ROOT / "scripts" / "start-worktree-session.sh").read_text(encoding="utf-8")
    marker = "    python3 - \"${requested_agent:-auto}\" <<'PY'\n"
    return source.split(marker, 1)[1].split("\nPY\n)", 1)[0]


def _run_agent_resolution() -> None:
    # Execute the exact tracked heredoc so the fixture cannot drift into testing a duplicate.
    exec(compile(_agent_resolution_source(), "agent-resolution", "exec"), {})  # noqa: S102


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"fixture Git command failed: {result.stderr}")
    return result.stdout.strip()


@pytest.fixture
def effector_repo(tmp_path: Path) -> tuple[Path, Path, Path, int]:
    root = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    binary_dir = tmp_path / "bin"
    root.mkdir()
    binary_dir.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "relay-effector@example.invalid")
    _git(root, "config", "user.name", "Relay Effector Test")
    _git(root, "config", "commit.gpgsign", "false")
    started = int(time.time()) - (8 * 60 * 60) + 60
    predecessor_deadline = started + 8 * 60 * 60
    contract = new_contract("8h")
    contract["runway"].update(
        {
            "started_epoch": started,
            "deadline_epoch": predecessor_deadline,
            "started_at": datetime.fromtimestamp(started, UTC).isoformat(timespec="seconds"),
            "deadline_at": datetime.fromtimestamp(predecessor_deadline, UTC).isoformat(timespec="seconds"),
        }
    )
    predecessor = root / "docs" / "continuations" / "predecessor" / "workstream.json"
    predecessor.parent.mkdir(parents=True)
    predecessor.write_text(
        json.dumps(
            {
                "branch": "work/predecessor",
                "contract": contract,
                "private_capsule": {
                    "content": "redacted",
                    "modules": list(RECEIPT_MODULES),
                },
                "schema": "limen.workstream.receipt.v1",
                "slug": "predecessor",
                "workstream": "institutional-omega",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("relay fixture\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    _git(remote.parent, "init", "--bare", "-q", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "-u", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    provider = binary_dir / "codex"
    provider.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "for key in LIMEN_CAMPAIGN_RELAY_ACK_FD LIMEN_CAMPAIGN_RELAY_CONTROL_FD "
            "LIMEN_CAMPAIGN_RELAY_EXEC_FD LIMEN_CAMPAIGN_RELAY_FINAL_EXEC "
            "LIMEN_CAMPAIGN_RELAY_REAL_BINARY LIMEN_CODEX_BIN LIMEN_NATIVE_RUN_ID "
            "LIMEN_NATIVE_SESSION_ID LIMEN_PROVIDER_IDENTITY LIMEN_RUN_ID; do\n"
            '  if [[ -n "${!key:-}" ]]; then printf "%s\\n" "$key" >> "$PROVIDER_ENV_LEAKS"; fi\n'
            "done\n"
            'printf "%s\\n" "$$" > "$PROVIDER_PID"\n'
            'sleep "${PROVIDER_SLEEP:-8}"\n'
        ),
        encoding="utf-8",
    )
    provider.chmod(0o755)
    return root, predecessor, provider, predecessor_deadline


def test_campaign_relay_second_census_retains_remaining_candidate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from limen import capacity

    monkeypatch.setattr(capacity, "select_lanes", lambda _selector: ["claude"])
    monkeypatch.setattr(
        shutil,
        "which",
        lambda binary: f"/fixture/{binary}" if binary == "claude" else None,
    )
    monkeypatch.setattr(sys, "argv", ["agent-resolution", "auto"])
    monkeypatch.setenv("LIMEN_CAMPAIGN_RELAY_ELIGIBLE_LANES", "codex,claude")
    monkeypatch.delenv("LIMEN_CODEX_BIN", raising=False)
    monkeypatch.delenv("LIMEN_CLAUDE_BIN", raising=False)

    _run_agent_resolution()

    resolved = capsys.readouterr().out.splitlines()
    assert resolved[:2] == ["claude", "claude"]


def test_campaign_relay_second_census_fails_for_empty_intersection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import capacity

    monkeypatch.setattr(capacity, "select_lanes", lambda _selector: ["opencode"])
    monkeypatch.setattr(shutil, "which", lambda _binary: None)
    monkeypatch.setattr(sys, "argv", ["agent-resolution", "auto"])
    monkeypatch.setenv("LIMEN_CAMPAIGN_RELAY_ELIGIBLE_LANES", "codex,claude")
    monkeypatch.delenv("LIMEN_CODEX_BIN", raising=False)
    monkeypatch.delenv("LIMEN_CLAUDE_BIN", raising=False)

    with pytest.raises(
        SystemExit,
        match="campaign relay has no remaining live provider capacity before launch",
    ):
        _run_agent_resolution()


def test_full_relay_exec_proof_closes_while_keepalive_remains_live(
    effector_repo,
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, predecessor_deadline = effector_repo
    exact_main = _git(root, "rev-parse", "HEAD")
    reservation = reserve_relay(root, predecessor, exact_remote_main=exact_main)
    provider_pid_path = tmp_path / "provider.pid"
    provider_env_leaks = tmp_path / "provider-env-leaks.txt"
    registrations: list[bool] = []

    def register(**kwargs):
        registrations.append(kwargs["accepting_work"])
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(provider_env_leaks))
    monkeypatch.setenv("PROVIDER_PID", str(provider_pid_path))
    started_at = time.monotonic()
    launch = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )
    elapsed = time.monotonic() - started_at

    assert launch.receipt.state == "ready", (
        launch.receipt.terminal_code,
        launch.receipt.startup_stdout_bytes,
        launch.receipt.startup_stderr_bytes,
    )
    assert launch.receipt.attempts == 1
    assert launch.receipt.activation_response_sha256 is not None
    assert registrations == [False, True]
    assert elapsed < 10
    assert provider_pid_path.is_file()
    assert not provider_env_leaks.exists()
    assert launch.receipt.launch_pid == int(provider_pid_path.read_text(encoding="utf-8"))
    os.kill(launch.receipt.launch_pid, 0)
    status = json.loads(
        (
            root / ".worktrees" / launch.receipt.successor_slug / ".limen-workstream" / "conduct-keepalive.json"
        ).read_text(encoding="utf-8")
    )
    os.kill(int(status["keepalive_pid"]), 0)
    capsule_ref = f"refs/heads/limen-relay/capsule/{launch.receipt.publication_commit}"
    ready_ref = f"refs/heads/limen-relay/ready/{launch.receipt.relay_id}"
    latest_ref = "refs/heads/limen-relay/latest/institutional-omega"
    assert _git(root, "ls-remote", "origin", capsule_ref).startswith(str(launch.receipt.publication_commit))
    ready_commit = _git(root, "ls-remote", "origin", ready_ref).split("\t", 1)[0]
    assert ready_commit
    assert _git(root, "ls-remote", "origin", latest_ref).startswith(ready_commit)

    repeated = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        lane_selector=lambda _root: pytest.fail("ready relay must not reselect a lane"),
        registration=lambda **_kwargs: pytest.fail("ready relay must not re-register"),
    )
    assert repeated.launched is False
    assert repeated.receipt == launch.receipt

    _replace_relay(
        root,
        launch.receipt.relay_id,
        expected_states=frozenset({"ready"}),
        updates={
            "state": "indeterminate",
            "terminal_code": "relay_ready_verification_interrupted",
        },
    )
    recovered_terminal = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        lane_selector=lambda _root: pytest.fail("durable readiness must not respawn"),
        registration=lambda **_kwargs: pytest.fail("durable readiness must not re-register"),
    )
    assert recovered_terminal.launched is False
    assert recovered_terminal.receipt == launch.receipt

    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            os.kill(launch.receipt.launch_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("fixture provider did not exit naturally")

    worktree = root / ".worktrees" / launch.receipt.successor_slug
    (worktree / "provider-result.txt").write_text("descendant\n", encoding="utf-8")
    _git(worktree, "add", "provider-result.txt")
    _git(worktree, "commit", "-qm", "provider descendant")
    _git(worktree, "push", "-q", "origin", f"HEAD:{launch.receipt.successor_branch}")
    historical_refs = "".join(
        f"create refs/heads/limen-relay/ready/{index:064x} {ready_commit}\n"
        for index in range(1, 71)
        if f"{index:064x}" != launch.receipt.relay_id
    )
    subprocess.run(
        ["git", "update-ref", "--stdin"],
        cwd=root.parent / "origin.git",
        input=historical_refs,
        capture_output=True,
        text=True,
        check=True,
    )
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    (common / "limen" / "campaign-relays" / f"{launch.receipt.relay_id}.json").unlink()
    recovered = discover_ready_relay(
        root,
        now_epoch=predecessor_deadline + 1,
    )
    assert recovered.receipt == launch.receipt
    assert recovered.payload["contract"]["schema"] == "limen.workstream.contract.v1"

    _git(root.parent / "origin.git", "update-ref", ready_ref, exact_main)
    with pytest.raises(
        CampaignRelayError,
        match="latest-ready ref is not held by its dedicated relay ref",
    ) as mismatched_ready:
        discover_ready_relay(
            root,
            now_epoch=predecessor_deadline + 1,
        )
    assert mismatched_ready.value.code == "relay_ready_invalid"
    _git(root.parent / "origin.git", "update-ref", ready_ref, ready_commit)

    (root / "main-advanced.txt").write_text("advanced\n", encoding="utf-8")
    _git(root, "add", "main-advanced.txt")
    _git(root, "commit", "-qm", "advance main after relay")
    _git(root, "push", "-q", "origin", "main")
    moved_main = _git(root, "rev-parse", "HEAD")
    recreated = reserve_relay(root, predecessor, exact_remote_main=moved_main)
    assert recreated.receipt.state == "reserved"
    assert recreated.receipt.exact_remote_main == moved_main
    moved_discovery = discover_ready_relay(
        root,
        now_epoch=predecessor_deadline + 1,
    )
    assert moved_discovery.receipt == launch.receipt
    _git(
        root.parent / "origin.git",
        "update-ref",
        "-d",
        f"refs/heads/{launch.receipt.successor_branch}",
    )
    recovered_without_topic = launch_reserved_relay(
        root,
        recreated.receipt.relay_id,
        lane_selector=lambda _root: pytest.fail("durable remote readiness must be recovered before lane selection"),
        process_factory=lambda *_args, **_kwargs: pytest.fail("durable remote readiness must not spawn"),
    )
    assert recovered_without_topic.launched is False
    assert recovered_without_topic.receipt == launch.receipt
    assert recovered_without_topic.receipt.exact_remote_main == exact_main


def test_activation_serializes_a_delayed_accepting_confirmation_with_keepalive(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registrations: list[bool] = []
    refresh_log = tmp_path / "refresh.log"
    registration_wrapper = tmp_path / "limen-register"
    registration_wrapper.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'for value in "$@"; do\n'
            '  case "$value" in\n'
            '    --accepting-work|--not-accepting-work) printf \'%s\\n\' "$value" >> "$RELAY_REFRESH_LOG" ;;\n'
            "  esac\n"
            "done\n"
        ),
        encoding="utf-8",
    )
    registration_wrapper.chmod(0o755)

    def register(**kwargs):
        accepting = kwargs["accepting_work"]
        registrations.append(accepting)
        if accepting:
            time.sleep(1.5)
        raw = json.dumps(
            {
                "accepting_work": accepting,
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", str(registration_wrapper))
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_SECONDS", "1")
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("RELAY_REFRESH_LOG", str(refresh_log))
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(tmp_path / "provider.pid"))
    monkeypatch.setenv("PROVIDER_SLEEP", "4")

    launch = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )

    assert launch.receipt.state == "ready"
    assert registrations == [False, True]
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not refresh_log.is_file():
        time.sleep(0.05)
    assert refresh_log.is_file()
    refreshes = refresh_log.read_text(encoding="utf-8").splitlines()
    assert "--accepting-work" in refreshes
    assert "--not-accepting-work" not in refreshes


def test_local_store_loss_during_live_remote_attempt_recovers_later_ready(
    effector_repo,
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    exact_main = _git(root, "rev-parse", "HEAD")
    reservation = reserve_relay(root, predecessor, exact_remote_main=exact_main)
    attempt_published = threading.Event()
    continue_spawn = threading.Event()
    registrations: list[bool] = []

    def register(**kwargs):
        registrations.append(kwargs["accepting_work"])
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        attempt_published.set()
        assert continue_spawn.wait(timeout=5)
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(tmp_path / "provider.pid"))
    monkeypatch.setenv("PROVIDER_SLEEP", "2")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            launch_reserved_relay,
            root,
            reservation.receipt.relay_id,
            timeout_seconds=20,
            process_factory=spawn,
            lane_selector=lambda _root: ("codex",),
            registration=register,
        )
        assert attempt_published.wait(timeout=5)
        common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        (common / "limen" / "campaign-relays" / f"{reservation.receipt.relay_id}.json").unlink()
        recreated = reserve_relay(root, predecessor, exact_remote_main=exact_main)
        duplicate = launch_reserved_relay(
            root,
            recreated.receipt.relay_id,
            process_factory=lambda *_args, **_kwargs: pytest.fail(
                "recovered remote attempt must not spawn a second provider"
            ),
            lane_selector=lambda _root: pytest.fail("recovered remote attempt must precede lane selection"),
            registration=lambda **_kwargs: pytest.fail("recovered remote attempt must not register a second session"),
        )
        assert duplicate.launched is False
        assert duplicate.receipt.state == "launching"
        assert duplicate.receipt.remote_attempt_commit is not None
        continue_spawn.set()
        completed = future.result(timeout=25)

    assert completed.receipt.state == "ready"
    assert registrations == [False, True]
    repeated = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        lane_selector=lambda _root: pytest.fail("ready relay must not reselect a lane"),
    )
    assert repeated.receipt == completed.receipt


def test_spawn_oserror_is_terminal_and_remote_attempt_blocks_recreation(
    effector_repo,
) -> None:
    root, predecessor, _provider, _deadline = effector_repo
    exact_main = _git(root, "rev-parse", "HEAD")
    reservation = reserve_relay(root, predecessor, exact_remote_main=exact_main)

    def fail_spawn(*_args, **_kwargs):
        raise OSError("injected spawn failure")

    failed = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        process_factory=fail_spawn,
        lane_selector=lambda _root: ("codex",),
    )
    assert failed.launched is True
    assert failed.receipt.state == "failed"
    assert failed.receipt.terminal_code == "relay_spawn_failed"
    assert failed.receipt.remote_attempt_commit is not None
    assert failed.receipt.remote_attempt_token is not None

    (root / "main-advanced.txt").write_text("advanced\n", encoding="utf-8")
    _git(root, "add", "main-advanced.txt")
    _git(root, "commit", "-qm", "advance main after relay attempt")
    _git(root, "push", "-q", "origin", "main")
    moved_main = _git(root, "rev-parse", "HEAD")
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    (common / "limen" / "campaign-relays" / f"{failed.receipt.relay_id}.json").unlink()
    recreated = reserve_relay(root, predecessor, exact_remote_main=moved_main)
    assert recreated.receipt.exact_remote_main == moved_main
    recovered = launch_reserved_relay(
        root,
        recreated.receipt.relay_id,
        process_factory=lambda *_args, **_kwargs: pytest.fail("durable remote attempt must suppress a second spawn"),
        lane_selector=lambda _root: pytest.fail("durable remote attempt must suppress lane reselection"),
    )
    assert recovered.launched is False
    assert recovered.receipt.state == "launching"
    assert recovered.receipt.remote_attempt_commit == failed.receipt.remote_attempt_commit
    assert recovered.receipt.exact_remote_main == exact_main


def test_exec_failure_channel_prevents_false_readiness(
    effector_repo,
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registrations: list[bool] = []
    provider_pid_path = tmp_path / "provider.pid"

    def register(**kwargs):
        accepting = kwargs["accepting_work"]
        registrations.append(accepting)
        if not accepting:
            provider.unlink()
        raw = json.dumps(
            {
                "accepting_work": accepting,
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(provider_pid_path))

    launch = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )

    assert launch.receipt.state == "failed"
    assert launch.receipt.terminal_code == "relay_exec_failed"
    assert registrations == [False]
    assert not provider_pid_path.exists()


@pytest.mark.parametrize(
    ("channel", "payload", "expected_code"),
    [
        ("exec", b"failed\n", "relay_exec_failed"),
        (
            "control",
            b"x" * (relay_core._CONTROL_LINE_CEILING + 1),
            "relay_control_oversized",
        ),
    ],
)
def test_startup_channel_terminal_errors_are_not_replaced_by_timeout(
    effector_repo,
    channel: str,
    payload: bytes,
    expected_code: str,
) -> None:
    root, predecessor, _provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    spawned: list[subprocess.Popen[bytes]] = []

    def spawn(_command, **kwargs):
        descriptor = kwargs[f"{channel}_descriptor"]
        child_source = f"""
import os
import time

os.write({descriptor}, {payload!r})
time.sleep(10)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", child_source],
            cwd=root,
            env=kwargs["env"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(
                kwargs["ack_descriptor"],
                kwargs["control_descriptor"],
                kwargs["exec_descriptor"],
            ),
        )
        spawned.append(process)
        return process

    launch = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=5,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
    )

    assert launch.receipt.terminal_code == expected_code
    assert len(spawned) == 1
    spawned[0].terminate()
    spawned[0].wait(timeout=2)


def test_startup_stream_read_error_after_partial_bytes_fails_closed(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registrations: list[bool] = []
    underlying_streams = []

    class PartialThenError:
        def __init__(self, stream):
            self.stream = stream
            self.reads = 0

        def read(self, _size):
            self.reads += 1
            if self.reads == 1:
                return self.stream.read(1)
            raise OSError("injected startup stream read failure")

        def close(self):
            return None

    def register(**kwargs):
        registrations.append(kwargs["accepting_work"])
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        process = _spawn_relay_process(command, **kwargs)
        assert process.stdout is not None
        underlying_streams.append(process.stdout)
        process.stdout = PartialThenError(process.stdout)
        return process

    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(tmp_path / "provider.pid"))
    monkeypatch.setenv("PROVIDER_SLEEP", "2")

    try:
        launch = launch_reserved_relay(
            root,
            reservation.receipt.relay_id,
            timeout_seconds=20,
            process_factory=spawn,
            lane_selector=lambda _root: ("codex",),
            registration=register,
        )
    finally:
        for stream in underlying_streams:
            stream.close()

    assert launch.receipt.state == "indeterminate"
    assert launch.receipt.terminal_code == "relay_startup_output_read_failed"
    assert launch.receipt.startup_stdout_bytes == 1
    assert launch.receipt.startup_stdout_truncated is False
    assert registrations == [False]


def test_startup_output_ceiling_crossed_before_selected_ack_fails_closed(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, predecessor, _provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    observed_digests: list[relay_process._BoundedStreamDigest] = []
    registrations: list[bool] = []
    ack_observation = tmp_path / "ack-observation.txt"
    original_digest = relay_process._BoundedStreamDigest

    class ObservableDigest(original_digest):
        def __init__(self) -> None:
            super().__init__()
            observed_digests.append(self)

    def register(**kwargs):
        registrations.append(kwargs["accepting_work"])
        assert observed_digests[0].wait_for_output_ceiling(timeout=2)
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(_command, **kwargs):
        successor = root / ".worktrees" / reservation.receipt.successor_slug
        successor.parent.mkdir(exist_ok=True)
        _git(root, "worktree", "add", "--detach", str(successor), "HEAD")
        child_source = f"""
import json
import os
from pathlib import Path

control_fd = {kwargs["control_descriptor"]}
exec_fd = {kwargs["exec_descriptor"]}
ack_fd = {kwargs["ack_descriptor"]}
event = {{
    "agent": "codex",
    "capabilities": ["conduct"],
    "relay_id": os.environ["LIMEN_CAMPAIGN_RELAY_ID"],
    "schema": "limen.campaign_relay_control.v1",
    "session_id": os.environ["LIMEN_WORKSTREAM_SESSION_ID"],
    "stage": "selected",
}}
payload = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\\n").encode()
while payload:
    payload = payload[os.write(control_fd, payload):]
payload = b"x" * {relay_process._STARTUP_OUTPUT_CEILING + 8192}
while payload:
    payload = payload[os.write(1, payload):]
ack = os.read(ack_fd, 32)
Path(os.environ["ACK_OBSERVATION"]).write_text(ack.hex() if ack else "closed", encoding="utf-8")
os.close(control_fd)
os.close(exec_fd)
"""
        env = {**kwargs["env"], "ACK_OBSERVATION": str(ack_observation)}
        return subprocess.Popen(
            [sys.executable, "-c", child_source],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(
                kwargs["ack_descriptor"],
                kwargs["control_descriptor"],
                kwargs["exec_descriptor"],
            ),
        )

    monkeypatch.setattr(
        "limen.conduct.campaign_relay_protocol._BoundedStreamDigest",
        ObservableDigest,
    )

    launch = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=10,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )

    assert launch.receipt.state == "indeterminate"
    assert launch.receipt.terminal_code == "relay_startup_output_oversized"
    assert launch.receipt.startup_stdout_truncated is True
    assert launch.receipt.startup_stdout_bytes == relay_process._STARTUP_OUTPUT_CEILING + 1
    assert registrations == [False]
    assert ack_observation.read_text(encoding="utf-8") == "closed"


def test_ready_publication_failure_rolls_broker_back_to_dormant(
    effector_repo,
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registrations: list[bool] = []
    provider_pid_path = tmp_path / "provider.pid"

    def register(**kwargs):
        accepting = kwargs["accepting_work"]
        registrations.append(accepting)
        raw = json.dumps(
            {
                "accepting_work": accepting,
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    def fail_ready_publication(*_args, **_kwargs):
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "injected atomic ready publication failure",
        )

    monkeypatch.setattr(
        "limen.conduct.campaign_relay_protocol._publish_ready_receipt",
        fail_ready_publication,
    )
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(provider_pid_path))
    monkeypatch.setenv("PROVIDER_SLEEP", "3")

    launch = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )

    assert launch.receipt.state == "indeterminate"
    assert launch.receipt.terminal_code == "relay_ready_publication_failed"
    assert launch.receipt.activation_response_sha256 is None
    assert registrations == [False, True, False]
    marker = root / ".worktrees" / launch.receipt.successor_slug / ".limen-workstream" / "relay-activated"
    assert not marker.exists()
    assert not _git(
        root,
        "ls-remote",
        "origin",
        f"refs/heads/limen-relay/ready/{launch.receipt.relay_id}",
    )
    assert not _git(
        root,
        "ls-remote",
        "origin",
        "refs/heads/limen-relay/latest/institutional-omega",
    )

    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        try:
            os.kill(launch.receipt.launch_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("rolled-back fixture provider did not exit naturally")


def test_expired_startup_deadline_bounds_activation_rollback_and_terminalization(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registration_deadlines: list[float | None] = []
    lock_deadlines: list[float | None] = []
    rollback_state_deadlines: list[float | None] = []
    original_lock = relay_protocol._activation_registration_lock
    original_replace = relay_protocol._replace_relay
    real_monotonic = time.monotonic

    class ExpiringClock:
        expired_value: float | None = None

        def monotonic(self) -> float:
            return real_monotonic() if self.expired_value is None else self.expired_value

    clock = ExpiringClock()

    def register(**kwargs):
        registration_deadlines.append(kwargs["deadline_monotonic"])
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    @contextmanager
    def observe_lock(worktree, *, deadline_monotonic=None):
        lock_deadlines.append(deadline_monotonic)
        if len(lock_deadlines) == 1:
            with original_lock(
                worktree,
                deadline_monotonic=deadline_monotonic,
            ):
                yield
        else:
            yield

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    def expire_then_fail(*_args, deadline_monotonic=None, **_kwargs):
        assert deadline_monotonic is not None
        clock.expired_value = deadline_monotonic + 1
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "injected publication failure after startup expiry",
        )

    def observe_replace(*args, **kwargs):
        if kwargs.get("updates") == {"activation_response_sha256": None}:
            rollback_state_deadlines.append(kwargs.get("deadline_monotonic"))
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(relay_core, "time", clock)
    monkeypatch.setattr(relay_protocol, "_activation_registration_lock", observe_lock)
    monkeypatch.setattr(relay_protocol, "_publish_ready_receipt", expire_then_fail)
    monkeypatch.setattr(relay_protocol, "_replace_relay", observe_replace)
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(tmp_path / "provider.pid"))
    monkeypatch.setenv("PROVIDER_SLEEP", "1")

    with pytest.raises(CampaignRelayError) as raised:
        launch_reserved_relay(
            root,
            reservation.receipt.relay_id,
            timeout_seconds=20,
            process_factory=spawn,
            lane_selector=lambda _root: ("codex",),
            registration=register,
        )

    assert raised.value.code == "relay_startup_timeout"
    assert len(lock_deadlines) == 2
    assert len(registration_deadlines) == 3
    assert len(rollback_state_deadlines) == 1
    assert len(set(lock_deadlines + registration_deadlines + rollback_state_deadlines)) == 1
    assert lock_deadlines[0] is not None


def _ready_publication_fixture() -> CampaignRelayReceiptV1:
    return CampaignRelayReceiptV1.model_validate(
        {
            "relay_id": "a" * 64,
            "workstream": "institutional-omega",
            "predecessor_receipt_blob": "b" * 40,
            "predecessor_contract_digest": "c" * 64,
            "predecessor_deadline_epoch": 2_000_000_000,
            "exact_remote_main": "d" * 40,
            "successor_slug": "successor",
            "successor_branch": "work/successor",
            "successor_session_id": "relay-successor",
            "state": "ready",
            "attempts": 1,
            "controller_pid": 11,
            "controller_process_started": "fixture-controller",
            "remote_attempt_commit": "e" * 40,
            "remote_attempt_token": "f" * 64,
            "selected_agent": "codex",
            "selected_capabilities": ["conduct"],
            "launch_pid": 12,
            "launch_process_started": "fixture-provider",
            "registration_response_sha256": "1" * 64,
            "activation_response_sha256": "2" * 64,
            "publication_commit": "3" * 40,
            "publication_parent": "d" * 40,
            "publication_receipt_blob": "4" * 40,
            "startup_stdout_sha256": "5" * 64,
            "startup_stdout_bytes": 0,
            "startup_stderr_sha256": "6" * 64,
            "startup_stderr_bytes": 0,
        }
    )


def test_ready_discovery_propagates_one_absolute_deadline(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _predecessor, _provider, _predecessor_deadline = effector_repo
    receipt = _ready_publication_fixture()
    deadline = time.monotonic() + 5
    observed_git_deadlines: list[float | None] = []
    observed_load_deadlines: list[float | None] = []
    observed_payload_deadlines: list[float | None] = []

    def git_result(_root, *args, deadline_monotonic=None):
        observed_git_deadlines.append(deadline_monotonic)
        ref = args[-1]
        return f"{receipt.publication_commit}\t{ref}"

    def load_ready(*_args, deadline_monotonic=None, **_kwargs):
        observed_load_deadlines.append(deadline_monotonic)
        return receipt

    def publication_payload(*_args, deadline_monotonic=None, **_kwargs):
        observed_payload_deadlines.append(deadline_monotonic)
        return {
            "contract": {
                "runway": {
                    "deadline_epoch": receipt.predecessor_deadline_epoch + 100,
                }
            }
        }

    monkeypatch.setattr(relay_protocol, "_git", git_result)
    monkeypatch.setattr(relay_protocol, "_load_remote_ready", load_ready)
    monkeypatch.setattr(relay_protocol, "_publication_payload", publication_payload)

    discovered = discover_ready_relay(
        root,
        now_epoch=receipt.predecessor_deadline_epoch + 1,
        deadline_monotonic=deadline,
    )

    assert discovered.receipt == receipt
    assert observed_git_deadlines == [deadline, deadline]
    assert observed_load_deadlines == [deadline]
    assert observed_payload_deadlines == [deadline]


def test_ready_discovery_bounds_a_stalled_remote_probe(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _predecessor, _provider, _predecessor_deadline = effector_repo
    observed_timeouts: list[float] = []

    def stalled_remote(*_args, timeout_seconds, **_kwargs):
        observed_timeouts.append(timeout_seconds)
        raise BoundedSubprocessError("timeout")

    monkeypatch.setattr(relay_core, "run_bounded_subprocess", stalled_remote)
    deadline = time.monotonic() + 0.25

    with pytest.raises(CampaignRelayError) as raised:
        discover_ready_relay(root, deadline_monotonic=deadline)

    assert raised.value.code == "relay_git_timeout"
    assert len(observed_timeouts) == 1
    assert 0 < observed_timeouts[0] <= 0.25


@pytest.mark.parametrize(
    ("push_code", "outcome", "expected_code"),
    [
        ("relay_ready_publication_failed", "success", None),
        ("relay_git_timeout", "confirmed_failure", "relay_ready_publication_failed"),
        ("relay_git_unavailable", "uncertain", "relay_ready_publication_uncertain"),
    ],
)
def test_every_ready_push_exception_uses_three_way_exact_ref_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    push_code: str,
    outcome: str,
    expected_code: str | None,
) -> None:
    receipt = _ready_publication_fixture()

    def git_result(_root, args, **_kwargs):
        if args[:2] == ["push", "--atomic"]:
            raise CampaignRelayError(push_code, "injected push result")
        if args[0] == "hash-object":
            return "7" * 40
        if args[0] == "write-tree":
            return "8" * 40
        if args[0] == "commit-tree":
            return "9" * 40
        return ""

    observed: list[str] = []

    def reconcile(*_args, **_kwargs):
        observed.append(outcome)
        return outcome

    monkeypatch.setattr(relay_publication, "_git_with_input", git_result)
    monkeypatch.setattr(relay_publication, "_ready_publication_outcome", reconcile)
    if expected_code is None:
        relay_publication._publish_ready_receipt(tmp_path, receipt)
    else:
        with pytest.raises(CampaignRelayError) as raised:
            relay_publication._publish_ready_receipt(tmp_path, receipt)
        assert raised.value.code == expected_code
    assert observed == [outcome]


@pytest.mark.parametrize(
    ("ready_head", "latest_head", "error_code", "expected"),
    [
        ("a" * 40, "a" * 40, None, "success"),
        ("a" * 40, "b" * 40, None, "confirmed_failure"),
        (None, None, "relay_publication_unreachable", "confirmed_failure"),
        (None, None, "relay_git_unavailable", "uncertain"),
    ],
)
def test_ready_ref_reconciliation_distinguishes_remote_truth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ready_head: str | None,
    latest_head: str | None,
    error_code: str | None,
    expected: str,
) -> None:
    commit = "a" * 40

    def remote_head(_root, ref, **_kwargs):
        if error_code is not None:
            raise CampaignRelayError(error_code, "injected reconciliation result")
        return ready_head if "/ready/" in ref else latest_head

    monkeypatch.setattr(relay_publication, "_remote_ref_head", remote_head)
    assert (
        relay_publication._ready_publication_outcome(
            tmp_path,
            commit=commit,
            ready_ref="refs/heads/limen-relay/ready/" + "c" * 64,
            latest_ref="refs/heads/limen-relay/latest/institutional-omega",
        )
        == expected
    )


def test_uncertain_accepted_ready_push_preserves_activation_until_recovery(
    effector_repo,
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registrations: list[bool] = []
    atomic_pushed = False
    original_git_with_input = relay_publication._git_with_input
    original_remote_ref_head = relay_publication._remote_ref_head

    def register(**kwargs):
        registrations.append(kwargs["accepting_work"])
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    def ambiguous_git(root, args, **kwargs):
        nonlocal atomic_pushed
        result = original_git_with_input(root, args, **kwargs)
        if args[:2] == ["push", "--atomic"]:
            atomic_pushed = True
            raise CampaignRelayError(
                "relay_git_output_oversized",
                "injected accepted push with an ambiguous output boundary",
            )
        return result

    def unavailable_reconciliation(root, ref, **kwargs):
        if atomic_pushed:
            raise CampaignRelayError(
                "relay_git_unavailable",
                "injected remote reconciliation outage",
            )
        return original_remote_ref_head(root, ref, **kwargs)

    monkeypatch.setattr(relay_publication, "_git_with_input", ambiguous_git)
    monkeypatch.setattr(
        relay_publication,
        "_remote_ref_head",
        unavailable_reconciliation,
    )
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(tmp_path / "provider.pid"))
    monkeypatch.setenv("PROVIDER_SLEEP", "4")

    uncertain = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )

    assert uncertain.receipt.state == "indeterminate"
    assert uncertain.receipt.terminal_code == "relay_ready_publication_uncertain"
    assert uncertain.receipt.activation_response_sha256 is not None
    assert registrations == [False, True]
    marker = root / ".worktrees" / uncertain.receipt.successor_slug / ".limen-workstream" / "relay-activated"
    assert marker.read_text(encoding="utf-8") == f"{uncertain.receipt.relay_id}\n"
    assert _git(
        root,
        "ls-remote",
        "origin",
        f"refs/heads/limen-relay/ready/{uncertain.receipt.relay_id}",
    )

    monkeypatch.setattr(
        relay_publication,
        "_git_with_input",
        original_git_with_input,
    )
    monkeypatch.setattr(
        relay_publication,
        "_remote_ref_head",
        original_remote_ref_head,
    )
    recovered = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        lane_selector=lambda _root: pytest.fail("durable ready ref must not reselect a lane"),
        registration=lambda **_kwargs: pytest.fail("durable ready ref must not rewrite broker activation"),
    )
    assert recovered.launched is False
    assert recovered.receipt.state == "ready"
    assert recovered.receipt.activation_response_sha256 == uncertain.receipt.activation_response_sha256
    assert registrations == [False, True]
    assert marker.is_file()


def test_uncertain_absent_ready_push_is_republished_without_a_second_provider(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, predecessor, provider, _predecessor_deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    registrations: list[bool] = []
    atomic_attempted = False
    original_git_with_input = relay_publication._git_with_input
    original_remote_ref_head = relay_publication._remote_ref_head

    def register(**kwargs):
        registrations.append(kwargs["accepting_work"])
        raw = json.dumps(
            {
                "accepting_work": kwargs["accepting_work"],
                "agent": kwargs["agent"],
                "session_id": kwargs["session_id"],
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(raw).hexdigest(), len(raw)

    def spawn(command, **kwargs):
        command = [str(ROOT / "scripts" / "start-worktree-session.sh"), *command[1:]]
        return _spawn_relay_process(command, **kwargs)

    def drop_atomic_push(root, args, **kwargs):
        nonlocal atomic_attempted
        if args[:2] == ["push", "--atomic"]:
            atomic_attempted = True
            raise CampaignRelayError(
                "relay_git_timeout",
                "injected unaccepted atomic ready push timeout",
            )
        return original_git_with_input(root, args, **kwargs)

    def unavailable_reconciliation(root, ref, **kwargs):
        if atomic_attempted:
            raise CampaignRelayError(
                "relay_git_unavailable",
                "injected remote reconciliation outage",
            )
        return original_remote_ref_head(root, ref, **kwargs)

    monkeypatch.setattr(relay_publication, "_git_with_input", drop_atomic_push)
    monkeypatch.setattr(relay_publication, "_remote_ref_head", unavailable_reconciliation)
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CLI_BIN", "/usr/bin/true")
    monkeypatch.setenv("LIMEN_CODEX_BIN", str(provider))
    monkeypatch.setenv("LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS", "1")
    monkeypatch.setenv("PROVIDER_ENV_LEAKS", str(tmp_path / "provider-env-leaks.txt"))
    monkeypatch.setenv("PROVIDER_PID", str(tmp_path / "provider.pid"))
    monkeypatch.setenv("PROVIDER_SLEEP", "8")

    uncertain = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        timeout_seconds=20,
        process_factory=spawn,
        lane_selector=lambda _root: ("codex",),
        registration=register,
    )

    assert uncertain.receipt.state == "indeterminate"
    assert uncertain.receipt.terminal_code == "relay_ready_publication_uncertain"
    assert uncertain.receipt.selected_capabilities
    assert registrations == [False, True]
    assert not _git(
        root,
        "ls-remote",
        "origin",
        f"refs/heads/limen-relay/ready/{uncertain.receipt.relay_id}",
    )

    monkeypatch.setattr(relay_publication, "_git_with_input", original_git_with_input)
    monkeypatch.setattr(relay_publication, "_remote_ref_head", original_remote_ref_head)
    recovered = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        process_factory=lambda *_args, **_kwargs: pytest.fail(
            "uncertain ready reconciliation must not spawn a second provider"
        ),
        lane_selector=lambda _root: pytest.fail("uncertain ready reconciliation must not reselect a lane"),
        registration=register,
    )

    assert recovered.launched is False
    assert recovered.receipt.state == "ready"
    assert recovered.receipt.terminal_code is None
    assert registrations == [False, True]
    assert _git(
        root,
        "ls-remote",
        "origin",
        f"refs/heads/limen-relay/ready/{uncertain.receipt.relay_id}",
    )


def test_capacity_denial_keeps_attempt_unconsumed_and_refreshes_its_base(
    effector_repo,
) -> None:
    root, predecessor, _provider, _deadline = effector_repo
    initial_main = _git(root, "rev-parse", "HEAD")
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=initial_main,
    )

    with pytest.raises(CampaignRelayError, match="capacity"):
        launch_reserved_relay(
            root,
            reservation.receipt.relay_id,
            lane_selector=lambda _root: (),
        )

    current = _read_relay(root, reservation.receipt.relay_id)
    assert current.state == "reserved"
    assert current.attempts == 0

    (root / "main-advanced-after-capacity-denial.txt").write_text("advanced\n", encoding="utf-8")
    _git(root, "add", "main-advanced-after-capacity-denial.txt")
    _git(root, "commit", "-qm", "advance main after capacity denial")
    _git(root, "push", "-q", "origin", "main")
    advanced_main = _git(root, "rev-parse", "HEAD")
    refreshed = reserve_relay(
        root,
        predecessor,
        exact_remote_main=advanced_main,
    )
    assert refreshed.receipt.relay_id == reservation.receipt.relay_id
    assert refreshed.receipt.exact_remote_main == advanced_main

    def observe_spawn(command, **kwargs):
        assert command[command.index("--from") + 1] == advanced_main
        assert kwargs["env"]["LIMEN_CAMPAIGN_RELAY_BASE"] == advanced_main
        raise OSError("stop after proving the refreshed launch base")

    launch = launch_reserved_relay(
        root,
        refreshed.receipt.relay_id,
        lane_selector=lambda _root: ("codex",),
        process_factory=observe_spawn,
    )
    assert launch.receipt.state == "failed"
    assert launch.receipt.terminal_code == "relay_spawn_failed"


def test_capacity_census_consumes_the_entry_time_startup_deadline(
    effector_repo,
) -> None:
    root, predecessor, _provider, _deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )

    def slow_capacity(_root):
        time.sleep(1.05)
        return ("codex",)

    started = time.monotonic()
    with pytest.raises(CampaignRelayError) as raised:
        launch_reserved_relay(
            root,
            reservation.receipt.relay_id,
            timeout_seconds=1,
            lane_selector=slow_capacity,
            process_factory=lambda *_args, **_kwargs: pytest.fail(
                "an expired startup deadline must not spawn a provider"
            ),
        )

    assert raised.value.code == "relay_startup_timeout"
    assert time.monotonic() - started < 1.5
    current = _read_relay(root, reservation.receipt.relay_id)
    assert current.state == "reserved"
    assert current.attempts == 0


@pytest.mark.parametrize("expire_before_lock", [False, True])
def test_linked_worktree_reconciliation_rolls_back_the_primary_successor_session(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    expire_before_lock: bool,
) -> None:
    root, predecessor, _provider, _deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    successor = root / ".worktrees" / reservation.receipt.successor_slug
    observer = tmp_path / "observer"
    successor.parent.mkdir(exist_ok=True)
    _git(root, "worktree", "add", "--detach", str(successor), "HEAD")
    _git(root, "worktree", "add", "--detach", str(observer), "HEAD")
    capsule_dir = successor / ".limen-workstream"
    capsule_dir.mkdir()
    marker = capsule_dir / "relay-activated"
    marker.write_text(f"{reservation.receipt.relay_id}\n", encoding="utf-8")
    marker.chmod(0o600)
    uncertain = _replace_relay(
        root,
        reservation.receipt.relay_id,
        expected_states=frozenset({"reserved"}),
        updates={
            "state": "indeterminate",
            "attempts": 1,
            "controller_pid": 11,
            "controller_process_started": "fixture-controller",
            "remote_attempt_commit": "a" * 40,
            "remote_attempt_token": "b" * 64,
            "selected_agent": "codex",
            "selected_capabilities": ("conduct",),
            "launch_pid": 12,
            "launch_process_started": "fixture-provider",
            "registration_response_sha256": "c" * 64,
            "activation_response_sha256": "d" * 64,
            "terminal_code": "relay_ready_publication_uncertain",
        },
    )
    registrations: list[tuple[Path, bool, float | None]] = []
    lock_deadlines: list[float | None] = []
    original_lock = relay_protocol._activation_registration_lock
    real_monotonic = time.monotonic

    class ExpiringClock:
        expired_value: float | None = None

        def monotonic(self) -> float:
            return real_monotonic() if self.expired_value is None else self.expired_value

    clock = ExpiringClock()

    def register(**kwargs):
        registrations.append(
            (
                kwargs["worktree"],
                kwargs["accepting_work"],
                kwargs["deadline_monotonic"],
            )
        )
        return "e" * 64, 1

    @contextmanager
    def observe_lock(worktree, *, deadline_monotonic=None):
        lock_deadlines.append(deadline_monotonic)
        if expire_before_lock:
            assert deadline_monotonic is not None
            clock.expired_value = deadline_monotonic + 1
        with original_lock(
            worktree,
            deadline_monotonic=deadline_monotonic,
        ):
            yield

    monkeypatch.setattr(relay_core, "time", clock)
    monkeypatch.setattr(relay_protocol, "_activation_registration_lock", observe_lock)

    def launch():
        return launch_reserved_relay(
            observer,
            uncertain.relay_id,
            process_identity=lambda _pid: (_ for _ in ()).throw(
                CampaignRelayError("fixture_absent", "fixture provider is absent")
            ),
            lane_selector=lambda _root: pytest.fail("a consumed relay must not reselect capacity"),
            registration=register,
        )

    if expire_before_lock:
        with pytest.raises(CampaignRelayError) as raised:
            launch()
        assert raised.value.code == "relay_startup_timeout"
        clock.expired_value = None
        current = _read_relay(root, uncertain.relay_id)
        assert current.state == "indeterminate"
        assert current.activation_response_sha256 == uncertain.activation_response_sha256
        assert registrations == []
        assert marker.is_file()
    else:
        reconciled = launch()
        assert reconciled.launched is False
        assert reconciled.receipt.state == "indeterminate"
        assert reconciled.receipt.terminal_code == "relay_ready_provider_absent"
        assert reconciled.receipt.activation_response_sha256 is None
        assert registrations == [(successor.resolve(), False, lock_deadlines[0])]
        assert not marker.exists()

    assert len(lock_deadlines) == 1
    assert lock_deadlines[0] is not None


def test_relay_git_probe_closes_oversized_output_during_execution(
    effector_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _predecessor, _provider, _deadline = effector_repo

    def overflow(*_args, **_kwargs):
        raise BoundedSubprocessError("output")

    monkeypatch.setattr(
        "limen.conduct.campaign_relay.run_bounded_subprocess",
        overflow,
    )
    with pytest.raises(CampaignRelayError, match="output ceiling") as raised:
        _git_bytes(root, "status")
    assert raised.value.code == "relay_git_output_oversized"


def test_registration_timeout_kills_an_exited_wrappers_pipe_holding_descendant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = tmp_path / "register-wrapper"
    child_pid_path = tmp_path / "child.pid"
    wrapper.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import os, subprocess, sys\n"
            "child = subprocess.Popen("
            "[sys.executable, '-c', 'import time; time.sleep(30)'],"
            " stdout=sys.stdout, stderr=sys.stderr)\n"
            "open(os.environ['RELAY_TEST_CHILD_PID'], 'w', encoding='utf-8').write(str(child.pid))\n"
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = {
        **os.environ,
        "LIMEN_CLI_BIN": str(wrapper),
        "RELAY_TEST_CHILD_PID": str(child_pid_path),
    }
    monkeypatch.setattr(relay_process, "_REGISTRATION_TIMEOUT_SECONDS", 0.3)

    with pytest.raises(CampaignRelayError, match="bounded deadline") as raised:
        _bounded_registration(
            root=tmp_path,
            env=env,
            agent="codex",
            capabilities=("conduct",),
            session_id="relay-fixture",
            worktree=tmp_path,
            accepting_work=False,
        )

    assert raised.value.code == "relay_registration_timeout"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("registration cleanup left its descendant alive")


def test_dead_controller_reconciles_to_indeterminate_without_respawn(
    effector_repo,
) -> None:
    root, predecessor, _provider, _deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    _replace_relay(
        root,
        reservation.receipt.relay_id,
        expected_states=frozenset({"reserved"}),
        updates={
            "attempts": 1,
            "controller_pid": 999_999_999,
            "controller_process_started": "linux-clock-ticks:1",
            "state": "launching",
        },
    )

    reconciled = launch_reserved_relay(
        root,
        reservation.receipt.relay_id,
        process_identity=lambda _pid: (_ for _ in ()).throw(
            CampaignRelayError("fixture_absent", "fixture process is absent")
        ),
        lane_selector=lambda _root: pytest.fail("consumed relay must not reselect a lane"),
    )

    assert reconciled.launched is False
    assert reconciled.receipt.state == "indeterminate"
    assert reconciled.receipt.terminal_code == "relay_controller_interrupted"
    assert reconciled.receipt.attempts == 1


def test_terminalization_does_not_open_a_fresh_bound_after_startup_expiry(
    effector_repo,
) -> None:
    root, predecessor, _provider, _deadline = effector_repo
    reservation = reserve_relay(
        root,
        predecessor,
        exact_remote_main=_git(root, "rev-parse", "HEAD"),
    )
    _replace_relay(
        root,
        reservation.receipt.relay_id,
        expected_states=frozenset({"reserved"}),
        updates={
            "attempts": 1,
            "controller_pid": 999_999_999,
            "controller_process_started": "fixture-controller",
            "state": "launching",
        },
    )
    expired = time.monotonic() - 1
    started = time.monotonic()

    with pytest.raises(CampaignRelayError) as raised:
        relay_process._terminalize_relay(
            root,
            reservation.receipt.relay_id,
            state="indeterminate",
            code="fixture_expired",
            stdout=relay_process._BoundedStreamDigest(),
            stderr=relay_process._BoundedStreamDigest(),
            deadline_monotonic=expired,
        )

    assert raised.value.code == "relay_startup_timeout"
    assert time.monotonic() - started < 0.2
    assert _read_relay(root, reservation.receipt.relay_id).state == "launching"
