"""Immutable capsule publication and remote-ready recovery for campaign relays."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import rfc8785

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.campaign_relay import (
    _GIT_CONTROL_OUTPUT_CEILING,
    _GIT_TIMEOUT_SECONDS,
    _PREDECESSOR_RECEIPT_CEILING,
    _RECEIPT_CEILING,
    _RELAY_ATTEMPT_SCHEMA,
    _RELAY_READY_SCHEMA,
    CampaignRelayError,
    _attempt_remote_ref,
    _capsule_remote_ref,
    _deadline_timeout,
    _ensure_remote_branch_contains,
    _git,
    _git_bytes,
    _git_succeeds,
    _latest_remote_ref,
    _ready_remote_ref,
    _remote_ref_head,
)
from limen.conduct.campaign_relay_state import _same_relay_identity, _same_relay_lineage
from limen.conduct.models import CampaignRelayReceiptV1
from limen.workstream_contract import (
    RECEIPT_MODULES,
    RECEIPT_SCHEMA,
    ContractError,
    validate_contract,
    validate_receipt_metadata,
)
from limen.workstream_contract import (
    SCHEMA as WORKSTREAM_SCHEMA,
)


@dataclass(frozen=True)
class RemoteRelayAttempt:
    """One immutable remote claim for the relay's sole provider attempt."""

    commit: str
    token: str  # allow-secret: relay claim nonce, not a credential
    controller_pid: int
    controller_process_started: str
    exact_remote_main: str
    won: bool = False


def _capsule_receipt_path(receipt: CampaignRelayReceiptV1) -> str:
    return f"docs/continuations/{receipt.successor_slug}/workstream.json"


def _publication_payload(
    root: Path,
    receipt: CampaignRelayReceiptV1,
    *,
    publication_commit: str,
    publication_parent: str,
    publication_receipt_blob: str,
    require_topic_branch: bool = True,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    if publication_parent != receipt.exact_remote_main:
        raise CampaignRelayError(
            "relay_publication_base_mismatch",
            "successor receipt publication is not based on the reserved exact main",
        )
    commit_row = _git(
        root,
        "rev-list",
        "--parents",
        "-n",
        "1",
        publication_commit,
        deadline_monotonic=deadline_monotonic,
    ).split()
    if commit_row != [publication_commit, publication_parent]:
        raise CampaignRelayError(
            "relay_publication_commit_invalid",
            "successor receipt publication is not one exact single-parent commit",
        )
    receipt_path = _capsule_receipt_path(receipt)
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        publication_commit,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if changed != [receipt_path]:
        raise CampaignRelayError(
            "relay_publication_scope_invalid",
            "successor publication commit is not receipt-only",
        )
    observed_blob = _git(
        root,
        "rev-parse",
        f"{publication_commit}:{receipt_path}",
        deadline_monotonic=deadline_monotonic,
    )
    if observed_blob != publication_receipt_blob:
        raise CampaignRelayError(
            "relay_publication_blob_mismatch",
            "successor publication receipt blob does not match its exact commit",
        )
    if (
        _remote_ref_head(
            root,
            _capsule_remote_ref(publication_commit),
            deadline_monotonic=deadline_monotonic,
        )
        != publication_commit
    ):
        raise CampaignRelayError(
            "relay_publication_unreachable",
            "successor publication commit is not held by its dedicated immutable receipt ref",
        )
    if require_topic_branch:
        _ensure_remote_branch_contains(
            root,
            branch=receipt.successor_branch,
            commit=publication_commit,
            deadline_monotonic=deadline_monotonic,
        )
    try:
        blob_size = int(
            _git(
                root,
                "cat-file",
                "-s",
                publication_receipt_blob,
                deadline_monotonic=deadline_monotonic,
            )
        )
    except ValueError as exc:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt size is invalid",
        ) from exc
    if not 0 < blob_size <= _PREDECESSOR_RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt exceeds its bounded size",
        )
    raw = _git_bytes(
        root,
        "cat-file",
        "blob",
        publication_receipt_blob,
        output_ceiling=_PREDECESSOR_RECEIPT_CEILING,
        deadline_monotonic=deadline_monotonic,
    )
    if len(raw) != blob_size:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt size changed during validation",
        )
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt is invalid JSON",
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {
        "branch",
        "contract",
        "private_capsule",
        "schema",
        "slug",
        "workstream",
    }:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt has unknown or missing fields",
        )
    if payload.get("schema") != RECEIPT_SCHEMA:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt schema is unsupported",
        )
    try:
        slug, branch, workstream = validate_receipt_metadata(
            slug=str(payload.get("slug") or ""),
            branch=str(payload.get("branch") or ""),
            workstream=str(payload.get("workstream") or ""),
        )
        contract = validate_contract(payload.get("contract"))
    except ContractError as exc:
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt contract is invalid",
        ) from exc
    runway = contract["runway"]
    started = runway.get("started_epoch")
    deadline = runway.get("deadline_epoch")
    private = payload.get("private_capsule")
    if (
        slug != receipt.successor_slug
        or branch != receipt.successor_branch
        or workstream != receipt.workstream
        or contract.get("schema") != WORKSTREAM_SCHEMA
        or runway.get("requested") != "8h"
        or runway.get("duration_seconds") != 8 * 60 * 60
        or isinstance(started, bool)
        or not isinstance(started, int)
        or isinstance(deadline, bool)
        or not isinstance(deadline, int)
        or not isinstance(private, dict)
        or private.get("content") != "redacted"
        or private.get("modules") != list(RECEIPT_MODULES)
    ):
        raise CampaignRelayError(
            "relay_publication_receipt_invalid",
            "successor publication receipt is not the exact admitted provider-neutral capsule",
        )
    return payload


