"""Execute one pinned assessment only after keeper-owned attempt admission."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from limen.conduct.assessment_packet import compile_assessment_packet
from limen.conduct.assessor_execution import AssessorExecutionError, execute_assessor
from limen.conduct.assessor_source import AssessorSnapshot
from limen.conduct.client import HttpConductClient
from limen.conduct.models import AgentIdentityV1, ExecutorAttemptV1, PredicateEvidenceV1, RunReceiptV1, WorkPacketV1


class AssessmentExecutorError(ValueError):
    """A callback could not establish source, authority or an accepted receipt."""


def execute_assessment_run(
    client: HttpConductClient,
    run_id: str,
    *,
    source: AssessorSnapshot,
    credential: str,
    repository: str,
    repository_id: int,
    executor: AgentIdentityV1,
    predicate: str,
) -> dict[str, Any]:
    """Claim, admit one attempt, assess and report once. Never retry ambiguity.

    Source, credential, repository and predicate come from reviewed deployment
    configuration, independently of the broker packet. A fresh attempt ID plus
    max_attempts=1 lets the keeper arbitrate simultaneous callbacks atomically.
    """
    try:
        if (
            not isinstance(client, HttpConductClient)
            or not isinstance(executor, AgentIdentityV1)
            or type(repository_id) is not int
            or not 0 < repository_id < 2**53
            or not isinstance(credential, str)
            or not credential.strip()
            or any(char in credential for char in "\r\n\x00")
        ):
            raise ValueError
        graph = client.graph(run_id)
        nodes = graph.get("nodes")
        if (
            graph.get("schema_version") != "limen.conduct_graph.v1"
            or graph.get("root_run_id") != run_id
            or not isinstance(nodes, list)
            or len(nodes) != 1
        ):
            raise ValueError
        node = nodes[0]
        if (
            node.get("run_id") != run_id
            or node.get("status") != "reserved"
            or node.get("attempts")
            or node.get("receipts")
        ):
            raise ValueError
        packet = WorkPacketV1.model_validate(node["packet"])
        if packet.work_loan is None:
            raise ValueError
        binding = packet.intent["dependency_completion"]
        if binding.get("repository_id") != repository_id or type(binding.get("repository_id")) is not int:
            raise ValueError
        hint = {
            **binding,
            "coordinate": repository,
            "automatic_acceptance": False,
            "key": f"{repository_id}:{binding['run_id']}:{binding['run_attempt']}",
        }
        expected = compile_assessment_packet(
            hint,
            source=source,
            identity=packet.conductor,
            executor_session_id=executor.session_id,
            deadline=packet.deadline,
            predicate=predicate,
            receipt_target=packet.receipt_target,
            work_loan=packet.work_loan,
        )
        if expected.model_dump() != packet.model_dump():
            raise ValueError
        lease = node["lease"]
        lease_id, generation = lease["lease_id"], lease["generation"]
        if (
            lease.get("run_id") != run_id
            or lease.get("executor") != executor.model_dump(mode="json")
            or lease.get("state") != "reserved"
            or type(generation) is not int
        ):
            raise ValueError
        claim = client.claim(lease_id, generation)
        token = claim.get("capability_token")  # allow-secret: runtime broker response
        if (
            claim.get("run_id") != run_id
            or claim.get("lease_id") != lease_id
            or claim.get("generation") != generation
            or not isinstance(token, str)
            or not token
        ):
            raise ValueError
        heads = {"dependency_head": binding["head_sha"]}
        attempt = ExecutorAttemptV1(
            attempt_id="assessment-" + uuid.uuid4().hex,
            run_id=run_id,
            lease_id=lease_id,
            lease_generation=generation,
            executor=executor,
            adapter="dependency-assessment",
            status="launching",
        )
        admission = client.heartbeat(lease_id, token, generation=generation, observed_heads=heads, attempt=attempt)
        active = admission.get("lease", {})
        if (
            admission.get("status") != "active"
            or admission.get("attempt_created") is not True
            or active.get("run_id") != run_id
            or active.get("lease_id") != lease_id
            or active.get("generation") != generation
            or active.get("state") != "active"
            or active.get("executor") != executor.model_dump(mode="json")
            or active.get("observed_heads") != heads
            or (datetime.fromisoformat(active["hard_deadline"]) - datetime.now(timezone.utc)).total_seconds() <= 95
        ):
            raise ValueError
        try:
            assessment = execute_assessor(
                source,
                credential=credential,
                repository=repository,
                repository_id=repository_id,
                run_id=binding["run_id"],
                run_attempt=binding["run_attempt"],
                head_sha=binding["head_sha"],
            )
        except AssessorExecutionError:
            assessment = {"status": "HOLD", "reason": "EXECUTION_UNMEASURED", "automatic_acceptance": False}
        succeeded = assessment["status"] == "REVIEW_READY"
        outcome: Literal["succeeded", "blocked"] = "succeeded" if succeeded else "blocked"
        terminal = attempt.model_copy(
            update={"status": outcome, "updated_at": datetime.now(timezone.utc), "detail": assessment["reason"]}
        )
        settled = client.heartbeat(lease_id, token, generation=generation, observed_heads=heads, attempt=terminal)
        if settled.get("status") != "active":
            raise ValueError
        receipt = RunReceiptV1(
            receipt_id="receipt-" + attempt.attempt_id,
            run_id=run_id,
            lease_id=lease_id,
            lease_generation=generation,
            executor=executor,
            observed_heads_before=heads,
            observed_heads_after=heads,
            predicate=PredicateEvidenceV1(
                command=predicate, exit_code=0 if succeeded else 77, summary=json.dumps(assessment, sort_keys=True)
            ),
            spend={"runs": 1},
            outcome=outcome,
        )
        reported = client.report(lease_id, token, receipt, generation=generation)
        if reported.get("mutation_authorized") is not True or reported.get("run_status") != outcome:
            raise ValueError
        return {
            "run_id": run_id,
            "state": "reported",
            "outcome": outcome,
            "receipt_id": receipt.receipt_id,
            "assessment": assessment,
            "automatic_acceptance": False,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError):
        raise AssessmentExecutorError("assessment callback is unmeasured; no automatic retry") from None
