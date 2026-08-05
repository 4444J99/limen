"""Canonical, keeper-backed supervisor for one finite institutional campaign epoch."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import rfc8785

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.campaign_relay import (
    RelayLaunch,
    RelayReservation,
    launch_reserved_relay,
    relay_boundary_projection,
    reserve_relay,
)
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    CampaignPacketV1,
    FanoutBoundsV1,
    RetryPolicyV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.omega_remediation import (
    OmegaRemediationError,
    OmegaRemediationV1,
    annotate_omega_stamp,
    load_omega_remediations,
)
from limen.work_loan import WorkLoanV1
from limen.workstream_contract import (
    RECEIPT_MODULES,
    RECEIPT_SCHEMA,
    ContractError,
    validate_contract,
    validate_receipt_metadata,
)

RESULT_SCHEMA = "limen.campaign_supervisor_result.v1"
T_MINUS_SECONDS = 30 * 60
_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_CAPSULE_BLOB_CEILING = 262_144
_GIT_TIMEOUT_SECONDS = 10
_GIT_OUTPUT_CEILING = 65_536
_RELAY_OUTER_MARGIN_SECONDS = 180
_RELAY_STARTUP_CEILING_SECONDS = 120


class CampaignSupervisorError(RuntimeError):
    """One fail-closed campaign boundary that is safe to render to an operator."""


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _bounded_submission_summary(submission: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        key: str(submission[key])[:512]
        for key in ("schema_version", "status", "work_id")
        if submission.get(key) is not None
    }
    conflicts = submission.get("conflicts")
    if isinstance(conflicts, list):
        summary["conflicts"] = [str(conflict)[:512] for conflict in conflicts[:32]]
    return summary


def _missing_capability_sets(
    capabilities: dict[str, Any],
    packets: tuple[WorkPacketV1, ...],
) -> list[list[str]]:
    if capabilities.get("schema_version") != "limen.conduct_capabilities.v1":
        raise CampaignSupervisorError("keeper capabilities response has an unsupported schema")
    sessions = capabilities.get("sessions")
    if not isinstance(sessions, list):
        raise CampaignSupervisorError("keeper capabilities response has no session catalog")
    available: list[frozenset[str]] = []
    for raw in sessions:
        if not isinstance(raw, dict):
            raise CampaignSupervisorError("keeper capability catalog contains a non-object session")
        raw_capabilities = raw.get("capabilities")
        concurrency = raw.get("concurrency")
        active_leases = raw.get("active_leases")
        if (
            not isinstance(raw_capabilities, list)
            or any(not isinstance(capability, str) for capability in raw_capabilities)
            or isinstance(concurrency, bool)
            or not isinstance(concurrency, int)
            or concurrency < 1
            or isinstance(active_leases, bool)
            or not isinstance(active_leases, int)
            or active_leases < 0
        ):
            raise CampaignSupervisorError("keeper capability catalog contains an invalid session")
        if raw.get("healthy") is True and raw.get("accepting_work") is True and active_leases < concurrency:
            available.append(frozenset(raw_capabilities))
    required = {packet.required_capabilities for packet in packets}
    return [
        sorted(requirement)
        for requirement in sorted(required, key=lambda candidate: tuple(sorted(candidate)))
        if not any(requirement <= candidate for candidate in available)
    ]


def _git(root: Path, *args: str) -> str:
    try:
        result = run_bounded_subprocess(
            ["git", *args],
            cwd=root,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
            stdout_ceiling=_GIT_OUTPUT_CEILING,
            stderr_ceiling=_GIT_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        raise CampaignSupervisorError("bounded campaign Git probe is unavailable") from exc
    if result.returncode != 0:
        raise CampaignSupervisorError("bounded campaign Git probe failed")
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CampaignSupervisorError("bounded campaign Git probe returned invalid text") from exc


def _git_succeeds(root: Path, *args: str) -> bool:
    try:
        result = run_bounded_subprocess(
            ["git", *args],
            cwd=root,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
            stdout_ceiling=_GIT_OUTPUT_CEILING,
            stderr_ceiling=_GIT_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        raise CampaignSupervisorError("bounded campaign Git probe is unavailable") from exc
    return result.returncode == 0


def exact_remote_main(root: Path) -> dict[str, str]:
    root = root.resolve()
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    remote_rows = _git(root, "ls-remote", "--symref", "origin", "HEAD").splitlines()
    symrefs = [row.split() for row in remote_rows if row.startswith("ref:")]
    heads = [row.split() for row in remote_rows if not row.startswith("ref:")]
    if (
        len(symrefs) != 1
        or len(symrefs[0]) != 3
        or symrefs[0][0] != "ref:"
        or not symrefs[0][1].startswith("refs/heads/")
        or symrefs[0][2] != "HEAD"
        or len(heads) != 1
        or len(heads[0]) != 2
        or heads[0][1] != "HEAD"
    ):
        raise CampaignSupervisorError("remote default branch did not resolve to one symbolic ref")
    remote_ref = symrefs[0][1]
    remote = heads[0][0]
    if not _SHA_RE.fullmatch(head) or not _SHA_RE.fullmatch(remote):
        raise CampaignSupervisorError("local or remote default-branch identity is malformed")
    if head != remote:
        raise CampaignSupervisorError(f"campaign checkout is not exact remote default: head={head} remote={remote}")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise CampaignSupervisorError("campaign checkout is not clean")
    return {
        "head": head,
        "remote_default": remote,
        "remote_default_ref": remote_ref,
        "tree": tree,
    }


def _validate_capsule_payload(
    payload: Any,
    *,
    now_epoch: int | None,
) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict) or set(payload) != {
        "branch",
        "contract",
        "private_capsule",
        "schema",
        "slug",
        "workstream",
    }:
        raise CampaignSupervisorError("campaign capsule receipt has unknown or missing fields")
    if payload.get("schema") != RECEIPT_SCHEMA:
        raise CampaignSupervisorError("campaign capsule receipt schema is unsupported")
    try:
        validate_receipt_metadata(
            slug=str(payload.get("slug") or ""),
            branch=str(payload.get("branch") or ""),
            workstream=str(payload.get("workstream") or ""),
        )
        contract = validate_contract(payload.get("contract"))
    except ContractError as exc:
        raise CampaignSupervisorError(f"campaign capsule receipt is invalid: {exc}") from exc
    private = payload.get("private_capsule")
    if (
        not isinstance(private, dict)
        or private.get("content") != "redacted"
        or private.get("modules") != list(RECEIPT_MODULES)
    ):
        raise CampaignSupervisorError("campaign capsule receipt does not preserve the redacted module contract")
    runway = contract["runway"]
    deadline = runway.get("deadline_epoch")
    started = runway.get("started_epoch")
    now = int(time.time()) if now_epoch is None else now_epoch
    if (
        isinstance(started, bool)
        or not isinstance(started, int)
        or isinstance(deadline, bool)
        or not isinstance(deadline, int)
    ):
        raise CampaignSupervisorError("campaign capsule has not been admitted")
    remaining = deadline - now
    if remaining <= 0:
        raise CampaignSupervisorError("campaign capsule runway has expired")
    return payload, remaining


def load_capsule_receipt(
    path: Path,
    *,
    root: Path,
    now_epoch: int | None = None,
) -> tuple[dict[str, Any], int]:
    root = root.resolve()
    if path.is_symlink():
        raise CampaignSupervisorError("campaign capsule receipt must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CampaignSupervisorError("campaign capsule receipt must be a real file inside the repository") from exc
    if not resolved.is_file():
        raise CampaignSupervisorError("campaign capsule receipt must be a real file")
    _git(root, "ls-files", "--error-unmatch", "--", relative.as_posix())
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignSupervisorError(f"campaign capsule receipt is unreadable: {exc}") from exc
    return _validate_capsule_payload(payload, now_epoch=now_epoch)


def load_capsule_receipt_ref(
    *,
    root: Path,
    commit: str,
    base: str,
    path: str,
    branch: str,
    now_epoch: int | None = None,
) -> tuple[dict[str, Any], int]:
    """Read one admitted capsule from an immutable commit without changing the checkout."""

    root = root.resolve()
    if not _SHA_RE.fullmatch(commit) or not _SHA_RE.fullmatch(base):
        raise CampaignSupervisorError("campaign capsule commit and base must be exact lowercase Git object ids")
    relative = PurePosixPath(path)
    if (
        len(relative.parts) != 4
        or relative.parts[:2] != ("docs", "continuations")
        or relative.name != "workstream.json"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise CampaignSupervisorError("campaign capsule Git path is not canonical")
    if not re.fullmatch(r"work/[a-z0-9][a-z0-9._-]{0,63}", branch):
        raise CampaignSupervisorError("campaign capsule topic branch is invalid")
    receipt_ref = f"refs/heads/limen-relay/capsule/{commit}"
    receipt_rows = _git(root, "ls-remote", "origin", receipt_ref).splitlines()
    if receipt_rows != [f"{commit}\t{receipt_ref}"]:
        raise CampaignSupervisorError("campaign capsule commit is not held by its immutable receipt ref")
    if not _git_succeeds(
        root,
        "fetch",
        "--no-tags",
        "--quiet",
        "--no-write-fetch-head",
        "origin",
        commit,
    ):
        raise CampaignSupervisorError("campaign capsule commit could not be loaded immutably")
    if (
        _git(root, "rev-parse", f"{commit}^{{commit}}") != commit
        or _git(root, "rev-parse", f"{base}^{{commit}}") != base
    ):
        raise CampaignSupervisorError("campaign capsule commit did not resolve immutably")
    parent_row = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
    if parent_row != [commit, base]:
        raise CampaignSupervisorError(
            "campaign capsule commit is not one single-parent publication on its expected base"
        )
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        base,
        commit,
    ).splitlines()
    if changed != [relative.as_posix()]:
        raise CampaignSupervisorError("campaign capsule commit is not an exact receipt-only publication")
    try:
        blob = _git(root, "rev-parse", f"{commit}:{relative.as_posix()}")
        blob_size = int(_git(root, "cat-file", "-s", blob))
    except ValueError as exc:
        raise CampaignSupervisorError("campaign capsule Git blob size is invalid") from exc
    if not _SHA_RE.fullmatch(blob) or not 0 < blob_size <= _CAPSULE_BLOB_CEILING:
        raise CampaignSupervisorError("campaign capsule Git blob is invalid or oversized")
    try:
        result = run_bounded_subprocess(
            ["git", "cat-file", "blob", blob],
            cwd=root,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
            stdout_ceiling=_CAPSULE_BLOB_CEILING,
            stderr_ceiling=_GIT_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        raise CampaignSupervisorError("campaign capsule Git blob could not be read within its deadline") from exc
    if result.returncode != 0 or len(result.stdout) != blob_size:
        raise CampaignSupervisorError("campaign capsule Git blob could not be read exactly")
    try:
        payload = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignSupervisorError("campaign capsule Git blob is invalid JSON") from exc
    receipt, remaining = _validate_capsule_payload(payload, now_epoch=now_epoch)
    if (
        receipt.get("branch") != branch
        or relative.parts[2] != receipt.get("slug")
        or branch != f"work/{receipt.get('slug')}"
    ):
        raise CampaignSupervisorError("campaign capsule immutable ref disagrees with its receipt identity")
    branch_ref = f"refs/heads/{branch}"
    branch_rows = _git(root, "ls-remote", "origin", branch_ref).splitlines()
    if len(branch_rows) != 1:
        raise CampaignSupervisorError("campaign capsule topic branch is missing or ambiguous")
    branch_fields = branch_rows[0].split("\t")
    if len(branch_fields) != 2 or branch_fields[1] != branch_ref or not _SHA_RE.fullmatch(branch_fields[0]):
        raise CampaignSupervisorError("campaign capsule topic branch identity is malformed")
    branch_head = branch_fields[0]
    if branch_head != commit:
        if not _git_succeeds(
            root,
            "fetch",
            "--no-tags",
            "--quiet",
            "--no-write-fetch-head",
            "origin",
            branch_head,
        ):
            raise CampaignSupervisorError("campaign capsule topic head could not be loaded immutably")
        if not _git_succeeds(root, "merge-base", "--is-ancestor", commit, branch_head):
            raise CampaignSupervisorError("campaign capsule commit is not reachable from its topic branch")
    return receipt, remaining


def _fresh_omega_evaluation(root: Path, timeout_seconds: int) -> tuple[int, dict[str, Any]]:
    stamp = root / "logs" / "omega.json"
    started_ns = time.time_ns()
    try:
        result = subprocess.run(
            ["bash", "scripts/omega.sh", "--strict", "--quiet"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CampaignSupervisorError("strict Omega evaluation exceeded its finite timeout") from exc
    try:
        stat = stamp.stat()
        payload = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignSupervisorError(f"strict Omega produced no readable stamp: {exc}") from exc
    if stat.st_mtime_ns < started_ns:
        raise CampaignSupervisorError("strict Omega did not produce a fresh stamp")
    if not isinstance(payload, dict):
        raise CampaignSupervisorError("strict Omega stamp must be an object")
    try:
        rungs, remediations = load_omega_remediations(root)
        expected = annotate_omega_stamp(payload, rungs, remediations)
    except OmegaRemediationError as exc:
        raise CampaignSupervisorError(f"strict Omega remediation contract is invalid: {exc}") from exc
    if expected != payload:
        raise CampaignSupervisorError("strict Omega stamp is missing current typed remediation metadata")
    return result.returncode, payload


def validate_omega_evaluation(exit_code: int, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    rows = payload.get("rungs")
    if payload.get("schema_version") != 3 or not isinstance(rows, list) or not rows:
        raise CampaignSupervisorError("strict Omega stamp has an unsupported schema")
    if payload.get("strict") is not True or payload.get("offline") is not False:
        raise CampaignSupervisorError("campaign settlement requires a live strict Omega evaluation")
    ids: list[str] = []
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    failed: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise CampaignSupervisorError("strict Omega stamp contains a non-object rung")
        rung_id = str(raw.get("id") or "")
        status = str(raw.get("status") or "")
        if not rung_id or status not in counts:
            raise CampaignSupervisorError("strict Omega stamp contains an invalid rung identity or status")
        try:
            remediation = OmegaRemediationV1.model_validate(raw.get("remediation"))
        except ValueError as exc:
            raise CampaignSupervisorError(f"{rung_id}: typed remediation metadata is invalid: {exc}") from exc
        if remediation.id != rung_id:
            raise CampaignSupervisorError(f"{rung_id}: remediation identity does not match the rung")
        ids.append(rung_id)
        counts[status] += 1
        if status != "PASS":
            failed.append({**raw, "remediation": remediation})
    if len(ids) != len(set(ids)):
        raise CampaignSupervisorError("strict Omega stamp contains duplicate rung identities")
    if (
        payload.get("pass") != counts["PASS"]
        or payload.get("fail") != counts["FAIL"]
        or payload.get("skip") != counts["SKIP"]
    ):
        raise CampaignSupervisorError("strict Omega stamp counts do not match its typed rows")
    contract_hash = str(payload.get("contract_hash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", contract_hash):
        raise CampaignSupervisorError("strict Omega stamp contract hash is invalid")
    holds = not failed and payload.get("verdict") == "HOLDS" and exit_code == 0
    broken = bool(failed) and payload.get("verdict") in {"BROKEN", "INCOMPLETE"} and exit_code != 0
    if not holds and not broken:
        raise CampaignSupervisorError("strict Omega exit, verdict, and rung statuses disagree")
    return failed, contract_hash


def _run_id(packet: WorkPacketV1) -> str:
    digest = canonical_hash(
        {
            "work_id": packet.work_id,
            "intent_hash": packet.intent_hash,
            "execution_hash": packet.execution_hash,
        }
    )
    return f"run-{digest[:32]}"


def compile_omega_packets(
    *,
    receipt: dict[str, Any],
    identity: AgentIdentityV1,
    git_state: dict[str, str],
    omega_payload: dict[str, Any],
    failed_rows: list[dict[str, Any]],
    omega_contract_hash: str,
) -> tuple[WorkPacketV1, ...]:
    if not failed_rows:
        raise CampaignSupervisorError("cannot compile an empty Omega remediation graph")
    remediations = [row["remediation"] for row in failed_rows]
    if any(remediation.effect != "read" for remediation in remediations):
        raise CampaignSupervisorError(
            "write or external Omega remediation requires an owner packet with explicit resource claims"
        )
    deadline_epoch = int(receipt["contract"]["runway"]["deadline_epoch"])
    deadline = datetime.fromtimestamp(deadline_epoch, UTC)
    head = git_state["head"]
    state_payload = {key: value for key, value in omega_payload.items() if key not in {"generated", "generated_at"}}
    state_digest = _canonical_hash(state_payload)
    campaign_id = f"omega-{head[:12]}-{omega_contract_hash[:12]}"
    graph_id = f"{campaign_id}-{state_digest[:12]}"
    graph_key = _canonical_hash(
        {
            "head": head,
            "omega_contract_hash": omega_contract_hash,
            "omega_state_digest": state_digest,
        }
    )
    root_work_id = f"{graph_id}-root"
    total_cost = sum(remediation.work_loan.budget_cost for remediation in remediations)
    root_loan = WorkLoanV1(
        source_origin="system_debt",
        horizon="present",
        value_case="Close every currently failing typed strict-Omega rung without capability shrinkage.",
        budget_cost=total_cost,
        owner_surface="github:organvm/limen:issue:1571",
    )
    root_campaign = CampaignPacketV1(
        campaign_id=campaign_id,
        failed_predicate="strict Omega and its unchanged two-pass proof hold",
        owner="github:organvm/limen:issue:1571",
        next_action="Harvest every typed child receipt, re-evaluate exact remote main, and select one finite boundary.",
        output_ceiling_bytes=65_536,
    )
    root = WorkPacketV1(
        work_id=root_work_id,
        work_key=f"omega/graph/{graph_key}",
        intent={
            "kind": "fanout-root",
            "campaign_id": campaign_id,
            "failed_rung_count": len(failed_rows),
            "omega_state_digest": state_digest,
        },
        execution={
            "adapter": "fanout-keeper",
            "omega_contract_hash": omega_contract_hash,
            "omega_state_digest": state_digest,
        },
        initiator=identity,
        conductor=identity,
        required_capabilities=frozenset({"conduct"}),
        predicate="python3 scripts/omega-two-pass.py --check",
        receipt_target="github:organvm/limen:issue:1571",
        work_loan=root_loan,
        campaign=root_campaign,
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"read"}),
            repositories=frozenset().union(*(remediation.authority.repositories for remediation in remediations)),
            path_prefixes=frozenset().union(*(remediation.authority.path_prefixes for remediation in remediations)),
            may_delegate=True,
        ),
        deadline=deadline,
        spend=SpendEnvelopeV1(limit=total_cost),
        retry=RetryPolicyV1(max_attempts=1),
        fanout=FanoutBoundsV1(max_children=len(failed_rows), max_depth=1),
        effect="read",
    )
    root_run_id = _run_id(root)
    packets = [root]
    for row in failed_rows:
        remediation: OmegaRemediationV1 = row["remediation"]
        rung_slug = re.sub(r"[^a-z0-9]+", "-", remediation.id.casefold()).strip("-")
        rung_key = _canonical_hash(
            {
                "head": head,
                "omega_contract_hash": omega_contract_hash,
                "omega_state_digest": state_digest,
                "rung_id": remediation.id,
            }
        )
        packets.append(
            WorkPacketV1(
                root_run_id=root_run_id,
                parent_run_id=root_run_id,
                work_id=f"{graph_id}-{rung_slug[:48]}-{rung_key[:12]}",
                work_key=f"omega/rung/{rung_key}",
                intent={
                    "kind": "fanout-leaf",
                    "campaign_id": campaign_id,
                    "rung_id": remediation.id,
                    "rung_status": row["status"],
                },
                execution={
                    "adapter": "campaign-remediation",
                    "command": remediation.predicate,
                    "omega_contract_hash": omega_contract_hash,
                    "omega_state_digest": state_digest,
                },
                initiator=identity,
                conductor=identity,
                required_capabilities=remediation.required_capabilities,
                predicate=remediation.predicate,
                receipt_target=remediation.receipt_target,
                work_loan=remediation.work_loan,
                campaign=CampaignPacketV1(
                    campaign_id=campaign_id,
                    failed_predicate=f"strict Omega rung {remediation.id} is PASS",
                    owner=remediation.owner,
                    next_action=remediation.next_action,
                    output_ceiling_bytes=remediation.output_ceiling_bytes,
                ),
                authority=remediation.authority,
                deadline=deadline,
                spend=SpendEnvelopeV1(limit=remediation.work_loan.budget_cost),
                retry=RetryPolicyV1(max_attempts=1),
                depth=1,
                effect="read",
            )
        )
    return tuple(packets)


def _settle_omega(root: Path, timeout_seconds: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for mode in ("--run", "--check", "--check"):
        try:
            result = subprocess.run(
                [sys.executable, "scripts/omega-two-pass.py", mode],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CampaignSupervisorError("Omega two-pass settlement exceeded its finite timeout") from exc
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CampaignSupervisorError("Omega two-pass settlement returned invalid JSON") from exc
        if result.returncode != 0 or not isinstance(payload, dict) or payload.get("ok") is not True:
            raise CampaignSupervisorError(f"Omega two-pass settlement failed during {mode}: {payload}")
        if mode == "--check" and payload.get("changed") is not False:
            raise CampaignSupervisorError("Omega two-pass check did not reproduce an unchanged receipt")
        results.append(
            {
                "changed": payload.get("changed"),
                "content_hash": payload.get("content_hash"),
                "head": payload.get("head"),
                "mode": mode,
            }
        )
    return results


def _validate_settlement(results: Any) -> list[dict[str, Any]]:
    if not isinstance(results, list) or len(results) != 3:
        raise CampaignSupervisorError("Omega settlement must return exactly one run and two check receipts")
    expected_modes = ("--run", "--check", "--check")
    for index, (result, expected_mode) in enumerate(zip(results, expected_modes, strict=True)):
        if not isinstance(result, dict) or result.get("mode") != expected_mode:
            raise CampaignSupervisorError("Omega settlement receipt sequence is invalid")
        changed = result.get("changed")
        if not isinstance(changed, bool):
            raise CampaignSupervisorError(f"Omega settlement receipt {index + 1} has no boolean changed result")
        if expected_mode == "--check" and changed:
            raise CampaignSupervisorError("Omega two-pass check did not reproduce an unchanged receipt")
    return results


def run_campaign(
    *,
    client: Any,
    root: Path,
    capsule: Path | None,
    identity: AgentIdentityV1,
    capsule_commit: str | None = None,
    capsule_base: str | None = None,
    capsule_path: str | None = None,
    capsule_branch: str | None = None,
    terminal_predicate: str = "omega",
    now_epoch: int | None = None,
    evaluator: Callable[[Path, int], tuple[int, dict[str, Any]]] = _fresh_omega_evaluation,
    settler: Callable[[Path, int], list[dict[str, Any]]] = _settle_omega,
    relay_reserver: Callable[..., RelayReservation] = reserve_relay,
    relay_launcher: Callable[..., RelayLaunch] = launch_reserved_relay,
    evaluation_timeout_seconds: int = 1800,
    wake_deadline_monotonic_ns: int | None = None,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    if terminal_predicate != "omega":
        raise CampaignSupervisorError("only the registry-owned omega terminal predicate is supported")
    if not 1 <= evaluation_timeout_seconds <= 7200:
        raise CampaignSupervisorError("campaign evaluation timeout must be between 1 and 7200 seconds")
    campaign_started_monotonic_ns = monotonic_ns()
    if wake_deadline_monotonic_ns is None:
        campaign_deadline_monotonic_ns = campaign_started_monotonic_ns + evaluation_timeout_seconds * 1_000_000_000
    else:
        if isinstance(wake_deadline_monotonic_ns, bool) or not isinstance(wake_deadline_monotonic_ns, int):
            raise CampaignSupervisorError("campaign wake deadline must be a positive monotonic timestamp")
        remaining_wake_ns = wake_deadline_monotonic_ns - campaign_started_monotonic_ns
        if remaining_wake_ns <= 0:
            raise CampaignSupervisorError("campaign wake deadline has expired")
        if remaining_wake_ns > (evaluation_timeout_seconds + 1) * 1_000_000_000:
            raise CampaignSupervisorError("campaign wake deadline exceeds the bounded evaluation timeout")
        campaign_deadline_monotonic_ns = wake_deadline_monotonic_ns

    def phase_timeout(capsule_ceiling_seconds: int) -> int:
        outer_remaining = int((campaign_deadline_monotonic_ns - monotonic_ns()) / 1_000_000_000)
        bounded = min(
            evaluation_timeout_seconds,
            capsule_ceiling_seconds,
            outer_remaining,
        )
        if bounded < 1:
            raise CampaignSupervisorError("campaign wake budget expired before the next bounded phase")
        return bounded

    local_source = capsule is not None
    ref_values = (capsule_commit, capsule_base, capsule_path, capsule_branch)
    if local_source == any(value is not None for value in ref_values) or (
        not local_source and any(value is None for value in ref_values)
    ):
        raise CampaignSupervisorError(
            "campaign run requires exactly one local capsule or one complete immutable capsule ref"
        )
    git_state = exact_remote_main(root)
    if capsule is not None:
        receipt, remaining = load_capsule_receipt(capsule, root=root, now_epoch=now_epoch)
        predecessor_path = capsule
        predecessor_commit = None
    else:
        assert capsule_commit is not None
        assert capsule_base is not None
        assert capsule_path is not None
        assert capsule_branch is not None
        receipt, remaining = load_capsule_receipt_ref(
            root=root,
            commit=capsule_commit,
            base=capsule_base,
            path=capsule_path,
            branch=capsule_branch,
            now_epoch=now_epoch,
        )
        predecessor_path = Path(capsule_path)
        predecessor_commit = capsule_commit
    if remaining <= T_MINUS_SECONDS:
        reservation_kwargs: dict[str, Any] = {
            "exact_remote_main": git_state["head"],
        }
        if predecessor_commit is not None:
            reservation_kwargs["predecessor_commit"] = predecessor_commit
        reservation = relay_reserver(root, predecessor_path, **reservation_kwargs)
        relay_timeout = min(
            float(_RELAY_STARTUP_CEILING_SECONDS),
            (campaign_deadline_monotonic_ns - monotonic_ns()) / 1_000_000_000 - _RELAY_OUTER_MARGIN_SECONDS,
        )
        if relay_timeout < 1:
            raise CampaignSupervisorError("campaign wake budget leaves no strict margin for a terminal relay receipt")
        launch = relay_launcher(
            root,
            reservation.receipt.relay_id,
            timeout_seconds=relay_timeout,
        )
        return {
            "schema": RESULT_SCHEMA,
            "boundary": "wait_relay",
            "campaign_id": receipt["workstream"],
            "exact_head": git_state["head"],
            "reason": (
                "T-30 reached; one deterministic successor launch is bounded below the outer "
                "wake deadline and recorded through its terminal lifecycle receipt"
            ),
            "relay": relay_boundary_projection(launch.receipt),
            "remaining_seconds": remaining,
            "successor_required": True,
            "terminal_predicate": terminal_predicate,
        }
    exit_code, omega_payload = evaluator(root, phase_timeout(remaining - T_MINUS_SECONDS))
    failed_rows, omega_contract_hash = validate_omega_evaluation(exit_code, omega_payload)
    if not failed_rows:
        settlement = _validate_settlement(settler(root, phase_timeout(remaining - T_MINUS_SECONDS)))
        return {
            "schema": RESULT_SCHEMA,
            "boundary": "settled",
            "campaign_id": receipt["workstream"],
            "exact_head": git_state["head"],
            "omega_contract_hash": omega_contract_hash,
            "remaining_seconds": remaining,
            "settlement": settlement,
            "successor_required": False,
            "terminal_predicate": terminal_predicate,
        }
    capabilities = client.capabilities()
    if not isinstance(capabilities, dict):
        raise CampaignSupervisorError("keeper capabilities response must be an object")
    packets = compile_omega_packets(
        receipt=receipt,
        identity=identity,
        git_state=git_state,
        omega_payload=omega_payload,
        failed_rows=failed_rows,
        omega_contract_hash=omega_contract_hash,
    )
    campaign = packets[0].campaign
    if campaign is None:
        raise CampaignSupervisorError("compiled Omega graph has no campaign root")
    campaign_id = campaign.campaign_id
    missing_capabilities = _missing_capability_sets(capabilities, packets)
    if missing_capabilities:
        return {
            "schema": RESULT_SCHEMA,
            "boundary": "switch",
            "campaign_id": campaign_id,
            "capabilities_digest": _canonical_hash(capabilities),
            "exact_head": git_state["head"],
            "failed_rung_count": len(failed_rows),
            "missing_capabilities": missing_capabilities,
            "reason": "no healthy accepting session can satisfy every typed remediation capability set",
            "remaining_seconds": remaining,
            "successor_required": False,
            "terminal_predicate": terminal_predicate,
        }
    submission = client.submit_graph(packets)
    if not isinstance(submission, dict):
        raise CampaignSupervisorError("keeper graph submission response must be an object")
    if submission.get("status") != "reserved" or not submission.get("root_run_id"):
        return {
            "schema": RESULT_SCHEMA,
            "boundary": "wait_relay",
            "campaign_id": campaign_id,
            "capabilities_digest": _canonical_hash(capabilities),
            "exact_head": git_state["head"],
            "failed_rung_count": len(failed_rows),
            "reason": "keeper could not atomically reserve the typed remediation graph",
            "remaining_seconds": remaining,
            "submission": _bounded_submission_summary(submission),
            "successor_required": False,
            "terminal_predicate": terminal_predicate,
        }
    root_run_id = str(submission["root_run_id"])
    expected_root_run_id = _run_id(packets[0])
    runs = submission.get("runs")
    if (
        root_run_id != expected_root_run_id
        or not isinstance(runs, list)
        or len(runs) != len(packets)
        or any(not isinstance(run, dict) for run in runs)
        or [run.get("work_id") for run in runs] != [packet.work_id for packet in packets]
    ):
        raise CampaignSupervisorError("keeper did not acknowledge the exact typed remediation graph")
    harvest = client.harvest(root_run_id)
    if not isinstance(harvest, dict):
        raise CampaignSupervisorError("keeper harvest response must be an object")
    unharvested = harvest.get("unharvested")
    if (
        harvest.get("root_run_id") != root_run_id
        or harvest.get("run_count") != len(packets)
        or not isinstance(unharvested, list)
        or len(unharvested) > len(packets)
        or any(not isinstance(run_id, str) for run_id in unharvested)
    ):
        raise CampaignSupervisorError("keeper harvest does not match the reserved remediation graph")
    return {
        "schema": RESULT_SCHEMA,
        "boundary": "continue",
        "campaign_id": campaign_id,
        "capabilities_digest": _canonical_hash(capabilities),
        "exact_head": git_state["head"],
        "failed_rung_count": len(failed_rows),
        "omega_contract_hash": omega_contract_hash,
        "packet_count": len(packets),
        "remaining_seconds": remaining,
        "root_run_id": root_run_id,
        "run_count": harvest.get("run_count"),
        "successor_required": False,
        "terminal_predicate": terminal_predicate,
        "unharvested": unharvested,
    }
