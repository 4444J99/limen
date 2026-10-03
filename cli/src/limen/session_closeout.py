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
from urllib.parse import quote, urlsplit

SCHEMA = "limen.session_closeout.v1"
SCHEMA_V2 = "limen.session_closeout.v2"
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
    slug = github_repository_slug(git(root, "remote", "get-url", "origin"))
    if slug is not None:
        # GitHub publication uses the authenticated exact-ref API. Ambient SSH
        # ControlPersist otherwise creates a detached master during this read,
        # which the same predicate correctly rejects as an unattributed process.
        # Never turn that self-created state into an SSH ownership exemption.
        value = json.loads(
            run(["gh", "api", "--method", "GET", f"repos/{slug}/git/ref/heads/{quote(branch, safe='')}"])
        )
        if not isinstance(value, dict) or not isinstance(value.get("object"), dict):
            raise Unmeasured("GitHub publication ref readback is malformed")
        if value["object"].get("type") != "commit":
            raise Unmeasured("GitHub publication ref is not a commit")
        tip, remote_ref = value["object"].get("sha"), value.get("ref")
    else:
        # Preserve non-GitHub/local transport support and its exact live-ref proof.
        rows = git(root, "ls-remote", "--exit-code", "origin", ref).splitlines()
        if len(rows) != 1:
            return False
        tip, remote_ref = rows[0].split()
    if remote_ref != ref or not isinstance(tip, str) or not SHA.fullmatch(tip):
        return False
    # A moving remote never makes a cached origin/* ref publication evidence.
    if tip == revision:
        return True
    try:
        git(root, "merge-base", "--is-ancestor", revision, tip)
    except subprocess.CalledProcessError:
        return False
    return True


def process_observation(root: Path, session_id: str, *, evidence: list[dict] | tuple[dict, ...] = ()) -> dict:
    from limen.process_ownership import observe

    return observe(root, session_id, evidence=evidence)


def native_witness(path: Path, session_id: str) -> bool:
    from limen.process_ownership import transcript_witness

    return transcript_witness(path)["thread_id"] == session_id


def evaluate(
    root: Path,
    session_id: str,
    receipt_path: Path,
    *,
    audit: dict,
    binding: dict | None,
    native_verified: bool = False,
    read_owner: Callable[[str], dict] = owner_readback,
    observe_processes: Callable[..., Any] = process_observation,
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
        if type(check.get("exit_code")) is not int or not SHA.fullmatch(revision):
            findings.append("required scoped predicate has no passing exact-head receipt")
            continue
        if check["exit_code"] != 0:
            if (
                disposition == "handoff"
                and check.get("purpose") == "completion"
                and check.get("owner_url") == receipt["owner_url"]
                and current_owner.get("state") == "open"
            ):
                notes.append({"owner_url": receipt["owner_url"], "completion_check_exit": check["exit_code"]})
            else:
                findings.append("required scoped predicate has no passing exact-head receipt")
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
    process_evidence = []
    if attribution := receipt.get("process_ownership"):
        if not isinstance(attribution, dict):
            raise Unmeasured("malformed process ownership evidence")
        attribution_path = safe_path(attribution.get("evidence"))
        evidence_paths.add(attribution_path)
        payload = git(receipt_root, "show", f"{receipt_head}:{attribution_path}", raw=True)
        if hashlib.sha256(payload).hexdigest() != attribution.get("sha256"):
            raise Unmeasured("process ownership evidence digest mismatch")
        packet = json.loads(payload)
        if packet.get("schema") != "limen.process_ownership.v1" or not isinstance(packet.get("processes"), list):
            raise Unmeasured("malformed process ownership evidence")
        process_evidence = packet["processes"]
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
    observation = (
        observe_processes(root, session_id, evidence=process_evidence)
        if process_evidence
        else observe_processes(root, session_id)
    )
    # Legacy observer injection remains supported; unidentified PIDs always block.
    if isinstance(observation, list):
        observation = {
            "complete": True,
            "process_count": len(observation),
            "observed_count": len(observation),
            "counts": {"unknown": len(observation)},
            "processes": [{"pid": pid, "category": "unknown"} for pid in observation],
        }
    if not isinstance(observation, dict) or observation.get("complete") is not True:
        raise Unmeasured("process ownership observation unavailable or invalid")
    if observation["process_count"]:
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
        "process_count": observation["process_count"],
        "process_observation": observation,
        "coverage": audit["coverage"],
    }


