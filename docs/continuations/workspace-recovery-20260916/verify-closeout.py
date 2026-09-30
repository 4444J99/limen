#!/usr/bin/env python3
"""Historical custody remains separate; --check delegates to canonical session evidence."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.workstream_contract import validate_workstream_receipt

CAPSULE_FILES = ["README.md", "launch.sh", "session-closeout.json", "workstream.json", "verify-closeout.py"]

# argv[0] values that mutate the checkout; session mode must never issue them.
MUTATING_ARGV = ("stash", "reset", "commit", "checkout", "clean", "rm", "mv", "push")


def make_git(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=20).rstrip("\n")

    return git


def historical_branch(here=HERE):
    """Expected branch of the preserved capsule, read from its own workstream data."""
    workstream = json.loads((here / "workstream.json").read_text())
    branch = workstream.get("branch")
    assert branch, "workstream.json declares no branch"
    return branch


def remote_tip(git, branch):
    """Read-only remote tip of a branch; None when absent from origin."""
    try:
        out = git("ls-remote", "origin", "refs/heads/" + branch)
        return out.split()[0] if out else None
    except (OSError, subprocess.SubprocessError):
        return None


def historical_validate(git, here=HERE, root=ROOT):
    """One-time custody check of the preserved historical capsule (unchanged semantics)."""
    receipt = json.loads((here / "session-closeout.json").read_text())
    assert receipt["outcome"] == "unfinished"
    assert receipt["automatic_continuation"] is False
    contract = validate_workstream_receipt(json.loads((here / "workstream.json").read_text()))
    assert contract["contract"]["runway"]["started_epoch"] == 1789597790
    assert contract["contract"]["runway"]["duration_seconds"] == 1800
    assert contract["contract"]["runway"]["deadline_epoch"] == 1789599590
    assert receipt["runtime_audit"]["removed"] == 0
    assert len(receipt["runtime_audit"]["rows"]) == receipt["runtime_audit"]["candidates"]
    for row in receipt["runtime_audit"]["rows"]:
        assert row["ancestor_of_deployed_main"] and row["wheel_digest_matches"]
        assert not row["changed_source"] and not row["changed_installed_package"]
    for name in CAPSULE_FILES:
        subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", str(here / name)], check=True, capture_output=True
        )
    assert not git("status", "--porcelain", "--untracked-files=all"), "session checkout is not clean"
    branch = git("branch", "--show-current")
    assert branch == historical_branch(here), "not on the capsule's preserved branch"
    remote = remote_tip(git, branch)
    assert remote == git("rev-parse", "HEAD"), "session HEAD is not remotely durable"
    policy_path = root.parent.parent / "logs/autonomy-policy.json"
    policy = json.loads(policy_path.read_text())
    for key, value in receipt["containment"].items():
        assert policy.get(key) == value, "containment changed: " + key
    print(
        "PASS: session custody, retained original deadline, remote tip, clean checkout and containment; recovery remains unfinished"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Workspace-recovery capsule closeout predicates")
    parser.add_argument("--check", action="store_true", help="session-scoped read-only inspection")
    args, remaining = parser.parse_known_args(argv)
    git = make_git(ROOT)
    if args.check:
        from limen.session_closeout import main as session_main

        raise SystemExit(session_main(remaining))
    else:
        historical_validate(git, HERE, ROOT)


if __name__ == "__main__":
    main()