def _git_with_input(
    root: Path,
    args: list[str],
    *,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
    deadline_monotonic: float | None = None,
) -> str:
    try:
        result = run_bounded_subprocess(
            ["git", *args],
            cwd=root,
            env=env,
            input_bytes=stdin,
            timeout_seconds=_deadline_timeout(
                deadline_monotonic,
                _GIT_TIMEOUT_SECONDS,
            ),
            stdout_ceiling=_GIT_CONTROL_OUTPUT_CEILING,
            stderr_ceiling=_GIT_CONTROL_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        if exc.kind == "timeout":
            raise CampaignRelayError(
                "relay_git_timeout",
                "campaign relay Git write exceeded its bounded deadline",
            ) from exc
        if exc.kind == "output":
            raise CampaignRelayError(
                "relay_git_output_oversized",
                "campaign relay Git write exceeded its output ceiling",
            ) from exc
        raise CampaignRelayError(
            "relay_git_unavailable",
            "campaign relay Git write is unavailable",
        ) from exc
    if result.returncode != 0:
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "campaign relay ready receipt could not be published",
        )
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "campaign relay ready publication returned invalid text",
        ) from exc


def _attempt_receipt_path(receipt: CampaignRelayReceiptV1) -> str:
    return f"docs/continuations/{receipt.successor_slug}/campaign-relay-attempt.json"


def _attempt_claim_payload(
    receipt: CampaignRelayReceiptV1,
    *,
    token: str,  # allow-secret: relay claim nonce, not a credential
    controller_pid: int,
    controller_process_started: str,
) -> dict[str, Any]:
    return {
        "claim": {
            "controller_pid": controller_pid,
            "controller_process_started": controller_process_started,
            "exact_remote_main": receipt.exact_remote_main,
            "predecessor_contract_digest": receipt.predecessor_contract_digest,
            "predecessor_deadline_epoch": receipt.predecessor_deadline_epoch,
            "predecessor_receipt_blob": receipt.predecessor_receipt_blob,
            "relay_id": receipt.relay_id,
            "successor_branch": receipt.successor_branch,
            "successor_session_id": receipt.successor_session_id,
            "successor_slug": receipt.successor_slug,
            "token": token,
            "workstream": receipt.workstream,
        },
        "schema": _RELAY_ATTEMPT_SCHEMA,
    }