def path_digest(path: Path) -> str:
    return hashlib.sha256(os.fsencode(str(path))).hexdigest()


def repository_readback(slug: str) -> dict:
    return json.loads(run(["gh", "api", "--method", "GET", f"repos/{slug}"]))


def github_repository_slug(remote: str) -> str | None:
    if remote.startswith("git@github.com:"):
        slug = remote.removeprefix("git@github.com:")
    else:
        parsed = urlsplit(remote)
        if parsed.hostname != "github.com" or parsed.scheme not in {"https", "http", "ssh", "git"}:
            return None
        slug = parsed.path.lstrip("/")
    slug = slug.removesuffix(".git")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", slug):
        raise Unmeasured("invalid GitHub repository remote")
    return slug


def evaluate_scoped(
    session_root: Path,
    session_id: str,
    receipt_path: Path,
    scope_roots: dict[str, Path],
    *,
    audit: dict,
    binding: dict | None,
    native_transcript: Path | None = None,
    read_owner: Callable[[str], dict] = owner_readback,
    read_repository: Callable[[str], dict] | None = None,
    observe_processes: Callable[..., Any] | None = None,
) -> dict:
    """Validate explicit roots and one native anchor without guessing repositories."""
    from limen.process_ownership import observe_many, transcript_witness

    anchor = session_root.resolve(strict=True)
    roots = {key: path.resolve(strict=True) for key, path in scope_roots.items()}
    if any(not path.is_absolute() or path.absolute() != roots[key] for key, path in scope_roots.items()):
        raise Unmeasured("scope mappings must use canonical absolute paths")
    if len(set(roots.values())) != len(roots):
        raise Unmeasured("duplicate canonical scope roots")
    receipt_path = receipt_path.resolve(strict=True)
    receipt_root = Path(git(receipt_path.parent, "rev-parse", "--show-toplevel")).resolve()
    receipt_head = git(receipt_root, "rev-parse", "HEAD")
    relative = receipt_path.relative_to(receipt_root).as_posix()
    raw = receipt_path.read_bytes()
    if raw != git(receipt_root, "show", f"{receipt_head}:{relative}", raw=True):
        raise Unmeasured("closeout receipt is not committed at the inspected head")
    receipt = json.loads(raw)
    if receipt.get("schema") != SCHEMA_V2 or receipt.get("session_id") != session_id:
        raise Unmeasured("closeout receipt session identity mismatch")
    if receipt.get("session_root_path_sha256") != path_digest(anchor):
        raise Unmeasured("native session root mismatch")
    if audit.get("session_id") != session_id or audit.get("coverage", {}).get("retained_state_complete") is not True:
        raise Unmeasured("session audit missing or incomplete")
    runs = audit.get("runs")
    if not isinstance(runs, list) or audit.get("retained_run_count") != len(runs):
        raise Unmeasured("retained run coverage is incomplete")
    broker_scope = receipt.get("broker_scope_root_id")
    expected_binding = anchor
    if broker_scope is not None:
        if (
            not isinstance(broker_scope, str)
            or broker_scope not in roots
            or native_transcript is None
            or binding is None
            or audit.get("session_present") is not True
        ):
            raise Unmeasured("explicit broker scope witness unavailable")
        # A broker's current execution checkout may differ from the native start
        # directory. Accept only an explicitly named, fully checked receipt scope;
        # never substitute that checkout for the native anchor or infer a sibling.
        expected_binding = roots[broker_scope]
    if binding is not None:
        bound_path = Path(binding.get("worktree") or "")
        if (
            binding.get("session_id") != session_id
            or not bound_path.is_absolute()
            or bound_path != bound_path.resolve()
            or bound_path != expected_binding
        ):
            raise Unmeasured("broker session/worktree binding mismatch")
    elif audit.get("session_present") is not False or native_transcript is None:
        raise Unmeasured("no broker binding or exact native-session witness")
    if native_transcript is not None:
        witness = transcript_witness(native_transcript)
        cwd = Path(witness.get("cwd") or "")
        if witness["thread_id"] != session_id or not cwd.is_absolute() or cwd != cwd.resolve() or cwd != anchor:
            raise Unmeasured("native transcript identity or root mismatch")
    declarations = receipt.get("scope_roots")
    if not isinstance(declarations, list) or not declarations:
        raise Unmeasured("explicit scope roots are required")
    ids = [row.get("id") for row in declarations if isinstance(row, dict)]
    if len(ids) != len(declarations) or len(set(ids)) != len(ids) or set(ids) != set(roots):
        raise Unmeasured("scope mappings do not match receipt")
    by_id = {row["id"]: row for row in declarations}
    for row in declarations:
        retained = row.get("retained_work", [])
        if not isinstance(retained, list) or any(not isinstance(item, dict) for item in retained):
            raise Unmeasured("malformed retained work ownership")
    for identifier, root in roots.items():
        parents = [key for key, path in roots.items() if key != identifier and root.is_relative_to(path)]
        if parents:
            parent = max(parents, key=lambda key: len(roots[key].parts))
            prefix = root.relative_to(roots[parent]).as_posix()
            retained = by_id[parent].get("retained_work", [])
            if by_id[identifier].get("nested_in") != parent or not any(
                matches(prefix, item.get("paths", [])) for item in retained
            ):
                raise Unmeasured("nested scope lacks explicit parent ownership")
    receipt_id = receipt.get("receipt_root_id")
    if receipt_id not in roots or roots[receipt_id] != receipt_root:
        raise Unmeasured("receipt repository scope mismatch")
    disposition = receipt.get("disposition")
    if disposition not in {"complete", "handoff", "read_only"}:
        raise Unmeasured("invalid session disposition")
    owner_cache: dict[str, dict] = {}

    def owner(url: Any) -> dict:
        if not isinstance(url, str) or not OWNER.fullmatch(url):
            raise Unmeasured("durable owner is required")
        if url not in owner_cache:
            owner_cache[url] = read_owner(url)
        return owner_cache[url]

    current_owner = owner(receipt.get("owner_url"))
    findings: list[str] = []
    notes: list[dict] = []
    if disposition == "handoff" and current_owner.get("state") != "open":
        findings.append("unfinished handoff owner is not open")
    if type(audit.get("active_lease_count")) is not int or audit["active_lease_count"] != 0:
        findings.append("session has active or unmeasured leases")
    terminal = {
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
    if any(row.get("status") not in terminal for row in runs):
        findings.append("session has nonterminal runs")
    if disposition == "complete" and any(row.get("status") not in {"done", "succeeded", "archived"} for row in runs):
        findings.append("failed or handed-off runs do not prove task completion")
    evidence_paths = {relative}

    def evidence(packet: dict) -> bytes:
        path = safe_path(packet.get("evidence"))
        evidence_paths.add(path)
        payload = git(receipt_root, "show", f"{receipt_head}:{path}", raw=True)
        if hashlib.sha256(payload).hexdigest() != packet.get("sha256"):
            raise Unmeasured("committed evidence digest mismatch")
        if (receipt_root / path).read_bytes() != payload:
            raise Unmeasured("committed evidence has local changes")
        return payload

    custody = receipt.get("custody")
    if not isinstance(custody, dict) or custody.get("verified") is not True:
        findings.append("required artifact custody is unproven")
    elif not isinstance(custody.get("root_ids"), list) or sorted(custody["root_ids"]) != sorted(roots):
        raise Unmeasured("custody coverage does not match scope")
    else:
        custody_payload = evidence(custody)
        if contract := custody.get("contract"):
            if contract != "limen.custody_receipt.v2":
                raise Unmeasured("unsupported scoped custody contract")
            from limen.portable_custody import validate_bundle

            try:
                validate_bundle(
                    custody_payload,
                    session_id=session_id,
                    scope_paths={row["id"]: row.get("path_sha256") for row in declarations},
                    read_evidence=evidence,
                )
            except (ValueError, TypeError, KeyError) as exc:
                raise Unmeasured("portable custody evidence graph is incomplete or invalid") from exc
    process_evidence = []
    if packet := receipt.get("process_ownership"):
        value = json.loads(evidence(packet))
        if value.get("schema") != "limen.process_ownership.v1" or not isinstance(value.get("processes"), list):
            raise Unmeasured("malformed process ownership evidence")
        process_evidence = value["processes"]
    checks = receipt.get("verification")
    if not isinstance(checks, list) or not checks:
        raise Unmeasured("scoped verification evidence is required")
    checks_by_root: dict[str, list[dict]] = {key: [] for key in roots}
    for check in checks:
        if not isinstance(check, dict) or check.get("root_id") not in roots:
            raise Unmeasured("verification scope is unavailable")
        evidence(check)
        checks_by_root[check["root_id"]].append(check)
        if type(check.get("exit_code")) is not int:
            raise Unmeasured("verification exit is unavailable")
        if check["exit_code"] != 0:
            if (
                disposition == "handoff"
                and check.get("purpose") == "completion"
                and owner(check.get("owner_url")).get("state") == "open"
            ):
                notes.append(
                    {
                        "root_id": check["root_id"],
                        "owner_url": check["owner_url"],
                        "completion_check_exit": check["exit_code"],
                    }
                )
            else:
                findings.append(f"{check['root_id']}: required scoped predicate failed")
    effects = receipt.get("external_effects", [])
    if not isinstance(effects, list):
        raise Unmeasured("malformed external effect coverage")
    for effect in effects:
        if not isinstance(effect, dict) or not effect.get("kind") or not effect.get("id"):
            raise Unmeasured("malformed external effect")
        evidence(effect)
        if effect.get("verified") is not True and (
            disposition != "handoff" or owner(effect.get("owner_url")).get("state") != "open"
        ):
            findings.append(f"external effect {effect['id']}: readback unavailable")
    heads: dict[str, str] = {}
    read_repository = read_repository or repository_readback
    repository_cache: dict[str, dict] = {}
    for row in declarations:
        identifier = row["id"]
        root = roots[identifier]
        if row.get("path_sha256") != path_digest(root):
            raise Unmeasured("scope path binding mismatch")
        if row.get("kind") == "retained":
            if identifier == receipt_id or owner(row.get("owner_url")).get("state") != "open":
                raise Unmeasured("retained scope owner unavailable")
            notes.append({"root_id": identifier, "owner_url": row["owner_url"]})
            if disposition == "complete":
                findings.append(f"{identifier}: retained scope requires handoff")
            continue
        if row.get("kind") != "git" or Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            raise Unmeasured("scope is not an exact Git root")
        head = git(root, "rev-parse", "HEAD")
        heads[identifier] = head
        if identifier != receipt_id and row.get("subject_head") != head:
            raise Unmeasured("scope is not bound to the exact subject head")
        remote = git(root, "remote", "get-url", "origin")
        github_slug = github_repository_slug(remote)
        slug = github_slug if github_slug is not None else remote.removesuffix(".git")
        if github_slug is not None:
            if slug not in repository_cache:
                repository_cache[slug] = read_repository(slug)
            repo = repository_cache[slug]
            if (
                type(row.get("repository_id")) is not int
                or row["repository_id"] != repo.get("id")
                or row.get("repository") != repo.get("full_name")
            ):
                raise Unmeasured("scope repository identity mismatch")
        elif row.get("repository") != slug:
            raise Unmeasured("scope repository identity mismatch")
        if not published(root, head, row.get("publication_branch", "")):
            findings.append(f"{identifier}: inspected head is not remotely durable")
        base = row.get("base_head", "")
        if not isinstance(base, str) or not SHA.fullmatch(base):
            raise Unmeasured("scope baseline revision is required")
        git(root, "merge-base", "--is-ancestor", base, head)
        own, retained = row.get("owned_paths"), row.get("retained_work")
        if not isinstance(own, list) or not isinstance(retained, list):
            raise Unmeasured("explicit scope path ownership is required")
        own = [safe_path(path) for path in own]
        siblings = []
        for item in retained:
            paths = [safe_path(path) for path in item.get("paths", [])]
            if not paths or owner(item.get("owner_url")).get("state") != "open":
                raise Unmeasured("retained work owner unavailable")
            siblings.extend(paths)
            notes.append({"root_id": identifier, "paths": paths, "owner_url": item["owner_url"]})
        dirty = dirty_paths(git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", raw=True))
        for path in sorted(dirty):
            if matches(path, own) or (identifier == receipt_id and path in evidence_paths):
                findings.append(f"{identifier}: owned uncommitted path: {path}")
            elif not matches(path, siblings):
                findings.append(f"{identifier}: unattributed dirty path: {path}")
        for check in checks_by_root[identifier]:
            revision = check.get("head", "")
            if not isinstance(revision, str) or not SHA.fullmatch(revision):
                raise Unmeasured("verification revision is required")
            git(root, "merge-base", "--is-ancestor", revision, head)
            if own and git(root, "diff", "--name-only", revision, head, "--", *own):
                findings.append(f"{identifier}: owned implementation changed since verification")
        if own and not checks_by_root[identifier]:
            raise Unmeasured("owned scope has no verification")
        for raw_path in git(root, "diff", "--name-only", "-z", base, head, raw=True).split(b"\0"):
            if raw_path:
                path = os.fsdecode(raw_path)
                if not (identifier == receipt_id and path in evidence_paths) and not matches(path, own + siblings):
                    findings.append(f"{identifier}: unattributed committed path: {path}")
        if disposition == "read_only" and own:
            findings.append(f"{identifier}: implementation paths cannot be read-only")
    observer = observe_processes or observe_many
    observation = observer(tuple(roots.values()), session_id, anchor=anchor, evidence=process_evidence)
    if (
        not isinstance(observation, dict)
        or observation.get("complete") is not True
        or type(observation.get("process_count")) is not int
    ):
        raise Unmeasured("process ownership observation unavailable or invalid")
    if observation["process_count"]:
        findings.append("session scopes have surviving or unattributed processes")
    return {
        "schema": SCHEMA_V2,
        "session_id": session_id,
        "head": heads[receipt_id],
        "heads": heads,
        "receipt_head": receipt_head,
        "session_released": not findings,
        "disposition": disposition,
        "task_completed": not findings and disposition == "complete",
        "estate_completed": False,
        "retirement_authorized": False,
        "successor_required": False,
        "findings": findings,
        "retained_work": notes,
        "process_count": observation["process_count"],
        "process_observation": observation,
        "coverage": audit["coverage"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--native-transcript", type=Path)
    parser.add_argument("--scope-root", action="append", default=[], metavar="ID=PATH")
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
        if args.scope_root:
            roots = {}
            for value in args.scope_root:
                identifier, separator, path = value.partition("=")
                if (
                    not separator
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", identifier)
                    or identifier in roots
                ):
                    raise Unmeasured("invalid or duplicate scope mapping")
                roots[identifier] = Path(path)
            result = evaluate_scoped(
                args.worktree,
                args.session_id,
                receipt,
                roots,
                audit=audit,
                binding=binding,
                native_transcript=args.native_transcript,
            )
        else:
            result = evaluate(
                args.worktree, args.session_id, receipt, audit=audit, binding=binding, native_verified=native
            )
        code = 0 if result["session_released"] else 1
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError, RuntimeError) as exc:
        # Do not print subprocess stderr, credential-bearing argv, or private paths.
        result = {
            "schema": SCHEMA_V2 if args.scope_root else SCHEMA,
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
