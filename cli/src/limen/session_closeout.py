"""Read-only session release, distinct from task completion and estate health.

The evidence belongs in the existing continuation/owner receipt, never a second
task registry. Unattributed paths and unavailable observations fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, Literal, overload

SCHEMA = "limen.session_closeout.v1"
SHA = re.compile(r"[0-9a-f]{40}")
OWNER = re.compile(r"https://github.com/([\w.-]+/[\w.-]+)/(issues|pull)/(\d+)")


class Unmeasured(ValueError):
    """Evidence is unavailable, malformed or not bound to this session."""


@overload
def run(command: list[str], *, raw: Literal[False] = False) -> str: ...


@overload
def run(command: list[str], *, raw: Literal[True]) -> bytes: ...


@overload
def run(command: list[str], *, raw: bool) -> str | bytes: ...


def run(command: list[str], *, raw: bool = False) -> str | bytes:
    result = subprocess.run(command, capture_output=True, timeout=20, check=True)
    return result.stdout if raw else result.stdout.decode("utf-8").rstrip("\n")


def git(root: Path, *args: str, raw: bool = False) -> Any:
    return run(["git", "--no-optional-locks", "-C", str(root), *args], raw=raw)


def safe_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise Unmeasured("invalid receipt path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value == ".":
        raise Unmeasured("receipt paths must be repository-relative")
    return value


def dirty_paths(porcelain: bytes) -> set[str]:
    """Parse NUL-delimited porcelain without stripping status or filename bytes."""
    rows = iter(porcelain.split(b"\0"))
    paths = set()
    for row in rows:
        if not row:
            continue
        if len(row) < 4 or row[2:3] != b" ":
            raise Unmeasured("invalid Git porcelain")
        paths.add(os.fsdecode(row[3:]))
        if b"R" in row[:2] or b"C" in row[:2]:
            old = next(rows, b"")
            if not old:
                raise Unmeasured("missing rename source")
            paths.add(os.fsdecode(old))
    return paths


def matches(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def owner_readback(url: str) -> dict:
    match = OWNER.fullmatch(url)
    if not match:
        raise Unmeasured("owner must be an exact GitHub issue or PR URL")
    repo, kind, number = match.groups()
    endpoint = "pulls" if kind == "pull" else "issues"
    value = json.loads(run(["gh", "api", "--method", "GET", f"repos/{repo}/{endpoint}/{number}"]))
    if value.get("html_url") != url:
        raise Unmeasured("owner readback identity mismatch")
    return value


def published(root: Path, revision: str, branch: str) -> bool:
    if not SHA.fullmatch(revision) or not branch or branch.startswith("-"):
        return False
    ref = f"refs/heads/{branch}"
    rows = git(root, "ls-remote", "--exit-code", "origin", ref).splitlines()
    if len(rows) != 1:
        return False
    tip, remote_ref = rows[0].split()
    if remote_ref != ref or not SHA.fullmatch(tip):
        return False
    # A moving remote never makes a cached origin/* ref publication evidence.
    if tip == revision:
        return True
    try:
        git(root, "merge-base", "--is-ancestor", revision, tip)
    except subprocess.CalledProcessError:
        return False
    return True


def process_observation(root: Path, session_id: str) -> list[int]:
    """Observe exact checkout cwd and session-tagged processes without signaling."""
    rows = run(["ps", "-axo", "pid=,ppid=,command="]).splitlines()
    processes = {}
    for row in rows:
        bits = row.strip().split(None, 2)
        if len(bits) == 3:
            processes[int(bits[0])] = (int(bits[1]), bits[2])
    ancestors = {os.getpid()}
    cursor = os.getpid()
    while cursor in processes and processes[cursor][0] not in ancestors:
        cursor = processes[cursor][0]
        ancestors.add(cursor)
    # lsof exit 1 can mean an incomplete permission-limited scan; never turn it
    # into an empty successful observation.
    cwd_rows = run(["lsof", "-nP", "-a", "-d", "cwd", "-F", "pn"]).splitlines()
    owned = {pid for pid, (_, command) in processes.items() if session_id in command}
    pid = None
    for row in cwd_rows:
        if row.startswith("p"):
            pid = int(row[1:])
        elif row.startswith("n") and pid is not None and Path(row[1:]).resolve() == root:
            owned.add(pid)
    return sorted(owned - ancestors)


def native_witness(path: Path, session_id: str) -> bool:
    # Read only the metadata header; no prompt bodies enter the public report.
    with path.open() as source:
        first = json.loads(source.readline(64 * 1024))
    return first.get("type") == "session_meta" and first.get("payload", {}).get("id") == session_id


def evaluate(
    root: Path,
    session_id: str,
    receipt_path: Path,
    *,
    audit: dict,
    binding: dict | None,
    native_verified: bool = False,
    read_owner: Callable[[str], dict] = owner_readback,
    observe_processes: Callable[[Path, str], list[int]] = process_observation,
) -> dict:
    root = root.resolve(strict=True)
    head = git(root, "rev-parse", "HEAD")
    receipt_path = receipt_path.resolve(strict=True)
    receipt_root = Path(git(receipt_path.parent, "rev-parse", "--show-toplevel")).resolve()
    receipt_head = git(receipt_root, "rev-parse", "HEAD")
    receipt_relative = receipt_path.relative_to(receipt_root).as_posix()
    raw = receipt_path.read_bytes()
    committed = git(receipt_root, "show", f"{receipt_head}:{receipt_relative}", raw=True)
    if raw != committed:
        raise Unmeasured("closeout receipt is not committed at the inspected head")
    receipt = json.loads(raw)
    if receipt.get("schema") != SCHEMA or receipt.get("session_id") != session_id:
        raise Unmeasured("closeout receipt session identity mismatch")
    if receipt.get("worktree_name") != root.name:
        raise Unmeasured("closeout receipt names a different worktree")
    remote = git(root, "remote", "get-url", "origin")
    slug = re.sub(r"^(?:https://github.com/|git@github.com:)", "", remote).removesuffix(".git")
    if receipt.get("repository") != slug:
        raise Unmeasured("closeout receipt repository mismatch")
    if git(receipt_root, "remote", "get-url", "origin") != remote:
        raise Unmeasured("receipt and subject repositories differ")
    if receipt_root != root and receipt.get("subject_head") != head:
        raise Unmeasured("external receipt is not bound to the exact subject head")
    if audit.get("session_id") != session_id or audit.get("coverage", {}).get("retained_state_complete") is not True:
        raise Unmeasured("session audit missing or incomplete")
    runs = audit.get("runs")
    if not isinstance(runs, list) or audit.get("retained_run_count") != len(runs):
        raise Unmeasured("retained run coverage is incomplete")
    if binding is not None:
        if binding.get("session_id") != session_id or Path(binding.get("worktree") or "").resolve() != root:
            raise Unmeasured("broker session/worktree binding mismatch")
    elif not native_verified or audit.get("session_present") is not False:
        raise Unmeasured("no broker binding or exact native-session witness")
    disposition = receipt.get("disposition")
    if disposition not in {"complete", "handoff", "read_only"}:
        raise Unmeasured("invalid session disposition")
    own = receipt.get("owned_paths")
    retained = receipt.get("retained_work")
    if not isinstance(own, list) or not isinstance(retained, list):
        raise Unmeasured("explicit path ownership evidence is required")
    own = [safe_path(path) for path in own]
    findings = []
    notes = []
    if not published(receipt_root, receipt_head, receipt.get("publication_branch", "")):
        findings.append("owner receipt is not remotely durable")
    subject_branch = receipt.get("subject_publication_branch", receipt.get("publication_branch", ""))
    if not published(root, head, subject_branch):
        findings.append("inspected head is not remotely durable")
    if type(audit.get("active_lease_count")) is not int or audit["active_lease_count"] != 0:
        findings.append("session has active or unmeasured leases")
    if any(
        row.get("status")
        not in {
            "done",
            "failed",
            "failed_blocked",
            "needs_human",
            "archived",
            "succeeded",
            "blocked",
            "cancelled",
            "partial",
        }
        for row in audit.get("runs", [])
    ):
        findings.append("session has nonterminal runs")
    owner_cache = {}

    def owner(url: str) -> dict:
        if url not in owner_cache:
            owner_cache[url] = read_owner(url)
        return owner_cache[url]

    if not OWNER.fullmatch(str(receipt.get("owner_url", ""))):
        raise Unmeasured("durable session owner is required")
    current_owner = owner(receipt["owner_url"])
    if disposition == "handoff" and current_owner.get("state") != "open":
        findings.append("unfinished handoff owner is not open")
    siblings = []
    for item in retained:
        if not isinstance(item, dict) or not item.get("owner_url"):
            raise Unmeasured("retained work has no explicit owner")
        paths = [safe_path(path) for path in item.get("paths", [])]
        if not paths or owner(item["owner_url"]).get("state") != "open":
            raise Unmeasured("retained work owner is unavailable or closed")
        siblings.extend(paths)
        notes.append({"owner_url": item["owner_url"], "paths": paths})
    dirty = dirty_paths(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", raw=True))
    for path in sorted(dirty):
        if path == receipt_relative or matches(path, own):
            findings.append(f"owned uncommitted path: {path}")
        elif not matches(path, siblings):
            findings.append(f"unattributed dirty path: {path}")
    evidence = receipt.get("verification", [])
    if not isinstance(evidence, list) or not evidence:
        raise Unmeasured("scoped verification evidence is required")
    evidence_paths = {receipt_relative}
    for check in evidence:
        if not isinstance(check, dict) or not isinstance(check.get("head"), str):
            raise Unmeasured("malformed scoped verification")
        revision = check.get("head", "")
        if type(check.get("exit_code")) is not int or check["exit_code"] != 0 or not SHA.fullmatch(revision):
            findings.append("required scoped predicate has no passing exact-head receipt")
            continue
        git(root, "merge-base", "--is-ancestor", revision, head)
        evidence_path = safe_path(check.get("evidence"))
        evidence_paths.add(evidence_path)
        payload = git(receipt_root, "show", f"{receipt_head}:{evidence_path}", raw=True)
        if hashlib.sha256(payload).hexdigest() != check.get("sha256"):
            findings.append("predicate evidence digest mismatch")
        if own and git(root, "diff", "--name-only", revision, head, "--", *own):
            findings.append("owned implementation changed since verification")
    custody = receipt.get("custody")
    if not isinstance(custody, dict) or custody.get("verified") is not True or not custody.get("evidence"):
        findings.append("required artifact custody is unproven")
    else:
        custody_path = safe_path(custody["evidence"])
        evidence_paths.add(custody_path)
        payload = git(receipt_root, "show", f"{receipt_head}:{custody_path}", raw=True)
        if hashlib.sha256(payload).hexdigest() != custody.get("sha256"):
            findings.append("artifact custody evidence digest mismatch")
    base = receipt.get("base_head", "")
    if not isinstance(base, str) or not SHA.fullmatch(base):
        raise Unmeasured("session baseline revision is required")
    git(root, "merge-base", "--is-ancestor", base, head)
    changed = git(root, "diff", "--name-only", "-z", base, head, raw=True)
    for raw_path in changed.split(b"\0"):
        if raw_path:
            path = os.fsdecode(raw_path)
            if path not in evidence_paths and not matches(path, own) and not matches(path, siblings):
                findings.append(f"unattributed committed path: {path}")
    if disposition == "read_only" and own:
        findings.append("implementation paths cannot be declared read-only")
    if disposition == "complete" and any(row.get("status") not in {"done", "succeeded", "archived"} for row in runs):
        findings.append("failed or handed-off runs do not prove task completion")
    processes = observe_processes(root, session_id)
    if processes:
        findings.append("session worktree has surviving or unattributed processes")
    return {
        "schema": SCHEMA,
        "session_id": session_id,
        "head": head,
        "receipt_head": receipt_head,
        "session_released": not findings,
        "disposition": disposition,
        "task_completed": not findings and disposition == "complete",
        "estate_completed": False,
        "retirement_authorized": False,
        "successor_required": False,
        "findings": findings,
        "retained_work": notes,
        "process_count": len(processes),
        "coverage": audit["coverage"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--native-transcript", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true", help="Read-only (all invocations are read-only)")
    args = parser.parse_args(argv)
    try:
        from limen.conduct.client import client_from_env

        client = client_from_env()
        audit = client.session_audit(args.session_id)
        sessions = client.capabilities().get("sessions", [])
        binding = next((row for row in sessions if row.get("session_id") == args.session_id), None)
        native = bool(args.native_transcript and native_witness(args.native_transcript, args.session_id))
        receipt = args.receipt if args.receipt.is_absolute() else args.worktree / args.receipt
        result = evaluate(args.worktree, args.session_id, receipt, audit=audit, binding=binding, native_verified=native)
        code = 0 if result["session_released"] else 1
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError, RuntimeError) as exc:
        # Do not print subprocess stderr, credential-bearing argv, or private paths.
        result = {
            "schema": SCHEMA,
            "session_released": False,
            "task_completed": False,
            "successor_required": False,
            "status": "unmeasured",
            "error_type": type(exc).__name__,
        }
        if isinstance(exc, Unmeasured):
            result["reason"] = str(exc)
        code = 2
    print(
        json.dumps(result, indent=2, sort_keys=True)
        if args.json
        else f"session-closeout: {'PASS' if code == 0 else 'FAIL'} " + json.dumps(result, sort_keys=True)
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
