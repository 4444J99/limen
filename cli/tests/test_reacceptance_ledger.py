import copy
import datetime as dt
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reacceptance-ledger.py"
SPEC = importlib.util.spec_from_file_location("reacceptance_ledger", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
OWNER_FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "reacceptance_owner_fixtures",
    Path(__file__).with_name("test_reacceptance_owners.py"),
)
assert OWNER_FIXTURE_SPEC and OWNER_FIXTURE_SPEC.loader
OWNER_FIXTURES = importlib.util.module_from_spec(OWNER_FIXTURE_SPEC)
OWNER_FIXTURE_SPEC.loader.exec_module(OWNER_FIXTURES)

T1 = "2026-07-16T20:00:00Z"
T2 = "2026-07-16T20:01:00Z"
HEAD = "a" * 40
NEW_HEAD = "b" * 40
SESSION_ID = "claude-session-sha256:" + "a" * 20
WORKFLOW_ID = "claude-workflow-sha256:" + "b" * 20
PR_IDS = [f"pull_request:example/repo#{number}" for number in range(1, 6)]
FINDING_URLS = [
    "https://example.invalid/review/thread-p1",
    "https://example.invalid/review/thread-p2",
]


def _digest_urls(urls):
    return "sha256:" + hashlib.sha256("\n".join(sorted(urls)).encode()).hexdigest()


def scope():
    source_references = {
        f"session:{SESSION_ID}": [f"private_prompt_corpus:{SESSION_ID}"],
        f"workflow:{WORKFLOW_ID}": [f"private_prompt_corpus:{WORKFLOW_ID}"],
        **{row_id: [f"private_prompt_corpus:example/repo#{number}"] for number, row_id in enumerate(PR_IDS, start=1)},
    }
    frozen_findings = [
        {
            "discussion_url": FINDING_URLS[0],
            "historical_row_id": PR_IDS[0],
            "severity": "p1",
        },
        {
            "discussion_url": FINDING_URLS[1],
            "historical_row_id": PR_IDS[1],
            "severity": "p2",
        },
    ]
    return {
        "schema": MODULE.SCOPE_SCHEMA,
        "review_gate_app_slug": "keeper-gate",
        "boundary": {"starts_at": "2026-07-12T15:37:35Z"},
        "cutoff_receipt": {
            "schema": MODULE.CUTOFF_SCHEMA,
            "status": "verified",
            "owner": "private_prompt_corpus_owner",
            "event_offsets": ["event-offset:fixture:0001"],
            "digest": MODULE._event_offsets_digest(["event-offset:fixture:0001"]),
            "verified_at": T1,
        },
        "sessions": [SESSION_ID],
        "workflows": [WORKFLOW_ID],
        "pull_requests": [{"repository": "example/repo", "numbers": list(range(1, 6))}],
        "baseline_open_prs": list(PR_IDS),
        "privacy_affected_row_ids": [PR_IDS[0]],
        "privacy_content_manifest_digest": "sha256:" + "e" * 64,
        "known_side_effects": {
            PR_IDS[0]: ["privacy_material_publicly_reachable"],
        },
        "known_side_effect_owners": {
            PR_IDS[0]: {
                "privacy_material_publicly_reachable": "private_privacy_custody_owner",
            },
        },
        "source_reference_manifest_digest": MODULE._source_reference_manifest_digest(source_references),
        "legacy_v1_rows_digest": "sha256:" + "f" * 64,
        "owner_attestation_requirements": copy.deepcopy(OWNER_FIXTURES._scope()["owner_attestation_requirements"]),
        "findings": {
            "p1": 1,
            "p2": 1,
            "unclassified": 0,
            "total": 2,
            "discussion_url_digest": _digest_urls(FINDING_URLS),
            "manifest_digest": MODULE._finding_manifest_digest(frozen_findings),
        },
    }


def receipt(url, *, exact_head=None, disposition=None, schema=None, **extra):
    value = {
        "status": "verified",
        "url": url,
        "verified_at": T2,
        **extra,
    }
    if exact_head is not None:
        value["exact_head"] = exact_head
    if disposition is not None:
        value["disposition"] = disposition
    if schema is not None:
        value["schema"] = schema
    return value


def predicate(*, exact_head=None, schema=None):
    value = {
        "status": "verified",
        "result": "passed",
        "command": "scripts/verify-scoped.sh",
        "verified_at": T2,
    }
    if exact_head is not None:
        value["exact_head"] = exact_head
    if schema is not None:
        value["schema"] = schema
    return value


def attested_effect_outcome(outcome, *, subject_id):
    payload = OWNER_FIXTURES.effect_owner_attestation_payload(
        subject_id=subject_id,
        historical_row_ids=outcome["historical_row_ids"],
        effect=outcome["effect"],
        owner_surface=outcome["owner_surface"],
        status=outcome["status"],
        outcome=outcome["outcome"],
        predicate=outcome["predicate"],
        receipt=outcome["receipt"],
    )
    outcome["owner_attestation"] = {
        "schema": OWNER_FIXTURES.EFFECT_OWNER_ATTESTATION_SCHEMA,
        "algorithm": OWNER_FIXTURES.RSA_SHA256_PKCS1_V1_5,
        "key_id": "fixture-effect-owner-key-2026",
        "payload": payload,
        "signature": OWNER_FIXTURES._effect_sign(OWNER_FIXTURES.canonical_effect_owner_attestation_payload(payload)),
    }
    return outcome


def sign_owner_evidence(owner, *, gate_key, binding_value):
    requirement = scope()["owner_attestation_requirements"]["gates"][gate_key]
    owner["owner"] = requirement["owner"]
    owner["predicate"]["command"] = requirement["predicate_command"]
    payload = OWNER_FIXTURES.owner_attestation_payload(
        gate_key=gate_key,
        owner=owner["owner"],
        binding_digest=OWNER_FIXTURES.owner_binding_digest(binding_value),
        predicate=owner["predicate"],
        receipt=owner["receipt"],
    )
    owner["attestation"] = {
        "schema": OWNER_FIXTURES.OWNER_ATTESTATION_SCHEMA,
        "algorithm": OWNER_FIXTURES.RSA_SHA256_PKCS1_V1_5,
        "key_id": "fixture-owner-key-2026",
        "payload": payload,
        "signature": OWNER_FIXTURES._sign(OWNER_FIXTURES.canonical_owner_attestation_payload(payload)),
    }


