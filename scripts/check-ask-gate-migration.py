#!/usr/bin/env python3
"""Verify the frozen 2026-07-12 ask-gate migration receipt.

This verifier is deliberately read-only and offline.  It proves the frozen-id
hash, action/replacement coverage, typed child contracts, supersession routing,
and the public-safe receipt boundary.  It never reads or writes ``tasks.yaml``
and never creates TABVLARIVS tickets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECEIPT = ROOT / "docs" / "ask-gate-migration-2026-07-12.json"
SCHEMA = "limen.ask_gate_migration.v1"
SOURCE_COMMIT = "04baa47d471f44a8faa3beb790f5636fe65d77ef"
EXPECTED_SHA256 = "8882781adf152655150ac8d49b53b5d5b5a33762581e5fed9afaa2e8410c82da"
EXPECTED_ACTIONS = {
    "split": 14,
    "normalize": 31,
    "done": 4,
    "needs_human": 2,
    "superseded": 1,
}
EXPECTED_CHILDREN = 29
EXPECTED_PREREQUISITES = {978, 982}
APPLICATION_SCHEMA = "limen.ask_gate_migration.application.v1"
APPLICATION_HELPER = "scripts/apply-ask-gate-migration.py"
APPLICATION_VERIFIER = "scripts/check-ask-gate-migration.py"
EXPECTED_APPLICATION_PHASES = [
    {
        "name": "children",
        "count": 29,
        "intent": "task.upsert",
        "patch": "full_task",
        "append_log": True,
        "precondition": "task_absent",
    },
    {
        "name": "parents",
        "count": 52,
        "intent": "task.upsert",
        "patch": "predicate + receipt_target + status_patch",
        "append_log": True,
        "precondition": "exact_current_task_sha256_and_status",
    },
]
VALID_STATUSES = {
    "open",
    "dispatched",
    "in_progress",
    "done",
    "failed",
    "failed_blocked",
    "needs_human",
    "archived",
}
EXPECTED_STATUS_PATCH = {
    "split": {"status": "archived"},
    "normalize": {},
    "done": {"status": "done"},
    "needs_human": {"status": "needs_human"},
    "superseded": {"status": "archived"},
}

EXECUTABLES = frozenset(
    {
        "[",
        "bash",
        "bundle",
        "cargo",
        "curl",
        "gh",
        "git",
        "go",
        "just",
        "make",
        "node",
        "nox",
        "npm",
        "pnpm",
        "py.test",
        "pytest",
        "python",
        "python3",
        "ruby",
        "sh",
        "test",
        "tox",
        "uv",
        "yarn",
        "zsh",
    }
)
PLACEHOLDER_RE = re.compile(r"(?:<[^>]+>|\b(?:tbd|todo|fixme|replace[-_ ]me)\b)", re.IGNORECASE)
GITHUB_DECLARED_RE = re.compile(
    r"^github:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:"
    r"(?:pull-request|issue):[A-Za-z0-9][A-Za-z0-9._/-]*$"
)
GIT_PATH_RE = re.compile(r"^git:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:(?P<path>[^\s#]+)(?:#[^\s]+)?$")
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
    r"(?:issues|pull|actions/(?:runs|workflows)|commit|blob|tree)/[^/?#]+"
)
PRIVATE_KEY_MARKER_RE = re.compile("-" * 5 + r"BEGIN [A-Z0-9 ]*PRIVATE KEY" + "-" * 5)
SECRET_PATTERNS = {
    "private-key-block": PRIVATE_KEY_MARKER_RE,
    "openai-key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    "github-token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{16,}"),
    "aws-key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}"),
}
PRIVATE_PATH_PATTERNS = (
    "/Users/",
    "/Volumes/",
    "/private/",
    "~/",
    ".limen-private",
    ".gpg-secrets",
)
SENSITIVE_KEYS = {"secret", "token", "password", "passphrase", "private_key", "private-key"}


def _serialized_ids(ids: list[str]) -> bytes:
    return "".join(f"{task_id}\n" for task_id in sorted(ids)).encode("utf-8")


def _is_executable_predicate(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    command = value.strip()
    if not command or "\n" in command or "\r" in command or PLACEHOLDER_RE.search(command):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    index = 0
    while index < len(argv) and (
        argv[index] in {"command", "env", "sudo"}
        or ("=" in argv[index] and not argv[index].startswith(("/", "./", "../")))
        or argv[index].startswith("-")
    ):
        index += 1
    if index >= len(argv):
        return False
    first = argv[index]
    return bool(first in EXECUTABLES or "/" in first or first.endswith((".py", ".sh")))


def _is_durable_receipt(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    target = value.strip()
    if not target or PLACEHOLDER_RE.search(target):
        return False
    if GITHUB_DECLARED_RE.fullmatch(target):
        return True
    git_target = GIT_PATH_RE.fullmatch(target)
    if git_target:
        path = git_target.group("path")
        return not path.startswith("/") and all(part not in {"", ".", "..", ".git"} for part in path.split("/"))
    parsed = urlparse(target)
    return parsed.scheme == "https" and parsed.netloc.lower() == "github.com" and bool(GITHUB_URL_RE.match(target))


def _predicate_syntax_error(value: str) -> str | None:
    argv = shlex.split(value)
    if argv[:2] == ["python3", "-c"]:
        try:
            compile(argv[2], "<migration-predicate>", "exec")
        except (IndexError, SyntaxError) as exc:
            return f"embedded Python does not compile: {exc}"
    if argv[:2] == ["bash", "-lc"]:
        try:
            result = subprocess.run(
                ["bash", "-n", "-c", argv[2]],
                capture_output=True,
                text=True,
                check=False,
            )
        except (IndexError, OSError) as exc:
            return f"cannot syntax-check embedded Bash: {exc}"
        if result.returncode != 0:
            return f"embedded Bash does not parse: {result.stderr.strip()}"
    return None


def _validate_predicate(label: str, value: Any, errors: list[str]) -> None:
    if not _is_executable_predicate(value):
        errors.append(f"{label}: invalid predicate")
        return
    syntax_error = _predicate_syntax_error(value)
    if syntax_error:
        errors.append(f"{label}: {syntax_error}")


def _validate_with_owner_contract(task: dict[str, Any], errors: list[str]) -> None:
    """Use #978's owner validator when present; retain an offline fallback before merge."""

    try:
        from limen.intake import validate_intake_contract  # type: ignore[import-not-found]
        from limen.models import Task  # type: ignore[import-not-found]
    except ImportError:
        _validate_predicate(str(task.get("id")), task.get("predicate"), errors)
        if not _is_durable_receipt(task.get("receipt_target")):
            errors.append(f"{task.get('id')}: receipt_target is not durable")
        return
    try:
        validated = Task.model_validate(task)
        validate_intake_contract(validated, is_new=True)
    except Exception as exc:  # noqa: BLE001 - verifier reports the owner contract verbatim
        errors.append(f"{task.get('id')}: typed intake rejected child: {exc}")


