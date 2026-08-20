#!/usr/bin/env python3
"""Read-only fixed-point predicate for the literal-substrate producer closeout."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT_PATH = HERE / "producer-closeout.json"
ALLOWED_CHECK_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}


class CloseoutError(RuntimeError):
    pass


def run(command: Sequence[str], *, cwd: Path = ROOT) -> str:
    proc = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
        timeout=120,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "command failed").strip()[:500]
        raise CloseoutError(f"{' '.join(command)}: {detail}")
    return proc.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CloseoutError(f"JSON contract must be an object: {path}")
    return value


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_owner(row: dict[str, Any]) -> dict[str, Any]:
    repository = str(row["repository"])
    pull_request = int(row["pull_request"])
    expected_head = str(row["head"])
    pr = json.loads(
        run(
            [
                "gh",
                "pr",
                "view",
                str(pull_request),
                "--repo",
                repository,
                "--json",
                "headRefOid,state,isDraft,mergeable,statusCheckRollup",
            ]
        )
    )
    if pr.get("headRefOid") != expected_head:
        raise CloseoutError(f"{repository}#{pull_request}: head changed")
    if pr.get("state") != "OPEN" or pr.get("isDraft") is not False:
        raise CloseoutError(f"{repository}#{pull_request}: PR is not an open, non-draft owner")
    if pr.get("mergeable") != "MERGEABLE":
        raise CloseoutError(f"{repository}#{pull_request}: PR is not mergeable")

    checks = pr.get("statusCheckRollup")
    if not isinstance(checks, list) or not checks:
        raise CloseoutError(f"{repository}#{pull_request}: no exact-head checks found")
    for check in checks:
        if not isinstance(check, dict):
            raise CloseoutError(f"{repository}#{pull_request}: malformed check")
        check_type = check.get("__typename")
        if check_type == "CheckRun":
            if check.get("status") != "COMPLETED" or check.get("conclusion") not in ALLOWED_CHECK_CONCLUSIONS:
                raise CloseoutError(f"{repository}#{pull_request}: non-terminal or failing check {check.get('name')}")
        elif check_type == "StatusContext":
            if check.get("state") != "SUCCESS":
                raise CloseoutError(f"{repository}#{pull_request}: non-success status {check.get('context')}")
        else:
            raise CloseoutError(f"{repository}#{pull_request}: unknown check type {check_type!r}")

    owner, name = repository.split("/", 1)
    query = """
      query($owner:String!, $name:String!, $number:Int!) {
        repository(owner:$owner, name:$name) {
          pullRequest(number:$number) {
            reviewThreads(first:100) { nodes { isResolved } }
          }
        }
      }
    """
    review = json.loads(
        run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={pull_request}",
            ]
        )
    )
    threads = review["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    unresolved = sum(not thread.get("isResolved", False) for thread in threads)
    if unresolved:
        raise CloseoutError(f"{repository}#{pull_request}: {unresolved} unresolved review thread(s)")
    return {
        "repository": repository,
        "pull_request": pull_request,
        "head": expected_head,
        "checks": len(checks),
        "unresolved_threads": 0,
    }


def verify_private_capsule(successor: dict[str, Any]) -> dict[str, Any]:
    capsule = ROOT / str(successor["private_capsule"])
    identity_path = capsule / "capsule.identity"
    identity = load_json(identity_path)
    modules = identity.get("modules")
    if identity.get("schema") != "limen.workstream.capsule-identity.v2" or not isinstance(modules, dict):
        raise CloseoutError("private capsule identity schema is invalid")
    for name, expected in modules.items():
        path = capsule / str(name)
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise CloseoutError(f"private capsule module identity mismatch: {name}")
    run(["bash", "-n", str(capsule / "kickstart.sh")])

    private_contract = load_json(capsule / "workstream.json")
    public_receipt = load_json(ROOT / str(successor["receipt"]))
    if public_receipt.get("contract") != private_contract:
        raise CloseoutError("public successor receipt and private contract disagree")
    if public_receipt.get("branch") != successor["branch"]:
        raise CloseoutError("successor receipt branch disagrees with producer contract")
    return {
        "identity_modules": len(modules),
        "runway": private_contract["runway"]["requested"],
        "admitted": private_contract["runway"]["started_at"] is not None,
    }


def verify_launch_preflight() -> dict[str, str]:
    required_fragments = (
        'workspace_root="${WORKSPACE_ROOT:-$HOME/Workspace}"',
        'canonical_limen_root="${LIMEN_ROOT:-$workspace_root/library/engine/organvm/limen}"',
        'canonical_capsule="$canonical_limen_root/.worktrees/omega-substrate-convergence-next"',
        'legacy_capsule="$workspace_root/limen/.worktrees/omega-substrate-convergence-next"',
    )
    for document in (HERE / "README.md", HERE / "RELAY.md"):
        body = document.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in body]
        if missing:
            raise CloseoutError(f"{document.name}: successor launch derivation is incomplete")

    workspace_root = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "Workspace"))).resolve()
    canonical_limen_root = Path(
        os.environ.get(
            "LIMEN_ROOT",
            str(workspace_root / "library" / "engine" / "organvm" / "limen"),
        )
    ).resolve()
    candidates = (
        ("canonical", canonical_limen_root / ".worktrees" / "omega-substrate-convergence-next"),
        ("migration", workspace_root / "limen" / ".worktrees" / "omega-substrate-convergence-next"),
    )
    for label, capsule in candidates:
        kickstart = capsule / ".limen-workstream" / "kickstart.sh"
        if not kickstart.is_file() or not os.access(kickstart, os.X_OK):
            continue
        if capsule.resolve() != ROOT.resolve():
            raise CloseoutError(f"{label} launch candidate selects a different successor checkout")
        run(["bash", "-n", str(kickstart)])
        return {"selected_route": label, "kickstart": "syntax-valid"}
    raise CloseoutError("successor launch preflight found no executable capsule")


def verify_private_session_receipt(contract: dict[str, Any]) -> dict[str, Any]:
    common_dir = Path(run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]))
    private_receipt = (
        common_dir.parent / ".limen-private" / "session-corpus" / "omega-substrate-literal" / "protected-sessions.json"
    )
    payload = load_json(private_receipt)
    expected = int(contract["protected_session_receipt"]["expected_sessions"])
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != expected:
        raise CloseoutError("private protected-session receipt count disagrees")
    mode = stat.S_IMODE(private_receipt.stat().st_mode)
    if mode != 0o600:
        raise CloseoutError("private protected-session receipt mode is not 0600")
    return {"sessions": expected, "mode": "0600"}


def main() -> int:
    try:
        contract = load_json(CONTRACT_PATH)
        if contract.get("schema") != "limen.omega_substrate_producer_closeout.v1":
            raise CloseoutError("producer closeout schema is invalid")
        dirty = run(["git", "status", "--porcelain=v1", "--untracked-files=all"])
        if dirty:
            raise CloseoutError("successor worktree is not clean")
        branch = run(["git", "branch", "--show-current"])
        successor = contract["successor"]
        if branch != successor["branch"]:
            raise CloseoutError(f"expected successor branch {successor['branch']}, found {branch}")
        local_head = run(["git", "rev-parse", "HEAD"])
        remote_line = run(["git", "ls-remote", "origin", f"refs/heads/{branch}"])
        remote_head = remote_line.split()[0] if remote_line else ""
        if local_head != remote_head:
            raise CloseoutError("successor local and remote heads disagree")

        owners = [verify_owner(row) for row in contract["owners"]]
        capsule = verify_private_capsule(successor)
        launch = verify_launch_preflight()
        protected = verify_private_session_receipt(contract)
        for relative in (
            "README.md",
            "intent.md",
            "runtime.md",
            "closeout.md",
            "RELAY.md",
            "completion-predicate.sh",
            "switch-predicate.sh",
            "workstream.json",
        ):
            if not (HERE / relative).is_file():
                raise CloseoutError(f"tracked successor module is missing: {relative}")
        print(
            json.dumps(
                {
                    "schema": "limen.omega_substrate_producer_closeout_result.v1",
                    "ok": True,
                    "successor_branch": branch,
                    "successor_head": local_head,
                    "owners": owners,
                    "capsule": capsule,
                    "launch_preflight": launch,
                    "protected_session_receipt": protected,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (CloseoutError, KeyError, TypeError, ValueError) as exc:
        print(f"producer-closeout: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