def review_gate(*, head=HEAD, repository="example/remedies", number=99):
    return {
        "schema": MODULE.REVIEW_GATE_SCHEMA,
        "status": "accepted",
        "final_status": "accepted",
        "ok": True,
        "evaluated_at": T2,
        "repository": repository,
        "pull_request": number,
        "url": f"https://example.invalid/{repository}/pull/{number}",
        "fixture": False,
        "expected_head": head,
        "head_sha": head,
        "rechecked_head_sha": head,
        "reviewed_sha": head,
        "executing_keeper": "keeper-citrine",
        "reviewing_keeper": "keeper-umber",
        "reviewer_receipt": {
            "kind": "github_pull_request_review",
            "review_id": "RVW_01",
            "executing_keeper": "keeper-citrine",
            "reviewing_keeper": "keeper-umber",
            "reviewer_association": "COLLABORATOR",
            "reviewed_sha": head,
            "state": "APPROVED",
            "submitted_at": T2,
            "url": "https://example.invalid/reviews/RVW_01",
        },
        "signed_receipts": {
            "enabled": False,
            "markers": 0,
            "execution_markers": 0,
            "execution_verified": 0,
            "verified": 0,
            "ignored": 0,
        },
        "unresolved_current_thread_count": 0,
        "checks": {
            "total": 2,
            "successful": 2,
            "pending": 0,
            "failed": 0,
            "unknown": 0,
            "contexts": [
                {
                    "kind": "check_run",
                    "name": "python",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "classification": "successful",
                },
                {
                    "kind": "check_run",
                    "name": "web",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                    "classification": "successful",
                },
            ],
        },
        "review_threads": {"unresolved_current": 0, "unresolved_outdated": 0},
        "reason_codes": [],
        "reasons": [],
        "publication": {"requested": True, "published": True},
    }


def base_document():
    rows = [
        MODULE._base_row("session", SESSION_ID),
        MODULE._base_row("workflow", WORKFLOW_ID),
    ]
    for number, row_id in enumerate(PR_IDS, start=1):
        row = MODULE._base_row("pull_request", f"example/repo#{number}")
        row.update(
            {
                "id": row_id,
                "session": None,
                "exact_head": chr(96 + number) * 40,
                "owner_surfaces": ["example/repo"],
                "review_findings": {
                    "status": "current_remote_snapshot",
                    "p1": 1 if number == 1 else 0,
                    "p2": 1 if number == 2 else 0,
                    "unclassified": 0,
                    "unresolved_current": 1 if number in {1, 2} else 0,
                    "urls": [FINDING_URLS[number - 1]] if number in {1, 2} else [],
                },
                "receipt": {
                    "status": "merged",
                    "url": f"https://example.invalid/example/repo/pull/{number}",
                    "merge_commit": str(row["exact_head"]),
                    "review_decision": None,
                    "draft": False,
                    "merged_at": T1,
                    "closed_at": T1,
                },
                "keeper": {
                    "executing_keeper": "claude",
                    "reviewing_keeper": None,
                    "provider_route": "claude",
                    "github_author": "keeper-citrine",
                    "owner_surface": "example/repo",
                },
            }
        )
        row["side_effects"]["observed"] = copy.deepcopy(scope()["known_side_effects"].get(row_id, []))
        rows.append(row)
    findings = [
        {
            "id": MODULE._finding_id(FINDING_URLS[0]),
            "historical_row_id": PR_IDS[0],
            "discussion_url": FINDING_URLS[0],
            "severity": "p1",
            "current_status": "unresolved",
            "disposition": "repair_required",
        },
        {
            "id": MODULE._finding_id(FINDING_URLS[1]),
            "historical_row_id": PR_IDS[1],
            "discussion_url": FINDING_URLS[1],
            "severity": "p2",
            "current_status": "unresolved",
            "disposition": "repair_required",
        },
    ]
    document = {
        "schema": MODULE.SCHEMA,
        "refreshed_at": T1,
        "scope": MODULE._document_scope(scope()),
        "rows": sorted(rows, key=lambda item: item["id"]),
        "attempts": [],
        "remedies": [],
        "coverage": [],
        "findings": sorted(findings, key=lambda item: item["id"]),
        "owner_evidence": MODULE._default_owner_evidence(scope()),
    }
    return MODULE._finalize_document(document, scope=scope())


def attempt():
    lineage = [
        f"private_prompt_corpus:{SESSION_ID}",
        f"private_prompt_corpus:{WORKFLOW_ID}",
        *(f"private_prompt_corpus:example/repo#{number}" for number in range(1, 6)),
    ]
    outputs = [
        {
            "kind": "pull_request",
            "url": "https://example.invalid/example/remedies/pull/99",
            "repository": "example/remedies",
            "pull_request": 99,
            "exact_head": HEAD,
        }
    ]
    output_digest = MODULE._output_digest(outputs)
    return {
        "id": "attempt:recovery-001",
        "source_lineage": lineage,
        "source_owner": "private_prompt_corpus_owner",
        "source_receipt": receipt(
            "https://example.invalid/receipts/source-lineage",
            schema=MODULE.SOURCE_LINEAGE_SCHEMA,
            subject_id="attempt:recovery-001",
            lineage_digest=MODULE._lineage_digest(lineage),
            owner="private_prompt_corpus_owner",
        ),
        "executor": {"keeper": "keeper-citrine", "session": "session-redacted-001"},
        "trajectory_receipt": receipt(
            "https://example.invalid/receipts/trajectory",
            schema=MODULE.TRAJECTORY_SCHEMA,
            attempt_id="attempt:recovery-001",
            session="session-redacted-001",
            terminal=True,
            output_digest=output_digest,
        ),
        "owner_surface": "example/remedies",
        "spend": {
            "status": "reconciled",
            "tokens": 123,
            "cost_amount": 1.25,
            "currency": "USD",
            "receipt": receipt("https://example.invalid/receipts/spend"),
        },
        "outputs": outputs,
        "side_effects": {
            "status": "reconciled",
            "observed": ["privacy_material_publicly_reachable"],
            "replay_authorized": False,
            "receipt": receipt(
                "https://example.invalid/receipts/effects",
                schema=MODULE.SIDE_EFFECT_SCHEMA,
                subject_id="attempt:recovery-001",
                effect_digest=MODULE._effect_digest(["privacy_material_publicly_reachable"]),
            ),
            "outcomes": [
                attested_effect_outcome(
                    {
                        "effect": "privacy_material_publicly_reachable",
                        "historical_row_ids": [PR_IDS[0]],
                        "owner_surface": "private_privacy_custody_owner",
                        "status": "terminal",
                        "outcome": "contained",
                        "predicate": predicate(),
                        "receipt": receipt(
                            "https://example.invalid/receipts/effects/privacy-contained",
                            schema=MODULE.SIDE_EFFECT_OUTCOME_SCHEMA,
                            subject_id="attempt:recovery-001",
                            effect="privacy_material_publicly_reachable",
                            historical_row_ids=[PR_IDS[0]],
                            owner_surface="private_privacy_custody_owner",
                            outcome="contained",
                        ),
                    },
                    subject_id="attempt:recovery-001",
                )
            ],
        },
        "predicate": {
            **predicate(),
            "attempt_id": "attempt:recovery-001",
            "output_digest": output_digest,
        },
        "receipt": receipt(
            "https://example.invalid/receipts/attempt",
            attempt_id="attempt:recovery-001",
            output_digest=output_digest,
        ),
        "value": {
            "status": "verified",
            "classification": "durable_value",
            "credit_amount": 1,
            "receipt": receipt(
                "https://example.invalid/receipts/value",
                schema=MODULE.TRAJECTORY_SCHEMA,
                attempt_id="attempt:recovery-001",
                output_digest=output_digest,
            ),
        },
    }


