from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prompt-claude-session.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prompt_claude_session", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture()
def checkouts(tmp_path: Path) -> tuple[Path, Path]:
    """A shared checkout plus one linked worktree of it."""
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "seed")
    linked = tmp_path / "linked"
    git(main, "worktree", "add", "-q", "-b", "topic", str(linked))
    return main, linked


def session(name: str, cwd: Path, *, kind="background", status="idle", sid=None) -> dict:
    sid = sid or f"{name[:8]}-0000-0000-0000-000000000000"
    return {"id": sid[:8], "sessionId": sid, "name": name, "cwd": str(cwd), "kind": kind, "status": status}


class FakeRun:
    def __init__(self, stdout="", returncode=0):
        self.calls: list[tuple[list[str], dict]] = []
        self.stdout, self.returncode = stdout, returncode

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, self.returncode, stdout=self.stdout, stderr="")


def test_resolve_prefers_exact_name_then_unique_prefix(checkouts):
    mod = load_module()
    _, linked = checkouts
    rows = [session("external session review", linked), session("closeout skill agnostic", linked)]
    assert mod.resolve_target(rows, "external session review")["name"] == "external session review"
    assert mod.resolve_target(rows, "closeout")["name"] == "closeout skill agnostic"


def test_resolve_refuses_ambiguous_and_missing(checkouts):
    mod = load_module()
    _, linked = checkouts
    rows = [session("review a", linked, sid="aaaaaaaa-1"), session("review b", linked, sid="bbbbbbbb-2")]
    with pytest.raises(mod.Refused, match="ambiguous"):
        mod.resolve_target(rows, "review")
    with pytest.raises(mod.Refused, match="no live session"):
        mod.resolve_target(rows, "nothing")


def test_deliver_runs_claude_from_the_targets_linked_worktree(checkouts):
    mod = load_module()
    _, linked = checkouts
    run = FakeRun()
    receipt = mod.deliver(session("t", linked), "do the thing\nsecond line", run=run)
    argv, kwargs = run.calls[0]
    assert argv[:3] == ["claude", "--bg", "--resume"]
    assert argv[-2:] == ["--", "do the thing\nsecond line"]
    assert Path(kwargs["cwd"]) == linked
    assert receipt["delivered"] is True and receipt["acknowledged"] is False
    assert "do the thing" not in json.dumps(receipt)


def test_busy_target_is_refused_unless_copy_allowed(checkouts):
    mod = load_module()
    _, linked = checkouts
    run = FakeRun()
    with pytest.raises(mod.Refused, match="busy"):
        mod.deliver(session("t", linked, status="busy"), "x", run=run)
    assert run.calls == []
    assert mod.deliver(session("t", linked, status="busy"), "x", allow_copy=True, run=run)["delivered"]


def test_interactive_target_is_never_prompted(checkouts):
    mod = load_module()
    _, linked = checkouts
    run = FakeRun()
    with pytest.raises(mod.Refused, match="not a background session"):
        mod.deliver(session("t", linked, kind="interactive"), "x", run=run)
    assert run.calls == []


def test_shared_checkout_and_non_repo_cwd_are_refused(checkouts, tmp_path):
    mod = load_module()
    main, _ = checkouts
    run = FakeRun()
    with pytest.raises(mod.Refused, match="shared checkout"):
        mod.deliver(session("t", main), "x", run=run)
    outside = tmp_path / "plain"
    outside.mkdir()
    with pytest.raises(mod.Refused, match="not a resolvable git checkout"):
        mod.deliver(session("t", outside), "x", run=run)
    assert run.calls == []


def test_dry_run_sends_nothing(checkouts):
    mod = load_module()
    _, linked = checkouts
    run = FakeRun()
    receipt = mod.deliver(session("t", linked), "x", dry_run=True, run=run)
    assert run.calls == [] and receipt["dry_run"] is True and receipt["delivered"] is False


def test_nonzero_claude_exit_is_not_reported_delivered(checkouts):
    mod = load_module()
    _, linked = checkouts
    receipt = mod.deliver(session("t", linked), "x", run=FakeRun(returncode=1))
    assert receipt["delivered"] is False and receipt["exit_code"] == 1
