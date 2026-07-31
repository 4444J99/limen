"""The UMA checkout has ONE name, and a missing one is a named blocker — never a crash.

The defect these pin (2026-07-27 → 2026-07-31): five call sites resolved the UMA checkout
independently under two env-var names (`UMA_ROOT` in four, `LIMEN_UMA_ROOT` in a fifth), all
defaulting to `~/Workspace/universal-mail--automation`. That path does not exist — the real checkout
is one directory deeper. So `correspondence-walk._import_uma()` returned None every beat and, per its
own docstring, "every reply-owed row → needs-human": a live recruiter thread sat unanswered while the
mailbox looked like it had nothing owed in it.

Nothing failed loudly, because the resolution chain ended in `["umail"]` — a binary installed
nowhere — so a missing checkout reached `subprocess.run` and raised `FileNotFoundError: 'umail'`
inside a fail-open beat rung, where a crash is indistinguishable from silence.

Hermetic: every test builds its own fake checkout and clears the real environment, so these prove the
same thing on a CI runner that has no UMA checkout at all.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "scripts" / "_uma_root.py"


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def uma(monkeypatch):
    module = _load("uma_root_mod", "scripts/_uma_root.py")
    for var in ("UMA_ROOT", "LIMEN_UMA_ROOT", "UMA_BIN"):
        monkeypatch.delenv(var, raising=False)
    # No host checkout may leak in — these tests must mean the same thing on a bare CI runner.
    monkeypatch.setattr(module, "default_candidates", lambda: [])
    return module


def _checkout(tmp_path: Path, name: str = "uma") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "cli.py").write_text("# fake UMA cli\n")
    return root


# ── the marker: existing is not the same as being the checkout ───────────────────────────────


def test_a_directory_without_the_marker_is_not_a_checkout(uma, tmp_path):
    """The 2026-07-27 failure was a plausible-looking path with nothing behind it."""
    empty = tmp_path / "looks-right"
    empty.mkdir()
    assert uma.is_checkout(empty) is False
    assert uma.is_checkout(_checkout(tmp_path)) is True


# ── explicit configuration wins, and a wrong one is LOUD ─────────────────────────────────────


def test_explicit_uma_root_resolves(uma, monkeypatch, tmp_path):
    root = _checkout(tmp_path)
    monkeypatch.setenv("UMA_ROOT", str(root))
    assert uma.resolve()[0] == root


def test_explicit_but_wrong_is_an_error_not_a_fallthrough(uma, monkeypatch, tmp_path):
    """Silently correcting bad config is what makes config errors invisible. A wrong UMA_ROOT must
    NOT be quietly replaced by a working default — it must say so and resolve to nothing."""
    good = _checkout(tmp_path, "real")
    monkeypatch.setattr(uma, "default_candidates", lambda: [good])
    monkeypatch.setenv("UMA_ROOT", str(tmp_path / "typo"))

    root, reason = uma.resolve()
    assert root is None, "a working default silently rescued a wrong explicit value"
    assert "UMA_ROOT" in reason and "typo" in reason


def test_limen_uma_root_is_honoured_as_the_second_name(uma, monkeypatch, tmp_path):
    """check-opportunity-lane.sh read this name while four other sites read UMA_ROOT."""
    root = _checkout(tmp_path)
    monkeypatch.setenv("LIMEN_UMA_ROOT", str(root))
    assert uma.resolve()[0] == root


def test_uma_root_outranks_limen_uma_root(uma, monkeypatch, tmp_path):
    first = _checkout(tmp_path, "first")
    second = _checkout(tmp_path, "second")
    monkeypatch.setenv("UMA_ROOT", str(first))
    monkeypatch.setenv("LIMEN_UMA_ROOT", str(second))
    assert uma.resolve()[0] == first


def test_default_candidates_are_searched_in_order(uma, monkeypatch, tmp_path):
    missing = tmp_path / "absent"
    present = _checkout(tmp_path, "present")
    monkeypatch.setattr(uma, "default_candidates", lambda: [missing, present])
    assert uma.resolve()[0] == present


def test_unresolved_reason_names_what_was_searched(uma, monkeypatch, tmp_path):
    """The log must say what to fix. The old code said nothing at all."""
    monkeypatch.setattr(uma, "default_candidates", lambda: [tmp_path / "nowhere"])
    root, reason = uma.resolve()
    assert root is None
    assert "nowhere" in reason and "UMA_ROOT" in reason


# ── the crash that started this ──────────────────────────────────────────────────────────────


def test_uma_command_never_returns_the_phantom_binary(uma):
    """`umail` is installed nowhere on this host. Returning it converted a resolvable config problem
    into FileNotFoundError raised from inside a fail-open rung."""
    assert uma.uma_command() is None


def test_uma_command_runs_the_resolved_cli(uma, monkeypatch, tmp_path):
    root = _checkout(tmp_path)
    monkeypatch.setenv("UMA_ROOT", str(root))
    command = uma.uma_command()
    assert command is not None
    assert command[-1] == str(root / "cli.py")


def test_uma_bin_override_wins(uma, monkeypatch):
    monkeypatch.setenv("UMA_BIN", "/opt/bin/umail")
    assert uma.uma_command() == ["/opt/bin/umail"]


def test_explicit_override_argument_wins(uma):
    assert uma.uma_command("/x/y") == ["/x/y"]


# ── the CLI the shell rungs call ─────────────────────────────────────────────────────────────


def test_cli_path_exits_1_with_a_reason_on_stderr(tmp_path):
    """mail-beat.sh and check-opportunity-lane.sh read this. A silent empty string is what let the
    beat skip the whole mail organ without a word."""
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        [sys.executable, str(RESOLVER), "--path"], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode == 1
    assert proc.stdout.strip() == ""
    assert "UMA_ROOT" in proc.stderr


def test_cli_command_emits_json_argv(tmp_path):
    root = tmp_path / "uma"
    root.mkdir()
    (root / "cli.py").write_text("#\n")
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "UMA_ROOT": str(root)}
    proc = subprocess.run(
        [sys.executable, str(RESOLVER), "--command"], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)[-1] == str(root / "cli.py")


def test_cli_explain_always_exits_0(tmp_path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        [sys.executable, str(RESOLVER), "--explain"], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode == 0
    assert proc.stdout.strip()


# ── the consumer regression, end to end ──────────────────────────────────────────────────────


def test_mail_story_reports_blocked_instead_of_crashing(monkeypatch, tmp_path):
    """THE regression. On origin/main this raised FileNotFoundError: 'umail' — the exact traceback in
    logs/heartbeat.out.log at beat 6. It must now return the blocked status the file already builds."""
    monkeypatch.setenv("UMA_ROOT", str(tmp_path / "nope"))
    monkeypatch.delenv("UMA_BIN", raising=False)
    ledger = _load("mail_story_mod", "scripts/mail-story-ledger.py")

    status, path = ledger.fetch_status(status_path=tmp_path / "status.json")
    assert status["status"] == "blocked"
    assert path is None
    assert status["blockers"], "a blocked status with no blocker names nothing to fix"