def remedy():
    return {
        "id": "remedy:example/remedies#99",
        "kind": "pull_request",
        "status": "accepted",
        "attempt_ids": ["attempt:recovery-001"],
        "owner_surface": "example/remedies",
        "repository": "example/remedies",
        "pull_request": 99,
        "exact_head": HEAD,
        "review_gate_app_slug": "keeper-gate",
        "remote": {
            "url": "https://example.invalid/example/remedies/pull/99",
            "state": "MERGED",
            "draft": False,
            "head_sha": HEAD,
            "merge_commit": "c" * 40,
            "merged_at": T2,
            "closed_at": T2,
            "review_gate_check": {
                "name": MODULE.REVIEW_GATE_CONTEXT,
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "details_url": "https://example.invalid/checks/review-gate",
                "app_slug": "keeper-gate",
            },
        },
        "predicate": predicate(exact_head=HEAD),
        "deployed_path": {
            "status": "verified",
            "entrypoint": "python3 -m example.remedy",
            "predicate": predicate(exact_head=HEAD),
            "receipt": receipt(
                "https://example.invalid/deployments/remedy-99",
                exact_head=HEAD,
            ),
        },
        "review_gate": review_gate(),
        "receipt": receipt(
            "https://example.invalid/example/remedies/pull/99",
            exact_head=HEAD,
            disposition="accepted",
        ),
    }


def _mark_row_superseded(row):
    exact_head = row.get("exact_head")
    source_references = copy.deepcopy(row["source_ask"]["references"])
    row["source_ask"] = {
        "status": "reconciled",
        "references": source_references,
        "private_owner": "private_prompt_corpus_owner",
        "lineage_digest": MODULE._lineage_digest(source_references),
        "receipt": receipt(
            f"https://example.invalid/source/{hashlib.sha256(row['id'].encode()).hexdigest()}",
            schema=MODULE.SOURCE_LINEAGE_SCHEMA,
            subject_id=row["id"],
            lineage_digest=MODULE._lineage_digest(source_references),
            owner="private_prompt_corpus_owner",
        ),
    }
    row["attempt_ids"] = ["attempt:recovery-001"]
    row["outputs"] = {"status": "registry_owned", "attempt_ids": ["attempt:recovery-001"]}
    observed = row.get("side_effects", {}).get("observed", [])
    row["side_effects"] = {
        "status": "registry_owned",
        "attempt_ids": ["attempt:recovery-001"],
        "observed": observed,
        "replay_authorized": False,
        "receipt": receipt(
            f"https://example.invalid/effects/{hashlib.sha256(row['id'].encode()).hexdigest()}",
            schema=MODULE.SIDE_EFFECT_SCHEMA,
            subject_id=row["id"],
            effect_digest=MODULE._effect_digest(observed),
        ),
    }
    row["owner_surfaces"] = sorted(set([*row.get("owner_surfaces", []), "example/remedies"]))
    row["predicate"] = predicate(exact_head=exact_head)
    row["disposition"] = "superseded"
    adjudication = receipt(
        f"https://example.invalid/adjudications/{hashlib.sha256(row['id'].encode()).hexdigest()}",
        exact_head=exact_head,
        disposition="superseded",
    )
    row.setdefault("receipt", {})["adjudication"] = adjudication


def _coverage(row_id, *, finding_id=None, disposition="superseded", suffix="row"):
    return {
        "id": ("coverage:" + hashlib.sha256(f"{row_id}|{finding_id}|{disposition}|{suffix}".encode()).hexdigest()),
        "historical_row_id": row_id,
        "finding_id": finding_id,
        "remedy_id": "remedy:example/remedies#99",
        "disposition": disposition,
        "evidence": receipt(
            f"https://example.invalid/crosswalk/{hashlib.sha256((row_id + str(finding_id)).encode()).hexdigest()}",
            exact_head=HEAD,
            historical_row_id=row_id,
            finding_id=finding_id,
            remedy_id="remedy:example/remedies#99",
            coverage_disposition=disposition,
        ),
    }


