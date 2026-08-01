"""Bounded heartbeat adapter for the canonical institutional campaign supervisor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.campaign_relay import CampaignRelayError, discover_ready_relay
from limen.conduct.supervisor import RESULT_SCHEMA, CampaignSupervisorError, exact_remote_main
from limen.workstream_contract import (
    RECEIPT_MODULES,
    RECEIPT_SCHEMA,
    ContractError,
    validate_contract,
    validate_receipt_metadata,
)

WAKE_SCHEMA = "limen.campaign_wake.v1"
BOUNDARIES = frozenset({"continue", "switch", "wait_relay", "invalid", "settled"})


class CampaignWakeError(RuntimeError):
    """A bounded wake failure that must not fall back to direct provider launch."""


class NoActiveCampaign(CampaignWakeError):
    """The tracked campaign registry has no admitted capsule with remaining runway."""


def _git(root: Path, *args: str) -> str:
    try:
        result = run_bounded_subprocess(
            ["git", *args],
            cwd=root,
            timeout_seconds=10,
            stdout_ceiling=65_536,
            stderr_ceiling=65_536,
        )
    except BoundedSubprocessError as exc:
        if exc.kind == "output":
            raise CampaignWakeError("campaign wake Git output exceeded its bounded ceiling") from exc
        if exc.kind == "timeout":
            raise CampaignWakeError("campaign wake Git probe exceeded its deadline") from exc
        raise CampaignWakeError("campaign wake Git probe is unavailable") from exc
    if result.returncode != 0:
        raise CampaignWakeError(f"campaign wake Git probe failed with exit {result.returncode}")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CampaignWakeError("campaign wake Git probe returned invalid text") from exc


def _tracked_receipts(root: Path) -> tuple[Path, ...]:
    rows = _git(root, "ls-files", "-z", "--", "docs/continuations").split("\0")
    receipts: list[Path] = []
    for row in rows:
        if not row:
            continue
        relative = PurePosixPath(row)
        if (
            len(relative.parts) == 4
            and relative.parts[:2] == ("docs", "continuations")
            and relative.name == "workstream.json"
        ):
            receipts.append(root / Path(*relative.parts))
    return tuple(sorted(receipts))


def discover_active_capsule(
    root: Path,
    *,
    workstream: str,
    now_epoch: int | None = None,
) -> tuple[Path, int]:
    root = root.resolve()
    now = int(time.time()) if now_epoch is None else now_epoch
    active: list[tuple[int, int, str, Path]] = []
    for path in _tracked_receipts(root):
        if path.is_symlink() or not path.is_file():
            raise CampaignWakeError(f"tracked continuation receipt is not a real file: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CampaignWakeError(f"tracked continuation receipt is unreadable: {path.name}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("workstream") != workstream:
            continue
        if payload.get("schema") != RECEIPT_SCHEMA:
            raise CampaignWakeError(f"{path.parent.name}: unsupported campaign receipt schema")
        try:
            slug, _branch, normalized_workstream = validate_receipt_metadata(
                slug=str(payload.get("slug") or ""),
                branch=str(payload.get("branch") or ""),
                workstream=str(payload.get("workstream") or ""),
            )
            contract = validate_contract(payload.get("contract"))
        except ContractError as exc:
            raise CampaignWakeError(f"{path.parent.name}: invalid campaign receipt: {exc}") from exc
        private = payload.get("private_capsule")
        if (
            normalized_workstream != workstream
            or slug != path.parent.name
            or not isinstance(private, dict)
            or private.get("content") != "redacted"
            or private.get("modules") != list(RECEIPT_MODULES)
        ):
            raise CampaignWakeError(f"{path.parent.name}: campaign receipt custody metadata is invalid")
        runway = contract["runway"]
        started = runway.get("started_epoch")
        deadline = runway.get("deadline_epoch")
        if (
            isinstance(started, bool)
            or not isinstance(started, int)
            or isinstance(deadline, bool)
            or not isinstance(deadline, int)
        ):
            raise CampaignWakeError(f"{slug}: campaign capsule has not been admitted")
        if deadline > now:
            active.append((started, deadline, slug, path))
    if not active:
        raise NoActiveCampaign(f"no active tracked capsule for workstream {workstream}")
    _started, deadline, _slug, selected = max(active)
    return selected, deadline - now


def wake_campaign(
    root: Path,
    *,
    workstream: str = "institutional-omega",
    now_epoch: int | None = None,
    timeout_seconds: int = 300,
    environ: Mapping[str, str] | None = None,
    preflight: Callable[[Path], dict[str, str]] = exact_remote_main,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    if not 300 <= timeout_seconds <= 7200:
        raise CampaignWakeError("campaign wake timeout must be between 300 and 7200 seconds")
    wake_deadline_monotonic_ns = time.monotonic_ns() + timeout_seconds * 1_000_000_000
    wake_deadline_monotonic = wake_deadline_monotonic_ns / 1_000_000_000
    root = root.resolve()
    env = dict(os.environ if environ is None else environ)
    agent = env.get("LIMEN_AGENT", "").strip()
    session_id = (env.get("LIMEN_SESSION_ID") or env.get("LIMEN_RUN_ID") or "").strip()
    if not agent or not session_id:
        raise CampaignWakeError("campaign wake requires LIMEN_AGENT and LIMEN_SESSION_ID")
    immutable_commit: str | None = None
    immutable_base: str | None = None
    immutable_branch: str | None = None
    try:
        capsule, remaining = discover_active_capsule(
            root,
            workstream=workstream,
            now_epoch=now_epoch,
        )
        capsule_label = str(capsule.relative_to(root))
    except NoActiveCampaign as active_error:
        try:
            ready = discover_ready_relay(
                root,
                workstream=workstream,
                now_epoch=now_epoch,
                deadline_monotonic=wake_deadline_monotonic,
            )
        except CampaignRelayError as exc:
            raise NoActiveCampaign(f"{active_error}; ready successor unavailable: {exc.public_reason}") from exc
        capsule = Path(ready.capsule_path)
        remaining = ready.remaining_seconds
        immutable_commit = ready.receipt.publication_commit
        immutable_base = ready.receipt.publication_parent
        immutable_branch = ready.receipt.successor_branch
        if immutable_commit is None or immutable_base is None:
            raise CampaignWakeError("ready successor has no immutable publication commit and base") from active_error
        capsule_label = f"git:{immutable_commit}:{ready.capsule_path}"
    try:
        git_state = preflight(root)
    except CampaignSupervisorError as exc:
        raise CampaignWakeError(f"campaign preflight failed: {exc}") from exc
    head = git_state.get("head") if isinstance(git_state, dict) else None
    if not isinstance(head, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", head):
        raise CampaignWakeError("campaign preflight returned no exact head")
    command = [
        sys.executable,
        "-m",
        "limen",
        "conduct",
        "campaign",
        "run",
    ]
    if immutable_commit is None:
        command.extend(["--capsule", str(capsule)])
    else:
        assert immutable_branch is not None
        assert immutable_base is not None
        command.extend(
            [
                "--capsule-commit",
                immutable_commit,
                "--capsule-base",
                immutable_base,
                "--capsule-path",
                capsule.as_posix(),
                "--capsule-branch",
                immutable_branch,
            ]
        )
    command.extend(
        [
            "--terminal-predicate",
            "omega",
            "--agent",
            agent,
            "--session-id",
            session_id,
            "--evaluation-timeout",
            str(timeout_seconds),
            "--wake-deadline-monotonic-ns",
            str(wake_deadline_monotonic_ns),
        ]
    )
    runner_timeout_seconds = (wake_deadline_monotonic_ns - time.monotonic_ns()) / 1_000_000_000
    if runner_timeout_seconds <= 0:
        raise CampaignWakeError("campaign wake budget expired before the supervisor could start")
    if runner is None:
        try:
            bounded = run_bounded_subprocess(
                command,
                cwd=root,
                env=env,
                timeout_seconds=runner_timeout_seconds,
                stdout_ceiling=65_536,
                stderr_ceiling=65_536,
            )
        except BoundedSubprocessError as exc:
            if exc.kind == "timeout":
                raise CampaignWakeError("campaign supervisor exceeded the heartbeat wake timeout") from exc
            if exc.kind == "output":
                raise CampaignWakeError("campaign supervisor output exceeded the heartbeat ceiling") from exc
            raise CampaignWakeError("campaign supervisor could not start") from exc
        try:
            result = subprocess.CompletedProcess(
                command,
                bounded.returncode,
                bounded.stdout.decode("utf-8"),
                bounded.stderr.decode("utf-8"),
            )
        except UnicodeDecodeError as exc:
            raise CampaignWakeError("campaign supervisor returned non-text output") from exc
    else:
        try:
            result = runner(
                command,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=runner_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CampaignWakeError("campaign supervisor exceeded the heartbeat wake timeout") from exc
        except OSError as exc:
            raise CampaignWakeError(f"campaign supervisor could not start: {exc}") from exc
    if not isinstance(result.stdout, str) or not isinstance(result.stderr, str):
        raise CampaignWakeError("campaign supervisor returned non-text output")
    if len(result.stdout.encode("utf-8")) > 65_536 or len(result.stderr.encode("utf-8")) > 65_536:
        raise CampaignWakeError("campaign supervisor output exceeded the heartbeat ceiling")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:1000]
        raise CampaignWakeError(f"campaign supervisor returned invalid JSON: {detail}") from exc
    boundary = payload.get("boundary") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != RESULT_SCHEMA
        or not isinstance(boundary, str)
        or boundary not in BOUNDARIES
        or (result.returncode == 0) != (boundary != "invalid")
    ):
        raise CampaignWakeError("campaign supervisor exit and boundary receipt disagree")
    if boundary != "invalid" and payload.get("exact_head") != head:
        raise CampaignWakeError("campaign supervisor exact head differs from heartbeat preflight")
    return {
        "schema": WAKE_SCHEMA,
        "boundary": boundary,
        "capsule": capsule_label,
        "exact_head": head,
        "invoked": True,
        "remaining_seconds": remaining,
        "supervisor": payload,
        "workstream": workstream,
    }
