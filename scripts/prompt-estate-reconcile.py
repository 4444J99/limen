#!/usr/bin/env python3
"""Reconcile unresolved prompt atoms with existing estate owner receipts.

This bridge is deliberately read-only with respect to the estate.  It accepts
only the same validated, exact ``all/all`` atom projection used by
``prompt-priority-map.py`` and looks for exact atom-ID references in:

* ``tasks.yaml``;
* an open-pull-request JSON list (provided or queried through ``gh``); and
* ``git worktree list --porcelain``.

It never derives ownership from prompt text and never creates or mutates a
task, pull request, branch, or worktree.  Outputs contain opaque atom IDs and
sanitized receipt metadata only; task/PR prose, branch names, and local paths
are intentionally excluded.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(
    os.environ.get(
        "LIMEN_PRIVATE_SESSION_CORPUS",
        ROOT / ".limen-private" / "session-corpus",
    )
)
ATOM_INDEX = ROOT / "docs" / "prompt-atom-ledger.json"
TASKS_PATH = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
PRIVATE_OUTPUT = PRIVATE_ROOT / "lifecycle" / "prompt-estate-reconciliation.json"
PRIORITY_MAP_SCRIPT = Path(__file__).with_name("prompt-priority-map.py")

SAFE_ATOM_TOKEN = re.compile(r"(?<![A-Za-z0-9._:-])([A-Za-z0-9][A-Za-z0-9._:-]{0,127})(?![A-Za-z0-9._:-])")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SAFE_ROUTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,159}$")
SAFE_REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$")
GITHUB_PR_URL = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99}))/"
    r"(?P<repo>[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99}))/pull/"
    r"(?P<number>[1-9][0-9]*)/?$"
)
GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")

KNOWN_TASK_STATUSES = {
    "open",
    "dispatched",
    "in_progress",
    "done",
    "failed",
    "failed_blocked",
    "needs_human",
    "archived",
}
TERMINAL_TASK_STATUSES = {"done", "archived"}


class EstateReconciliationError(RuntimeError):
    """An input is not authoritative or safe enough to reconcile."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_hash(value: Any, *, length: int = 16) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError):
        encoded = repr(type(value)).encode("utf-8")
    return _sha256_bytes(encoded)[:length]


def _redacted_label(value: Any, *, kind: str, pattern: re.Pattern[str] = SAFE_ID) -> str:
    label = str(value or "").strip()
    if pattern.fullmatch(label):
        return label
    return f"redacted-{kind}-{_stable_hash(label)}"


def _safe_owner(value: Any, *, fallback: str) -> str:
    label = str(value or "").strip()
    if SAFE_REPOSITORY.fullmatch(label) or SAFE_ROUTE.fullmatch(label):
        return label
    if not label:
        return fallback
    return f"redacted-owner-{_stable_hash(label)}"