def _owner_evidence_ready(document):
    def pair(key):
        schema = MODULE.OWNER_EVIDENCE_SCHEMAS[key]
        return {
            "predicate": predicate(schema=f"{schema}.predicate"),
            "receipt": receipt(f"https://example.invalid/gates/{key}", schema=schema),
        }

    def attest(owner, gate_key, binding_value):
        sign_owner_evidence(owner, gate_key=gate_key, binding_value=binding_value)

    owners = document["owner_evidence"]
    owners["baseline_open_prs"].update(pair("baseline_open_prs"))
    owners["baseline_open_prs"]["terminal_row_ids"] = sorted(PR_IDS)
    baseline_binding = {
        "baseline_row_ids": list(PR_IDS),
        "terminal_row_ids": sorted(PR_IDS),
        "cutoff_digest": MODULE._scope_cutoff_digest(scope()),
    }
    baseline_digest = MODULE._owner_binding_digest(baseline_binding)
    owners["baseline_open_prs"]["baseline_digest"] = baseline_digest
    owners["baseline_open_prs"]["receipt"]["binding_digest"] = baseline_digest
    attest(
        owners["baseline_open_prs"],
        "open_prs_closed_or_reaccepted",
        baseline_binding,
    )

    owners["session_value"].update(pair("session_value"))
    owners["session_value"]["attempt_ids"] = ["attempt:recovery-001"]
    attempt_digest = MODULE._owner_binding_digest(document["attempts"])
    owners["session_value"]["attempt_registry_digest"] = attempt_digest
    owners["session_value"]["receipt"]["binding_digest"] = attempt_digest
    attest(owners["session_value"], "session_value_verified", document["attempts"])

    owners["inflight_custody"].update(pair("inflight_custody"))
    owners["inflight_custody"]["campaign_attempt_ids"] = ["attempt:recovery-001"]
    owners["inflight_custody"]["cutoff_receipt"] = copy.deepcopy(scope()["cutoff_receipt"])
    custody_binding = {
        "attempt_ids": ["attempt:recovery-001"],
        "stale_ids": [],
        "cutoff_digest": MODULE._scope_cutoff_digest(scope()),
    }
    custody_digest = MODULE._owner_binding_digest(custody_binding)
    owners["inflight_custody"]["campaign_attempt_digest"] = custody_digest
    owners["inflight_custody"]["receipt"]["binding_digest"] = custody_digest
    attest(
        owners["inflight_custody"],
        "no_stale_inflight_custody",
        custody_binding,
    )

    owners["privacy"].update(pair("privacy"))
    owners["privacy"]["affected_row_ids"] = [PR_IDS[0]]
    owners["privacy"]["content_manifest_digest"] = "sha256:" + "e" * 64
    owners["privacy"]["frozen_manifest_digest"] = OWNER_FIXTURES.privacy_frozen_manifest_digest(scope())
    owners["privacy"]["current_trees_clean"] = True
    owners["privacy"]["history_status"] = "completed"
    owners["privacy"]["private_copy_receipts"] = [
        receipt(
            "https://example.invalid/privacy/copy-a",
            schema=MODULE.PRIVACY_COPY_SCHEMA,
            copy_id="copy-a",
            custody_location_id="vault-a",
            content_digest="sha256:" + "e" * 64,
        ),
        receipt(
            "https://example.invalid/privacy/copy-b",
            schema=MODULE.PRIVACY_COPY_SCHEMA,
            copy_id="copy-b",
            custody_location_id="vault-b",
            content_digest="sha256:" + "e" * 64,
        ),
    ]
    privacy_binding = {
        "affected_row_ids": [PR_IDS[0]],
        "current_trees_clean": True,
        "history_status": "completed",
        "content_manifest_digest": "sha256:" + "e" * 64,
        "frozen_manifest_digest": owners["privacy"]["frozen_manifest_digest"],
        "copies": [
            {
                "copy_id": copy_receipt["copy_id"],
                "custody_location_id": copy_receipt["custody_location_id"],
                "content_digest": copy_receipt["content_digest"],
                "receipt_identity": list(MODULE._evidence_identity(copy_receipt) or ()),
            }
            for copy_receipt in owners["privacy"]["private_copy_receipts"]
        ],
    }
    privacy_digest = MODULE._owner_binding_digest(privacy_binding)
    owners["privacy"]["privacy_denominator_digest"] = privacy_digest
    owners["privacy"]["receipt"]["binding_digest"] = privacy_digest
    attest(
        owners["privacy"],
        "privacy_containment_terminal",
        privacy_binding,
    )

    owners["continuation"].update(pair("continuation"))
    owners["continuation"]["capsule"] = {"url": "https://example.invalid/capsules/reacceptance-v2"}
    owners["continuation"]["launch_command"] = "bash scripts/start-worktree-session.sh limen successor"
    continuation_requirement = scope()["owner_attestation_requirements"]["gates"]["continuation_fixed_point"]
    owners["continuation"]["owner"] = continuation_requirement["owner"]
    owners["continuation"]["predicate"]["command"] = continuation_requirement["predicate_command"]


def ready_document():
    document = base_document()
    document["attempts"] = [attempt()]
    document["remedies"] = [remedy()]
    for row in document["rows"]:
        _mark_row_superseded(row)
        document["coverage"].append(_coverage(row["id"]))
    for finding in document["findings"]:
        finding["current_status"] = "resolved"
        finding["disposition"] = "repaired"
        document["coverage"].append(
            _coverage(
                finding["historical_row_id"],
                finding_id=finding["id"],
                disposition="repaired",
                suffix="finding",
            )
        )
    document["coverage"].sort(key=lambda item: item["id"])
    _owner_evidence_ready(document)
    document["refreshed_at"] = T2
    digest = MODULE.normalized_evidence_digest(document)
    document["owner_evidence"]["continuation"]["refresh_receipts"] = [
        receipt(
            "https://example.invalid/refresh/one",
            schema=MODULE.REFRESH_RECEIPT_SCHEMA,
            evidence_digest=digest,
            refreshed_at=T1,
        ),
        receipt(
            "https://example.invalid/refresh/two",
            schema=MODULE.REFRESH_RECEIPT_SCHEMA,
            evidence_digest=digest,
            refreshed_at=T2,
        ),
    ]
    document = MODULE._finalize_document(
        document,
        scope=scope(),
        previous_history=[{"refreshed_at": T1, "evidence_digest": digest}],
    )
    continuation = document["owner_evidence"]["continuation"]
    continuation_binding = {
        "capsule": continuation["capsule"],
        "launch_command": continuation["launch_command"],
        "refresh_history": copy.deepcopy(document["refresh_history"][-2:]),
        "refresh_receipt_identities": [
            list(MODULE._evidence_identity(refresh_receipt) or ())
            for refresh_receipt in continuation["refresh_receipts"]
        ],
    }
    continuation_digest = MODULE._owner_binding_digest(continuation_binding)
    continuation["continuation_digest"] = continuation_digest
    continuation["receipt"]["binding_digest"] = continuation_digest
    sign_owner_evidence(
        continuation,
        gate_key="continuation_fixed_point",
        binding_value=continuation_binding,
    )
    assert document["evidence_digest"] == MODULE.normalized_evidence_digest(document)
    rederive(document)
    return document


def rederive(document):
    document["completion_gates"] = MODULE._derive_completion_gates(
        scope=scope(),
        rows=document["rows"],
        attempts=document["attempts"],
        remedies=document["remedies"],
        findings=document["findings"],
        owner_evidence=document["owner_evidence"],
        refresh_history=document["refresh_history"],
        as_of=MODULE._parse_timestamp(document["refreshed_at"]),
    )
    document["summary"] = MODULE._summary_for(
        rows=document["rows"],
        attempts=document["attempts"],
        remedies=document["remedies"],
        findings=document["findings"],
        completion_gates=document["completion_gates"],
    )


def sync_document(document, *, stable=False):
    digest = MODULE.normalized_evidence_digest(document)
    document["evidence_digest"] = digest
    document["refresh_history"][-1]["evidence_digest"] = digest
    if stable and len(document["refresh_history"]) > 1:
        document["refresh_history"][-2]["evidence_digest"] = digest
    rederive(document)
    return digest


def test_migration_preserves_real_frozen_105_rows_and_208_finding_urls():
    real_scope = MODULE.load_scope()
    current = MODULE.load_json(MODULE.LEDGER_PATH)
    assert all(isinstance(row.get("legacy_v1"), dict) for row in current["rows"])
    v1_rows = [copy.deepcopy(row["legacy_v1"]) for row in current["rows"]]
    assert MODULE._legacy_v1_rows_digest(v1_rows) == real_scope["legacy_v1_rows_digest"]
    v1 = {
        "schema": MODULE.V1_SCHEMA,
        "refreshed_at": current["refreshed_at"],
        "rows": v1_rows,
    }

    migrated = MODULE.migrate_v1_document(v1, real_scope)

    assert migrated["schema"] == MODULE.SCHEMA
    assert migrated["summary"]["historical_rows"] == 105
    assert migrated["summary"]["repair_required"] == 105
    assert migrated["summary"]["current_p1"] == 28
    assert migrated["summary"]["current_p2"] == 180
    assert len(migrated["findings"]) == 208
    assert len({item["discussion_url"] for item in migrated["findings"]}) == 208
    assert migrated["scope"]["baseline_open_prs"] == real_scope["baseline_open_prs"]
    assert all("legacy_v1" in row for row in migrated["rows"])
    assert all("receipt" in row["legacy_v1"] for row in migrated["rows"])
    assert (
        MODULE._legacy_v1_rows_digest([row["legacy_v1"] for row in migrated["rows"]])
        == real_scope["legacy_v1_rows_digest"]
    )
    assert MODULE.validate_document(migrated, real_scope) == []


