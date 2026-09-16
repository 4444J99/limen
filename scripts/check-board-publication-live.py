#!/usr/bin/env python3
"""Read-only, counts-only acceptance of the current keeper/public board boundary."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.bounded_subprocess import run_bounded_subprocess  # noqa: E402

REPOSITORY = "4444J99/limen"
SHA = re.compile(r"[0-9a-f]{40}")


def github(path):
    result = run_bounded_subprocess(
        ["gh", "api", f"repos/{REPOSITORY}{path}"],
        cwd=ROOT,
        timeout_seconds=20,
        stdout_ceiling=2_097_152,
        stderr_ceiling=16384,
    )
    if result.returncode:
        raise ValueError("github_read_unavailable")
    return json.loads(result.stdout)


def private_counts(board):
    if not isinstance(board, dict) or board.get("schema_version") != "limen.private_board.v1":
        raise ValueError("private_board_schema_unmeasured")
    rows = board.get("tasks")
    if not isinstance(rows, list):
        raise ValueError("private_board_rows_unmeasured")
    spec = importlib.util.spec_from_file_location("board_validator", ROOT / "scripts/validate-task-board.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    statuses = validator.load_valid_statuses()
    priorities = {"critical", "high", "medium", "low", "backlog"}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("private_row_unmeasured")
        identity = row.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError("private_identity_unmeasured")
        seen.add(identity)
        if not isinstance(row.get("status"), str) or row["status"] not in statuses:
            raise ValueError("private_status_unmeasured")
        if not isinstance(row.get("priority"), str) or row["priority"] not in priorities:
            raise ValueError("private_priority_unmeasured")
    by_status = dict(Counter(row["status"] for row in rows))
    completed = by_status.get("done", 0) + by_status.get("archived", 0)
    return {
        "total": len(rows),
        "completed": completed,
        "active": by_status.get("dispatched", 0) + by_status.get("in_progress", 0),
        "completion_rate": round(completed / max(1, len(rows)), 3),
        "by_status": by_status,
        "by_priority": dict(Counter(row["priority"] for row in rows)),
    }


def observe(client, expected_sha, *, read=github):
    """Only GET interfaces; changed sources yield unmeasured, never an implicit retry."""
    if not isinstance(expected_sha, str) or not SHA.fullmatch(expected_sha):
        raise ValueError("expected_runtime_sha_required")
    repository = read("")
    if repository.get("full_name") != REPOSITORY or type(repository.get("id")) is not int:
        raise ValueError("repository_identity_unmeasured")
    branch = repository.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise ValueError("default_branch_unmeasured")
    ref_path = "/git/ref/heads/" + quote(branch, safe="")
    head = read(ref_path)["object"]["sha"]
    if not isinstance(head, str) or not SHA.fullmatch(head):
        raise ValueError("default_head_unmeasured")
    runtime = client.capabilities().get("runtime_identity")
    if not isinstance(runtime, dict) or runtime.get("git_sha") != expected_sha or not runtime.get("deployment_id"):
        raise ValueError("runtime_identity_unmeasured")
    ancestry = read(f"/compare/{expected_sha}...{head}")
    if ancestry.get("status") not in ("ahead", "identical"):
        raise ValueError("runtime_source_not_on_default")
    before = client.private_board()
    counts = private_counts(before)
    content = read(f"/contents/tasks.yaml?ref={head}")
    if content.get("encoding") != "base64" or content.get("type") != "file":
        raise ValueError("public_board_content_unmeasured")
    public = yaml.safe_load(base64.b64decode(content["content"]).decode("utf-8"))
    generated = public["portal"]["public_projection"]["generated_at"]
    if not isinstance(generated, str):
        raise ValueError("public_timestamp_unmeasured")
    timestamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
        raise ValueError("public_timestamp_unmeasured")
    expected = {
        "schema_version": "limen.public_board_projection.v1",
        "portal": {
            "name": "Universal Task Intake",
            "description": "Aggregate operational health; authenticated board details are private.",
            "public_projection": {
                "schema_version": "limen.public_board_projection.v1",
                "generated_at": generated,
                **counts,
            },
        },
        "tasks": [],
    }
    rate = public["portal"]["public_projection"].get("completion_rate")
    if type(rate) in (int, float) and rate == counts["completion_rate"]:
        expected["portal"]["public_projection"]["completion_rate"] = rate
    # JSON distinguishes booleans from integer counts and rejects additional public fields.
    parity = json.dumps(public, sort_keys=True) == json.dumps(expected, sort_keys=True)
    after = client.private_board()
    private_counts(after)
    after_runtime = client.capabilities().get("runtime_identity")
    after_head = read(ref_path)["object"]["sha"]
    after_repository = read("")
    if (
        before != after
        or runtime != after_runtime
        or head != after_head
        or any(repository.get(k) != after_repository.get(k) for k in ("id", "full_name", "default_branch"))
    ):
        raise ValueError("source_changed_during_observation")
    return {
        "schema": "limen.board_publication_acceptance.v1",
        "status": "passed" if parity else "failed",
        "reason": "current_counts_only_parity" if parity else "public_projection_mismatch",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "repository_id": repository["id"],
        "default_sha": head,
        "runtime_sha": expected_sha,
        "deployment_id": runtime["deployment_id"],
        "public_blob_sha": content.get("sha"),
        "counts": counts,
        "scope": "Current default/public and authenticated private snapshot parity; no task mutation or lifecycle discharge.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-runtime-sha", required=True)
    args = parser.parse_args()
    try:
        from limen.dispatch import _load_limen_env
        from limen.conduct.client import HttpConductClient, client_from_env

        _load_limen_env()
        client = client_from_env()
        if not isinstance(client, HttpConductClient):
            raise ValueError("authenticated_remote_keeper_required")
        client.timeout = 10
        result = observe(client, args.expected_runtime_sha)
    except Exception:
        # Provider errors and malformed private values must never reach public output.
        result = {
            "schema": "limen.board_publication_acceptance.v1",
            "status": "unmeasured",
            "reason": "required_source_unavailable_malformed_or_changed",
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return {"passed": 0, "failed": 1, "unmeasured": 77}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
