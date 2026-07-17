"""Migration and refresh transforms for the recovery reacceptance ledger."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
from functools import partial
from typing import Any

from limen.reacceptance_contract import (
    SCHEMA,
    TERMINAL_DISPOSITIONS,
    V1_SCHEMA,
    LedgerError,
    _base_row,
    _default_owner_evidence,
    _discussion_url_digest,
    _document_scope,
    _expected_row_ids,
    _finding_manifest_digest,
    _parse_timestamp,
    _summary_for,
    expand_prs,
    normalized_evidence_digest,
    utc_now,
)
from limen.reacceptance_github import _pr_row, _refresh_remedy
from limen.reacceptance_policy import _derive_completion_gates, validate_document


REMOTE_RECEIPT_KEYS = {
    "status",
    "url",
    "merge_commit",
    "review_decision",
    "draft",
    "merged_at",
    "closed_at",
}


def _finalize_document(
    document: dict[str, Any],
    *,
    scope: dict[str, Any],
    previous_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    document["schema"] = SCHEMA
    document["scope"] = _document_scope(scope)
    digest = normalized_evidence_digest(document)
    document["evidence_digest"] = digest
    history = copy.deepcopy(previous_history or [])
    history.append({"refreshed_at": document["refreshed_at"], "evidence_digest": digest})
    document["refresh_history"] = history[-2:]
    as_of = _parse_timestamp(document["refreshed_at"])
    gates = _derive_completion_gates(
        scope=scope,
        rows=document["rows"],
        attempts=document["attempts"],
        remedies=document["remedies"],
        findings=document["findings"],
        owner_evidence=document["owner_evidence"],
        refresh_history=document["refresh_history"],
        as_of=as_of,
    )
    document["completion_gates"] = gates
    document["summary"] = _summary_for(
        rows=document["rows"],
        attempts=document["attempts"],
        remedies=document["remedies"],
        findings=document["findings"],
        completion_gates=gates,
    )
    return document


def build_live_release_candidate(
    scope: dict[str, Any],
    *,
    previous_document: dict[str, Any],
    workers: int = 8,
) -> dict[str, Any]:
    """Refresh owner reads without manufacturing a new fixed-point attestation.

    Release checking is read-only.  It must recompute every policy gate from
    live GitHub state while retaining the two refresh records and owner
    attestations that the tracked candidate actually claims.
    """

    live = build_document(
        scope,
        previous_document=previous_document,
        workers=workers,
    )
    live["refreshed_at"] = previous_document["refreshed_at"]
    live["refresh_history"] = copy.deepcopy(previous_document["refresh_history"])
    live["evidence_digest"] = normalized_evidence_digest(live)
    as_of = _parse_timestamp(live["refreshed_at"])
    gates = _derive_completion_gates(
        scope=scope,
        rows=live["rows"],
        attempts=live["attempts"],
        remedies=live["remedies"],
        findings=live["findings"],
        owner_evidence=live["owner_evidence"],
        refresh_history=live["refresh_history"],
        as_of=as_of,
    )
    live["completion_gates"] = gates
    live["summary"] = _summary_for(
        rows=live["rows"],
        attempts=live["attempts"],
        remedies=live["remedies"],
        findings=live["findings"],
        completion_gates=gates,
    )
    return live


def _migrate_source_ask(value: Any, *, fallback: str) -> dict[str, Any]:
    if isinstance(value, dict):
        reference = value.get("reference")
        owner = value.get("private_owner")
    else:
        reference = None
        owner = None
    return {
        "status": "unreconciled",
        "references": [str(reference or fallback)],
        "private_owner": str(owner or "private_prompt_corpus_owner"),
        "lineage_digest": None,
        "receipt": None,
    }


def _migrate_v1_row(row: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(row)
    identifier = str(row.get("id") or "")
    migrated["legacy_v1"] = copy.deepcopy(row)
    migrated.pop("spend", None)
    migrated["source_ask"] = _migrate_source_ask(
        row.get("source_ask"),
        fallback=f"private_prompt_corpus:{identifier}:unreconciled",
    )
    migrated["attempt_ids"] = []
    migrated["outputs"] = {"status": "unreconciled", "attempt_ids": []}
    previous_effects = row.get("side_effects")
    observed = (
        copy.deepcopy(previous_effects.get("observed"))
        if isinstance(previous_effects, dict) and isinstance(previous_effects.get("observed"), list)
        else []
    )
    migrated["side_effects"] = {
        "status": "unreconciled",
        "attempt_ids": [],
        "observed": observed,
        "replay_authorized": False,
        "receipt": None,
    }
    keeper = row.get("keeper")
    owner_surface = keeper.get("owner_surface") if isinstance(keeper, dict) else None
    migrated["owner_surfaces"] = [owner_surface] if isinstance(owner_surface, str) and owner_surface else []
    review_findings = migrated.get("review_findings")
    if isinstance(review_findings, dict):
        for field in ("p1", "p2", "unclassified"):
            if not isinstance(review_findings.get(field), int) or isinstance(review_findings.get(field), bool):
                review_findings[field] = 0
        review_findings["unresolved_current"] = sum(review_findings[field] for field in ("p1", "p2", "unclassified"))
    migrated["disposition"] = "repair_required"
    migrated["predicate"] = {
        "status": "not_verified",
        "command": None,
        "requirement": "reconcile source, attempts, spend, outputs, effects, predicate, and receipt",
    }
    receipt = migrated.get("receipt")
    if isinstance(receipt, dict):
        receipt.pop("adjudication", None)
        receipt.pop("adjudication_note", None)
    return migrated


def _finding_id(url: str) -> str:
    return "finding:sha256:" + hashlib.sha256(url.encode()).hexdigest()


def _migrate_v1_findings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in rows:
        snapshot = row.get("review_findings")
        if not isinstance(snapshot, dict):
            continue
        urls = snapshot.get("urls")
        if not isinstance(urls, list):
            continue
        p1 = int(snapshot.get("p1") or 0)
        p2 = int(snapshot.get("p2") or 0)
        unclassified = int(snapshot.get("unclassified") or 0)
        severities = ["p1"] * p1 + ["p2"] * p2 + ["unclassified"] * unclassified
        if len(urls) != len(severities):
            raise LedgerError(f"v1 row {row.get('id')} finding URLs do not match classified counts")
        for url, severity in zip(urls, severities, strict=True):
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                raise LedgerError(f"v1 row {row.get('id')} contains an invalid finding URL")
            findings.append(
                {
                    "id": _finding_id(url),
                    "historical_row_id": row["id"],
                    "discussion_url": url,
                    "severity": severity,
                    "current_status": "unresolved",
                    "disposition": "repair_required",
                }
            )
    findings.sort(key=lambda item: item["id"])
    return findings


def migrate_v1_document(
    previous: dict[str, Any],
    scope: dict[str, Any],
    *,
    refreshed_at: str | None = None,
) -> dict[str, Any]:
    if previous.get("schema") != V1_SCHEMA:
        raise LedgerError(f"migration source schema must be {V1_SCHEMA}")
    raw_rows = previous.get("rows")
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) for row in raw_rows):
        raise LedgerError("v1 migration source rows are invalid")
    if {str(row.get("id")) for row in raw_rows} != _expected_row_ids(scope):
        raise LedgerError("v1 migration source does not match the frozen 105-row denominator")
    findings = _migrate_v1_findings(raw_rows)
    if len(findings) != scope["findings"]["total"]:
        raise LedgerError("v1 migration source does not preserve the frozen finding denominator")
    if len({finding["id"] for finding in findings}) != len(findings):
        raise LedgerError("v1 migration source contains duplicate finding URLs")
    if _discussion_url_digest(findings) != scope["findings"]["discussion_url_digest"]:
        raise LedgerError("v1 migration finding digest does not match scope")
    if _finding_manifest_digest(findings) != scope["findings"]["manifest_digest"]:
        raise LedgerError("v1 migration finding row/severity manifest does not match scope")
    migrated_rows = sorted((_migrate_v1_row(row) for row in raw_rows), key=lambda item: item["id"])
    document = {
        "schema": SCHEMA,
        "refreshed_at": refreshed_at or str(previous.get("refreshed_at") or utc_now()),
        "scope": _document_scope(scope),
        "rows": migrated_rows,
        "attempts": [],
        "remedies": [],
        "coverage": [],
        "findings": findings,
        "owner_evidence": _default_owner_evidence(scope),
    }
    return _finalize_document(document, scope=scope)


def _row_has_adjudication(row: dict[str, Any]) -> bool:
    if row.get("disposition") in TERMINAL_DISPOSITIONS:
        return True
    predicate = row.get("predicate")
    if isinstance(predicate, dict) and predicate.get("status") == "verified":
        return True
    receipt = row.get("receipt")
    adjudication = receipt.get("adjudication") if isinstance(receipt, dict) else None
    return isinstance(adjudication, dict) and adjudication.get("status") == "verified"


def _merge_refreshed_row(fresh: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    identifier = str(fresh.get("id") or "")
    if identifier != previous.get("id") or fresh.get("kind") != previous.get("kind"):
        raise LedgerError(f"stable row identity conflict for {identifier}")
    if fresh.get("session") != previous.get("session"):
        raise LedgerError(f"stable row session conflict for {identifier}")
    old_head = previous.get("exact_head")
    new_head = fresh.get("exact_head")
    if fresh.get("kind") == "pull_request" and old_head != new_head and _row_has_adjudication(previous):
        raise LedgerError(f"adjudicated row {identifier} is stale: exact head changed from {old_head} to {new_head}")
    if fresh.get("kind") == "pull_request" and previous.get("disposition") == "accepted":
        current = fresh.get("review_findings")
        if not isinstance(current, dict) or current.get("unresolved_current") != 0:
            raise LedgerError(f"accepted row {identifier} is stale: current review debt changed")
    merged = copy.deepcopy(fresh)
    for field in (
        "source_ask",
        "attempt_ids",
        "outputs",
        "side_effects",
        "owner_surfaces",
        "predicate",
        "disposition",
    ):
        merged[field] = copy.deepcopy(previous.get(field))
    if fresh.get("kind") != "pull_request":
        merged["exact_head"] = copy.deepcopy(previous.get("exact_head"))
        merged["receipt"] = copy.deepcopy(previous.get("receipt"))
        merged["keeper"] = copy.deepcopy(previous.get("keeper"))
    else:
        fresh_receipt = fresh.get("receipt") if isinstance(fresh.get("receipt"), dict) else {}
        old_receipt = previous.get("receipt") if isinstance(previous.get("receipt"), dict) else {}
        merged_receipt = copy.deepcopy(fresh_receipt)
        merged_receipt.update(
            {key: copy.deepcopy(value) for key, value in old_receipt.items() if key not in REMOTE_RECEIPT_KEYS}
        )
        merged["receipt"] = merged_receipt
        old_keeper = previous.get("keeper") if isinstance(previous.get("keeper"), dict) else {}
        fresh_keeper = fresh.get("keeper") if isinstance(fresh.get("keeper"), dict) else {}
        merged_keeper = copy.deepcopy(old_keeper)
        merged_keeper.update(
            {
                key: copy.deepcopy(value)
                for key, value in fresh_keeper.items()
                if key in {"github_author", "owner_surface"}
            }
        )
        merged["keeper"] = merged_keeper
    for key, value in previous.items():
        if key not in merged:
            merged[key] = copy.deepcopy(value)
    return merged


def _refresh_findings(
    previous_findings: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    live_threads: dict[str, dict[str, Any]] = {}
    for row in rows:
        threads = row.get("review_threads")
        if not isinstance(threads, list):
            continue
        for thread in threads:
            if isinstance(thread, dict) and isinstance(thread.get("discussion_url"), str):
                live_threads[thread["discussion_url"]] = thread
    refreshed: list[dict[str, Any]] = []
    for finding in previous_findings:
        item = copy.deepcopy(finding)
        thread = live_threads.get(str(item.get("discussion_url")))
        if thread is None:
            item["current_status"] = "unavailable"
        else:
            if thread.get("severity") != item.get("severity"):
                raise LedgerError(f"finding severity drift for {item.get('id')}")
            if thread.get("outdated") is True:
                item["current_status"] = "outdated"
            elif thread.get("resolved") is True:
                item["current_status"] = "resolved"
            else:
                item["current_status"] = "unresolved"
        refreshed.append(item)
    return sorted(refreshed, key=lambda item: item["id"])


def build_document(
    scope: dict[str, Any],
    *,
    previous_document: dict[str, Any],
    workers: int = 8,
    refreshed_at: str | None = None,
) -> dict[str, Any]:
    previous_errors = validate_document(previous_document, scope)
    if previous_errors:
        raise LedgerError("cannot refresh invalid prior ledger: " + "; ".join(previous_errors))
    rows = [_base_row("session", identifier) for identifier in sorted(scope["sessions"])]
    rows.extend(_base_row("workflow", identifier) for identifier in sorted(scope["workflows"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        rows.extend(
            executor.map(
                partial(_pr_row, known_side_effects=scope["known_side_effects"]),
                expand_prs(scope),
            )
        )
        remedies = list(executor.map(_refresh_remedy, previous_document["remedies"]))
    rows.sort(key=lambda item: item["id"])
    previous_rows = {str(row["id"]): row for row in previous_document["rows"] if isinstance(row, dict)}
    if set(previous_rows) != {str(row["id"]) for row in rows}:
        raise LedgerError("prior ledger conflicts with the frozen refresh denominator")
    rows = [_merge_refreshed_row(row, previous_rows[str(row["id"])]) for row in rows]
    findings = _refresh_findings(previous_document["findings"], rows)
    document = {
        "schema": SCHEMA,
        "refreshed_at": refreshed_at or utc_now(),
        "scope": _document_scope(scope),
        "rows": rows,
        "attempts": copy.deepcopy(previous_document["attempts"]),
        "remedies": remedies,
        "coverage": copy.deepcopy(previous_document["coverage"]),
        "findings": findings,
        "owner_evidence": copy.deepcopy(previous_document["owner_evidence"]),
    }
    return _finalize_document(
        document,
        scope=scope,
        previous_history=previous_document.get("refresh_history"),
    )
