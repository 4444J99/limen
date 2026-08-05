from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CELLS = ROOT / "scripts" / "cells.sh"


def _init_repo(path: Path, branch: str) -> None:
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)


def _init_cell_with_remote(root: Path, slug: str) -> Path:
    cell = root / ".claude" / "worktrees" / slug
    cell.mkdir(parents=True)
    (cell / "README.md").write_text("cell\n", encoding="utf-8")
    _init_repo(cell, "main")
    remote = root / f"{slug}.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=cell, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=cell, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", f"cell/{slug}"], cwd=cell, check=True, capture_output=True, text=True)
    return cell


def _write_fake_reclaim(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "reclaim-worktrees.py").write_text(
        "import sys\nprint('fake reclaim ' + ' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )


def _receipt(path: Path) -> dict[str, str]:
    return {
        key: value
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }


def _wait_until(predicate, *, attempts: int = 100) -> bool:
    for _ in range(attempts):
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _write_recording_limen(path: Path) -> None:
    path.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$CELL_TEST_CALLS"\nprintf \'{"status":"ok"}\\n\'\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _terminate_exact_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    _wait_until(lambda: not _pid_alive(pid))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_scoped_conductor_registers_with_canonical_broker_without_cell_board(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    cell = root / ".claude" / "worktrees" / "demo"
    cell.mkdir(parents=True)
    (root / "logs" / "cells").mkdir(parents=True)
    canonical_board = root / "tasks.yaml"
    canonical_board.write_text(
        """version: "1.0"
portal:
  name: test
tasks:
  - id: T1
    title: mixed-purpose task
    target_agent: any
    status: open
    created: "2026-07-01"
""",
        encoding="utf-8",
    )
    (cell / "README.md").write_text("cell\n", encoding="utf-8")
    _init_repo(cell, "cell/demo")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_limen = fake_bin / "limen"
    fake_limen.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$*" > "$LIMEN_LIVE_ROOT/register.args"\n'
        "printf 'agent=%s\\nroot=%s\\nlive=%s\\nworkstream=%s\\n' "
        '"$LIMEN_AGENT" "$LIMEN_ROOT" "$LIMEN_LIVE_ROOT" "${LIMEN_WORKSTREAM:-}" '
        '> "$LIMEN_LIVE_ROOT/register.env"\n',
        encoding="utf-8",
    )
    fake_limen.chmod(0o755)

    env = {
        **os.environ,
        "LIMEN_ROOT": str(root),
        "LIMEN_AGENT": "opencode",
        "LIMEN_CONDUCT_STATE": str(root / "conduct.sqlite"),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        ["bash", str(CELLS), "conduct", "demo", "--workstream", "financial"],
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    register_env = root / "register.env"
    for _ in range(50):
        if register_env.exists():
            break
        time.sleep(0.02)

    assert register_env.exists()
    assert not (cell / "tasks.cell.yaml").exists()
    assert "T1" in canonical_board.read_text(encoding="utf-8")
    assert (
        (root / "register.args")
        .read_text(encoding="utf-8")
        .startswith("conduct register --agent opencode --surface cell:financial --session-id cell-demo")
    )
    env_text = register_env.read_text(encoding="utf-8")
    assert f"root={cell}" in env_text
    assert f"live={root}" in env_text
    assert "agent=opencode" in env_text
    assert "workstream=financial" in env_text
    receipt = _receipt(root / "logs" / "cells" / "demo.pid")
    assert receipt["schema"] == "limen.cell_registration.v1"
    assert receipt["session_id"] == "cell-demo"
    assert receipt["agent"] == "opencode"
    assert receipt["cell_path"] == str(cell)
    assert receipt["run_id"] == ""
    assert receipt["human_protected"] == "0"


def test_cell_commands_ignore_non_cell_worktrees(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    cells = root / ".claude" / "worktrees"
    (root / "logs" / "cells").mkdir(parents=True)

    real = cells / "demo"
    other = cells / "not-a-cell"
    for path, branch in ((real, "cell/demo"), (other, "worktree-not-a-cell")):
        (path / "scripts").mkdir(parents=True)
        (path / "tasks.yaml").write_text('version: "1.0"\ntasks: []\n', encoding="utf-8")
        _init_repo(path, branch)

    env = {**os.environ, "LIMEN_ROOT": str(root)}
    listing = subprocess.run(
        ["bash", str(CELLS), "ls"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert listing.returncode == 0
    assert "demo" in listing.stdout
    assert "not-a-cell" not in listing.stdout

    rejected = subprocess.run(
        ["bash", str(CELLS), "cd", "not-a-cell"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert rejected.returncode != 0
    assert "not a cell" in rejected.stderr


def test_cell_reap_force_is_retired(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    cell = _init_cell_with_remote(root, "demo")
    _write_fake_reclaim(root)

    result = subprocess.run(
        ["bash", str(CELLS), "reap", "demo", "--force"],
        text=True,
        capture_output=True,
        env={**os.environ, "LIMEN_ROOT": str(root)},
        check=False,
    )

    assert result.returncode != 0
    assert "cell reap --force is retired" in result.stderr
    assert cell.exists()


def test_cell_reap_delegates_without_removing_worktree_or_branch(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    cell = _init_cell_with_remote(root, "demo")
    _write_fake_reclaim(root)

    result = subprocess.run(
        ["bash", str(CELLS), "reap", "demo"],
        text=True,
        capture_output=True,
        env={**os.environ, "LIMEN_ROOT": str(root)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "physical removal is delegated" in result.stdout
    assert "fake reclaim --force" in result.stdout
    assert cell.exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "cell/demo"],
        cwd=cell,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "cell/demo" in branches.stdout


@pytest.mark.parametrize(
    ("start_identity", "expected_reason"),
    [
        ("definitely-not-the-live-start", "stale-start"),
        (None, "foreign-process"),
    ],
)
def test_cell_stop_rejects_stale_or_reused_foreign_pid_without_signalling(
    tmp_path: Path,
    start_identity: str | None,
    expected_reason: str,
) -> None:
    root = tmp_path / "limen"
    logs = root / "logs" / "cells"
    logs.mkdir(parents=True)
    victim = subprocess.Popen(["sleep", "30"])
    try:
        live_start = subprocess.run(
            ["ps", "-p", str(victim.pid), "-o", "lstart="],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (logs / "demo.pid").write_text(
            "\n".join(
                [
                    "schema=limen.cell_registration.v1",
                    "state=registered",
                    "registration_status=accepted",
                    f"pid={victim.pid}",
                    f"start_identity={start_identity or live_start}",
                    "owner_token=forged-owner-token",
                    f"script_path={CELLS}",
                    "slug=demo",
                    "session_id=cell-demo",
                    "agent=codex",
                    "surface=cell",
                    f"cell_path={root / '.claude' / 'worktrees' / 'demo'}",
                    "loop=1",
                    "workstream=",
                    "run_id=",
                    "run_owner_session_id=",
                    "human_protected=0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", str(CELLS), "stop", "demo"],
            text=True,
            capture_output=True,
            env={**os.environ, "LIMEN_ROOT": str(root)},
            check=False,
        )

        assert result.returncode != 0
        assert expected_reason in result.stderr
        assert "refusing to signal recorded PID" in result.stderr
        assert victim.poll() is None
    finally:
        victim.terminate()
        victim.wait(timeout=5)


def test_cell_stop_requests_cooperative_broker_stop_for_owned_run_without_local_signal(
    tmp_path: Path,
) -> None:
    root = tmp_path / "limen"
    _init_cell_with_remote(root, "demo")
    (root / "logs" / "cells").mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_recording_limen(fake_bin / "limen")
    calls = root / "limen.calls"
    env = {
        **os.environ,
        "LIMEN_ROOT": str(root),
        "LIMEN_AGENT": "opencode",
        "LIMEN_CONDUCT_STATE": str(root / "conduct.sqlite"),
        "LIMEN_RUN_ID": "run-child-7",
        "LIMEN_CONDUCTOR_SESSION_ID": "conductor-session",
        "CELL_TEST_CALLS": str(calls),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    launched = subprocess.run(
        ["bash", str(CELLS), "conduct", "demo", "--loop"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    receipt_path = root / "logs" / "cells" / "demo.pid"
    assert _wait_until(
        lambda: receipt_path.exists() and _receipt(receipt_path).get("registration_status") == "accepted"
    )
    cpid = int(_receipt(receipt_path)["pid"])
    try:
        stopped = subprocess.run(
            ["bash", str(CELLS), "stop", "demo"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        assert stopped.returncode == 0, stopped.stderr
        assert "cooperative stop requested" in stopped.stdout
        assert "conduct request-stop run-child-7 --session-id conductor-session" in calls.read_text(encoding="utf-8")
        assert _pid_alive(cpid)
        assert "kill -9" not in CELLS.read_text(encoding="utf-8")
    finally:
        _terminate_exact_pid(cpid)


def test_cell_stop_gracefully_terms_only_exact_owned_registration_loop(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    _init_cell_with_remote(root, "demo")
    (root / "logs" / "cells").mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_recording_limen(fake_bin / "limen")
    calls = root / "limen.calls"
    env = {
        **os.environ,
        "LIMEN_ROOT": str(root),
        "LIMEN_AGENT": "codex",
        "LIMEN_CONDUCT_STATE": str(root / "conduct.sqlite"),
        "CELL_TEST_CALLS": str(calls),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    launched = subprocess.run(
        ["bash", str(CELLS), "conduct", "demo", "--loop"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    receipt_path = root / "logs" / "cells" / "demo.pid"
    assert _wait_until(
        lambda: receipt_path.exists() and _receipt(receipt_path).get("registration_status") == "accepted"
    )
    cpid = int(_receipt(receipt_path)["pid"])

    stopped = subprocess.run(
        ["bash", str(CELLS), "stop", "demo"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert stopped.returncode == 0, stopped.stderr
    assert "stopped gracefully" in stopped.stdout
    assert _wait_until(lambda: not _pid_alive(cpid))
    assert _receipt(receipt_path)["state"] == "stopped"
    assert "request-stop" not in calls.read_text(encoding="utf-8")


def test_cell_stop_refuses_human_protected_registration(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    _init_cell_with_remote(root, "demo")
    (root / "logs" / "cells").mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_recording_limen(fake_bin / "limen")
    calls = root / "limen.calls"
    env = {
        **os.environ,
        "LIMEN_ROOT": str(root),
        "LIMEN_AGENT": "claude",
        "LIMEN_CONDUCT_STATE": str(root / "conduct.sqlite"),
        "LIMEN_HUMAN_PROTECTED": "1",
        "CELL_TEST_CALLS": str(calls),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    launched = subprocess.run(
        ["bash", str(CELLS), "conduct", "demo", "--loop"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    receipt_path = root / "logs" / "cells" / "demo.pid"
    assert _wait_until(
        lambda: receipt_path.exists() and _receipt(receipt_path).get("registration_status") == "accepted"
    )
    cpid = int(_receipt(receipt_path)["pid"])
    try:
        stopped = subprocess.run(
            ["bash", str(CELLS), "stop", "demo"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

        assert stopped.returncode != 0
        assert "human-protected" in stopped.stderr
        assert _pid_alive(cpid)
        assert "--human-protected" in calls.read_text(encoding="utf-8")
    finally:
        _terminate_exact_pid(cpid)