def test_external_remedy_and_many_to_many_coverage_can_make_campaign_reachable():
    document = ready_document()

    assert document["remedies"][0]["repository"] == "example/remedies"
    assert len(document["coverage"]) == len(document["rows"]) + len(document["findings"])
    assert {item["remedy_id"] for item in document["coverage"]} == {"remedy:example/remedies#99"}
    assert document["summary"]["release_ready"] is True
    assert MODULE.validate_document(document, scope()) == []


def test_duplicate_attempt_registry_id_is_rejected_without_duplicating_spend():
    document = ready_document()
    document["attempts"].append(copy.deepcopy(document["attempts"][0]))
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    errors = MODULE.validate_document(document, scope())

    assert any("attempts ids must be unique" in error for error in errors)


def test_renamed_attempt_cannot_duplicate_the_same_execution_receipt_and_spend():
    document = ready_document()
    duplicate = copy.deepcopy(document["attempts"][0])
    duplicate["id"] = "attempt:renamed-duplicate"
    document["attempts"].append(duplicate)
    document["owner_evidence"]["session_value"]["attempt_ids"].append(duplicate["id"])
    document["owner_evidence"]["inflight_custody"]["campaign_attempt_ids"].append(duplicate["id"])
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    document["refresh_history"][-2]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    errors = MODULE.validate_document(document, scope())

    assert any("execution receipts must be unique" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "mutate", "message"),
    [
        ("source", lambda doc: doc["rows"][0]["source_ask"].update(status="unreconciled"), "source ask"),
        ("spend", lambda doc: doc["attempts"][0]["spend"].update(status="unreconciled"), "spend"),
        ("outputs", lambda doc: doc["attempts"][0].update(outputs=[]), "outputs"),
        (
            "effects",
            lambda doc: doc["attempts"][0]["side_effects"].update(status="unreconciled"),
            "side_effects",
        ),
        ("owner", lambda doc: doc["attempts"][0].update(owner_surface=""), "owner_surface"),
    ],
)
def test_terminal_claim_rejects_unreconciled_mandatory_field(field, mutate, message):
    document = ready_document()
    mutate(document)
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    errors = MODULE.validate_document(document, scope())

    assert any(message in error for error in errors), (field, errors)


def test_manual_review_status_string_cannot_replace_complete_review_gate_receipt():
    document = ready_document()
    document["remedies"][0]["review_gate"] = {"status": "accepted"}
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    errors = MODULE.validate_document(document, scope())

    assert any("is incomplete" in error for error in errors)
    assert any("schema must be limen.pr_review_gate.v1" in error for error in errors)


def test_stale_remedy_head_is_rejected_against_preserved_review_receipt():
    document = ready_document()
    document["remedies"][0]["exact_head"] = NEW_HEAD
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    errors = MODULE.validate_document(document, scope())

    assert any("head_sha does not match" in error for error in errors)
    assert any("reviewed_sha does not match" in error for error in errors)


def test_merged_remedy_can_preserve_accepted_premerge_review_receipt():
    document = ready_document()
    document["remedies"][0]["receipt"]["merged_at"] = T2
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    document["refresh_history"][-2]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    assert MODULE.validate_document(document, scope()) == []
    assert document["remedies"][0]["review_gate"]["status"] == "accepted"


def test_finding_cannot_be_marked_repaired_without_original_thread_crosswalk():
    document = ready_document()
    finding_id = document["findings"][0]["id"]
    document["coverage"] = [item for item in document["coverage"] if item.get("finding_id") != finding_id]
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    errors = MODULE.validate_document(document, scope())

    assert any("terminal disposition needs accepted remedy coverage" in error for error in errors)


def test_five_pr_baseline_gate_is_derived_not_asserted():
    document = ready_document()
    document["owner_evidence"]["baseline_open_prs"]["terminal_row_ids"].pop()
    document["evidence_digest"] = MODULE.normalized_evidence_digest(document)
    document["refresh_history"][-1]["evidence_digest"] = document["evidence_digest"]
    rederive(document)

    assert MODULE.validate_document(document, scope()) == []
    assert document["completion_gates"]["open_prs_closed_or_reaccepted"]["status"] == "failed"
    assert document["summary"]["release_ready"] is False


def test_tampered_completion_gate_is_rejected():
    document = base_document()
    document["completion_gates"]["session_value_verified"]["status"] = "passed"
    document["completion_gates"]["session_value_verified"]["blockers"] = []

    errors = MODULE.validate_document(document, scope())

    assert any("completion_gates must be derived" in error for error in errors)


def test_semantic_fixed_point_requires_two_ordered_equal_normalized_digests():
    document = ready_document()
    assert document["completion_gates"]["continuation_fixed_point"]["status"] == "passed"

    document["refresh_history"] = document["refresh_history"][-1:]
    rederive(document)

    assert MODULE.validate_document(document, scope()) == []
    assert document["completion_gates"]["continuation_fixed_point"]["status"] == "failed"
    assert "two_refreshes_required" in document["completion_gates"]["continuation_fixed_point"]["blockers"]