def _load_remote_attempt(
    root: Path,
    receipt: CampaignRelayReceiptV1,
    *,
    allow_base_adoption: bool = False,
    deadline_monotonic: float | None = None,
) -> RemoteRelayAttempt | None:
    attempt_ref = _attempt_remote_ref(receipt.relay_id)
    rows = _git(
        root,
        "ls-remote",
        "origin",
        attempt_ref,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if not rows:
        return None
    fields = rows[0].split("\t") if len(rows) == 1 else []
    if len(fields) != 2 or fields[1] != attempt_ref:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt ref is malformed or ambiguous",
        )
    commit = fields[0]
    if not _git_succeeds(
        root,
        "fetch",
        "--no-tags",
        "--quiet",
        "--no-write-fetch-head",
        "origin",
        commit,
        deadline_monotonic=deadline_monotonic,
    ):
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt could not be loaded immutably",
        )
    parent_row = _git(
        root,
        "rev-list",
        "--parents",
        "-n",
        "1",
        commit,
        deadline_monotonic=deadline_monotonic,
    ).split()
    if len(parent_row) != 2 or parent_row[0] != commit:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt is not one single-parent commit",
        )
    remote_base = parent_row[1]
    if remote_base != receipt.exact_remote_main and not allow_base_adoption:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt is not anchored to its exact reserved base",
        )
    try:
        validation_receipt = CampaignRelayReceiptV1.model_validate(
            {
                **receipt.model_dump(mode="json"),
                "exact_remote_main": remote_base,
            }
        )
    except ValueError as exc:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt base is invalid",
        ) from exc
    attempt_path = _attempt_receipt_path(receipt)
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        remote_base,
        commit,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if changed != [attempt_path]:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt is not receipt-only",
        )
    blob = _git(
        root,
        "rev-parse",
        f"{commit}:{attempt_path}",
        deadline_monotonic=deadline_monotonic,
    )
    try:
        blob_size = int(
            _git(
                root,
                "cat-file",
                "-s",
                blob,
                deadline_monotonic=deadline_monotonic,
            )
        )
    except ValueError as exc:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt has an invalid receipt size",
        ) from exc
    if not 0 < blob_size <= _RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt receipt exceeded its bounded size",
        )
    raw = _git_bytes(
        root,
        "cat-file",
        "blob",
        blob,
        output_ceiling=_RECEIPT_CEILING,
        deadline_monotonic=deadline_monotonic,
    )
    if len(raw) != blob_size:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt changed during validation",
        )
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt is invalid JSON",
        ) from exc
    claim = payload.get("claim") if isinstance(payload, dict) else None
    expected_claim_fields = set(
        _attempt_claim_payload(
            validation_receipt,
            token="0" * 64,  # allow-secret: field-shape fixture, not a credential
            controller_pid=1,
            controller_process_started="fixture",
        )["claim"]
    )
    if (
        not isinstance(payload, dict)
        or set(payload) != {"claim", "schema"}
        or payload.get("schema") != _RELAY_ATTEMPT_SCHEMA
        or not isinstance(claim, dict)
        or set(claim) != expected_claim_fields
    ):
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt has unknown or missing fields",
        )
    token = claim.get("token")  # allow-secret: relay claim nonce, not a credential
    controller_pid = claim.get("controller_pid")
    controller_started = claim.get("controller_process_started")
    expected_identity = _attempt_claim_payload(
        validation_receipt,
        token=str(token or ""),  # allow-secret: relay claim nonce, not a credential
        controller_pid=controller_pid if type(controller_pid) is int else 1,
        controller_process_started=str(controller_started or ""),
    )["claim"]
    if (
        not isinstance(token, str)
        or len(token) != 64
        or any(character not in "0123456789abcdef" for character in token)
        or type(controller_pid) is not int
        or controller_pid < 1
        or not isinstance(controller_started, str)
        or not controller_started
        or len(controller_started) > 256
        or "\x00" in controller_started
        or controller_started != " ".join(controller_started.split())
        or claim != expected_identity
    ):
        raise CampaignRelayError(
            "relay_attempt_invalid",
            "campaign relay remote attempt identity is invalid",
        )
    return RemoteRelayAttempt(
        commit=commit,
        token=token,  # allow-secret: relay claim nonce, not a credential
        controller_pid=controller_pid,
        controller_process_started=controller_started,
        exact_remote_main=remote_base,
    )


