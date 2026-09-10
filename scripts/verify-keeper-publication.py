#!/usr/bin/env python3
"""Bind two real acceptance amendments to one deployed keeper and publication history.

This is an explicit mutation canary. It never logs in, writes Git refs, changes task
status, retries a submitted mutation, or exposes private task context in its receipt.
An interrupted receipt must be reconciled with its keeper run before another run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))

from limen.conduct.client import HttpConductClient, client_from_env  # noqa: E402
from limen.conduct.models import WorkPacketV1  # noqa: E402

REPOSITORY = "4444J99/limen"
PUBLICATION_REF = "tabularius/board-projection"
SHA = re.compile(r"[0-9a-f]{40}")


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def persist(path, receipt):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".keeper-receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def github(path, *, missing_ok=False):
    result = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{path}"], capture_output=True, text=True, timeout=30)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub returned no inspectable JSON receipt") from exc
    if result.returncode:
        if missing_ok and str(value.get("status")) == "404":
            return None
        raise ValueError("GitHub read failed; no publication proof")
    return value


def runtime(client, expected, deployment=None):
    capabilities = client.capabilities()
    identity = capabilities.get("runtime_identity") or {}
    if identity.get("git_sha") != expected or not identity.get("deployment_id"):
        raise ValueError("deployed keeper does not match the captured merged SHA")
    if deployment and identity["deployment_id"] != deployment:
        raise ValueError("deployment changed during publication verification")
    return capabilities, identity


def task_from_board(client, task_id):
    rows = [task for task in client.private_board().get("tasks", []) if task.get("id") == task_id]
    if len(rows) != 1 or not rows[0].get("updated"):
        raise ValueError("acceptance task must have one canonical revision")
    return rows[0]


def verify(client, expected_sha, session_id, updates, receipt_path, *, github_read=github):
    if not SHA.fullmatch(expected_sha):
        raise ValueError("expected SHA must be one captured 40-character merged commit")
    if Path(receipt_path).exists():
        raise ValueError("receipt already exists; reconcile its keeper evidence before another run")
    if not isinstance(updates, list) or len(updates) != 2:
        raise ValueError("exactly two legitimate acceptance amendments are required")
    for update in updates:
        if (
            not isinstance(update, dict)
            or set(update) != {"task_id", "amendment"}
            or not isinstance(update["task_id"], str)
            or not isinstance(update["amendment"], str)
            or not 20 <= len(update["amendment"].strip()) <= 4000
        ):
            raise ValueError("invalid bounded acceptance amendment")
    if updates[0] == updates[1]:
        raise ValueError("duplicate amendment is not a second source intent")
    capabilities, identity = runtime(client, expected_sha)
    sessions = [s for s in capabilities.get("sessions", []) if s.get("session_id") == session_id]
    if len(sessions) != 1 or not sessions[0].get("healthy") or "task-submit" not in sessions[0]["capabilities"]:
        raise ValueError("existing native session must be healthy and registered for task-submit")
    executor = sessions[0]["identity"]
    ref = github_read(f"git/ref/heads/{PUBLICATION_REF}", missing_ok=True)
    receipt = {
        "schema_version": "limen.keeper_publication_verification.v1",
        "repository": REPOSITORY,
        "runtime_identity": identity,
        "publication_ref": PUBLICATION_REF,
        "initial_ref_missing": ref is None,
        "initial_ref_sha": None if ref is None else ref.get("object", {}).get("sha"),
        "status": "in_progress",
        "mutations": [],
        "manual_ref_writes": 0,
    }
    Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
    reservation = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(reservation)
    persist(receipt_path, receipt)
    try:
        for index, update in enumerate(updates, 1):
            runtime(client, expected_sha, identity["deployment_id"])
            task = task_from_board(client, update["task_id"])
            amendment = update["amendment"].strip()
            context = task.get("context", "")
            if not isinstance(context, str) or amendment in context:
                raise ValueError("amendment is already recorded or task context is malformed")
            amended = context + "\n\n" + amendment
            key = "publication-" + digest(expected_sha + session_id + str(index) + task["updated"] + amendment)[:40]
            packet = WorkPacketV1(
                work_id=key,
                work_key=key,
                intent={
                    "kind": "task.mutate",
                    "task_id": task["id"],
                    "expected_status": task["status"],
                    "expected_revision": task["updated"],
                    "patch": {"context": amended},
                    "log": {
                        "status": task["status"],
                        "agent": executor["agent"],
                        "session_id": session_id,
                        "output": "Acceptance amendment recorded; delivery remains subject to its original predicate.",
                    },
                },
                execution={"adapter": "tabularius", "projection": "tasks.yaml", "observed_heads": {}},
                initiator=executor,
                conductor=executor,
                preferred_agent="tabularius",
                required_capabilities=["board-write"],
                resource_claims=[{"key": "task/" + task["id"], "mode": "exclusive"}],
                predicate="python3 scripts/validate-task-board.py --tasks tasks.yaml",
                receipt_target=f"git:{REPOSITORY}:tasks.yaml#{task['id']}",
                authority={
                    "actions": ["task.mutate"],
                    "repositories": [REPOSITORY],
                    "path_prefixes": ["tasks.yaml"],
                    "may_delegate": False,
                },
                deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
                spend={"limit": 0},
                effect="write",
                task_id=task["id"],
            )
            evidence = {
                "sequence": index,
                "task_id": task["id"],
                "work_id": key,
                "expected_revision": task["updated"],
                "retained_status": task["status"],
                "amendment_sha256": digest(amendment),
                "status": "submission_started",
            }
            receipt["mutations"].append(evidence)
            persist(receipt_path, receipt)
            result = client.submit(packet)  # One attempt. Never resubmit to manufacture proof.
            evidence["run_id"] = result.get("run_id")
            projections = result.get("projection_receipts") or []
            if len(projections) != 1:
                raise ValueError("mutation has no unique keeper publication receipt")
            projection = projections[0]
            publication = projection.get("publication") or {}
            published_sha = publication.get("sha", "")
            if (
                projection.get("status") != "committed"
                or projection.get("mode") != "private-canonical"
                or publication.get("status") != "committed"
                or publication.get("mode") != "public-aggregate"
                or not SHA.fullmatch(published_sha)
                or projection.get("task", {}).get("id") != task["id"]
            ):
                raise ValueError("mutation lacks committed private and public custody")
            fresh = task_from_board(client, task["id"])
            if (
                fresh.get("context") != amended
                or fresh.get("status") != task["status"]
                or fresh["updated"] == task["updated"]
            ):
                raise ValueError("fresh canonical task does not prove the exact status-preserving amendment")
            runtime(client, expected_sha, identity["deployment_id"])
            evidence.update(
                {
                    "status": "verified",
                    "observed_revision": fresh["updated"],
                    "event_id": projection.get("event_id"),
                    "publication_sha": published_sha,
                }
            )
            persist(receipt_path, receipt)
        first, second = (item["publication_sha"] for item in receipt["mutations"])
        if first == second:
            raise ValueError("two publications must have distinct commit receipts")
        compare = github_read(f"compare/{first}...{second}")
        if compare.get("status") != "ahead" or compare.get("merge_base_commit", {}).get("sha") != first:
            raise ValueError("second publication does not preserve the first publication history")
        receipt["status"] = "passed"
        receipt["verified_at"] = datetime.now(timezone.utc).isoformat()
        persist(receipt_path, receipt)
        return receipt
    except Exception as exc:
        receipt["status"] = "incomplete"
        receipt["failure_type"] = type(exc).__name__
        persist(receipt_path, receipt)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-runtime-sha", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--updates", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="submit exactly two real task acceptance amendments")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required for this explicit canonical mutation canary")
    client = client_from_env()
    if not isinstance(client, HttpConductClient):
        parser.error("authenticated deployed keeper is required; local fixtures are not live proof")
    try:
        result = verify(
            client, args.expected_runtime_sha, args.session_id, json.loads(args.updates.read_text()), args.receipt
        )
    except Exception as exc:
        print(
            f"keeper publication verification incomplete: {type(exc).__name__}; inspect the bounded receipt",
            file=sys.stderr,
        )
        return 77
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