def test_structural_check_and_release_ready_have_distinct_exit_codes(tmp_path):
    document = base_document()
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(scope()), encoding="utf-8")

    structural = subprocess.run(
        [sys.executable, str(SCRIPT), "--scope", str(scope_path), "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    release = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scope",
            str(scope_path),
            "--require-release-ready",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert structural.returncode == 0
    assert "structurally_valid=true release_ready=false" in structural.stdout
    assert release.returncode == 3
    assert "campaign incomplete" in release.stderr


def test_release_check_requires_recomputed_live_gates(monkeypatch, tmp_path):
    document = ready_document()
    target = tmp_path / "ledger.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    live = copy.deepcopy(document)
    live["owner_evidence"]["continuation"]["refresh_receipts"] = []
    sync_document(live, stable=True)
    assert live["evidence_digest"] == document["evidence_digest"]
    assert live["summary"]["release_ready"] is False
    monkeypatch.setattr(MODULE._cli, "RELEASE_SNAPSHOT_MAX_AGE", dt.timedelta(days=3650))
    monkeypatch.setattr(MODULE._cli, "build_live_release_candidate", lambda *_args, **_kwargs: live)

    result = MODULE._cli._check_mode(target, scope=scope(), require_release_ready=True)

    assert result == 3


def test_release_check_accepts_only_an_unchanged_live_ready_candidate(monkeypatch, tmp_path):
    document = ready_document()
    target = tmp_path / "ledger.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(MODULE._cli, "RELEASE_SNAPSHOT_MAX_AGE", dt.timedelta(days=3650))
    monkeypatch.setattr(
        MODULE._cli,
        "build_live_release_candidate",
        lambda *_args, **_kwargs: copy.deepcopy(document),
    )

    result = MODULE._cli._check_mode(target, scope=scope(), require_release_ready=True)

    assert result == 0


def test_scope_rejects_missing_five_pr_baseline(tmp_path):
    value = scope()
    value["baseline_open_prs"].pop()
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(MODULE.LedgerError, match="five unique"):
        MODULE.load_scope(path)


def test_review_thread_refresh_preserves_resolved_crosswalk(monkeypatch):
    document = base_document()
    finding = document["findings"][0]
    rows = copy.deepcopy(document["rows"])
    row = next(item for item in rows if item["id"] == finding["historical_row_id"])
    row["review_threads"] = [
        {
            "discussion_url": finding["discussion_url"],
            "severity": finding["severity"],
            "resolved": True,
            "outdated": False,
        }
    ]

    refreshed = MODULE._refresh_findings(document["findings"], rows)

    item = next(value for value in refreshed if value["id"] == finding["id"])
    assert item["current_status"] == "resolved"


def test_live_remedy_refresh_rejects_a_subsequent_commit(monkeypatch):
    live = {
        "url": "https://example.invalid/example/remedies/pull/99",
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": NEW_HEAD,
        "mergeCommit": None,
        "mergedAt": None,
        "closedAt": None,
        "statusCheckRollup": {
            "contexts": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [],
            }
        },
    }
    monkeypatch.setattr(MODULE, "_gh_graphql", lambda _repository, _number: live)

    with pytest.raises(MODULE.LedgerError, match="exact head changed"):
        MODULE._refresh_remedy(remedy())


def test_review_gate_requires_live_app_provenance_and_bound_executor():
    document = ready_document()
    gate = document["remedies"][0]["review_gate"]
    gate["url"] = "https://example.invalid/not-the-remedy"
    gate["executing_keeper"] = "fabricated-executor"
    gate["reviewer_receipt"]["executing_keeper"] = "fabricated-executor"
    gate["reviewer_receipt"]["reviewer_association"] = "NONE"
    gate["publication"] = {"requested": False, "published": False}
    document["remedies"][0]["remote"]["review_gate_check"]["app_slug"] = "github-actions"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("URL does not match" in error for error in errors)
    assert any("not bound to a remedy attempt executor" in error for error in errors)
    assert any("association is not trusted" in error for error in errors)
    assert any("dedicated-App publication is required" in error for error in errors)
    assert any("CheckRun App is not the configured dedicated App" in error for error in errors)


def test_owner_adapter_evidence_expires_instead_of_self_asserting_readiness():
    document = ready_document()
    owner = document["owner_evidence"]["baseline_open_prs"]
    owner["predicate"]["verified_at"] = "2020-01-01T00:00:00Z"
    owner["receipt"]["verified_at"] = "2020-01-01T00:00:00Z"
    sync_document(document)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["open_prs_closed_or_reaccepted"]
    assert gate["status"] == "failed"
    assert "owner_predicate_or_receipt_invalid" in gate["blockers"]


def test_privacy_denominator_cannot_be_erased():
    document = ready_document()
    document["owner_evidence"]["privacy"]["affected_row_ids"] = []
    sync_document(document)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["privacy_containment_terminal"]
    assert gate["status"] == "failed"
    assert "affected_rows_denominator_mismatch" in gate["blockers"]


def test_semantic_digest_ignores_nested_timestamps_and_registry_order():
    first = ready_document()
    second = copy.deepcopy(first)
    second["rows"].reverse()
    second["attempts"][0]["receipt"]["verified_at"] = T1
    second["remedies"][0]["review_gate"]["evaluated_at"] = T1
    second["remedies"][0]["review_gate"]["reviewer_receipt"]["submitted_at"] = T1

    assert MODULE.normalized_evidence_digest(first) == MODULE.normalized_evidence_digest(second)


def test_fixed_point_requires_two_distinct_owner_attestations():
    document = ready_document()
    document["owner_evidence"]["continuation"]["refresh_receipts"] = []
    sync_document(document, stable=True)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["continuation_fixed_point"]
    assert gate["status"] == "failed"
    assert "owner_refresh_receipts_required" in gate["blockers"]


def test_owner_receipt_cannot_cover_peer_reviewed_repair_debt():
    document = ready_document()
    accepted = document["remedies"][0]
    accepted["kind"] = "owner_receipt"
    for field in (
        "repository",
        "pull_request",
        "exact_head",
        "review_gate_app_slug",
        "remote",
        "review_gate",
    ):
        accepted.pop(field, None)
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("requires an accepted exact-head peer-reviewed remedy" in error for error in errors)
    assert any("owner or reversal evidence cannot replace" in error for error in errors)


def test_finding_repair_requires_resolved_thread_and_matching_crosswalk():
    document = ready_document()
    finding = document["findings"][0]
    finding["current_status"] = "outdated"
    link = next(item for item in document["coverage"] if item.get("finding_id") == finding["id"])
    link["disposition"] = "obsolete"
    link["evidence"]["coverage_disposition"] = "obsolete"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("requires the original thread resolved" in error for error in errors)
    assert any("needs matching repaired coverage" in error for error in errors)


def test_orphan_attempt_cannot_receive_registry_credit():
    document = ready_document()
    duplicate = copy.deepcopy(document["attempts"][0])
    duplicate["id"] = "attempt:orphan-002"
    duplicate["executor"]["session"] = "session-redacted-002"
    duplicate["source_receipt"].update(
        url="https://example.invalid/receipts/source-lineage-2",
        subject_id=duplicate["id"],
    )
    duplicate["trajectory_receipt"].update(
        url="https://example.invalid/receipts/trajectory-2",
        attempt_id=duplicate["id"],
        session="session-redacted-002",
    )
    duplicate["spend"]["receipt"]["url"] = "https://example.invalid/receipts/spend-2"
    duplicate["side_effects"]["receipt"].update(
        url="https://example.invalid/receipts/effects-2",
        subject_id=duplicate["id"],
    )
    duplicate["receipt"]["url"] = "https://example.invalid/receipts/attempt-2"
    duplicate["value"]["receipt"]["url"] = "https://example.invalid/receipts/value-2"
    document["attempts"].append(duplicate)
    document["owner_evidence"]["session_value"]["attempt_ids"].append(duplicate["id"])
    document["owner_evidence"]["inflight_custody"]["campaign_attempt_ids"].append(duplicate["id"])
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("orphan attempts" in error for error in errors)


def test_motion_only_attempt_cannot_underwrite_an_accepted_remedy():
    document = ready_document()
    document["attempts"][0]["value"].update(classification="motion_only", credit_amount=0)
    value = document["owner_evidence"]["session_value"]
    value["motion_only_attempt_ids"] = ["attempt:recovery-001"]
    value["uncredited_attempt_ids"] = ["attempt:recovery-001"]
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("accepted remedy needs at least one durable-value attempt" in error for error in errors)


def test_cutoff_owner_evidence_must_equal_the_frozen_scope():
    document = ready_document()
    document["owner_evidence"]["inflight_custody"]["cutoff_receipt"]["event_offsets"] = ["event-offset:fixture:other"]
    sync_document(document)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["no_stale_inflight_custody"]
    assert gate["status"] == "failed"
    assert "immutable_cutoff_scope_mismatch" in gate["blockers"]


def test_source_ask_must_cross_bind_to_attempt_lineage():
    document = ready_document()
    row = document["rows"][0]
    references = ["private_prompt_corpus:not-in-the-attempt"]
    row["source_ask"].update(
        references=references,
        lineage_digest=MODULE._lineage_digest(references),
    )
    row["source_ask"]["receipt"].update(
        lineage_digest=MODULE._lineage_digest(references),
    )
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("not bound to its referenced attempt lineage" in error for error in errors)


def test_frozen_side_effect_inventory_cannot_disappear():
    document = ready_document()
    row = next(item for item in document["rows"] if item["id"] == PR_IDS[0])
    row["side_effects"]["observed"] = []
    row["side_effects"]["receipt"]["effect_digest"] = MODULE._effect_digest([])
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("side effects omit frozen known effects" in error for error in errors)


def test_non_finite_spend_fails_closed_without_crashing():
    document = ready_document()
    document["attempts"][0]["spend"]["cost_amount"] = float("nan")

    errors = MODULE.validate_document(document, scope())

    assert any("spend.cost_amount" in error for error in errors)
    assert any("non-finite or non-JSON" in error for error in errors)


def test_atomic_write_rejects_a_changed_destination(tmp_path):
    destination = tmp_path / "ledger.json"
    destination.write_text("first", encoding="utf-8")
    expected = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.write_text("concurrent", encoding="utf-8")

    with pytest.raises(MODULE.LedgerError, match="refusing stale overwrite"):
        MODULE._write_atomic(destination, base_document(), expected_digest=expected)

    assert destination.read_text(encoding="utf-8") == "concurrent"


def test_atomic_write_restores_content_changed_inside_exchange(monkeypatch, tmp_path):
    destination = tmp_path / "ledger.json"
    destination.write_text("first", encoding="utf-8")
    expected = hashlib.sha256(destination.read_bytes()).hexdigest()
    real_exchange = MODULE._cli._exchange_paths
    injected = False

    def exchange_with_race(first, second):
        nonlocal injected
        if not injected:
            injected = True
            Path(second).write_text("concurrent", encoding="utf-8")
        real_exchange(first, second)

    monkeypatch.setattr(MODULE._cli, "_exchange_paths", exchange_with_race)

    with pytest.raises(MODULE.LedgerError, match="changed during publication"):
        MODULE._write_atomic(destination, base_document(), expected_digest=expected)

    assert destination.read_text(encoding="utf-8") == "concurrent"


def test_coverage_receipt_is_bound_to_row_finding_remedy_and_head():
    document = ready_document()
    document["coverage"][0]["evidence"]["remedy_id"] = "remedy:substituted"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("evidence remedy_id does not match" in error for error in errors)


def test_remedy_cannot_self_select_a_different_review_gate_app():
    document = ready_document()
    document["remedies"][0]["review_gate_app_slug"] = "attacker-gate"
    document["remedies"][0]["remote"]["review_gate_check"]["app_slug"] = "attacker-gate"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("does not match the frozen scope App" in error for error in errors)


def test_successful_check_classification_must_match_live_check_state():
    document = ready_document()
    context = document["remedies"][0]["review_gate"]["checks"]["contexts"][0]
    context.update(status="IN_PROGRESS", conclusion="FAILURE", classification="successful")
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("classification is not supported by the live check state" in error for error in errors)


def test_signed_fallback_requires_distinct_execution_and_review_fingerprints():
    document = ready_document()
    gate = document["remedies"][0]["review_gate"]
    gate["reviewer_receipt"].update(
        kind="ssh_signed_peer_review",
        comment_id="comment-001",
        execution_signer_fingerprint="SHA256:same",
        review_signer_fingerprint="SHA256:same",
    )
    gate["signed_receipts"].update(enabled=True, execution_verified=1, verified=1)
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("requires distinct execution and review fingerprints" in error for error in errors)


def test_accepted_remedy_attempt_must_own_the_live_remote_output():
    document = ready_document()
    document["attempts"][0]["outputs"][0]["url"] = "https://example.invalid/unrelated/pull/1"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("durable-value attempt bound to its live output" in error for error in errors)


def test_renamed_attempt_cannot_reuse_role_specific_owner_receipts():
    document = ready_document()
    duplicate = copy.deepcopy(document["attempts"][0])
    duplicate["id"] = "attempt:renamed-with-reused-owner-receipts"
    duplicate["executor"]["session"] = "session-redacted-002"
    duplicate["source_receipt"]["subject_id"] = duplicate["id"]
    duplicate["trajectory_receipt"].update(
        attempt_id=duplicate["id"],
        session="session-redacted-002",
    )
    duplicate["spend"]["receipt"]["url"] = "https://example.invalid/receipts/spend-unique"
    duplicate["side_effects"]["receipt"]["subject_id"] = duplicate["id"]
    duplicate["receipt"]["url"] = "https://example.invalid/receipts/attempt-unique"
    document["attempts"].append(duplicate)
    document["remedies"][0]["attempt_ids"].append(duplicate["id"])
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    for role in ("source", "trajectory", "side-effect", "value"):
        assert any(f"attempt {role} receipts must be unique" in error for error in errors)


def test_two_private_copies_require_distinct_owner_receipts():
    document = ready_document()
    copies = document["owner_evidence"]["privacy"]["private_copy_receipts"]
    copies[1]["url"] = copies[0]["url"]
    sync_document(document)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["privacy_containment_terminal"]
    assert "private_copies_not_independently_custodied" in gate["blockers"]


def test_public_history_effect_cannot_claim_history_cleanup_not_required():
    document = ready_document()
    document["owner_evidence"]["privacy"]["history_status"] = "not_required"
    sync_document(document)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["privacy_containment_terminal"]
    assert "history_action_required" in gate["blockers"]


def test_deployed_path_evidence_expires():
    document = ready_document()
    deployed = document["remedies"][0]["deployed_path"]
    deployed["predicate"]["verified_at"] = "2020-01-01T00:00:00Z"
    deployed["receipt"]["verified_at"] = "2020-01-01T00:00:00Z"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert sum("deployed path" in error and "stale" in error for error in errors) == 2


def test_row_and_attempt_cannot_jointly_replace_a_frozen_source_atom():
    document = ready_document()
    row = document["rows"][0]
    original_reference = row["source_ask"]["references"][0]
    replacement = "https://example.invalid/unrelated/source"
    row["source_ask"]["references"] = [replacement]
    row["source_ask"]["lineage_digest"] = MODULE._lineage_digest([replacement])
    row["source_ask"]["receipt"]["lineage_digest"] = MODULE._lineage_digest([replacement])
    attempt_value = document["attempts"][0]
    attempt_value["source_lineage"] = [
        replacement if reference == original_reference else reference for reference in attempt_value["source_lineage"]
    ]
    attempt_value["source_receipt"]["lineage_digest"] = MODULE._lineage_digest(attempt_value["source_lineage"])
    attempt_digest = MODULE._owner_binding_digest(document["attempts"])
    session_value = document["owner_evidence"]["session_value"]
    session_value["attempt_registry_digest"] = attempt_digest
    session_value["receipt"]["binding_digest"] = attempt_digest
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("frozen row-anchored source manifest" in error for error in errors)


def test_attempt_output_must_bind_the_remedy_repository_pr_and_exact_head():
    document = ready_document()
    attempt_value = document["attempts"][0]
    attempt_value["outputs"][0]["exact_head"] = NEW_HEAD
    output_digest = MODULE._output_digest(attempt_value["outputs"])
    attempt_value["trajectory_receipt"]["output_digest"] = output_digest
    attempt_value["predicate"]["output_digest"] = output_digest
    attempt_value["receipt"]["output_digest"] = output_digest
    attempt_value["value"]["receipt"]["output_digest"] = output_digest
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("durable-value attempt bound to its live output" in error for error in errors)
    assert any("not bound to a remedy attempt executor" in error for error in errors)


def test_reviewer_cannot_also_be_any_exact_head_remedy_executor():
    document = ready_document()
    duplicate = copy.deepcopy(document["attempts"][0])
    duplicate["id"] = "attempt:reviewer-also-executor"
    duplicate["executor"] = {"keeper": "keeper-umber", "session": "session-redacted-reviewer"}
    duplicate["source_receipt"].update(
        url="https://example.invalid/receipts/source-reviewer",
        subject_id=duplicate["id"],
    )
    duplicate["trajectory_receipt"].update(
        url="https://example.invalid/receipts/trajectory-reviewer",
        attempt_id=duplicate["id"],
        session="session-redacted-reviewer",
    )
    duplicate["spend"]["receipt"]["url"] = "https://example.invalid/receipts/spend-reviewer"
    duplicate["side_effects"]["receipt"].update(
        url="https://example.invalid/receipts/effects-reviewer",
        subject_id=duplicate["id"],
    )
    duplicate["side_effects"]["outcomes"][0]["receipt"].update(
        url="https://example.invalid/receipts/effect-outcome-reviewer",
        subject_id=duplicate["id"],
    )
    duplicate["predicate"]["attempt_id"] = duplicate["id"]
    duplicate["receipt"].update(
        url="https://example.invalid/receipts/attempt-reviewer",
        attempt_id=duplicate["id"],
    )
    duplicate["value"]["receipt"].update(
        url="https://example.invalid/receipts/value-reviewer",
        attempt_id=duplicate["id"],
    )
    document["attempts"].append(duplicate)
    document["remedies"][0]["attempt_ids"].append(duplicate["id"])
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("reviewer cannot be any exact-head remedy executor" in error for error in errors)


def test_observed_external_effect_requires_terminal_owner_outcome():
    document = ready_document()
    document["attempts"][0]["side_effects"]["outcomes"] = []
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("must cover the exact observed effect inventory" in error for error in errors)


def test_observed_external_effect_cannot_be_adjudicated_by_a_different_owner():
    document = ready_document()
    document["attempts"][0]["side_effects"]["outcomes"][0]["owner_surface"] = "wrong_owner"
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("owner_surface does not match the frozen owner" in error for error in errors)


def test_observed_external_effect_requires_a_scope_pinned_owner_signature():
    document = ready_document()
    attestation = document["attempts"][0]["side_effects"]["outcomes"][0]["owner_attestation"]
    attestation["signature"] = "A" * len(attestation["signature"])
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("effect owner attestation signature is invalid" in error for error in errors)


def test_private_copy_digests_must_match_the_frozen_content_manifest():
    document = ready_document()
    copies = document["owner_evidence"]["privacy"]["private_copy_receipts"]
    for copy_receipt in copies:
        copy_receipt["content_digest"] = "sha256:" + "0" * 64
    sync_document(document)

    assert MODULE.validate_document(document, scope()) == []
    gate = document["completion_gates"]["privacy_containment_terminal"]
    assert "private_copy_manifest_mismatch" in gate["blockers"]


def test_review_check_counts_reject_json_booleans():
    document = ready_document()
    checks = document["remedies"][0]["review_gate"]["checks"]
    checks.update(total=1, successful=True, pending=False, failed=False, unknown=False)
    checks["contexts"] = checks["contexts"][:1]
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("checks.successful must be a non-negative integer" in error for error in errors)
    for field in ("pending", "failed", "unknown"):
        assert any(f"checks.{field} must be an integer" in error for error in errors)


def test_finding_row_and_severity_mapping_is_frozen():
    document = ready_document()
    first, second = document["findings"]
    first["historical_row_id"], second["historical_row_id"] = (
        second["historical_row_id"],
        first["historical_row_id"],
    )
    sync_document(document)

    errors = MODULE.validate_document(document, scope())

    assert any("finding row/severity crosswalk does not match" in error for error in errors)


def test_verified_cutoff_digest_must_derive_from_event_offsets(tmp_path):
    value = scope()
    value["cutoff_receipt"]["digest"] = "sha256:" + "d" * 64
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(MODULE.LedgerError, match="must derive from its immutable event offsets"):
        MODULE.load_scope(path)


def test_fake_owner_commands_and_receipt_urls_cannot_self_assert_release():
    document = ready_document()
    for owner in document["owner_evidence"].values():
        owner["predicate"]["command"] = "false"
        owner["receipt"]["url"] = "https://example.invalid/nonexistent-owner-claim"
    sync_document(document, stable=True)

    assert MODULE.validate_document(document, scope()) == []
    assert document["summary"]["release_ready"] is False
    for gate in document["completion_gates"].values():
        assert "owner_adapter_attestation_invalid" in gate["blockers"]
