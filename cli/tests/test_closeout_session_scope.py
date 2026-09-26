"""Focused tests for the session-scoped closeout repair (4444J99/limen#2747).

Covers: read-only reporting with concurrent edits, the session's own
unpublished implementation still failing, wrong/stale continuation identity,
and unchanged repeated verification. Pure git-stub tests: no checkout, no
network, no mutation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPSULE = REPO_ROOT / "docs" / "continuations" / "workspace-recovery-20260916"


def load_validator():
    sys_path = [str(REPO_ROOT / "cli" / "src")]
    import sys

    for entry in sys_path:
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location("verify_closeout_test", CAPSULE / "verify-closeout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeGit:
    """Recorded, canned git. `script` maps tuple(argv) -> output."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        key = tuple(args)
        if key in self.script:
            return self.script[key]
        raise AssertionError("unexpected git call: %r" % (args,))

    def argv_words(self):
        return [call[0] for call in self.calls]


PORCELAIN_CONCURRENT = " M docs/heartbeat-natural-receipt-20260924.md\n?? work/heartbeat-scratch/\n"
HEAD = "a" * 40
HIST_TIP = "b" * 40


def base_script(*, branch="docs/heartbeat-natural-receipt-20260924", porcelain=PORCELAIN_CONCURRENT):
    return {
        ("branch", "--show-current"): branch,
        ("rev-parse", "HEAD"): HEAD,
        ("status", "--porcelain", "--untracked-files=all"): porcelain,
        ("ls-remote", "origin", "refs/heads/work/workspace-recovery-20260916"): HIST_TIP
        + "\trefs/heads/work/workspace-recovery-20260916",
        ("ls-remote", "origin", "refs/heads/" + branch): HEAD + "\trefs/heads/" + branch,
        ("ls-files", "--error-unmatch", str(CAPSULE / "README.md")): "ok",
        ("ls-files", "--error-unmatch", str(CAPSULE / "launch.sh")): "ok",
        ("ls-files", "--error-unmatch", str(CAPSULE / "session-closeout.json")): "ok",
        ("ls-files", "--error-unmatch", str(CAPSULE / "workstream.json")): "ok",
        ("ls-files", "--error-unmatch", str(CAPSULE / "verify-closeout.py")): "ok",
        (
            "log",
            "-1",
            "--format=%an <%ae> %h",
            "HEAD",
            "--",
            "docs/heartbeat-natural-receipt-20260924.md",
        ): "4444J99 <a@b.c> deadbee",
        ("log", "-1", "--format=%an <%ae> %h", "HEAD", "--", "work/heartbeat-scratch/"): "4444J99 <a@b.c> deadbee",
    }


def test_read_only_reporting_with_concurrent_edits_passes_and_preserves():
    vc = load_validator()
    git = FakeGit(base_script())
    report = vc.session_validate(git, CAPSULE, REPO_ROOT)
    assert report.startswith("PASS (session-scoped read-only closeout)")
    assert "branch: docs/heartbeat-natural-receipt-20260924" in report
    assert "head: " + HEAD in report
    assert "historical capsule branch: work/workspace-recovery-20260916" in report
    assert "retained concurrent work (preserved, not this session's):" in report
    assert "docs/heartbeat-natural-receipt-20260924.md" in report
    assert "owner: 4444J99 <a@b.c> deadbee" in report
    for word in vc.MUTATING_ARGV:
        assert word not in git.argv_words(), "session mode issued mutating git call: %s" % word


def test_own_unpublished_implementation_still_fails():
    vc = load_validator()
    porcelain = PORCELAIN_CONCURRENT + " M docs/continuations/workspace-recovery-20260916/session-closeout.json\n"
    git = FakeGit(base_script(porcelain=porcelain))
    with pytest.raises(AssertionError, match="session has uncommitted implementation"):
        vc.session_validate(git, CAPSULE, REPO_ROOT)


def test_declared_owned_paths_fail_when_dirty():
    vc = load_validator()
    porcelain = PORCELAIN_CONCURRENT + " M cli/src/limen/my_feature.py\n"
    script = base_script(porcelain=porcelain)
    script[("log", "-1", "--format=%an <%ae> %h", "HEAD", "--", "cli/src/limen/my_feature.py")] = "me <m@x.y> 1234abc"
    git = FakeGit(script)
    with pytest.raises(AssertionError, match="cli/src/limen/my_feature.py"):
        vc.session_validate(git, CAPSULE, REPO_ROOT, owned_extra=("cli/src/limen/my_feature.py",))


def test_wrong_or_stale_continuation_identity_does_not_bind():
    vc = load_validator()
    # The checkout is on an unrelated branch; historical capsule branch is stale data.
    git = FakeGit(base_script(branch="some/unrelated-branch"))
    report = vc.session_validate(git, CAPSULE, REPO_ROOT)
    assert report.startswith("PASS (session-scoped read-only closeout)")
    assert "branch: some/unrelated-branch" in report


def test_historical_branch_resolves_from_workstream_not_literal():
    vc = load_validator()
    assert vc.historical_branch(CAPSULE) == "work/workspace-recovery-20260916"
    source = (CAPSULE / "verify-closeout.py").read_text(encoding="utf-8")
    # The literal may appear only in test fixtures and docstrings, never as an assertion operand.
    code_lines = [line for line in source.splitlines() if '"""' not in line and "#" not in line.split('"')[0]]
    assert not any(
        '== "work/workspace-recovery-20260916"' in line or "== 'work/workspace-recovery-20260916'" in line
        for line in code_lines
    )


def test_repeated_verification_exits_unchanged_with_no_mutation():
    vc = load_validator()
    git = FakeGit(base_script())
    first = vc.session_validate(git, CAPSULE, REPO_ROOT)
    calls_first = len(git.calls)
    git.calls.clear()
    second = vc.session_validate(git, CAPSULE, REPO_ROOT)
    assert first == second
    assert len(git.calls) == calls_first
    for word in vc.MUTATING_ARGV:
        assert word not in git.argv_words()


def test_launch_check_delegates_to_session_mode():
    script = (REPO_ROOT / "docs" / "continuations" / "workspace-recovery-20260916" / "launch.sh").read_text(
        encoding="utf-8"
    )
    assert 'verify-closeout.py" --check' in script
    assert "kickstart.sh" in script
