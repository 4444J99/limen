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


def session(name: str, cwd: Path | str, *, kind="background", status="idle", sid=None) -> dict:
    sid = sid or f"{name[:8]}-0000-0000-0000-000000000000"
    return {"id": sid[:8], "sessionId": sid, "name": name, "cwd": str(cwd), "kind": kind, "status": status}


class FakeRun:
    def __init__(self, stdout="", stderr="", returncode=0, raises=None):
        self.calls: list[tuple[list[str], dict]] = []
        self.stdout, self.stderr, self.returncode, self.raises = stdout, stderr, returncode, raises

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode, stdout=self.stdout, stderr=self.stderr)


def listing(*snapshots: list[dict]):
    """A lister returning each snapshot in turn, then repeating the last one."""
    queue = list(snapshots)

    def lister() -> list[dict]:
        return list(queue.pop(0) if len(queue) > 1 else queue[0])

    return lister


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


def test_deliver_runs_claude_from_the_targets_linked_worktree_and_verifies_receiver(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    run = FakeRun()
    receipt = mod.deliver(target, "do the thing\nsecond line", run=run, lister=listing([target]))
    argv, kwargs = run.calls[0]
    assert argv[:3] == ["claude", "--bg", "--resume"]
    assert argv[-2:] == ["--", "do the thing\nsecond line"]
    assert Path(kwargs["cwd"]) == linked
    assert receipt["delivered"] is True and receipt["acknowledged"] is False
    assert receipt["identity_verified"] is True and receipt["forked"] is False
    assert receipt["receiving_session"]["sessionId"] == target["sessionId"]
    assert "do the thing" not in json.dumps(receipt)
    assert mod.exit_code(receipt) == 0


def test_target_that_went_busy_after_the_first_listing_is_refused_before_sending(checkouts):
    mod = load_module()
    _, linked = checkouts
    stale = session("t", linked, status="idle")
    now_busy = session("t", linked, status="busy")
    run = FakeRun()
    with pytest.raises(mod.Refused, match="busy"):
        mod.deliver(stale, "x", run=run, lister=listing([now_busy]))
    assert run.calls == []


def test_target_that_vanished_is_refused(checkouts):
    mod = load_module()
    _, linked = checkouts
    run = FakeRun()
    with pytest.raises(mod.Refused, match="no longer a live session"):
        mod.deliver(session("t", linked), "x", run=run, lister=listing([]))
    assert run.calls == []


def test_a_fork_after_the_send_is_detected_and_not_reported_delivered(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    fork = session("t-copy", linked, sid="ffffffff-0000-0000-0000-000000000000")
    receipt = mod.deliver(target, "x", run=FakeRun(), lister=listing([target], [target], [target, fork]))
    assert receipt["forked"] is True and receipt["identity_verified"] is False
    assert receipt["delivered"] is False
    assert receipt["fork_sessions"][0]["sessionId"] == fork["sessionId"]
    assert mod.exit_code(receipt) == 4


def test_a_deliberate_copy_names_the_forked_session_as_receiver(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked, status="busy")
    fork = session("t-copy", linked, sid="ffffffff-0000-0000-0000-000000000000")
    receipt = mod.deliver(
        target, "x", allow_copy=True, run=FakeRun(), lister=listing([target], [target], [target, fork])
    )
    assert receipt["forked"] is True and receipt["identity_verified"] is True and receipt["delivered"] is True
    assert receipt["receiving_session"]["sessionId"] == fork["sessionId"]


def test_unlistable_after_send_is_sent_but_unverified(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    calls = {"n": 0}

    def flaky() -> list[dict]:
        calls["n"] += 1
        if calls["n"] > 2:
            raise mod.Refused("`claude agents --json` timed out")
        return [target]

    receipt = mod.deliver(target, "x", run=FakeRun(), lister=flaky)
    assert receipt["identity_verified"] is False and "receiver unverified" in receipt["error"]
    assert mod.exit_code(receipt) == 4


def test_concurrent_send_to_the_same_target_is_refused(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    held = mod._lock_path(target["sessionId"]).open("w")
    mod.fcntl.flock(held, mod.fcntl.LOCK_EX)
    try:
        run = FakeRun()
        with pytest.raises(mod.Refused, match="in progress"):
            mod.deliver(target, "x", run=run, lister=listing([target]))
        assert run.calls == []
    finally:
        held.close()


def test_interactive_target_is_never_prompted(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked, kind="interactive")
    run = FakeRun()
    with pytest.raises(mod.Refused, match="not a background session"):
        mod.deliver(target, "x", run=run, lister=listing([target]))
    assert run.calls == []


def test_shared_checkout_and_non_repo_cwd_are_refused(checkouts, tmp_path):
    mod = load_module()
    main, _ = checkouts
    outside = tmp_path / "plain"
    outside.mkdir()
    for cwd, reason in ((main, "shared checkout"), (outside, "not a resolvable git checkout")):
        target = session("t", cwd)
        run = FakeRun()
        with pytest.raises(mod.Refused, match=reason):
            mod.deliver(target, "x", run=run, lister=listing([target]))
        assert run.calls == []


@pytest.mark.parametrize("cwd", [None, "", "   ", "relative/path", "."])
def test_missing_or_relative_cwd_is_refused_not_defaulted_to_the_callers_checkout(checkouts, monkeypatch, cwd):
    mod = load_module()
    _, linked = checkouts
    monkeypatch.chdir(linked)  # the caller's cwd is a valid linked worktree: it must NOT be adopted
    target = session("t", linked)
    target["cwd"] = cwd
    if cwd is None:
        del target["cwd"]
    run = FakeRun()
    with pytest.raises(mod.Refused, match="no absolute cwd"):
        mod.deliver(target, "x", run=run, lister=listing([target]))
    assert run.calls == []


def test_dry_run_sends_nothing(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    run = FakeRun()
    receipt = mod.deliver(target, "x", dry_run=True, run=run, lister=listing([target]))
    assert run.calls == [] and receipt["dry_run"] is True and receipt["delivered"] is False
    assert mod.exit_code(receipt) == 0


def test_nonzero_claude_exit_is_not_reported_delivered(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    receipt = mod.deliver(target, "x", run=FakeRun(returncode=1), lister=listing([target]))
    assert receipt["delivered"] is False and receipt["exit_code"] == 1
    assert mod.exit_code(receipt) == 3


def test_timeout_yields_a_receipt_that_does_not_carry_the_prompt(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    secret = "rotate the api key SECRET-TOKEN-1234"
    timeout = subprocess.TimeoutExpired(cmd=["claude", "--bg", "--", secret], timeout=60)
    receipt = mod.deliver(target, secret, run=FakeRun(raises=timeout), lister=listing([target]))
    assert receipt["delivered"] is False and "delivery is unknown" in receipt["error"]
    assert "SECRET-TOKEN-1234" not in json.dumps(receipt)
    assert mod.exit_code(receipt) == 3


def test_prompt_echoed_by_claude_is_scrubbed_from_the_receipt(checkouts):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    prompt = "first line stays private\nsecond line also private"
    echo = FakeRun(stdout=f"got: {prompt}", stderr="usage error near: first line stays private", returncode=1)
    receipt = mod.deliver(target, prompt, run=echo, lister=listing([target]))
    rendered = json.dumps(receipt)
    assert "stays private" not in rendered and "also private" not in rendered


def test_main_never_prints_the_prompt_when_the_timeout_escapes(checkouts, tmp_path, monkeypatch, capsys):
    mod = load_module()
    _, linked = checkouts
    target = session("t", linked)
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("top secret instruction body", encoding="utf-8")

    def exploding_deliver(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["claude", "--", "top secret instruction body"], timeout=60)

    monkeypatch.setattr(mod, "list_sessions", lambda *_a, **_k: [target])
    monkeypatch.setattr(mod, "deliver", exploding_deliver)
    code = mod.main(["--to", "t", "--prompt-file", str(prompt_file)])
    captured = capsys.readouterr()
    assert code == 3
    assert "top secret" not in captured.out + captured.err
