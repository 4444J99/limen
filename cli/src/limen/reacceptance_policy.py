"""Fail-closed validation policy for recovery reacceptance evidence."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import math
import re
from typing import Any, Iterable

from limen.reacceptance_contract import (
    ALLOWED_DISPOSITIONS,
    COVERAGE_DISPOSITIONS,
    CUTOFF_SCHEMA,
    FINDING_DISPOSITIONS,
    FULL_HEAD,
    GENERIC_ACTIONS_APP_SLUG,
    OWNER_EVIDENCE_KEYS,
    OWNER_EVIDENCE_MAX_AGE,
    OWNER_EVIDENCE_SCHEMAS,
    PRIVACY_COPY_SCHEMA,
    REFRESH_RECEIPT_SCHEMA,
    REMEDY_KINDS,
    REMEDY_STATUSES,
    REQUIRED_REVIEW_GATE_KEYS,
    REQUIRED_ROW_KEYS,
    REVIEWED_REMEDY_KINDS,
    REVIEW_GATE_CONTEXT,
    REVIEW_GATE_SCHEMA,
    SAFE_ID,
    SCHEMA,
    SHA256_DIGEST,
    SIDE_EFFECT_OUTCOME_SCHEMA,
    SIDE_EFFECT_SCHEMA,
    SOURCE_LINEAGE_SCHEMA,
    TERMINAL_DISPOSITIONS,
    TERMINAL_FINDING_DISPOSITIONS,
    TRAJECTORY_SCHEMA,
    TRUSTED_REVIEWER_KINDS,
    TRUSTED_REVIEW_ASSOCIATIONS,
    _discussion_url_digest,
    _document_scope,
    _effect_digest,
    _expected_row_ids,
    _finding_manifest_digest,
    _id_map,
    _legacy_v1_rows_digest,
    _lineage_digest,
    _output_digest,
    _parse_timestamp,
    _scope_cutoff_digest,
    _source_reference_manifest_digest,
    _strict_json_dumps,
    _string_ids,
    _summary_for,
    expand_prs,
    normalized_evidence_digest,
)
from limen.reacceptance_owners import (
    effect_owner_attestation_errors,
    owner_gate_attestation_errors,
    privacy_manifest_binding_errors,
)


def _evidence_reference_present(evidence: dict[str, Any]) -> bool:
    url = evidence.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return True
    digest = evidence.get("digest")
    owner = evidence.get("owner")
    return bool(
        isinstance(digest, str) and SHA256_DIGEST.fullmatch(digest) and isinstance(owner, str) and owner.strip()
    )


def _evidence_identity(evidence: Any) -> tuple[str, ...] | None:
    if not isinstance(evidence, dict):
        return None
    identity: list[str] = []
    url = evidence.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        identity.extend(("url", url))
    digest = evidence.get("digest")
    owner = evidence.get("owner")
    if isinstance(digest, str) and SHA256_DIGEST.fullmatch(digest) and isinstance(owner, str) and owner.strip():
        identity.extend(("digest", owner, digest))
    return tuple(identity) or None


def _evidence_identity_atoms(evidence: Any) -> frozenset[tuple[str, ...]]:
    if not isinstance(evidence, dict):
        return frozenset()
    atoms: set[tuple[str, ...]] = set()
    url = evidence.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        atoms.add(("url", url))
    digest = evidence.get("digest")
    owner = evidence.get("owner")
    if isinstance(digest, str) and SHA256_DIGEST.fullmatch(digest) and isinstance(owner, str) and owner.strip():
        atoms.add(("digest", owner, digest))
    return frozenset(atoms)


def _receipt_identity_collides(receipts: Iterable[Any]) -> bool:
    seen: set[tuple[str, ...]] = set()
    for receipt in receipts:
        atoms = _evidence_identity_atoms(receipt)
        if not atoms or seen.intersection(atoms):
            return True
        seen.update(atoms)
    return False


def _verified_receipt_errors(
    evidence: Any,
    *,
    label: str,
    as_of: dt.datetime | None,
    exact_head: str | None = None,
    disposition: str | None = None,
    schema: str | None = None,
    max_age: dt.timedelta | None = None,
) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"{label} receipt must be an object"]
    errors: list[str] = []
    if schema is not None and evidence.get("schema") != schema:
        errors.append(f"{label} receipt schema must be {schema}")
    if evidence.get("status") != "verified":
        errors.append(f"{label} receipt status must be verified")
    if disposition is not None and evidence.get("disposition") != disposition:
        errors.append(f"{label} receipt disposition must be {disposition}")
    if not _evidence_reference_present(evidence):
        errors.append(f"{label} receipt needs a durable URL or owner-bound SHA-256 digest")
    verified_at = _parse_timestamp(evidence.get("verified_at"))
    if verified_at is None:
        errors.append(f"{label} receipt verified_at must be an ISO-8601 timestamp with timezone")
    elif as_of is not None and verified_at > as_of + dt.timedelta(minutes=5):
        errors.append(f"{label} receipt verification is newer than the ledger snapshot")
    elif as_of is not None and max_age is not None and as_of - verified_at > max_age:
        errors.append(f"{label} receipt is stale")
    if exact_head is not None and evidence.get("exact_head") != exact_head:
        errors.append(f"{label} receipt exact_head does not match")
    return errors


def _verified_predicate_errors(
    predicate: Any,
    *,
    label: str,
    as_of: dt.datetime | None,
    exact_head: str | None = None,
    schema: str | None = None,
    max_age: dt.timedelta | None = None,
) -> list[str]:
    if not isinstance(predicate, dict):
        return [f"{label} predicate must be an object"]
    errors: list[str] = []
    if schema is not None and predicate.get("schema") != schema:
        errors.append(f"{label} predicate schema must be {schema}")
    if predicate.get("status") != "verified" or predicate.get("result") != "passed":
        errors.append(f"{label} predicate must be verified and passed")
    if not isinstance(predicate.get("command"), str) or not predicate["command"].strip():
        errors.append(f"{label} predicate must name the executed command")
    verified_at = _parse_timestamp(predicate.get("verified_at"))
    if verified_at is None:
        errors.append(f"{label} predicate verified_at must be an ISO-8601 timestamp with timezone")
    elif as_of is not None and verified_at > as_of + dt.timedelta(minutes=5):
        errors.append(f"{label} predicate verification is newer than the ledger snapshot")
    elif as_of is not None and max_age is not None and as_of - verified_at > max_age:
        errors.append(f"{label} predicate is stale")
    if exact_head is not None and predicate.get("exact_head") != exact_head:
        errors.append(f"{label} predicate exact_head does not match")
    return errors


def _side_effect_receipt_errors(
    receipt: Any,
    *,
    label: str,
    subject_id: str,
    effects: list[str],
    as_of: dt.datetime | None,
) -> list[str]:
    errors = _verified_receipt_errors(
        receipt,
        label=label,
        as_of=as_of,
        schema=SIDE_EFFECT_SCHEMA,
    )
    if not isinstance(receipt, dict):
        return errors
    if receipt.get("subject_id") != subject_id:
        errors.append(f"{label} side-effect receipt subject_id does not match")
    if receipt.get("effect_digest") != _effect_digest(effects):
        errors.append(f"{label} side-effect receipt effect_digest does not match")
    return errors


def _side_effect_outcome_errors(
    outcomes: Any,
    *,
    subject_id: str,
    effects: list[str],
    scope: dict[str, Any],
    known_effect_owners: dict[str, dict[str, str]],
    as_of: dt.datetime | None,
) -> list[str]:
    label = f"attempt {subject_id} side-effect outcomes"
    if not isinstance(outcomes, list):
        return [f"{label} must be a list"]
    errors: list[str] = []
    by_effect: dict[str, dict[str, Any]] = {}
    for index, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        effect = outcome.get("effect")
        if not isinstance(effect, str) or effect not in effects:
            errors.append(f"{label}[{index}] effect is not in the observed inventory")
            continue
        if effect in by_effect:
            errors.append(f"{label} must contain one terminal outcome per effect")
            continue
        by_effect[effect] = outcome
        owner_surface = outcome.get("owner_surface")
        terminal_outcome = outcome.get("outcome")
        historical_row_ids = outcome.get("historical_row_ids")
        if not isinstance(owner_surface, str) or not owner_surface.strip():
            errors.append(f"{label}[{index}] owner_surface is required")
        if (
            not isinstance(historical_row_ids, list)
            or not historical_row_ids
            or any(not isinstance(row_id, str) or not row_id for row_id in historical_row_ids)
            or len(historical_row_ids) != len(set(historical_row_ids))
        ):
            errors.append(f"{label}[{index}] historical_row_ids must be unique non-empty strings")
        elif isinstance(owner_surface, str):
            for row_id in historical_row_ids:
                expected_owner = known_effect_owners.get(row_id, {}).get(effect)
                if expected_owner != owner_surface:
                    errors.append(f"{label}[{index}] owner_surface does not match the frozen owner for {row_id}")
        if outcome.get("status") != "terminal" or terminal_outcome not in {
            "contained",
            "custodied",
            "reconciled",
            "reverted",
            "verified_obsolete",
        }:
            errors.append(f"{label}[{index}] must record a supported terminal outcome")
        errors.extend(
            _verified_predicate_errors(
                outcome.get("predicate"),
                label=f"{label}[{index}]",
                as_of=as_of,
                max_age=OWNER_EVIDENCE_MAX_AGE,
            )
        )
        receipt = outcome.get("receipt")
        errors.extend(
            _verified_receipt_errors(
                receipt,
                label=f"{label}[{index}]",
                as_of=as_of,
                schema=SIDE_EFFECT_OUTCOME_SCHEMA,
                max_age=OWNER_EVIDENCE_MAX_AGE,
            )
        )
        if isinstance(receipt, dict):
            expected = {
                "subject_id": subject_id,
                "effect": effect,
                "owner_surface": owner_surface,
                "outcome": terminal_outcome,
                "historical_row_ids": historical_row_ids,
            }
            for field, value in expected.items():
                if receipt.get(field) != value:
                    errors.append(f"{label}[{index}] receipt {field} does not match")
        errors.extend(
            f"{label}[{index}] {error}"
            for error in effect_owner_attestation_errors(
                scope=scope,
                subject_id=subject_id,
                outcome=outcome,
            )
        )
    if set(by_effect) != set(effects):
        errors.append(f"{label} must cover the exact observed effect inventory")
    return errors


def _source_receipt_errors(
    receipt: Any,
    *,
    label: str,
    subject_id: str,
    references: list[str],
    owner: str,
    as_of: dt.datetime | None,
) -> list[str]:
    errors = _verified_receipt_errors(
        receipt,
        label=label,
        as_of=as_of,
        schema=SOURCE_LINEAGE_SCHEMA,
    )
    if not isinstance(receipt, dict):
        return errors
    digest = _lineage_digest(references)
    if receipt.get("subject_id") != subject_id:
        errors.append(f"{label} source receipt subject_id does not match")
    if receipt.get("lineage_digest") != digest:
        errors.append(f"{label} source receipt lineage_digest does not match")
    if receipt.get("owner") != owner:
        errors.append(f"{label} source receipt owner does not match")
    return errors


def _trajectory_receipt_errors(
    receipt: Any,
    *,
    attempt_id: str,
    session: str,
    output_digest: str | None,
    as_of: dt.datetime | None,
) -> list[str]:
    errors = _verified_receipt_errors(
        receipt,
        label=f"attempt {attempt_id} trajectory",
        as_of=as_of,
        schema=TRAJECTORY_SCHEMA,
    )
    if not isinstance(receipt, dict):
        return errors
    if receipt.get("attempt_id") != attempt_id:
        errors.append(f"attempt {attempt_id} trajectory receipt attempt_id does not match")
    if receipt.get("session") != session:
        errors.append(f"attempt {attempt_id} trajectory receipt session does not match")
    if output_digest is None or receipt.get("output_digest") != output_digest:
        errors.append(f"attempt {attempt_id} trajectory receipt output_digest does not match")
    if receipt.get("terminal") is not True:
        errors.append(f"attempt {attempt_id} trajectory receipt must be terminal")
    return errors


def _attempt_errors(
    attempt: dict[str, Any],
    *,
    as_of: dt.datetime | None,
    scope: dict[str, Any],
    known_effect_owners: dict[str, dict[str, str]],
) -> list[str]:
    label = f"attempt {attempt.get('id', '<missing>')}"
    errors: list[str] = []
    outputs = attempt.get("outputs")
    output_digest = (
        _output_digest(outputs)
        if isinstance(outputs, list) and outputs and all(isinstance(output, dict) for output in outputs)
        else None
    )
    lineage, lineage_errors = _string_ids(
        attempt.get("source_lineage"),
        label=f"{label} source_lineage",
        require_nonempty=True,
    )
    errors.extend(lineage_errors)
    if any(
        not reference.startswith(("private_prompt_corpus:", "https://", "http://", "sha256:")) for reference in lineage
    ):
        errors.append(f"{label} source_lineage contains an unsupported reference")
    executor = attempt.get("executor")
    executor_session = ""
    if not isinstance(executor, dict):
        errors.append(f"{label} executor must be an object")
    else:
        for field in ("keeper", "session"):
            if not isinstance(executor.get(field), str) or not executor[field].strip():
                errors.append(f"{label} executor.{field} is required")
        executor_session = str(executor.get("session") or "")
    source_owner = attempt.get("source_owner")
    if not isinstance(source_owner, str) or not source_owner.strip():
        errors.append(f"{label} source_owner is required")
        source_owner = ""
    errors.extend(
        _source_receipt_errors(
            attempt.get("source_receipt"),
            label=label,
            subject_id=str(attempt.get("id") or ""),
            references=lineage,
            owner=source_owner,
            as_of=as_of,
        )
    )
    errors.extend(
        _trajectory_receipt_errors(
            attempt.get("trajectory_receipt"),
            attempt_id=str(attempt.get("id") or ""),
            session=executor_session,
            output_digest=output_digest,
            as_of=as_of,
        )
    )
    owner_surface = attempt.get("owner_surface")
    if not isinstance(owner_surface, str) or not owner_surface.strip():
        errors.append(f"{label} owner_surface is required")
    spend = attempt.get("spend")
    if not isinstance(spend, dict) or spend.get("status") != "reconciled":
        errors.append(f"{label} spend must be reconciled")
    else:
        tokens = spend.get("tokens")
        amount = spend.get("cost_amount")
        currency = spend.get("currency")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            errors.append(f"{label} spend.tokens must be a non-negative integer")
        if (
            not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or not math.isfinite(float(amount))
            or amount < 0
        ):
            errors.append(f"{label} spend.cost_amount must be non-negative")
        if not isinstance(currency, str) or not currency.strip():
            errors.append(f"{label} spend.currency is required")
        errors.extend(
            _verified_receipt_errors(
                spend.get("receipt"),
                label=f"{label} spend",
                as_of=as_of,
            )
        )
    if not isinstance(outputs, list) or not outputs:
        errors.append(f"{label} outputs must contain at least one owner reference")
    else:
        for index, output in enumerate(outputs):
            if not isinstance(output, dict):
                errors.append(f"{label} output[{index}] must be an object")
                continue
            if not isinstance(output.get("kind"), str) or not output["kind"].strip():
                errors.append(f"{label} output[{index}] kind is required")
            if not _evidence_reference_present(output):
                errors.append(f"{label} output[{index}] needs a durable owner reference")
            if output.get("kind") == "pull_request":
                if not isinstance(output.get("repository"), str) or "/" not in output["repository"]:
                    errors.append(f"{label} output[{index}] repository is required")
                if (
                    not isinstance(output.get("pull_request"), int)
                    or isinstance(output.get("pull_request"), bool)
                    or output["pull_request"] <= 0
                ):
                    errors.append(f"{label} output[{index}] pull_request is required")
                if not isinstance(output.get("exact_head"), str) or not FULL_HEAD.fullmatch(output["exact_head"]):
                    errors.append(f"{label} output[{index}] exact_head is required")
    side_effects = attempt.get("side_effects")
    if not isinstance(side_effects, dict) or side_effects.get("status") != "reconciled":
        errors.append(f"{label} side_effects must be reconciled")
    else:
        if not isinstance(side_effects.get("observed"), list):
            errors.append(f"{label} side_effects.observed must be a list")
        elif any(
            not isinstance(effect, str) or not SAFE_ID.fullmatch(effect) for effect in side_effects["observed"]
        ) or len(side_effects["observed"]) != len(set(side_effects["observed"])):
            errors.append(f"{label} side_effects.observed must contain unique safe identifiers")
        if side_effects.get("replay_authorized") is not False:
            errors.append(f"{label} side_effects must explicitly deny replay")
        if isinstance(side_effects.get("observed"), list):
            errors.extend(
                _side_effect_receipt_errors(
                    side_effects.get("receipt"),
                    label=f"{label} side effects",
                    subject_id=str(attempt.get("id") or ""),
                    effects=side_effects["observed"],
                    as_of=as_of,
                )
            )
            errors.extend(
                _side_effect_outcome_errors(
                    side_effects.get("outcomes"),
                    subject_id=str(attempt.get("id") or ""),
                    effects=side_effects["observed"],
                    scope=scope,
                    known_effect_owners=known_effect_owners,
                    as_of=as_of,
                )
            )
    errors.extend(
        _verified_predicate_errors(
            attempt.get("predicate"),
            label=label,
            as_of=as_of,
        )
    )
    errors.extend(
        _verified_receipt_errors(
            attempt.get("receipt"),
            label=label,
            as_of=as_of,
        )
    )
    attempt_id = str(attempt.get("id") or "")
    for evidence_label, evidence in (
        ("predicate", attempt.get("predicate")),
        ("execution receipt", attempt.get("receipt")),
    ):
        if not isinstance(evidence, dict) or evidence.get("attempt_id") != attempt_id:
            errors.append(f"{label} {evidence_label} attempt_id does not match")
        if output_digest is None or not isinstance(evidence, dict) or evidence.get("output_digest") != output_digest:
            errors.append(f"{label} {evidence_label} output_digest does not match")
    value = attempt.get("value")
    if not isinstance(value, dict) or value.get("status") != "verified":
        errors.append(f"{label} value classification must be verified")
    else:
        classification = value.get("classification")
        credit = value.get("credit_amount")
        if classification not in {"durable_value", "motion_only", "unverifiable", "failed"}:
            errors.append(f"{label} value classification is invalid")
        if (
            not isinstance(credit, (int, float))
            or isinstance(credit, bool)
            or not math.isfinite(float(credit))
            or credit < 0
        ):
            errors.append(f"{label} value credit_amount must be finite and non-negative")
        elif classification == "durable_value" and credit <= 0:
            errors.append(f"{label} durable value must carry positive credit")
        elif classification in {"motion_only", "unverifiable", "failed"} and credit != 0:
            errors.append(f"{label} non-value attempt cannot carry credit")
        errors.extend(
            _verified_receipt_errors(
                value.get("receipt"),
                label=f"{label} value",
                as_of=as_of,
                schema=TRAJECTORY_SCHEMA,
            )
        )
        value_receipt = value.get("receipt")
        if not isinstance(value_receipt, dict) or value_receipt.get("attempt_id") != attempt_id:
            errors.append(f"{label} value receipt attempt_id does not match")
        if (
            output_digest is None
            or not isinstance(value_receipt, dict)
            or value_receipt.get("output_digest") != output_digest
        ):
            errors.append(f"{label} value receipt output_digest does not match")
    return errors


def _review_gate_errors(
    gate: Any,
    *,
    label: str,
    repository: str,
    pull_request: int,
    exact_head: str,
    remedy_url: str,
    executing_keepers: set[str],
    as_of: dt.datetime | None,
) -> list[str]:
    if not isinstance(gate, dict):
        return [f"{label} must store the complete {REVIEW_GATE_SCHEMA} receipt"]
    errors: list[str] = []
    missing = sorted(REQUIRED_REVIEW_GATE_KEYS - set(gate))
    if missing:
        errors.append(f"{label} is incomplete; missing {', '.join(missing)}")
    if gate.get("schema") != REVIEW_GATE_SCHEMA:
        errors.append(f"{label} schema must be {REVIEW_GATE_SCHEMA}")
    if gate.get("status") != "accepted" or gate.get("final_status") != "accepted" or gate.get("ok") is not True:
        errors.append(f"{label} must be accepted")
    if gate.get("repository") != repository or gate.get("pull_request") != pull_request:
        errors.append(f"{label} repository or pull request does not match the remedy")
    if gate.get("url") != remedy_url or not remedy_url.startswith("https://"):
        errors.append(f"{label} URL does not match the live remedy")
    for field in ("head_sha", "reviewed_sha", "rechecked_head_sha"):
        if gate.get(field) != exact_head:
            errors.append(f"{label} {field} does not match the remedy exact head")
    expected_head = gate.get("expected_head")
    if expected_head not in {None, exact_head}:
        errors.append(f"{label} expected_head conflicts with the remedy exact head")
    evaluated_at = _parse_timestamp(gate.get("evaluated_at"))
    if evaluated_at is None:
        errors.append(f"{label} evaluated_at is invalid")
    elif as_of is not None and evaluated_at > as_of + dt.timedelta(minutes=5):
        errors.append(f"{label} is newer than the ledger snapshot")
    if gate.get("fixture") is not False:
        errors.append(f"{label} cannot use a fixture receipt")
    executing = gate.get("executing_keeper")
    reviewing = gate.get("reviewing_keeper")
    if (
        not isinstance(executing, str)
        or not executing
        or not isinstance(reviewing, str)
        or not reviewing
        or executing.casefold() == reviewing.casefold()
    ):
        errors.append(f"{label} requires distinct executor and reviewer identities")
    elif executing.casefold() not in {keeper.casefold() for keeper in executing_keepers}:
        errors.append(f"{label} executing_keeper is not bound to a remedy attempt executor")
    if (
        isinstance(reviewing, str)
        and reviewing
        and reviewing.casefold() in {keeper.casefold() for keeper in executing_keepers}
    ):
        errors.append(f"{label} reviewer cannot be any exact-head remedy executor")
    reviewer = gate.get("reviewer_receipt")
    if not isinstance(reviewer, dict):
        errors.append(f"{label} reviewer_receipt is required")
    else:
        kind = reviewer.get("kind")
        if kind not in TRUSTED_REVIEWER_KINDS:
            errors.append(f"{label} reviewer_receipt kind is not trusted")
        if reviewer.get("reviewed_sha") != exact_head or reviewer.get("state") != "APPROVED":
            errors.append(f"{label} reviewer_receipt must approve the exact head")
        if reviewer.get("executing_keeper") != executing or reviewer.get("reviewing_keeper") != reviewing:
            errors.append(f"{label} reviewer_receipt identities do not match")
        if not _evidence_reference_present(reviewer):
            errors.append(f"{label} reviewer_receipt needs a durable URL or owner digest")
        submitted_at = _parse_timestamp(reviewer.get("submitted_at"))
        if submitted_at is None:
            errors.append(f"{label} reviewer_receipt submitted_at is invalid")
        elif evaluated_at is not None and submitted_at > evaluated_at:
            errors.append(f"{label} reviewer_receipt postdates gate evaluation")
        if kind == "github_pull_request_review":
            if not isinstance(reviewer.get("review_id"), str) or not reviewer["review_id"].strip():
                errors.append(f"{label} native reviewer_receipt review_id is required")
            if reviewer.get("reviewer_association") not in TRUSTED_REVIEW_ASSOCIATIONS:
                errors.append(f"{label} native reviewer association is not trusted")
        elif kind == "ssh_signed_peer_review":
            for field in ("comment_id", "execution_signer_fingerprint", "review_signer_fingerprint"):
                if not isinstance(reviewer.get(field), str) or not reviewer[field].strip():
                    errors.append(f"{label} signed reviewer_receipt {field} is required")
            execution_fingerprint = reviewer.get("execution_signer_fingerprint")
            review_fingerprint = reviewer.get("review_signer_fingerprint")
            if (
                isinstance(execution_fingerprint, str)
                and isinstance(review_fingerprint, str)
                and execution_fingerprint.casefold() == review_fingerprint.casefold()
            ):
                errors.append(f"{label} signed reviewer requires distinct execution and review fingerprints")
    checks = gate.get("checks")
    if not isinstance(checks, dict):
        errors.append(f"{label} checks summary is required")
    else:
        total = checks.get("total")
        if not isinstance(total, int) or isinstance(total, bool) or total < 1:
            errors.append(f"{label} needs at least one exact-head check")
        successful_count = checks.get("successful")
        if not isinstance(successful_count, int) or isinstance(successful_count, bool) or successful_count < 0:
            errors.append(f"{label} checks.successful must be a non-negative integer")
        elif successful_count != total:
            errors.append(f"{label} not all exact-head checks succeeded")
        for field in ("pending", "failed", "unknown"):
            value = checks.get(field)
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{label} checks.{field} must be an integer")
            elif value != 0:
                errors.append(f"{label} checks.{field} must be zero")
        contexts = checks.get("contexts")
        if not isinstance(contexts, list) or len(contexts) != total:
            errors.append(f"{label} checks.contexts must enumerate every exact-head check")
        else:
            for context in contexts:
                if (
                    not isinstance(context, dict)
                    or not isinstance(context.get("name"), str)
                    or not context["name"].strip()
                ):
                    errors.append(f"{label} checks.contexts contains an unnamed or malformed check")
                    continue
                kind = context.get("kind")
                if kind == "check_run":
                    successful = context.get("status") == "COMPLETED" and context.get("conclusion") in {
                        "SUCCESS",
                        "NEUTRAL",
                        "SKIPPED",
                    }
                elif kind == "status_context":
                    successful = context.get("state") == "SUCCESS"
                else:
                    successful = False
                if context.get("classification") != "successful" or not successful:
                    errors.append(f"{label} checks.contexts classification is not supported by the live check state")
    threads = gate.get("review_threads")
    if (
        not isinstance(threads, dict)
        or threads.get("unresolved_current") != 0
        or gate.get("unresolved_current_thread_count") != 0
    ):
        errors.append(f"{label} requires zero unresolved current conversations")
    if gate.get("reason_codes") != [] or gate.get("reasons") != []:
        errors.append(f"{label} accepted receipt cannot carry rejection reasons")
    signed = gate.get("signed_receipts")
    expected_signed_keys = {
        "enabled",
        "markers",
        "execution_markers",
        "execution_verified",
        "verified",
        "ignored",
    }
    if not isinstance(signed, dict) or set(signed) != expected_signed_keys:
        errors.append(f"{label} signed_receipts summary is malformed")
    else:
        for field in expected_signed_keys - {"enabled"}:
            value = signed.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{label} signed_receipts.{field} must be a non-negative integer")
        if not isinstance(signed.get("enabled"), bool):
            errors.append(f"{label} signed_receipts.enabled must be boolean")
        if isinstance(reviewer, dict) and reviewer.get("kind") == "ssh_signed_peer_review":
            if (
                signed.get("enabled") is not True
                or not isinstance(signed.get("verified"), int)
                or signed["verified"] < 1
                or not isinstance(signed.get("execution_verified"), int)
                or signed["execution_verified"] < 1
            ):
                errors.append(f"{label} signed reviewer lacks separately verified execution and review receipts")
    publication = gate.get("publication")
    if (
        not isinstance(publication, dict)
        or publication.get("requested") is not True
        or publication.get("published") is not True
    ):
        errors.append(f"{label} authoritative dedicated-App publication is required")
    return errors


def _deployed_path_errors(
    deployed: Any,
    *,
    label: str,
    exact_head: str | None,
    as_of: dt.datetime | None,
) -> list[str]:
    if not isinstance(deployed, dict) or deployed.get("status") != "verified":
        return [f"{label} deployed_path must be verified"]
    errors: list[str] = []
    if not isinstance(deployed.get("entrypoint"), str) or not deployed["entrypoint"].strip():
        errors.append(f"{label} deployed_path entrypoint is required")
    errors.extend(
        _verified_predicate_errors(
            deployed.get("predicate"),
            label=f"{label} deployed path",
            as_of=as_of,
            exact_head=exact_head,
            max_age=OWNER_EVIDENCE_MAX_AGE,
        )
    )
    errors.extend(
        _verified_receipt_errors(
            deployed.get("receipt"),
            label=f"{label} deployed path",
            as_of=as_of,
            exact_head=exact_head,
            max_age=OWNER_EVIDENCE_MAX_AGE,
        )
    )
    return errors


def _remote_remedy_errors(
    remote: Any,
    *,
    label: str,
    exact_head: str,
    status: str,
    review_gate_app_slug: str,
) -> list[str]:
    if not isinstance(remote, dict):
        return [f"{label} needs a current live remote snapshot"]
    errors: list[str] = []
    url = remote.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        errors.append(f"{label} live URL is invalid")
    if remote.get("head_sha") != exact_head:
        errors.append(f"{label} live head does not match exact_head")
    state = remote.get("state")
    if status == "accepted" and state != "MERGED":
        errors.append(f"{label} accepted remedy must be merged remotely")
    if status == "reverted" and state not in {"CLOSED", "MERGED"}:
        errors.append(f"{label} reverted remedy must be remotely terminal")
    if remote.get("draft") is not False:
        errors.append(f"{label} live remedy must not be a draft")
    merge_commit = remote.get("merge_commit")
    if status == "accepted" and (not isinstance(merge_commit, str) or not FULL_HEAD.fullmatch(merge_commit)):
        errors.append(f"{label} accepted remedy needs a live merge commit")
    check = remote.get("review_gate_check")
    if not isinstance(check, dict):
        errors.append(f"{label} needs the dedicated-App {REVIEW_GATE_CONTEXT} CheckRun")
    else:
        if check.get("name") != REVIEW_GATE_CONTEXT:
            errors.append(f"{label} authoritative CheckRun name is invalid")
        if check.get("app_slug") != review_gate_app_slug or review_gate_app_slug == GENERIC_ACTIONS_APP_SLUG:
            errors.append(f"{label} authoritative CheckRun App is not the configured dedicated App")
        if check.get("status") != "COMPLETED" or check.get("conclusion") != "SUCCESS":
            errors.append(f"{label} authoritative CheckRun is not successful")
        if not isinstance(check.get("details_url"), str) or not check["details_url"].startswith("https://"):
            errors.append(f"{label} authoritative CheckRun needs a durable details URL")
    return errors


def _remedy_errors(
    remedy: dict[str, Any],
    *,
    attempts: dict[str, dict[str, Any]],
    as_of: dt.datetime | None,
    expected_review_gate_app_slug: str | None,
) -> list[str]:
    label = f"remedy {remedy.get('id', '<missing>')}"
    errors: list[str] = []
    kind = remedy.get("kind")
    status = remedy.get("status")
    if kind not in REMEDY_KINDS:
        errors.append(f"{label} kind is invalid")
    if status not in REMEDY_STATUSES:
        errors.append(f"{label} status is invalid")
    attempt_ids, attempt_errors = _string_ids(
        remedy.get("attempt_ids"),
        label=f"{label} attempt_ids",
        require_nonempty=status in {"accepted", "reverted"},
    )
    errors.extend(attempt_errors)
    missing_attempts = sorted(set(attempt_ids) - set(attempts))
    if missing_attempts:
        errors.append(f"{label} references missing attempts: {', '.join(missing_attempts)}")
    owner_surface = remedy.get("owner_surface")
    if not isinstance(owner_surface, str) or not owner_surface.strip():
        errors.append(f"{label} owner_surface is required")
    exact_head = remedy.get("exact_head")
    head_kind = kind in REVIEWED_REMEDY_KINDS
    if head_kind and (not isinstance(exact_head, str) or not FULL_HEAD.fullmatch(exact_head)):
        errors.append(f"{label} requires a full exact_head")
    elif exact_head is not None and (not isinstance(exact_head, str) or not FULL_HEAD.fullmatch(exact_head)):
        errors.append(f"{label} exact_head is invalid")
    if status == "repair_required":
        return errors
    errors.extend(
        _verified_predicate_errors(
            remedy.get("predicate"),
            label=label,
            as_of=as_of,
            exact_head=exact_head if isinstance(exact_head, str) else None,
        )
    )
    errors.extend(
        _verified_receipt_errors(
            remedy.get("receipt"),
            label=label,
            as_of=as_of,
            exact_head=exact_head if isinstance(exact_head, str) else None,
            disposition=status,
        )
    )
    errors.extend(
        _deployed_path_errors(
            remedy.get("deployed_path"),
            label=label,
            exact_head=exact_head if isinstance(exact_head, str) else None,
            as_of=as_of,
        )
    )
    if head_kind:
        repository = remedy.get("repository")
        pull_request = remedy.get("pull_request")
        review_gate_app_slug = remedy.get("review_gate_app_slug")
        if not isinstance(repository, str) or "/" not in repository:
            errors.append(f"{label} repository is required")
        if not isinstance(pull_request, int) or isinstance(pull_request, bool) or pull_request <= 0:
            errors.append(f"{label} pull_request is required")
        if (
            not isinstance(review_gate_app_slug, str)
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?", review_gate_app_slug)
            or review_gate_app_slug == GENERIC_ACTIONS_APP_SLUG
        ):
            errors.append(f"{label} review_gate_app_slug must name a dedicated non-generic App")
        if expected_review_gate_app_slug is None:
            errors.append(f"{label} frozen scope does not configure a dedicated review-gate App")
        elif review_gate_app_slug != expected_review_gate_app_slug:
            errors.append(f"{label} review_gate_app_slug does not match the frozen scope App")
        remote = remedy.get("remote")
        remote_url = remote.get("url") if isinstance(remote, dict) else None
        bound_attempt_ids = {
            attempt_id
            for attempt_id in attempt_ids
            if attempt_id in attempts
            and isinstance(remote_url, str)
            and any(
                isinstance(output, dict)
                and output.get("kind") == "pull_request"
                and output.get("url") == remote_url
                and output.get("repository") == repository
                and output.get("pull_request") == pull_request
                and output.get("exact_head") == exact_head
                for output in attempts[attempt_id].get("outputs", [])
            )
        }
        if status == "accepted" and not any(
            isinstance(attempts[attempt_id].get("value"), dict)
            and attempts[attempt_id]["value"].get("classification") == "durable_value"
            for attempt_id in bound_attempt_ids
        ):
            errors.append(f"{label} accepted remedy needs at least one durable-value attempt bound to its live output")
        executing_keepers = {
            str(attempts[attempt_id].get("executor", {}).get("keeper"))
            for attempt_id in bound_attempt_ids
            if isinstance(attempts[attempt_id].get("executor"), dict)
        }
        if (
            isinstance(exact_head, str)
            and isinstance(expected_review_gate_app_slug, str)
            and review_gate_app_slug == expected_review_gate_app_slug
        ):
            errors.extend(
                _remote_remedy_errors(
                    remote,
                    label=label,
                    exact_head=exact_head,
                    status=str(status),
                    review_gate_app_slug=expected_review_gate_app_slug,
                )
            )
        if (
            isinstance(repository, str)
            and isinstance(pull_request, int)
            and isinstance(exact_head, str)
            and FULL_HEAD.fullmatch(exact_head)
            and isinstance(remote, dict)
            and isinstance(remote.get("url"), str)
        ):
            errors.extend(
                _review_gate_errors(
                    remedy.get("review_gate"),
                    label=f"{label} review_gate",
                    repository=repository,
                    pull_request=pull_request,
                    exact_head=exact_head,
                    remedy_url=remote["url"],
                    executing_keepers=executing_keepers,
                    as_of=as_of,
                )
            )
    if status == "reverted":
        receipt = remedy.get("receipt")
        if not isinstance(receipt, dict) or receipt.get("reversal_status") != "verified":
            errors.append(f"{label} reverted status needs verified reversal evidence")
    return errors


def _coverage_errors(
    coverage: dict[str, Any],
    *,
    rows: dict[str, dict[str, Any]],
    remedies: dict[str, dict[str, Any]],
    findings: dict[str, dict[str, Any]],
    as_of: dt.datetime | None,
) -> list[str]:
    label = f"coverage {coverage.get('id', '<missing>')}"
    errors: list[str] = []
    row_id = coverage.get("historical_row_id")
    remedy_id = coverage.get("remedy_id")
    finding_id = coverage.get("finding_id")
    if row_id not in rows:
        errors.append(f"{label} references a missing historical row")
    if remedy_id not in remedies:
        errors.append(f"{label} references a missing remedy")
    if finding_id is not None:
        if finding_id not in findings:
            errors.append(f"{label} references a missing finding")
        elif findings[finding_id].get("historical_row_id") != row_id:
            errors.append(f"{label} finding does not belong to its historical row")
    if coverage.get("disposition") not in COVERAGE_DISPOSITIONS:
        errors.append(f"{label} disposition is invalid")
    remedy = remedies.get(str(remedy_id)) if isinstance(remedy_id, str) else None
    disposition = coverage.get("disposition")
    if isinstance(remedy, dict):
        kind = remedy.get("kind")
        status = remedy.get("status")
        if disposition in {"repaired", "superseded", "obsolete"} and (
            kind not in REVIEWED_REMEDY_KINDS or kind in {"owner_receipt", "reversal"} or status != "accepted"
        ):
            errors.append(f"{label} requires an accepted exact-head peer-reviewed remedy")
        if disposition == "reverted" and status != "reverted":
            errors.append(f"{label} reverted coverage requires a reverted remedy")
        if kind in {"owner_receipt", "reversal"} and disposition != "reverted":
            errors.append(f"{label} owner or reversal evidence cannot replace peer-reviewed repair coverage")
        exact_head = remedy.get("exact_head")
    else:
        exact_head = None
    errors.extend(
        _verified_receipt_errors(
            coverage.get("evidence"),
            label=label,
            as_of=as_of,
            exact_head=exact_head if isinstance(exact_head, str) else None,
        )
    )
    evidence = coverage.get("evidence")
    if isinstance(evidence, dict):
        expected_bindings = {
            "historical_row_id": row_id,
            "finding_id": finding_id,
            "remedy_id": remedy_id,
            "coverage_disposition": disposition,
        }
        for field, expected in expected_bindings.items():
            if evidence.get(field) != expected:
                errors.append(f"{label} evidence {field} does not match the crosswalk")
    return errors


def _coverage_for(
    coverage: Iterable[dict[str, Any]],
    *,
    row_id: str,
    finding_id: str | None = None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in coverage
        if item.get("historical_row_id") == row_id and (finding_id is None or item.get("finding_id") == finding_id)
    ]


def _terminal_row_errors(
    row: dict[str, Any],
    *,
    attempts: dict[str, dict[str, Any]],
    remedies: dict[str, dict[str, Any]],
    coverage: list[dict[str, Any]],
    known_side_effects: dict[str, list[str]],
    as_of: dt.datetime | None,
) -> list[str]:
    disposition = row.get("disposition")
    if disposition not in TERMINAL_DISPOSITIONS:
        return []
    label = f"row {row.get('id', '<missing>')}"
    errors: list[str] = []
    exact_head = row.get("exact_head") if isinstance(row.get("exact_head"), str) else None
    source = row.get("source_ask")
    source_references: list[str] = []
    if not isinstance(source, dict) or source.get("status") != "reconciled":
        errors.append(f"{label} source ask must be reconciled")
    else:
        source_references, source_errors = _string_ids(
            source.get("references"),
            label=f"{label} source ask references",
            require_nonempty=True,
        )
        errors.extend(source_errors)
        if not isinstance(source.get("private_owner"), str) or not source["private_owner"].strip():
            errors.append(f"{label} source ask private_owner is required")
        if any(
            not item.startswith(("private_prompt_corpus:", "https://", "http://", "sha256:"))
            for item in source_references
        ):
            errors.append(f"{label} source ask has an unsupported reference")
        if source.get("lineage_digest") != _lineage_digest(source_references):
            errors.append(f"{label} source ask lineage_digest does not match")
        errors.extend(
            _source_receipt_errors(
                source.get("receipt"),
                label=label,
                subject_id=str(row.get("id") or ""),
                references=source_references,
                owner=str(source.get("private_owner") or ""),
                as_of=as_of,
            )
        )
    attempt_ids, attempt_id_errors = _string_ids(
        row.get("attempt_ids"),
        label=f"{label} attempt_ids",
        require_nonempty=True,
    )
    errors.extend(attempt_id_errors)
    missing_attempts = sorted(set(attempt_ids) - set(attempts))
    if missing_attempts:
        errors.append(f"{label} references missing attempts: {', '.join(missing_attempts)}")
    attempt_lineage = {
        reference
        for attempt_id in attempt_ids
        if attempt_id in attempts
        for reference in attempts[attempt_id].get("source_lineage", [])
        if isinstance(reference, str)
    }
    if not set(source_references).issubset(attempt_lineage):
        errors.append(f"{label} source ask is not bound to its referenced attempt lineage")
    outputs = row.get("outputs")
    if (
        not isinstance(outputs, dict)
        or outputs.get("status") != "registry_owned"
        or outputs.get("attempt_ids") != attempt_ids
    ):
        errors.append(f"{label} outputs must reconcile to the row attempt registry")
    side_effects = row.get("side_effects")
    if (
        not isinstance(side_effects, dict)
        or side_effects.get("status") != "registry_owned"
        or side_effects.get("attempt_ids") != attempt_ids
        or side_effects.get("replay_authorized") is not False
    ):
        errors.append(f"{label} side effects must reconcile to the row attempt registry and deny replay")
    else:
        observed = side_effects.get("observed")
        if (
            not isinstance(observed, list)
            or any(not isinstance(effect, str) or not SAFE_ID.fullmatch(effect) for effect in observed)
            or len(observed) != len(set(observed))
        ):
            errors.append(f"{label} side effects observed inventory is invalid")
        else:
            frozen = set(known_side_effects.get(str(row.get("id")), []))
            if not frozen.issubset(set(observed)):
                errors.append(f"{label} side effects omit frozen known effects")
            attempt_effects = {
                effect
                for attempt_id in attempt_ids
                if attempt_id in attempts
                for effect in attempts[attempt_id].get("side_effects", {}).get("observed", [])
                if isinstance(effect, str)
            }
            if not set(observed).issubset(attempt_effects):
                errors.append(f"{label} side effects are not reconciled through referenced attempts")
            attempt_outcome_atoms = {
                (row_id, str(outcome.get("effect")))
                for attempt_id in attempt_ids
                if attempt_id in attempts
                for outcome in attempts[attempt_id].get("side_effects", {}).get("outcomes", [])
                if isinstance(outcome, dict)
                for row_id in outcome.get("historical_row_ids", [])
                if isinstance(row_id, str)
            }
            missing_outcome_atoms = sorted(
                (str(row.get("id")), effect)
                for effect in observed
                if (str(row.get("id")), effect) not in attempt_outcome_atoms
            )
            if missing_outcome_atoms:
                errors.append(f"{label} side effects lack row-specific terminal owner outcomes")
            errors.extend(
                _side_effect_receipt_errors(
                    side_effects.get("receipt"),
                    label=label,
                    subject_id=str(row.get("id") or ""),
                    effects=observed,
                    as_of=as_of,
                )
            )
    owner_surfaces, owner_errors = _string_ids(
        row.get("owner_surfaces"),
        label=f"{label} owner_surfaces",
        require_nonempty=True,
    )
    errors.extend(owner_errors)
    attempt_owner_surfaces = {
        str(attempts[attempt_id].get("owner_surface")) for attempt_id in attempt_ids if attempt_id in attempts
    }
    if not attempt_owner_surfaces.issubset(set(owner_surfaces)):
        errors.append(f"{label} owner_surfaces omit an attempt owner")
    errors.extend(
        _verified_predicate_errors(
            row.get("predicate"),
            label=label,
            as_of=as_of,
            exact_head=exact_head,
        )
    )
    receipt = row.get("receipt")
    adjudication = receipt.get("adjudication") if isinstance(receipt, dict) else None
    errors.extend(
        _verified_receipt_errors(
            adjudication,
            label=label,
            as_of=as_of,
            exact_head=exact_head,
            disposition=str(disposition),
        )
    )
    links = _coverage_for(coverage, row_id=str(row.get("id")))
    if not links:
        errors.append(f"{label} has no remedy coverage")
        return errors
    accepted_links = [
        link
        for link in links
        if isinstance(link.get("remedy_id"), str)
        and link["remedy_id"] in remedies
        and remedies[link["remedy_id"]].get("status") in {"accepted", "reverted"}
    ]
    if not accepted_links:
        errors.append(f"{label} has no accepted or reverted remedy coverage")
    expected_coverage = {
        "accepted": {"repaired"},
        "superseded": {"superseded", "obsolete"},
        "reverted": {"reverted"},
    }[str(disposition)]
    if not any(link.get("disposition") in expected_coverage for link in accepted_links):
        errors.append(f"{label} coverage does not support disposition {disposition}")
    if disposition == "reverted" and (
        not isinstance(adjudication, dict) or adjudication.get("reversal_status") != "verified"
    ):
        errors.append(f"{label} reverted disposition needs verified reversal evidence")
    return errors


def _finding_errors(
    finding: dict[str, Any],
    *,
    rows: dict[str, dict[str, Any]],
    remedies: dict[str, dict[str, Any]],
    coverage: list[dict[str, Any]],
) -> list[str]:
    label = f"finding {finding.get('id', '<missing>')}"
    errors: list[str] = []
    row_id = finding.get("historical_row_id")
    url = finding.get("discussion_url")
    severity = finding.get("severity")
    disposition = finding.get("disposition")
    if row_id not in rows or rows[row_id].get("kind") != "pull_request":
        errors.append(f"{label} must belong to a historical pull request")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        errors.append(f"{label} discussion_url is invalid")
    if severity not in {"p1", "p2", "unclassified"}:
        errors.append(f"{label} severity is invalid")
    if disposition not in FINDING_DISPOSITIONS:
        errors.append(f"{label} disposition is invalid")
    current_status = finding.get("current_status")
    if current_status not in {"unresolved", "resolved", "outdated", "unavailable"}:
        errors.append(f"{label} current_status is invalid")
    if disposition in TERMINAL_FINDING_DISPOSITIONS:
        if current_status != "resolved":
            errors.append(f"{label} terminal disposition requires the original thread resolved")
        links = _coverage_for(coverage, row_id=str(row_id), finding_id=str(finding.get("id")))
        accepted = [
            item
            for item in links
            if item.get("remedy_id") in remedies
            and remedies[str(item["remedy_id"])].get("status") in {"accepted", "reverted"}
        ]
        if not accepted:
            errors.append(f"{label} terminal disposition needs accepted remedy coverage")
        expected_coverage = {
            "repaired": "repaired",
            "obsolete": "obsolete",
            "reverted": "reverted",
        }[str(disposition)]
        if not any(item.get("disposition") == expected_coverage for item in accepted):
            errors.append(f"{label} {disposition} disposition needs matching {expected_coverage} coverage")
    return errors


def _owner_binding_digest(value: Any) -> str:
    try:
        encoded = _strict_json_dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    except (TypeError, ValueError):
        return ""
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _owner_receipt_pair_errors(
    value: Any,
    *,
    key: str,
    label: str,
    as_of: dt.datetime | None,
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} owner evidence must be an object"]
    expected_schema = OWNER_EVIDENCE_SCHEMAS[key]
    errors: list[str] = []
    if value.get("schema") != expected_schema:
        errors.append(f"{label} schema must be {expected_schema}")
    errors.extend(
        _verified_predicate_errors(
            value.get("predicate"),
            label=label,
            as_of=as_of,
            schema=f"{expected_schema}.predicate",
            max_age=OWNER_EVIDENCE_MAX_AGE,
        )
    )
    errors.extend(
        _verified_receipt_errors(
            value.get("receipt"),
            label=label,
            as_of=as_of,
            schema=expected_schema,
            max_age=OWNER_EVIDENCE_MAX_AGE,
        )
    )
    return errors


def _gate(
    *,
    owner: str,
    blockers: Iterable[str],
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    unique_blockers = sorted(set(blockers))
    return {
        "status": "passed" if not unique_blockers else "failed",
        "owner": owner,
        "blockers": unique_blockers,
        "predicate": copy.deepcopy(evidence.get("predicate")) if isinstance(evidence, dict) else None,
        "receipt": copy.deepcopy(evidence.get("receipt")) if isinstance(evidence, dict) else None,
    }


def _derive_completion_gates(
    *,
    scope: dict[str, Any],
    rows: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    remedies: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    owner_evidence: Any,
    refresh_history: list[dict[str, Any]],
    as_of: dt.datetime | None,
) -> dict[str, dict[str, Any]]:
    owners = owner_evidence if isinstance(owner_evidence, dict) else {}
    rows_by_id = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    attempt_ids = {str(attempt.get("id")) for attempt in attempts if isinstance(attempt, dict)}

    baseline = owners.get("baseline_open_prs")
    open_blockers: list[str] = []
    expected_baseline = list(scope.get("baseline_open_prs") or [])
    if not isinstance(baseline, dict):
        open_blockers.append("owner_evidence_missing")
    else:
        if baseline.get("baseline_row_ids") != expected_baseline:
            open_blockers.append("baseline_denominator_mismatch")
        terminal = baseline.get("terminal_row_ids")
        expected_terminal = sorted(
            identifier
            for identifier in expected_baseline
            if rows_by_id.get(identifier, {}).get("disposition") in TERMINAL_DISPOSITIONS
        )
        if terminal != expected_terminal or len(expected_terminal) != len(expected_baseline):
            open_blockers.append("baseline_prs_not_terminal")
        baseline_binding = {
            "baseline_row_ids": expected_baseline,
            "terminal_row_ids": expected_terminal,
            "cutoff_digest": _scope_cutoff_digest(scope),
        }
        baseline_digest = _owner_binding_digest(baseline_binding)
        baseline_receipt = baseline.get("receipt")
        if (
            baseline.get("baseline_digest") != baseline_digest
            or not isinstance(baseline_receipt, dict)
            or baseline_receipt.get("binding_digest") != baseline_digest
        ):
            open_blockers.append("owner_binding_digest_mismatch")
        if _owner_receipt_pair_errors(
            baseline,
            key="baseline_open_prs",
            label="baseline open PR gate",
            as_of=as_of,
        ):
            open_blockers.append("owner_predicate_or_receipt_invalid")
        if owner_gate_attestation_errors(
            scope=scope,
            gate_key="open_prs_closed_or_reaccepted",
            owner_evidence=baseline,
            binding_value=baseline_binding,
        ):
            open_blockers.append("owner_adapter_attestation_invalid")
    open_gate = _gate(
        owner=str(baseline.get("owner") or "github_remote_owner")
        if isinstance(baseline, dict)
        else "github_remote_owner",
        blockers=open_blockers,
        evidence=baseline if isinstance(baseline, dict) else None,
    )

    value = owners.get("session_value")
    value_blockers: list[str] = []
    if not isinstance(value, dict):
        value_blockers.append("owner_evidence_missing")
    else:
        if value.get("attempt_ids") != sorted(attempt_ids):
            value_blockers.append("attempt_denominator_mismatch")
        classifications = {
            str(attempt.get("id")): (
                attempt.get("value", {}).get("classification") if isinstance(attempt.get("value"), dict) else None
            )
            for attempt in attempts
            if isinstance(attempt, dict)
        }
        expected_value_lists = {
            "motion_only_attempt_ids": sorted(
                attempt_id for attempt_id, kind in classifications.items() if kind == "motion_only"
            ),
            "unverifiable_attempt_ids": sorted(
                attempt_id for attempt_id, kind in classifications.items() if kind == "unverifiable"
            ),
            "failed_attempt_ids": sorted(
                attempt_id for attempt_id, kind in classifications.items() if kind == "failed"
            ),
            "uncredited_attempt_ids": sorted(
                attempt_id for attempt_id, kind in classifications.items() if kind != "durable_value"
            ),
            "unreconciled_attempt_ids": sorted(
                attempt_id
                for attempt_id, kind in classifications.items()
                if kind not in {"durable_value", "motion_only", "unverifiable", "failed"}
            ),
        }
        for field, expected in expected_value_lists.items():
            if value.get(field) != expected:
                value_blockers.append(f"{field}_mismatch")
        attempt_registry_digest = _owner_binding_digest(attempts)
        value_receipt = value.get("receipt")
        if (
            value.get("attempt_registry_digest") != attempt_registry_digest
            or not isinstance(value_receipt, dict)
            or value_receipt.get("binding_digest") != attempt_registry_digest
        ):
            value_blockers.append("owner_binding_digest_mismatch")
        if expected_value_lists["unreconciled_attempt_ids"]:
            value_blockers.append("unreconciled_attempt_ids")
        if _owner_receipt_pair_errors(
            value,
            key="session_value",
            label="session value gate",
            as_of=as_of,
        ):
            value_blockers.append("owner_predicate_or_receipt_invalid")
        if owner_gate_attestation_errors(
            scope=scope,
            gate_key="session_value_verified",
            owner_evidence=value,
            binding_value=attempts,
        ):
            value_blockers.append("owner_adapter_attestation_invalid")
    if any(remedy.get("status") == "repair_required" for remedy in remedies if isinstance(remedy, dict)):
        value_blockers.append("unreconciled_remedy_attempt")
    value_gate = _gate(
        owner=str(value.get("owner") or "execution_trajectory_owner")
        if isinstance(value, dict)
        else "execution_trajectory_owner",
        blockers=value_blockers,
        evidence=value if isinstance(value, dict) else None,
    )

    custody = owners.get("inflight_custody")
    custody_blockers: list[str] = []
    if not isinstance(custody, dict):
        custody_blockers.append("owner_evidence_missing")
    else:
        if custody.get("campaign_attempt_ids") != sorted(attempt_ids):
            custody_blockers.append("attempt_denominator_mismatch")
        if custody.get("stale_ids") != []:
            custody_blockers.append("stale_campaign_custody")
        cutoff = custody.get("cutoff_receipt")
        if cutoff != scope.get("cutoff_receipt"):
            custody_blockers.append("immutable_cutoff_scope_mismatch")
        if not isinstance(cutoff, dict) or cutoff.get("status") != "verified":
            custody_blockers.append("immutable_cutoff_not_verified")
        elif (
            cutoff.get("schema") != CUTOFF_SCHEMA
            or not cutoff.get("event_offsets")
            or not _evidence_reference_present(cutoff)
        ):
            custody_blockers.append("immutable_cutoff_receipt_missing")
        custody_binding = {
            "attempt_ids": sorted(attempt_ids),
            "stale_ids": custody.get("stale_ids"),
            "cutoff_digest": _scope_cutoff_digest(scope),
        }
        custody_digest = _owner_binding_digest(custody_binding)
        custody_receipt = custody.get("receipt")
        if (
            custody.get("campaign_attempt_digest") != custody_digest
            or not isinstance(custody_receipt, dict)
            or custody_receipt.get("binding_digest") != custody_digest
        ):
            custody_blockers.append("owner_binding_digest_mismatch")
        if _owner_receipt_pair_errors(
            custody,
            key="inflight_custody",
            label="inflight custody gate",
            as_of=as_of,
        ):
            custody_blockers.append("owner_predicate_or_receipt_invalid")
        if owner_gate_attestation_errors(
            scope=scope,
            gate_key="no_stale_inflight_custody",
            owner_evidence=custody,
            binding_value=custody_binding,
        ):
            custody_blockers.append("owner_adapter_attestation_invalid")
    custody_gate = _gate(
        owner=str(custody.get("owner") or "private_session_corpus_owner")
        if isinstance(custody, dict)
        else "private_session_corpus_owner",
        blockers=custody_blockers,
        evidence=custody if isinstance(custody, dict) else None,
    )

    privacy = owners.get("privacy")
    privacy_blockers: list[str] = []
    if not isinstance(privacy, dict):
        privacy_blockers.append("owner_evidence_missing")
    else:
        affected = privacy.get("affected_row_ids")
        expected_affected = sorted(scope.get("privacy_affected_row_ids") or [])
        expected_content_manifest = scope.get("privacy_content_manifest_digest")
        if affected != expected_affected or any(identifier not in rows_by_id for identifier in expected_affected):
            privacy_blockers.append("affected_rows_denominator_mismatch")
        if not isinstance(expected_content_manifest, str):
            privacy_blockers.append("privacy_content_manifest_not_frozen")
        if privacy.get("content_manifest_digest") != expected_content_manifest:
            privacy_blockers.append("privacy_content_manifest_mismatch")
        if privacy_manifest_binding_errors(privacy, scope):
            privacy_blockers.append("privacy_frozen_manifest_mismatch")
        if privacy.get("current_trees_clean") is not True:
            privacy_blockers.append("current_trees_not_clean")
        copies = privacy.get("private_copy_receipts")
        if not isinstance(copies, list) or len(copies) < 2:
            privacy_blockers.append("two_private_copies_not_verified")
        else:
            copy_ids = []
            custody_ids = []
            content_digests = []
            receipt_identities = []
            for index, receipt in enumerate(copies):
                if _verified_receipt_errors(
                    receipt,
                    label=f"privacy copy {index}",
                    as_of=as_of,
                    schema=PRIVACY_COPY_SCHEMA,
                    max_age=OWNER_EVIDENCE_MAX_AGE,
                ):
                    privacy_blockers.append("private_copy_receipt_invalid")
                if isinstance(receipt, dict):
                    copy_ids.append(receipt.get("copy_id"))
                    custody_ids.append(receipt.get("custody_location_id"))
                    content_digests.append(receipt.get("content_digest"))
                    receipt_identities.append(_evidence_identity(receipt))
            if (
                any(not isinstance(value, str) or not value for value in [*copy_ids, *custody_ids])
                or len(copy_ids) != len(set(copy_ids))
                or len(custody_ids) != len(set(custody_ids))
                or any(identity is None for identity in receipt_identities)
                or _receipt_identity_collides(copies)
            ):
                privacy_blockers.append("private_copies_not_independently_custodied")
            if (
                not content_digests
                or any(not SHA256_DIGEST.fullmatch(str(value or "")) for value in content_digests)
                or len(set(content_digests)) != 1
            ):
                privacy_blockers.append("private_copy_content_mismatch")
            elif content_digests[0] != expected_content_manifest:
                privacy_blockers.append("private_copy_manifest_mismatch")
        history_status = privacy.get("history_status")
        if history_status not in {"not_required", "completed"}:
            privacy_blockers.append("history_action_not_terminal")
        history_required = any(
            "public_history" in effect or "publicly_reachable" in effect
            for row_id in expected_affected
            for effect in scope.get("known_side_effects", {}).get(row_id, [])
        )
        if history_required and history_status != "completed":
            privacy_blockers.append("history_action_required")
        privacy_binding = {
            "affected_row_ids": expected_affected,
            "current_trees_clean": privacy.get("current_trees_clean"),
            "history_status": privacy.get("history_status"),
            "content_manifest_digest": expected_content_manifest,
            "frozen_manifest_digest": privacy.get("frozen_manifest_digest"),
            "copies": [
                {
                    "copy_id": receipt.get("copy_id"),
                    "custody_location_id": receipt.get("custody_location_id"),
                    "content_digest": receipt.get("content_digest"),
                    "receipt_identity": list(_evidence_identity(receipt) or ()),
                }
                for receipt in copies
                if isinstance(receipt, dict)
            ]
            if isinstance(copies, list)
            else [],
        }
        privacy_digest = _owner_binding_digest(privacy_binding)
        privacy_receipt = privacy.get("receipt")
        if (
            privacy.get("privacy_denominator_digest") != privacy_digest
            or not isinstance(privacy_receipt, dict)
            or privacy_receipt.get("binding_digest") != privacy_digest
        ):
            privacy_blockers.append("owner_binding_digest_mismatch")
        if _owner_receipt_pair_errors(
            privacy,
            key="privacy",
            label="privacy gate",
            as_of=as_of,
        ):
            privacy_blockers.append("owner_predicate_or_receipt_invalid")
        if owner_gate_attestation_errors(
            scope=scope,
            gate_key="privacy_containment_terminal",
            owner_evidence=privacy,
            binding_value=privacy_binding,
        ):
            privacy_blockers.append("owner_adapter_attestation_invalid")
    privacy_gate = _gate(
        owner=str(privacy.get("owner") or "private_privacy_custody_owner")
        if isinstance(privacy, dict)
        else "private_privacy_custody_owner",
        blockers=privacy_blockers,
        evidence=privacy if isinstance(privacy, dict) else None,
    )

    continuation = owners.get("continuation")
    continuation_blockers: list[str] = []
    if not isinstance(continuation, dict):
        continuation_blockers.append("owner_evidence_missing")
    else:
        if not isinstance(continuation.get("capsule"), dict) or not _evidence_reference_present(
            continuation["capsule"]
        ):
            continuation_blockers.append("durable_capsule_missing")
        if not isinstance(continuation.get("launch_command"), str) or not continuation["launch_command"].strip():
            continuation_blockers.append("launch_command_missing")
        if _owner_receipt_pair_errors(
            continuation,
            key="continuation",
            label="continuation gate",
            as_of=as_of,
        ):
            continuation_blockers.append("owner_predicate_or_receipt_invalid")
    if len(refresh_history) < 2:
        continuation_blockers.append("two_refreshes_required")
    else:
        last_two = refresh_history[-2:]
        if last_two[0].get("evidence_digest") != last_two[1].get("evidence_digest") or not SHA256_DIGEST.fullmatch(
            str(last_two[0].get("evidence_digest") or "")
        ):
            continuation_blockers.append("normalized_evidence_changed")
        first = _parse_timestamp(last_two[0].get("refreshed_at"))
        second = _parse_timestamp(last_two[1].get("refreshed_at"))
        if first is None or second is None or second <= first:
            continuation_blockers.append("refresh_order_invalid")
        elif (
            as_of is None
            or first > as_of + dt.timedelta(minutes=5)
            or second > as_of + dt.timedelta(minutes=5)
            or as_of - first > OWNER_EVIDENCE_MAX_AGE
            or as_of - second > OWNER_EVIDENCE_MAX_AGE
        ):
            continuation_blockers.append("refresh_events_stale")
        receipts = continuation.get("refresh_receipts") if isinstance(continuation, dict) else None
        if not isinstance(receipts, list) or len(receipts) != 2:
            continuation_blockers.append("owner_refresh_receipts_required")
        else:
            receipt_identities = []
            for index, (refresh, receipt) in enumerate(zip(last_two, receipts, strict=True)):
                receipt_errors = _verified_receipt_errors(
                    receipt,
                    label=f"refresh receipt {index}",
                    as_of=as_of,
                    schema=REFRESH_RECEIPT_SCHEMA,
                    max_age=OWNER_EVIDENCE_MAX_AGE,
                )
                if receipt_errors:
                    continuation_blockers.append("owner_refresh_receipt_invalid")
                if isinstance(receipt, dict):
                    if receipt.get("evidence_digest") != refresh.get("evidence_digest"):
                        continuation_blockers.append("owner_refresh_digest_mismatch")
                    if receipt.get("refreshed_at") != refresh.get("refreshed_at"):
                        continuation_blockers.append("owner_refresh_time_mismatch")
                    receipt_identities.append(_evidence_identity(receipt))
            if any(identity is None for identity in receipt_identities) or _receipt_identity_collides(receipts):
                continuation_blockers.append("owner_refresh_receipts_not_distinct")
    if isinstance(continuation, dict):
        continuation_binding = {
            "capsule": continuation.get("capsule"),
            "launch_command": continuation.get("launch_command"),
            "refresh_history": copy.deepcopy(refresh_history[-2:]),
            "refresh_receipt_identities": [
                list(_evidence_identity(receipt) or ())
                for receipt in continuation.get("refresh_receipts", [])
                if isinstance(receipt, dict)
            ],
        }
        continuation_digest = _owner_binding_digest(continuation_binding)
        continuation_receipt = continuation.get("receipt")
        if (
            continuation.get("continuation_digest") != continuation_digest
            or not isinstance(continuation_receipt, dict)
            or continuation_receipt.get("binding_digest") != continuation_digest
        ):
            continuation_blockers.append("owner_binding_digest_mismatch")
        if owner_gate_attestation_errors(
            scope=scope,
            gate_key="continuation_fixed_point",
            owner_evidence=continuation,
            binding_value=continuation_binding,
        ):
            continuation_blockers.append("owner_adapter_attestation_invalid")
    continuation_gate = _gate(
        owner=str(continuation.get("owner") or "limen_reacceptance_owner")
        if isinstance(continuation, dict)
        else "limen_reacceptance_owner",
        blockers=continuation_blockers,
        evidence=continuation if isinstance(continuation, dict) else None,
    )

    return {
        "open_prs_closed_or_reaccepted": open_gate,
        "session_value_verified": value_gate,
        "no_stale_inflight_custody": custody_gate,
        "privacy_containment_terminal": privacy_gate,
        "continuation_fixed_point": continuation_gate,
    }


def validate_document(document: dict[str, Any], scope: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    refreshed_at = _parse_timestamp(document.get("refreshed_at"))
    if refreshed_at is None:
        errors.append("refreshed_at must be an ISO-8601 timestamp with timezone")
    if document.get("scope") != _document_scope(scope):
        errors.append("document scope does not match the frozen v2 scope")

    rows_raw = document.get("rows")
    if not isinstance(rows_raw, list):
        return errors + ["rows must be a list"]
    rows, row_id_errors = _id_map(rows_raw, label="rows")
    errors.extend(row_id_errors)
    if set(rows) != _expected_row_ids(scope):
        errors.append("row IDs do not match the frozen 105-row denominator")
    expected_counts = {
        "session": len(scope["sessions"]),
        "workflow": len(scope["workflows"]),
        "pull_request": len(expand_prs(scope)),
    }
    actual_counts = {kind: sum(row.get("kind") == kind for row in rows.values()) for kind in expected_counts}
    if actual_counts != expected_counts:
        errors.append(f"row denominator mismatch: expected {expected_counts}, got {actual_counts}")
    legacy_rows: list[dict[str, Any]] = []
    for row_id, row in rows.items():
        legacy = row.get("legacy_v1")
        if not isinstance(legacy, dict):
            errors.append(f"row {row_id} must embed its complete frozen legacy_v1 payload")
            continue
        if (
            legacy.get("id") != row_id
            or legacy.get("kind") != row.get("kind")
            or legacy.get("session") != row.get("session")
        ):
            errors.append(f"row {row_id} legacy_v1 identity does not match")
        legacy_rows.append(legacy)
    if len(legacy_rows) == len(rows) and _legacy_v1_rows_digest(legacy_rows) != scope["legacy_v1_rows_digest"]:
        errors.append("embedded legacy_v1 rows do not match the frozen v1 denominator digest")

    attempts_raw = document.get("attempts")
    attempts, attempt_id_errors = _id_map(attempts_raw, label="attempts")
    errors.extend(attempt_id_errors)
    for attempt in attempts.values():
        errors.extend(
            _attempt_errors(
                attempt,
                as_of=refreshed_at,
                scope=scope,
                known_effect_owners=scope["known_side_effect_owners"],
            )
        )
    attempt_receipt_values = [attempt.get("receipt") for attempt in attempts.values()]
    if attempt_receipt_values and _receipt_identity_collides(attempt_receipt_values):
        errors.append("attempt execution receipts must be unique across the registry")
    trajectory_identities = [
        (
            str(attempt.get("executor", {}).get("session")) if isinstance(attempt.get("executor"), dict) else "",
            _evidence_identity(attempt.get("trajectory_receipt")),
        )
        for attempt in attempts.values()
    ]
    if any(not session or identity is None for session, identity in trajectory_identities):
        errors.append("attempt trajectory identities must bind an executor session and owner receipt")
    spend_receipt_values = [
        attempt.get("spend", {}).get("receipt") if isinstance(attempt.get("spend"), dict) else None
        for attempt in attempts.values()
    ]
    if any(not _evidence_identity_atoms(receipt) for receipt in spend_receipt_values):
        errors.append("attempt spend receipts must be owner-addressable")
    elif _receipt_identity_collides(spend_receipt_values):
        errors.append("attempt spend receipts must be unique across the registry")
    receipt_roles = {
        "source": [attempt.get("source_receipt") for attempt in attempts.values()],
        "trajectory": [attempt.get("trajectory_receipt") for attempt in attempts.values()],
        "spend": [
            attempt.get("spend", {}).get("receipt") if isinstance(attempt.get("spend"), dict) else None
            for attempt in attempts.values()
        ],
        "side-effect": [
            attempt.get("side_effects", {}).get("receipt") if isinstance(attempt.get("side_effects"), dict) else None
            for attempt in attempts.values()
        ],
        "execution": [attempt.get("receipt") for attempt in attempts.values()],
        "value": [
            attempt.get("value", {}).get("receipt") if isinstance(attempt.get("value"), dict) else None
            for attempt in attempts.values()
        ],
    }
    all_attempt_receipts: list[Any] = []
    for role, receipts in receipt_roles.items():
        if any(not _evidence_identity_atoms(receipt) for receipt in receipts):
            errors.append(f"attempt {role} receipts must be owner-addressable")
            continue
        all_attempt_receipts.extend(receipts)
        if _receipt_identity_collides(receipts):
            errors.append(f"attempt {role} receipts must be unique across the registry")
    if all_attempt_receipts and _receipt_identity_collides(all_attempt_receipts):
        errors.append("attempt evidence receipts cannot be reused across roles or attempts")

    remedies_raw = document.get("remedies")
    remedies, remedy_id_errors = _id_map(remedies_raw, label="remedies")
    errors.extend(remedy_id_errors)
    for remedy in remedies.values():
        errors.extend(
            _remedy_errors(
                remedy,
                attempts=attempts,
                as_of=refreshed_at,
                expected_review_gate_app_slug=scope.get("review_gate_app_slug"),
            )
        )
    referenced_attempt_ids = {
        attempt_id
        for item in [*rows.values(), *remedies.values()]
        for attempt_id in item.get("attempt_ids", [])
        if isinstance(attempt_id, str)
    }
    orphan_attempts = sorted(set(attempts) - referenced_attempt_ids)
    if orphan_attempts:
        errors.append(f"attempt registry contains orphan attempts: {', '.join(orphan_attempts)}")

    findings_raw = document.get("findings")
    findings, finding_id_errors = _id_map(findings_raw, label="findings")
    errors.extend(finding_id_errors)
    finding_scope = scope["findings"]
    if len(findings) != finding_scope["total"]:
        errors.append(f"finding denominator mismatch: expected {finding_scope['total']}, got {len(findings)}")
    severity_counts = {
        severity: sum(finding.get("severity") == severity for finding in findings.values())
        for severity in ("p1", "p2", "unclassified")
    }
    expected_severity_counts = {severity: finding_scope[severity] for severity in ("p1", "p2", "unclassified")}
    if severity_counts != expected_severity_counts:
        errors.append(
            f"finding severity denominator mismatch: expected {expected_severity_counts}, got {severity_counts}"
        )
    if _discussion_url_digest(list(findings.values())) != finding_scope["discussion_url_digest"]:
        errors.append("finding discussion URL denominator does not match the frozen digest")
    if _finding_manifest_digest(findings.values()) != finding_scope["manifest_digest"]:
        errors.append("finding row/severity crosswalk does not match the frozen manifest")
    finding_urls = [
        finding.get("discussion_url") for finding in findings.values() if isinstance(finding.get("discussion_url"), str)
    ]
    if len(finding_urls) != len(set(finding_urls)):
        errors.append("finding discussion URLs must be unique")

    coverage_raw = document.get("coverage")
    coverage, coverage_id_errors = _id_map(coverage_raw, label="coverage")
    errors.extend(coverage_id_errors)
    coverage_values = list(coverage.values())
    coverage_tuples = [
        (
            item.get("historical_row_id"),
            item.get("finding_id"),
            item.get("remedy_id"),
            item.get("disposition"),
        )
        for item in coverage_values
    ]
    if len(coverage_tuples) != len(set(coverage_tuples)):
        errors.append("coverage entries must not duplicate the same row/finding/remedy/disposition")
    for item in coverage_values:
        errors.extend(
            _coverage_errors(
                item,
                rows=rows,
                remedies=remedies,
                findings=findings,
                as_of=refreshed_at,
            )
        )

    source_references_by_row: dict[str, list[str]] = {}
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        missing = sorted(REQUIRED_ROW_KEYS - set(row))
        if missing:
            errors.append(f"row {index} missing keys: {', '.join(missing)}")
        if row.get("disposition") not in ALLOWED_DISPOSITIONS:
            errors.append(f"row {index} has invalid disposition {row.get('disposition')!r}")
        if row.get("kind") == "pull_request" and (
            not isinstance(row.get("exact_head"), str) or not FULL_HEAD.fullmatch(row["exact_head"])
        ):
            errors.append(f"row {index} pull request has no full exact_head")
        source = row.get("source_ask")
        if not isinstance(source, dict) or not isinstance(source.get("references"), list):
            errors.append(f"row {index} source ask must keep redacted references")
        elif any(not isinstance(reference, str) or not reference for reference in source["references"]):
            errors.append(f"row {index} source ask references must be non-empty strings")
        elif isinstance(row.get("id"), str):
            source_references_by_row[row["id"]] = source["references"]
        findings_snapshot = row.get("review_findings")
        if not isinstance(findings_snapshot, dict):
            errors.append(f"row {index} review_findings must be an object")
        else:
            counts: list[int] = []
            for field in ("p1", "p2", "unclassified"):
                value = findings_snapshot.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(f"row {index} review_findings.{field} must be non-negative")
                else:
                    counts.append(value)
            if len(counts) == 3 and findings_snapshot.get("unresolved_current") != sum(counts):
                errors.append(f"row {index} unresolved_current does not match classified debt")
        errors.extend(
            _terminal_row_errors(
                row,
                attempts=attempts,
                remedies=remedies,
                coverage=coverage_values,
                known_side_effects=scope["known_side_effects"],
                as_of=refreshed_at,
            )
        )
    if set(source_references_by_row) == set(rows):
        source_manifest_digest = _source_reference_manifest_digest(source_references_by_row)
        if source_manifest_digest != scope["source_reference_manifest_digest"]:
            errors.append("row source asks do not match the frozen row-anchored source manifest")
    for finding in findings.values():
        errors.extend(
            _finding_errors(
                finding,
                rows=rows,
                remedies=remedies,
                coverage=coverage_values,
            )
        )

    owner_evidence = document.get("owner_evidence")
    if not isinstance(owner_evidence, dict) or set(owner_evidence) != OWNER_EVIDENCE_KEYS:
        errors.append(f"owner_evidence keys must be exactly {sorted(OWNER_EVIDENCE_KEYS)}")

    refresh_history = document.get("refresh_history")
    if not isinstance(refresh_history, list) or not refresh_history:
        errors.append("refresh_history must contain at least one complete refresh")
        refresh_history_values: list[dict[str, Any]] = []
    else:
        refresh_history_values = []
        for index, item in enumerate(refresh_history):
            if not isinstance(item, dict):
                errors.append(f"refresh_history[{index}] must be an object")
                continue
            if _parse_timestamp(item.get("refreshed_at")) is None:
                errors.append(f"refresh_history[{index}] refreshed_at is invalid")
            if not SHA256_DIGEST.fullmatch(str(item.get("evidence_digest") or "")):
                errors.append(f"refresh_history[{index}] evidence_digest is invalid")
            refresh_history_values.append(item)
        if len(refresh_history_values) > 2:
            errors.append("refresh_history retains only the two most recent complete refreshes")

    try:
        calculated_digest = normalized_evidence_digest(document)
    except (TypeError, ValueError):
        calculated_digest = ""
        errors.append("normalized evidence contains non-finite or non-JSON values")
    if calculated_digest:
        if document.get("evidence_digest") != calculated_digest:
            errors.append(f"evidence_digest must be derived from normalized evidence: expected {calculated_digest}")
        if refresh_history_values and refresh_history_values[-1].get("evidence_digest") != calculated_digest:
            errors.append("latest refresh_history digest does not match current normalized evidence")

    derived_gates = _derive_completion_gates(
        scope=scope,
        rows=rows_raw,
        attempts=attempts_raw if isinstance(attempts_raw, list) else [],
        remedies=remedies_raw if isinstance(remedies_raw, list) else [],
        findings=findings_raw if isinstance(findings_raw, list) else [],
        owner_evidence=owner_evidence,
        refresh_history=refresh_history_values,
        as_of=refreshed_at,
    )
    if document.get("completion_gates") != derived_gates:
        errors.append("completion_gates must be derived from owner evidence and normalized registries")
    expected_summary = _summary_for(
        rows=rows_raw,
        attempts=attempts_raw if isinstance(attempts_raw, list) else [],
        remedies=remedies_raw if isinstance(remedies_raw, list) else [],
        findings=findings_raw if isinstance(findings_raw, list) else [],
        completion_gates=derived_gates,
    )
    if document.get("summary") != expected_summary:
        errors.append(f"summary must be derived from normalized evidence: expected {expected_summary}")
    return errors
