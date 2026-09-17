#!/usr/bin/env python3
"""Read-only session-custody predicate; never a recovery-completion claim."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.workstream_contract import validate_workstream_receipt


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True, timeout=20).strip()


def main():
    receipt = json.loads((HERE / "session-closeout.json").read_text())
    assert receipt["outcome"] == "unfinished"
    assert receipt["automatic_continuation"] is False
    contract = validate_workstream_receipt(json.loads((HERE / "workstream.json").read_text()))
    assert contract["contract"]["runway"]["started_epoch"] == 1789597790
    assert contract["contract"]["runway"]["duration_seconds"] == 1800
    assert contract["contract"]["runway"]["deadline_epoch"] == 1789599590
    assert receipt["runtime_audit"]["removed"] == 0
    assert len(receipt["runtime_audit"]["rows"]) == receipt["runtime_audit"]["candidates"]
    for row in receipt["runtime_audit"]["rows"]:
        assert row["ancestor_of_deployed_main"] and row["wheel_digest_matches"]
        assert not row["changed_source"] and not row["changed_installed_package"]
    for name in ["README.md", "launch.sh", "session-closeout.json", "workstream.json", "verify-closeout.py"]:
        subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", str(HERE / name)], check=True, capture_output=True)
    assert not git("status", "--porcelain", "--untracked-files=all"), "session checkout is not clean"
    branch = git("branch", "--show-current")
    assert branch == "work/workspace-recovery-20260916"
    remote = git("ls-remote", "origin", "refs/heads/" + branch).split()[0]
    assert remote == git("rev-parse", "HEAD"), "session HEAD is not remotely durable"
    policy_path = ROOT.parent.parent / "logs/autonomy-policy.json"
    policy = json.loads(policy_path.read_text())
    for key, value in receipt["containment"].items():
        assert policy.get(key) == value, "containment changed: " + key
    print("PASS: session custody, retained original deadline, remote tip, clean checkout and containment; recovery remains unfinished")


if __name__ == "__main__":
    main()