def _load_priority_map_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_limen_prompt_priority_map_for_estate_reconcile",
        PRIORITY_MAP_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise EstateReconciliationError(f"cannot load atom projection validator: {PRIORITY_MAP_SCRIPT.name}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, SyntaxError) as exc:
        raise EstateReconciliationError(f"cannot load atom projection validator: {PRIORITY_MAP_SCRIPT.name}") from exc
    if (
        not callable(getattr(module, "load_atom_projection", None))
        or not callable(getattr(module, "validate_atom_projection", None))
        or not callable(getattr(module, "verify_private_check_receipt", None))
    ):
        raise EstateReconciliationError("prompt priority map lacks its atom projection validator")
    return module


def load_validated_projection(
    path: Path,
    *,
    check_receipt: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str, dict[str, Any]]:
    """Load only complete, validated, exact all/all prompt-atom authority."""

    validator = _load_priority_map_validator()
    try:
        projection = validator.load_atom_projection(path)
        rows, projection_form = validator.validate_atom_projection(projection)
        private_check = validator.verify_private_check_receipt(
            projection,
            projection_path=path,
            receipt_path=check_receipt,
            allow_live=bool(check_receipt is None and path.resolve() == Path(validator.ATOM_INDEX).resolve()),
        )
    except validator.AtomProjectionError as exc:
        raise EstateReconciliationError(str(exc)) from exc

    declared_authority = projection.get("authority")
    if declared_authority not in (None, "prompt_atom_projection"):
        raise EstateReconciliationError("legacy or foreign projection authority is not accepted")
    if "legacy_compatibility" in projection:
        raise EstateReconciliationError("legacy session or batch authority is not accepted")

    if projection_form == "redacted":
        expected_unresolved = (projection.get("coverage") or {}).get("current_unresolved_atoms")
        if isinstance(expected_unresolved, bool) or not isinstance(expected_unresolved, int):
            raise EstateReconciliationError("redacted projection lacks current-unresolved completeness evidence")
        if expected_unresolved != len(rows):
            raise EstateReconciliationError("redacted projection unresolved count does not match coverage evidence")
    return projection, rows, projection_form, private_check


def _iter_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_text(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _iter_text(nested)


def exact_atom_references(value: Any, atom_ids: set[str]) -> set[str]:
    """Return explicit atom-ID tokens; substrings and prompt similarity never count."""

    found: set[str] = set()
    for text in _iter_text(value):
        for candidate in SAFE_ATOM_TOKEN.findall(text):
            if candidate in atom_ids:
                found.add(candidate)
    return found


def load_tasks(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise EstateReconciliationError(f"tasks board is missing: {path.name}") from exc
    except OSError as exc:
        raise EstateReconciliationError(f"cannot read tasks board: {path.name}") from exc
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise EstateReconciliationError("tasks board is malformed YAML") from exc
    if not isinstance(document, dict) or not isinstance(document.get("tasks"), list):
        raise EstateReconciliationError("tasks board must contain a tasks list")
    tasks = document["tasks"]
    if any(not isinstance(task, dict) for task in tasks):
        raise EstateReconciliationError("tasks board contains a non-object task")
    return tasks, _sha256_bytes(raw)


def _unwrap_pr_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "pullRequests", "pull_requests", "nodes", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise EstateReconciliationError("open PR input must be a JSON list of objects")
    return payload


def normalize_open_prs(payload: Any) -> list[dict[str, Any]]:
    """Keep rows that are open, accepting state-less output from ``gh pr list``."""

    rows = _unwrap_pr_payload(payload)
    return [row for row in rows if not row.get("state") or str(row.get("state")).strip().upper() == "OPEN"]


def load_open_prs(path: Path | None, *, root: Path) -> tuple[list[dict[str, Any]], str, str]:
    if path is not None:
        try:
            raw = sys.stdin.buffer.read() if str(path) == "-" else path.read_bytes()
        except OSError as exc:
            raise EstateReconciliationError("cannot read open PR JSON input") from exc
        try:
            payload = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise EstateReconciliationError("open PR input is malformed JSON") from exc
        return normalize_open_prs(payload), _sha256_bytes(raw), "provided_json"

    command = [
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        "1000",
        "--json",
        "number,url,state,isDraft,headRefName,title,body,author,labels",
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EstateReconciliationError("live gh open PR query was unavailable") from exc
    if proc.returncode != 0:
        raise EstateReconciliationError(f"live gh open PR query failed with exit {proc.returncode}")
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise EstateReconciliationError("live gh open PR query returned malformed JSON") from exc
    raw = proc.stdout.encode("utf-8")
    return normalize_open_prs(payload), _sha256_bytes(raw), "live_gh"


def parse_worktree_porcelain(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*text.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = line.partition(" ")
        if separator:
            current[key] = value
        else:
            current[key] = True
    if any(not isinstance(row.get("worktree"), str) for row in records):
        raise EstateReconciliationError("git worktree porcelain contains a malformed record")
    return records


def load_worktrees(path: Path | None, *, root: Path) -> tuple[list[dict[str, Any]], str, str]:
    if path is not None:
        try:
            raw = sys.stdin.buffer.read() if str(path) == "-" else path.read_bytes()
        except OSError as exc:
            raise EstateReconciliationError("cannot read worktree porcelain input") from exc
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise EstateReconciliationError("worktree porcelain input is not UTF-8") from exc
        return parse_worktree_porcelain(text), _sha256_bytes(raw), "provided_porcelain"

    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EstateReconciliationError("git worktree inventory was unavailable") from exc
    if proc.returncode != 0:
        raise EstateReconciliationError(f"git worktree inventory failed with exit {proc.returncode}")
    raw = proc.stdout.encode("utf-8")
    return parse_worktree_porcelain(proc.stdout), _sha256_bytes(raw), "live_git"


def _repository_from_pr(row: dict[str, Any], fallback: str) -> tuple[str, str | None]:
    url = str(row.get("url") or "").strip()
    match = GITHUB_PR_URL.fullmatch(url)
    if match:
        repository = f"{match.group('owner')}/{match.group('repo')}"
        return repository, match.group("number")
    repository = row.get("repository")
    if isinstance(repository, dict):
        repository = repository.get("nameWithOwner") or repository.get("name_with_owner")
    repository = str(repository or "").strip()
    if not SAFE_REPOSITORY.fullmatch(repository):
        repository = fallback
    number = row.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        return repository, None
    return repository, str(number)


def repository_owner_from_remote(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "local-repository"
    if proc.returncode != 0:
        return "local-repository"
    remote = proc.stdout.strip()
    match = re.search(r"github\.com(?::|/)([^/\s]+/[^/\s]+?)(?:\.git)?$", remote)
    if not match:
        return "local-repository"
    candidate = match.group(1).removesuffix(".git")
    return candidate if SAFE_REPOSITORY.fullmatch(candidate) else "local-repository"


def _task_receipt(task: dict[str, Any]) -> dict[str, Any]:
    task_id = _redacted_label(task.get("id"), kind="task")
    status = str(task.get("status") or "unknown")
    if status not in KNOWN_TASK_STATUSES:
        status = "unknown"
    owner = _safe_owner(task.get("repo"), fallback="task-board")
    agent = _redacted_label(task.get("target_agent"), kind="agent")
    return {
        "surface": "task",
        "receipt_id": f"task:{task_id}",
        "owner": owner,
        "status": status,
        "agent": agent,
        "live": status not in TERMINAL_TASK_STATUSES,
    }


def _pr_receipt(row: dict[str, Any], *, fallback_owner: str) -> dict[str, Any]:
    repository, number = _repository_from_pr(row, fallback_owner)
    owner = _safe_owner(repository, fallback="local-repository")
    if number is None:
        receipt_id = f"pr:redacted-{_stable_hash(row)}"
    else:
        receipt_id = f"pr:{owner}#{number}"
    return {
        "surface": "pull_request",
        "receipt_id": receipt_id,
        "owner": owner,
        "status": "open",
        "draft": bool(row.get("isDraft") or row.get("is_draft")),
        "live": True,
    }


def _worktree_receipt(row: dict[str, Any], *, repository_owner: str) -> dict[str, Any]:
    path_hash = _stable_hash(row.get("worktree"))
    head = str(row.get("HEAD") or "")
    return {
        "surface": "worktree",
        "receipt_id": f"worktree:wt-{path_hash}",
        "owner": _safe_owner(repository_owner, fallback="local-repository"),
        "head_sha": head if GIT_SHA.fullmatch(head) else None,
        "detached": bool(row.get("detached")),
        "locked": "locked" in row,
        "live": True,
    }


def _projection_route(row: dict[str, Any]) -> tuple[str, str]:
    outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
    owner = row.get("owner") or outcome.get("owner")
    route = (
        row.get("owner_route")
        or row.get("route_to")
        or row.get("route")
        or outcome.get("owner_route")
        or outcome.get("route_to")
        or outcome.get("route")
    )
    return (
        _safe_owner(owner, fallback="unassigned"),
        _safe_owner(route, fallback="unrouted"),
    )


def _add_matches(
    matches: dict[str, list[dict[str, Any]]],
    seen: dict[str, set[tuple[str, str]]],
    atom_ids: set[str],
    source: Any,
    receipt: dict[str, Any],
) -> None:
    for atom_id in exact_atom_references(source, atom_ids):
        key = (str(receipt["surface"]), str(receipt["receipt_id"]))
        if key not in seen[atom_id]:
            matches[atom_id].append(receipt)
            seen[atom_id].add(key)


def build_reconciliation(
    *,
    projection_path: Path,
    tasks_path: Path,
    open_prs: list[dict[str, Any]],
    open_prs_digest: str,
    open_prs_source: str,
    worktrees: list[dict[str, Any]],
    worktrees_digest: str,
    worktrees_source: str,
    repository_owner: str,
    projection_check_receipt: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a complete, redacted, non-mutating atom-to-estate map."""

    projection, atom_rows, projection_form, private_check = load_validated_projection(
        projection_path,
        check_receipt=projection_check_receipt,
    )
    tasks, tasks_digest = load_tasks(tasks_path)
    open_prs = normalize_open_prs(open_prs)
    retained_worktrees = [row for row in worktrees if "prunable" not in row]
    atom_ids = {str(row["atom_id"]) for row in atom_rows}

    matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for task in tasks:
        _add_matches(matches, seen, atom_ids, task, _task_receipt(task))
    for row in open_prs:
        _add_matches(
            matches,
            seen,
            atom_ids,
            row,
            _pr_receipt(row, fallback_owner=repository_owner),
        )
    for row in retained_worktrees:
        _add_matches(
            matches,
            seen,
            atom_ids,
            row,
            _worktree_receipt(row, repository_owner=repository_owner),
        )

    reconciliation: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    unmatched_ids: list[str] = []
    match_surface_counts: dict[str, int] = defaultdict(int)
    rows_by_id = {str(row["atom_id"]): row for row in atom_rows}
    for atom_id in sorted(atom_ids):
        receipts = sorted(
            matches.get(atom_id, []),
            key=lambda receipt: (str(receipt["surface"]), str(receipt["receipt_id"])),
        )
        for receipt in receipts:
            match_surface_counts[str(receipt["surface"])] += 1
        owner_receipts: list[dict[str, Any]] = []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for receipt in receipts:
            grouped[str(receipt["owner"])].append(receipt)
        for owner in sorted(grouped):
            owned = grouped[owner]
            owner_receipts.append(
                {
                    "owner": owner,
                    "live": any(bool(receipt["live"]) for receipt in owned),
                    "receipts": owned,
                }
            )

        live_owners = sorted(
            {
                str(receipt["owner"])
                for receipt in receipts
                if receipt.get("live") and receipt.get("owner") not in {"unassigned", "unrouted"}
            }
        )
        projected_owner, projected_route = _projection_route(rows_by_id[atom_id])
        duplicate_owner_conflict = len(live_owners) > 1
        projected_owner_mismatch = (
            projected_owner != "unassigned" and bool(live_owners) and projected_owner not in live_owners
        )
        if duplicate_owner_conflict or projected_owner_mismatch:
            conflicts.append(
                {
                    "atom_id": atom_id,
                    "live_owners": live_owners,
                    "projected_owner": projected_owner,
                    "duplicate_owner_conflict": duplicate_owner_conflict,
                    "projected_owner_mismatch": projected_owner_mismatch,
                }
            )
        if not receipts:
            unmatched_ids.append(atom_id)
        reconciliation.append(
            {
                "atom_id": atom_id,
                "projected_owner": projected_owner,
                "projected_route": projected_route,
                "owner_receipts": owner_receipts,
                "receipt_count": len(receipts),
                "live_owner_count": len(live_owners),
                "unmatched": not receipts,
                "without_live_owner": not live_owners,
                "duplicate_owner_conflict": duplicate_owner_conflict,
                "projected_owner_mismatch": projected_owner_mismatch,
            }
        )

    generated_at = generated_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return {
        "version": 1,
        "generated_at": generated_at,
        "control": {
            "authority": "prompt_atom_projection",
            "projection_form": projection_form,
            "source_scope": "all",
            "target_scope": "all",
            "semantic_digest": projection["semantic_digest"],
            "policy_digest": projection["policy_digest"],
            "source_cursor_digest": projection["source_cursor_digest"],
            "projection_digest": projection["projection_digest"],
            "private_check": private_check,
            "matching": "exact_atom_id_only",
            "legacy_authority_accepted": False,
            "read_only": True,
            "estate_mutations": 0,
        },
        "input_receipts": {
            "tasks": {
                "sha256": tasks_digest,
                "records": len(tasks),
                "source": "tasks_yaml",
            },
            "open_pull_requests": {
                "sha256": open_prs_digest,
                "records": len(open_prs),
                "source": open_prs_source,
            },
            "worktrees": {
                "sha256": worktrees_digest,
                "records": len(retained_worktrees),
                "source": worktrees_source,
            },
        },
        "live_counts": {
            "open_tasks": sum(1 for task in tasks if task.get("status") == "open"),
            "needs_human": sum(1 for task in tasks if task.get("status") == "needs_human"),
            "open_prs": len(open_prs),
            "retained_worktrees": len(retained_worktrees),
        },
        "coverage": {
            "unresolved_atom_ids": len(atom_ids),
            "matched_atom_ids": len(atom_ids) - len(unmatched_ids),
            "unmatched_atom_ids": len(unmatched_ids),
            "duplicate_owner_conflicts": sum(1 for row in reconciliation if row["duplicate_owner_conflict"]),
            "projected_owner_mismatches": sum(1 for row in reconciliation if row["projected_owner_mismatch"]),
            "matches_by_surface": dict(sorted(match_surface_counts.items())),
        },
        "unmatched_atom_ids": unmatched_ids,
        "owner_conflicts": conflicts,
        "atom_reconciliation": reconciliation,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    control = snapshot.get("control") or {}
    private_check = control.get("private_check") or {}
    if (
        control.get("authority") != "prompt_atom_projection"
        or control.get("source_scope") != "all"
        or control.get("target_scope") != "all"
        or control.get("read_only") is not True
        or control.get("estate_mutations") != 0
        or private_check.get("result") != "pass"
        or private_check.get("projection_digest") != control.get("projection_digest")
    ):
        raise EstateReconciliationError("refusing tracked summary without exact, read-only atom authority")
    counts = snapshot["live_counts"]
    coverage = snapshot["coverage"]
    lines = [
        "# Prompt Atom Estate Reconciliation",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "- Authority: validated prompt-atom projection with exact `all/all` source scope.",
        "- Matching: exact opaque `atom_id` references only; prompt text is never used to infer an owner.",
        "- Operation: read-only. This report created no task, pull request, branch, or worktree.",
        "- Redaction: task/PR prose, branch names, and filesystem paths are excluded.",
        "",
        "## Live estate counts",
        "",
        f"- Open tasks: `{counts['open_tasks']}`.",
        f"- Human gates (`needs_human`): `{counts['needs_human']}`.",
        f"- Open pull requests: `{counts['open_prs']}`.",
        f"- Retained worktrees: `{counts['retained_worktrees']}`.",
        "",
        "## Coverage",
        "",
        f"- Unresolved atom IDs: `{coverage['unresolved_atom_ids']}`.",
        f"- Matched atom IDs: `{coverage['matched_atom_ids']}`.",
        f"- Explicitly unmatched atom IDs: `{coverage['unmatched_atom_ids']}`.",
        f"- Duplicate live-owner conflicts: `{coverage['duplicate_owner_conflicts']}`.",
        f"- Projected-owner mismatches: `{coverage['projected_owner_mismatches']}`.",
        "",
        "## Atom-to-owner receipts",
        "",
        "| Atom ID | Existing owner receipts | State | Conflict |",
        "|---|---|---|---|",
    ]
    for row in snapshot.get("atom_reconciliation") or []:
        owner_bits = []
        for owner in row["owner_receipts"]:
            receipt_ids = ", ".join(f"`{receipt['receipt_id']}`" for receipt in owner["receipts"])
            owner_bits.append(f"`{owner['owner']}`: {receipt_ids}")
        owners = "; ".join(owner_bits) if owner_bits else "none"
        state = "unmatched" if row["unmatched"] else "reuse existing receipt(s)"
        conflict_bits = []
        if row["duplicate_owner_conflict"]:
            conflict_bits.append("duplicate live owners")
        if row["projected_owner_mismatch"]:
            conflict_bits.append("projected owner mismatch")
        conflicts = ", ".join(conflict_bits) if conflict_bits else "none"
        lines.append(f"| `{row['atom_id']}` | {owners} | {state} | {conflicts} |")
    lines.extend(
        [
            "",
            "Unmatched IDs remain explicit. This bridge does not mint replacement owners or duplicate work.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def write_outputs(
    snapshot: dict[str, Any],
    *,
    private_output: Path,
    markdown_output: Path | None,
) -> None:
    _atomic_write(
        private_output,
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    )
    if markdown_output is not None:
        _atomic_write(markdown_output, render_markdown(snapshot))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only exact-ID reconciliation of prompt atoms against estate receipts."
    )
    parser.add_argument("--projection", type=Path, default=ATOM_INDEX)
    parser.add_argument(
        "--atom-check-receipt",
        type=Path,
        help="Private hash-matched core-check receipt for a non-default projection.",
    )
    parser.add_argument("--tasks", type=Path, default=TASKS_PATH)
    parser.add_argument(
        "--open-prs-json",
        type=Path,
        help="Open-PR JSON list from gh; omit to query the current remote with gh.",
    )
    parser.add_argument(
        "--worktrees-porcelain",
        type=Path,
        help="Captured git worktree porcelain; omit to query git read-only.",
    )
    parser.add_argument("--private-output", type=Path, default=PRIVATE_OUTPUT)
    parser.add_argument(
        "--markdown-output",
        type=Path,
        help="Optional tracked-safe Markdown summary path.",
    )
    parser.add_argument(
        "--repository-owner",
        help="Explicit owner/repo for local worktree receipts; defaults to origin.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate and reconcile without writing output files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        open_prs, open_prs_digest, open_prs_source = load_open_prs(
            args.open_prs_json,
            root=ROOT,
        )
        worktrees, worktrees_digest, worktrees_source = load_worktrees(
            args.worktrees_porcelain,
            root=ROOT,
        )
        repository_owner = _safe_owner(
            args.repository_owner or repository_owner_from_remote(ROOT),
            fallback="local-repository",
        )
        snapshot = build_reconciliation(
            projection_path=args.projection,
            tasks_path=args.tasks,
            open_prs=open_prs,
            open_prs_digest=open_prs_digest,
            open_prs_source=open_prs_source,
            worktrees=worktrees,
            worktrees_digest=worktrees_digest,
            worktrees_source=worktrees_source,
            repository_owner=repository_owner,
            projection_check_receipt=args.atom_check_receipt,
        )
        if not args.check:
            write_outputs(
                snapshot,
                private_output=args.private_output,
                markdown_output=args.markdown_output,
            )
    except EstateReconciliationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    coverage = snapshot["coverage"]
    print(
        "OK: reconciled "
        f"{coverage['unresolved_atom_ids']} unresolved atom IDs; "
        f"matched={coverage['matched_atom_ids']} "
        f"unmatched={coverage['unmatched_atom_ids']} "
        f"owner_conflicts={coverage['duplicate_owner_conflicts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