def _publish_remote_attempt(
    root: Path,
    receipt: CampaignRelayReceiptV1,
    *,
    controller_pid: int,
    controller_process_started: str,
    deadline_monotonic: float | None = None,
) -> RemoteRelayAttempt:
    token = secrets.token_hex(32)  # allow-secret: one-time relay claim nonce
    payload = (
        rfc8785.dumps(
            _attempt_claim_payload(
                receipt,
                token=token,  # allow-secret: one-time relay claim nonce
                controller_pid=controller_pid,
                controller_process_started=controller_process_started,
            )
        )
        + b"\n"
    )
    if len(payload) > _RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_attempt_publication_failed",
            "campaign relay remote attempt receipt exceeded its bounded size",
        )
    attempt_path = _attempt_receipt_path(receipt)
    index_descriptor, index_path = tempfile.mkstemp(prefix="limen-relay-attempt-index-")
    os.close(index_descriptor)
    os.unlink(index_path)
    git_env = dict(os.environ)
    git_env["GIT_INDEX_FILE"] = index_path
    try:
        _git_with_input(
            root,
            ["read-tree", receipt.exact_remote_main],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        blob = _git_with_input(
            root,
            ["hash-object", "-w", "--stdin"],
            stdin=payload,
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        _git_with_input(
            root,
            ["update-index", "--add", "--cacheinfo", "100644", blob, attempt_path],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        tree = _git_with_input(
            root,
            ["write-tree"],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        commit = _git_with_input(
            root,
            [
                "commit-tree",
                tree,
                "-p",
                receipt.exact_remote_main,
                "-m",
                f"Claim campaign relay attempt {receipt.relay_id[:16]}",
            ],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
    except CampaignRelayError as exc:
        raise CampaignRelayError(
            "relay_attempt_publication_failed",
            "campaign relay remote attempt could not be prepared",
        ) from exc
    finally:
        try:
            os.unlink(index_path)
        except FileNotFoundError:
            pass

    attempt_ref = _attempt_remote_ref(receipt.relay_id)
    publication_error: CampaignRelayError | None = None
    try:
        _git_with_input(
            root,
            ["push", "origin", f"{commit}:{attempt_ref}"],
            deadline_monotonic=deadline_monotonic,
        )
    except CampaignRelayError as exc:
        publication_error = exc
    try:
        observed = _load_remote_attempt(
            root,
            receipt,
            deadline_monotonic=deadline_monotonic,
        )
    except CampaignRelayError:
        if publication_error is not None:
            raise CampaignRelayError(
                "relay_attempt_publication_failed",
                "campaign relay remote attempt could not be published or reconciled",
            ) from publication_error
        raise
    if observed is None:
        raise CampaignRelayError(
            "relay_attempt_publication_failed",
            "campaign relay remote attempt ref is missing after publication",
        ) from publication_error
    return RemoteRelayAttempt(
        commit=observed.commit,
        token=observed.token,  # allow-secret: relay claim nonce, not a credential
        controller_pid=observed.controller_pid,
        controller_process_started=observed.controller_process_started,
        exact_remote_main=observed.exact_remote_main,
        won=observed.commit == commit and observed.token == token,  # allow-secret: nonce comparison
    )


def _ready_receipt_path(receipt: CampaignRelayReceiptV1) -> str:
    return f"docs/continuations/{receipt.successor_slug}/campaign-relay-ready.json"


ReadyPublicationOutcome = Literal["success", "confirmed_failure", "uncertain"]


def _ready_publication_outcome(
    root: Path,
    *,
    commit: str,
    ready_ref: str,
    latest_ref: str,
    deadline_monotonic: float | None = None,
) -> ReadyPublicationOutcome:
    """Classify one failed push by re-reading only its two exact destination refs."""

    try:
        ready_head = _remote_ref_head(
            root,
            ready_ref,
            deadline_monotonic=deadline_monotonic,
        )
        latest_head = _remote_ref_head(
            root,
            latest_ref,
            deadline_monotonic=deadline_monotonic,
        )
    except CampaignRelayError as exc:
        if exc.code == "relay_publication_unreachable":
            return "confirmed_failure"
        return "uncertain"
    if ready_head == commit and latest_head == commit:
        return "success"
    return "confirmed_failure"


def _publish_ready_receipt(
    root: Path,
    receipt: CampaignRelayReceiptV1,
    *,
    deadline_monotonic: float | None = None,
) -> None:
    if receipt.state != "ready" or receipt.publication_commit is None:
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "campaign relay readiness is incomplete",
        )
    payload = (
        rfc8785.dumps(
            {
                "receipt": receipt.model_dump(mode="json"),
                "schema": _RELAY_READY_SCHEMA,
            }
        )
        + b"\n"
    )
    if len(payload) > _RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "campaign relay ready receipt exceeded its bounded size",
        )
    ready_path = _ready_receipt_path(receipt)
    index_descriptor, index_path = tempfile.mkstemp(prefix="limen-relay-index-")
    os.close(index_descriptor)
    os.unlink(index_path)
    git_env = dict(os.environ)
    git_env["GIT_INDEX_FILE"] = index_path
    try:
        _git_with_input(
            root,
            ["read-tree", receipt.publication_commit],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        blob = _git_with_input(
            root,
            ["hash-object", "-w", "--stdin"],
            stdin=payload,
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        _git_with_input(
            root,
            ["update-index", "--add", "--cacheinfo", "100644", blob, ready_path],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
        tree = _git_with_input(
            root,
            ["write-tree"],
            env=git_env,
            deadline_monotonic=deadline_monotonic,
        )
    finally:
        try:
            os.unlink(index_path)
        except FileNotFoundError:
            pass
    ready_ref = _ready_remote_ref(receipt.relay_id)
    latest_ref = _latest_remote_ref(receipt.workstream)
    latest_rows = _git_with_input(
        root,
        ["ls-remote", "origin", latest_ref],
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if len(latest_rows) > 1:
        raise CampaignRelayError(
            "relay_ready_publication_failed",
            "campaign relay latest-ready ref is ambiguous",
        )
    previous_latest: str | None = None
    if latest_rows:
        fields = latest_rows[0].split("\t")
        if (
            len(fields) != 2
            or fields[1] != latest_ref
            or len(fields[0]) not in {40, 64}
            or any(character not in "0123456789abcdef" for character in fields[0])
        ):
            raise CampaignRelayError(
                "relay_ready_publication_failed",
                "campaign relay latest-ready ref is malformed",
            )
        previous_latest = fields[0]
        _git_with_input(
            root,
            [
                "fetch",
                "--no-tags",
                "--quiet",
                "--no-write-fetch-head",
                "origin",
                previous_latest,
            ],
            deadline_monotonic=deadline_monotonic,
        )
    commit_args = [
        "commit-tree",
        tree,
        "-p",
        receipt.publication_commit,
    ]
    if previous_latest is not None and previous_latest != receipt.publication_commit:
        commit_args.extend(["-p", previous_latest])
    commit_args.extend(["-m", f"Record campaign relay readiness {receipt.relay_id[:16]}"])
    commit = _git_with_input(
        root,
        commit_args,
        deadline_monotonic=deadline_monotonic,
    )
    try:
        _git_with_input(
            root,
            [
                "push",
                "--atomic",
                "origin",
                f"{commit}:{ready_ref}",
                f"{commit}:{latest_ref}",
            ],
            deadline_monotonic=deadline_monotonic,
        )
    except CampaignRelayError as exc:
        outcome = _ready_publication_outcome(
            root,
            commit=commit,
            ready_ref=ready_ref,
            latest_ref=latest_ref,
            deadline_monotonic=deadline_monotonic,
        )
        if outcome == "success":
            return
        if outcome == "confirmed_failure":
            raise CampaignRelayError(
                "relay_ready_publication_failed",
                "campaign relay ready publication was confirmed absent or mismatched",
            ) from exc
        if outcome == "uncertain":
            raise CampaignRelayError(
                "relay_ready_publication_uncertain",
                "campaign relay ready publication outcome could not be reconciled",
            ) from exc


def _load_remote_ready(
    root: Path,
    *,
    commit: str,
    relay_id: str | None,
    validate_publication: bool = True,
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1:
    if not _git_succeeds(
        root,
        "fetch",
        "--no-tags",
        "--quiet",
        "--no-write-fetch-head",
        "origin",
        commit,
        deadline_monotonic=deadline_monotonic,
    ):
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready commit could not be loaded without checkout mutation",
        )
    parent_row = _git(
        root,
        "rev-list",
        "--parents",
        "-n",
        "1",
        commit,
        deadline_monotonic=deadline_monotonic,
    ).split()
    if len(parent_row) not in {2, 3} or parent_row[0] != commit:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping has an invalid parent contract",
        )
    changed = _git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        parent_row[1],
        commit,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if (
        len(changed) != 1
        or not changed[0].startswith("docs/continuations/")
        or not changed[0].endswith("/campaign-relay-ready.json")
        or len(changed[0]) > 256
    ):
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping is not receipt-only",
        )
    ready_path = changed[0]
    blob = _git(
        root,
        "rev-parse",
        f"{commit}:{ready_path}",
        deadline_monotonic=deadline_monotonic,
    )
    try:
        blob_size = int(
            _git(
                root,
                "cat-file",
                "-s",
                blob,
                deadline_monotonic=deadline_monotonic,
            )
        )
    except ValueError as exc:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping has an invalid size",
        ) from exc
    if not 0 < blob_size <= _RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping exceeded its bounded size",
        )
    raw = _git_bytes(
        root,
        "cat-file",
        "blob",
        blob,
        output_ceiling=_RECEIPT_CEILING,
        deadline_monotonic=deadline_monotonic,
    )
    if len(raw) != blob_size:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping changed during validation",
        )
    try:
        payload = json.loads(raw)
        receipt = CampaignRelayReceiptV1.model_validate(payload.get("receipt"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError) as exc:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping is invalid",
        ) from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"receipt", "schema"}
        or payload.get("schema") != _RELAY_READY_SCHEMA
        or (relay_id is not None and receipt.relay_id != relay_id)
        or receipt.state != "ready"
        or receipt.publication_commit != parent_row[1]
        or _ready_receipt_path(receipt) != ready_path
    ):
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready mapping identity is invalid",
        )
    if validate_publication:
        _publication_payload(
            root,
            receipt,
            publication_commit=receipt.publication_commit,
            publication_parent=str(receipt.publication_parent or ""),
            publication_receipt_blob=str(receipt.publication_receipt_blob or ""),
            require_topic_branch=False,
            deadline_monotonic=deadline_monotonic,
        )
    return receipt


def _recover_remote_ready(
    root: Path,
    receipt: CampaignRelayReceiptV1,
    *,
    allow_base_adoption: bool = False,
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1 | None:
    ready_ref = _ready_remote_ref(receipt.relay_id)
    rows = _git(
        root,
        "ls-remote",
        "origin",
        ready_ref,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if not rows:
        return None
    if len(rows) != 1 or rows[0].split("\t")[1:] != [ready_ref]:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay ready ref is malformed or ambiguous",
        )
    commit = rows[0].split("\t", 1)[0]
    recovered = _load_remote_ready(
        root,
        commit=commit,
        relay_id=receipt.relay_id,
        deadline_monotonic=deadline_monotonic,
    )
    same_identity = _same_relay_identity(receipt, recovered)
    if not same_identity and not (allow_base_adoption and _same_relay_lineage(receipt, recovered)):
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay remote readiness identity conflicts with its reservation",
        )
    return recovered
