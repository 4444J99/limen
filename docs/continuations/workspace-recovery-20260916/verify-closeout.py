#!/usr/bin/env python3
"""Session-custody closeout predicates; never a recovery-completion claim.

Two modes:

* Historical mode (no flags): validates the preserved workspace-recovery
  capsule's custody receipts against the historical checkout state. The
  expected branch comes from the capsule's own ``workstream.json`` — it is
  NOT a hard-coded literal and must NOT be invoked to judge a session that
  merely shares the checkout.

* Session mode (``--check``): read-only inspection of the *current* session.
  Resolves the current owner/continuation/branch/HEAD and the referenced
  remote receipts from the live checkout without binding to the historical
  branch. Dirty work that is not the session's own is reported as retained
  (with best-effort owner attribution) and preserved untouched; the
  session's own uncommitted implementation still fails. Pure read-only:
  no stash, reset, commit, cleanup, implicit launch, or budget renewal.
"""
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
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=20).strip()

    return git


def historical_branch(here=HERE):
    """Expected branch of the preserved capsule, read from its own workstream data."""
    workstream = json.loads((here / "workstream.json").read_text())
    branch = workstream.get("branch")
    assert branch, "workstream.json declares no branch"
    return branch


def resolve_session(git, here=HERE, root=ROOT):
    """Read-only resolution of the current session's checkout context."""
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    porcelain = git("status", "--porcelain", "--untracked-files=all")
    dirty = [line[3:] for line in porcelain.splitlines() if line.strip()]
    receipt = json.loads((here / "session-closeout.json").read_text())
    remote_refs = {
        "owner": receipt.get("owner"),
        "limen_merge": receipt.get("limen_merge"),
        "worker_deployment": receipt.get("worker_deployment"),
        "worker_live_sha": receipt.get("worker_live_sha"),
        "domus_merge": receipt.get("domus_merge"),
        "domus_owner": receipt.get("domus_owner"),
    }
    return {
        "branch": branch,
        "head": head,
        "dirty": dirty,
        "historical_branch": historical_branch(here),
        "receipt_outcome": receipt.get("outcome"),
        "automatic_continuation": receipt.get("automatic_continuation"),
        "remote_refs": remote_refs,
    }


def owner_of(git, root, path):
    """Best-effort owner attribution for a dirty path; read-only."""
    if path.endswith("/"):
        return "unknown (untracked directory)"
    try:
        line = git("log", "-1", "--format=%an <%ae> %h", "HEAD", "--", path)
        return line or "unknown (no history)"
    except Exception:
        return "unknown (untracked or unreadable)"


def partition_dirty(git, root, dirty, here, owned_extra=()):
    """Split dirty paths into the session's own vs retained concurrent work.

    The session owns the capsule directory itself plus any paths the caller
    declares via ``--owned``. Everything else is concurrent work owned by
    another session and must be preserved untouched.
    """
    session_prefix = str(here) + "/"
    owned, retained = [], []
    for path in dirty:
        # Porcelain paths are repo-root-relative; resolve against root, not here.
        abs_path = Path(path) if Path(path).is_absolute() else root / path
        is_own = str(abs_path.resolve()).startswith(session_prefix) or any(
            path == o or path.startswith(o.rstrip("/") + "/") for o in owned_extra
        )
        (owned if is_own else retained).append((path, owner_of(git, root, path)))
    return owned, retained


def remote_tip(git, branch):
    """Read-only remote tip of a branch; None when absent from origin."""
    try:
        out = git("ls-remote", "origin", "refs/heads/" + branch)
        return out.split()[0] if out else None
    except Exception:
        return None


def session_validate(git, here=HERE, root=ROOT, owned_extra=()):
    """Session-scoped read-only validation. Returns the report; raises on failure."""
    ctx = resolve_session(git, here, root)
    for name in CAPSULE_FILES:
        git("ls-files", "--error-unmatch", str(here / name))
    owned, retained = partition_dirty(git, root, ctx["dirty"], here, owned_extra)
    if owned:
        names = ", ".join(p for p, _ in owned)
        raise AssertionError("session has uncommitted implementation: " + names)
    lines = [
        "PASS (session-scoped read-only closeout)",
        "branch: %s" % ctx["branch"],
        "head: %s" % ctx["head"],
        "historical capsule branch: %s" % ctx["historical_branch"],
        "receipt outcome: %s; automatic_continuation: %s" % (ctx["receipt_outcome"], ctx["automatic_continuation"]),
    ]
    hist_tip = remote_tip(git, ctx["historical_branch"])
    lines.append("historical branch remote tip: %s" % (hist_tip or "absent from origin"))
    cur_tip = remote_tip(git, ctx["branch"]) if ctx["branch"] else None
    lines.append("current branch remote tip: %s" % (cur_tip or "absent from origin"))
    lines.append("referenced remote receipts:")
    for key, value in ctx["remote_refs"].items():
        lines.append("  %s: %s" % (key, value))
    if retained:
        lines.append("retained concurrent work (preserved, not this session's):")
        for path, owner in retained:
            lines.append("  %s  owner: %s" % (path, owner))
    else:
        lines.append("no concurrent dirty work observed")
    return "\n".join(lines)


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
        subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", str(here / name)], check=True, capture_output=True)
    assert not git("status", "--porcelain", "--untracked-files=all"), "session checkout is not clean"
    branch = git("branch", "--show-current")
    assert branch == historical_branch(here), "not on the capsule's preserved branch"
    remote = remote_tip(git, branch)
    assert remote == git("rev-parse", "HEAD"), "session HEAD is not remotely durable"
    policy_path = root.parent.parent / "logs/autonomy-policy.json"
    policy = json.loads(policy_path.read_text())
    for key, value in receipt["containment"].items():
        assert policy.get(key) == value, "containment changed: " + key
    print("PASS: session custody, retained original deadline, remote tip, clean checkout and containment; recovery remains unfinished")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Workspace-recovery capsule closeout predicates")
    parser.add_argument("--check", action="store_true", help="session-scoped read-only inspection")
    parser.add_argument("--owned", action="append", default=[], help="extra repo-relative paths owned by this session")
    args = parser.parse_args(argv)
    git = make_git(ROOT)
    if args.check:
        print(session_validate(git, HERE, ROOT, tuple(args.owned)))
    else:
        historical_validate(git, HERE, ROOT)


if __name__ == "__main__":
    main()
