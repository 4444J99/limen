"""Bounded read-only assessment from a deployment-pinned source snapshot.

The caller owns review and credential provenance. Integrity and REVIEW_READY do
not authorize deployment, acceptance, or a merge.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.assessor_source import MAX_SOURCE_BYTES, AssessorSnapshot


class AssessorExecutionError(ValueError):
    """An assessment is unmeasured; child output and credentials are redacted."""


def execute_assessor(
    snapshot: AssessorSnapshot,
    *,
    credential: str,
    repository: str,
    repository_id: int,
    run_id: int,
    run_attempt: int,
    head_sha: str,
) -> dict:
    """Run immutable bytes once with an explicit credential and no ambient secrets."""
    if (
        not isinstance(snapshot, AssessorSnapshot)
        or not isinstance(snapshot.source, bytes)
        or not 0 < len(snapshot.source) <= MAX_SOURCE_BYTES
        or hashlib.sha256(snapshot.source).hexdigest() != snapshot.script_sha256
        or not isinstance(snapshot.source_commit, str)
        or not re.fullmatch(r"[a-f0-9]{40}", snapshot.source_commit)
        or not isinstance(credential, str)
        or not credential.strip()
        or any(character in credential for character in "\r\n\x00")
        or not isinstance(repository, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or any(type(value) is not int or not 0 < value <= 2**53 - 1 for value in (repository_id, run_id, run_attempt))
        or not isinstance(head_sha, str)
        or not re.fullmatch(r"[a-f0-9]{40}", head_sha)
    ):
        raise AssessorExecutionError("assessor execution input is invalid")
    try:
        with tempfile.TemporaryDirectory(prefix="limen-assessor-") as directory:
            root = Path(directory)
            script = root / "assessor.py"
            script.write_bytes(snapshot.source)
            script.chmod(0o400)
            result = run_bounded_subprocess(
                [
                    sys.executable,
                    "-I",
                    str(script),
                    "--repo",
                    repository,
                    "--completed-run",
                    str(run_id),
                    "--expected-attempt",
                    str(run_attempt),
                    "--expected-head",
                    head_sha,
                ],
                cwd=root,
                timeout_seconds=95,
                stdout_ceiling=65536,
                stderr_ceiling=16384,
                env={"GH_TOKEN": credential, "HOME": directory, "LANG": "C.UTF-8"},
            )

        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate field")
                value[key] = item
            return value

        payload = json.loads(result.stdout, object_pairs_hook=unique_object)
        if not isinstance(payload, dict) or payload.get("automatic_acceptance") is not False:
            raise ValueError("invalid assessment")
        status = payload.get("status")
        reason = payload.get("reason")
        if not isinstance(reason, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", reason):
            raise ValueError("invalid reason")
        # Project known fields only: source output cannot smuggle unrelated data.
        observed = {
            "status": status,
            "reason": reason,
            "automatic_acceptance": False,
            "source_commit": snapshot.source_commit,
            "script_sha256": snapshot.script_sha256,
        }
        if status == "HOLD" and result.returncode == 2:
            return observed
        if (
            status != "REVIEW_READY"
            or result.returncode != 0
            or type(payload.get("repository_id")) is not int
            or payload["repository_id"] != repository_id
            or type(payload.get("run_id")) is not int
            or payload["run_id"] != run_id
            or type(payload.get("run_attempt")) is not int
            or payload["run_attempt"] != run_attempt
            or payload.get("head") != head_sha
            or type(payload.get("pr")) is not int
            or payload["pr"] <= 0
            or not isinstance(payload.get("base_sha"), str)
            or not re.fullmatch(r"[a-f0-9]{40}", payload["base_sha"])
        ):
            raise ValueError("assessment binding mismatch")
        return {
            **observed,
            "repository": repository,
            "repository_id": repository_id,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "head_sha": head_sha,
            "base_sha": payload["base_sha"],
            "pr": payload["pr"],
        }
    except (OSError, ValueError, TypeError, RecursionError, BoundedSubprocessError):
        raise AssessorExecutionError("assessor execution is unmeasured") from None