def _walk_public_safe(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                errors.append(f"{path}.{key}: sensitive key is forbidden in the tracked receipt")
            _walk_public_safe(child, f"{path}.{key}", errors)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_public_safe(child, f"{path}[{index}]", errors)
        return
    if not isinstance(value, str):
        return
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(value):
            errors.append(f"{path}: matched forbidden {name}")
    for fragment in PRIVATE_PATH_PATTERNS:
        if fragment in value:
            errors.append(f"{path}: contains private/local path fragment {fragment!r}")


def verify_receipt(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    source = payload.get("source") or {}
    if source.get("commit") != SOURCE_COMMIT:
        errors.append(f"source.commit must be {SOURCE_COMMIT}")

    hash_contract = payload.get("hash_contract") or {}
    if hash_contract.get("algorithm") != "sha256":
        errors.append("hash_contract.algorithm must be sha256")
    if hash_contract.get("sort") != "LC_ALL=C bytewise ascending":
        errors.append("hash_contract.sort must be LC_ALL=C bytewise ascending")
    if hash_contract.get("serialization") != "UTF-8 task IDs, one per line, including a trailing newline":
        errors.append("hash_contract.serialization does not name the trailing-newline contract")

    ids = payload.get("frozen_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        errors.append("frozen_ids must be a non-empty string list")
        ids = []
    if ids != sorted(ids):
        errors.append("frozen_ids must already be LC_ALL=C sorted")
    if len(ids) != 52 or len(set(ids)) != 52:
        errors.append(f"frozen_ids must contain 52 unique IDs, got {len(ids)}/{len(set(ids))}")
    actual_hash = hashlib.sha256(_serialized_ids(ids)).hexdigest()
    if actual_hash != EXPECTED_SHA256:
        errors.append(f"frozen ID digest mismatch: {actual_hash}")
    if hash_contract.get("sha256") != EXPECTED_SHA256:
        errors.append("recorded hash_contract.sha256 mismatch")

    prerequisites = payload.get("prerequisites") or {}
    prerequisite_prs = {
        value.get("pr")
        for value in prerequisites.values()
        if isinstance(value, dict) and isinstance(value.get("pr"), int)
    }
    if prerequisite_prs != EXPECTED_PREREQUISITES:
        errors.append(f"prerequisite PR set must be {sorted(EXPECTED_PREREQUISITES)}")
    for name, row in prerequisites.items():
        if not isinstance(row, dict) or row.get("required_state") != "MERGED":
            errors.append(f"prerequisites.{name}: required_state must be MERGED")
            continue
        _validate_predicate(f"prerequisites.{name}", row.get("predicate"), errors)
        if not _is_durable_receipt(row.get("receipt_target")):
            errors.append(f"prerequisites.{name}: invalid receipt_target")

    tasks = payload.get("tasks")
    if not isinstance(tasks, dict):
        errors.append("tasks must be an object keyed by frozen ID")
        tasks = {}
    if set(tasks) != set(ids):
        errors.append("tasks mapping must cover exactly the frozen ID set")
    actions = Counter()
    replacements: set[str] = set()
    for task_id, row in tasks.items():
        if not isinstance(row, dict):
            errors.append(f"{task_id}: task mapping row must be an object")
            continue
        action = row.get("action")
        actions[action] += 1
        if action not in EXPECTED_STATUS_PATCH:
            errors.append(f"{task_id}: unknown action {action!r}")
            continue
        if row.get("status_patch") != EXPECTED_STATUS_PATCH[action]:
            errors.append(f"{task_id}: status_patch does not match action {action}")
        _validate_predicate(task_id, row.get("predicate"), errors)
        if not _is_durable_receipt(row.get("receipt_target")):
            errors.append(f"{task_id}: invalid receipt_target")
        child_ids = row.get("replacement_child_ids")
        if not isinstance(child_ids, list) or any(not isinstance(child, str) for child in child_ids):
            errors.append(f"{task_id}: replacement_child_ids must be a string list")
            continue
        if action == "split" and len(child_ids) not in {2, 3}:
            errors.append(f"{task_id}: split action must name two or three children")
        if action != "split" and child_ids:
            errors.append(f"{task_id}: only split actions may name replacements")
        if action == "split":
            predicate = str(row.get("predicate") or "")
            for needle in ("tasks.yaml", "validate_intake_contract", *child_ids):
                if needle not in predicate:
                    errors.append(f"{task_id}: split archive predicate does not prove {needle}")
        replacements.update(child_ids)
    if dict(actions) != EXPECTED_ACTIONS:
        errors.append(f"action counts mismatch: {dict(actions)}")

    children = payload.get("children")
    if not isinstance(children, list):
        errors.append("children must be a list")
        children = []
    child_ids = [child.get("id") for child in children if isinstance(child, dict)]
    if len(children) != EXPECTED_CHILDREN or len(set(child_ids)) != EXPECTED_CHILDREN:
        errors.append(f"children must contain {EXPECTED_CHILDREN} unique definitions")
    if set(child_ids) != replacements:
        errors.append("children must exactly match the replacement_child_ids union")
    required_child_fields = {
        "id",
        "title",
        "description",
        "repo",
        "type",
        "target_agent",
        "priority",
        "budget_cost",
        "status",
        "labels",
        "urls",
        "context",
        "predicate",
        "receipt_target",
        "depends_on",
        "created",
        "dispatch_log",
    }
    for child in children:
        if not isinstance(child, dict):
            errors.append("child definition must be an object")
            continue
        missing = required_child_fields - set(child)
        if missing:
            errors.append(f"{child.get('id')}: missing child fields {sorted(missing)}")
            continue
        if child.get("status") not in VALID_STATUSES:
            errors.append(f"{child.get('id')}: invalid status {child.get('status')!r}")
        if child.get("budget_cost") != 1:
            errors.append(f"{child.get('id')}: migration children must cost one budget unit")
        if not isinstance(child.get("depends_on"), list) or not isinstance(child.get("dispatch_log"), list):
            errors.append(f"{child.get('id')}: depends_on/dispatch_log must be lists")
        _validate_with_owner_contract(child, errors)

    superseded = tasks.get("GH-organvm-limen-775") or {}
    if (
        superseded.get("action") != "superseded"
        or superseded.get("status_patch") != {"status": "archived"}
        or superseded.get("receipt_target") != "https://github.com/organvm/limen/issues/790"
    ):
        errors.append("GH-organvm-limen-775 must archive to canonical issue #790")
    superseded_predicate = str(superseded.get("predicate") or "")
    for needle in ("775", "NOT_PLANNED", "L-ESTATE-MOUNT-4444J99", "790"):
        if needle not in superseded_predicate:
            errors.append(f"GH-organvm-limen-775 predicate missing {needle}")

    for task_id in ("GH-organvm-limen-793", "GH-organvm-limen-817", "GH-organvm-limen-872"):
        row = tasks.get(task_id) or {}
        predicate = str(row.get("predicate") or "")
        if row.get("action") != "done" or "stateReason" not in predicate or "COMPLETED" not in predicate:
            errors.append(f"{task_id}: done predicate must require stateReason COMPLETED")

    application = payload.get("application_contract") or {}
    if application.get("schema_version") != APPLICATION_SCHEMA:
        errors.append(f"application_contract.schema_version must be {APPLICATION_SCHEMA}")
    if application.get("helper") != APPLICATION_HELPER or not (ROOT / APPLICATION_HELPER).is_file():
        errors.append(f"application_contract.helper must name tracked {APPLICATION_HELPER}")
    if application.get("canonical_verifier") != APPLICATION_VERIFIER:
        errors.append(f"application_contract.canonical_verifier must name {APPLICATION_VERIFIER}")
    if application.get("default_mode") != "dry-run":
        errors.append("application_contract.default_mode must be dry-run")
    if application.get("live_prerequisites") != ["typed_intake", "terminal_discovery_dispositions"]:
        errors.append("application_contract.live_prerequisites must name both merged-PR gates in order")
    identity = application.get("apply_identity") or {}
    if any(identity.get(field) != "required" for field in ("timestamp", "session_id", "agent")):
        errors.append("application_contract.apply_identity must require timestamp, session_id, and agent")
    phases = application.get("phases")
    if not isinstance(phases, list) or len(phases) != 2:
        errors.append("application_contract.phases must contain children then parents")
    else:
        for expected, phase in zip(EXPECTED_APPLICATION_PHASES, phases, strict=True):
            if not isinstance(phase, dict):
                errors.append("application_contract phase must be an object")
                continue
            for key, value in expected.items():
                if phase.get(key) != value:
                    errors.append(f"application_contract.{expected['name']}.{key} must be {value!r}")
        parent_phase = phases[1] if isinstance(phases[1], dict) else {}
        child_phase = phases[0] if isinstance(phases[0], dict) else {}
        if parent_phase.get("requires") != "children completion_gate":
            errors.append("parent application phase must require the child completion gate")
        owner_gate = str(parent_phase.get("owner_state_gate") or "")
        for needle in ("all 52 predicates", "done", "superseded", "split", "normalize", "needs_human"):
            if needle not in owner_gate:
                errors.append(f"parent owner-state gate must prove {needle}")
        child_gate = str(child_phase.get("completion_gate") or "")
        for needle in ("archive", "exact typed", "zero pending", "rejected"):
            if needle not in child_gate:
                errors.append(f"child completion gate must prove {needle}")
    if application.get("rejection_policy") != "fail_closed":
        errors.append("application_contract.rejection_policy must be fail_closed")
    if (
        application.get("batch_admission")
        != "reject_exact_precondition_ticket_on_any_same_task_pending_state_event_regardless_of_timestamp_order"
    ):
        errors.append("application_contract must reject same-task batch races regardless of timestamp order")
    if (
        application.get("publication_failure")
        != "shared_queue_lock_then_remove_only_this_invocation_exact_unconsumed_inbox_tickets"
    ):
        errors.append("application_contract must require exact unconsumed-prefix cleanup on publication failure")
    retry_identity = str(application.get("retry_identity") or "")
    for needle in ("independent_of_timestamp_agent_session", "preserve_first_archived_event_identity"):
        if needle not in retry_identity:
            errors.append(f"application_contract retry identity must prove {needle}")
    if application.get("direct_board_write") != "forbidden":
        errors.append("application_contract must forbid direct board writes")
    if application.get("deterministic_ticket_ids") is not True:
        errors.append("application_contract must require deterministic ticket IDs")

    safety = payload.get("safety") or {}
    if (
        safety.get("board_mutation") != "forbidden"
        or safety.get("ticket_creation") != "forbidden_without_explicit_apply_and_live_gates"
    ):
        errors.append("safety must forbid board mutation and gate ticket creation behind explicit apply")
    _walk_public_safe(payload, "$", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="verify the frozen ask-gate migration receipt")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    try:
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ask-gate-migration: FAIL - cannot read receipt: {exc}")
        return 1
    errors = verify_receipt(payload)
    if errors:
        for error in errors:
            print(f"ask-gate-migration: FAIL - {error}")
        return 1
    print(
        "ask-gate-migration: PASS - 52 frozen tasks, "
        "14 split / 31 normalize / 4 done / 2 needs_human / 1 superseded, 29 children"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
