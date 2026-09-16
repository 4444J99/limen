"""Compile one underwritten assessment packet without claiming or executing work."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from limen.conduct.assessor_source import MAX_SOURCE_BYTES, AssessorSnapshot
from limen.conduct.models import AgentIdentityV1, AuthorityEnvelopeV1, SpendEnvelopeV1, WorkPacketV1
from limen.work_loan import WorkLoanV1, packet_work_loan_missing


class AssessmentPacketError(ValueError):
    """A hint or deployment contract cannot produce a bounded assessment packet."""


def compile_assessment_packet(
    hint: dict[str, Any],
    *,
    source: AssessorSnapshot,
    identity: AgentIdentityV1,
    executor_session_id: str,
    deadline: datetime,
    predicate: str,
    receipt_target: str,
    work_loan: WorkLoanV1,
    now: datetime | None = None,
) -> WorkPacketV1:
    """Bind caller-reviewed deployment inputs to an authenticated keeper hint.

    Caller owns hint authentication and independent source approval. No provider,
    credential, session or capacity is invented here. Persist and reuse the exact
    compiled packet after an ambiguous submission; do not refresh its deadline.
    """
    now = now or datetime.now(timezone.utc)
    try:
        if not isinstance(hint, dict) or hint.get("automatic_acceptance") is not False:
            raise ValueError
        fields = ("repository_id", "run_id", "run_attempt", "head_sha")
        if any(type(hint.get(field)) is not int or not 0 < hint[field] < 2**53 for field in fields[:3]):
            raise ValueError
        head = hint.get("head_sha")
        coordinate = hint.get("coordinate")
        if (
            not isinstance(head, str)
            or not re.fullmatch(r"[a-f0-9]{40}", head)
            or not isinstance(coordinate, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", coordinate)
        ):
            raise ValueError
        key = f"{hint['repository_id']}:{hint['run_id']}:{hint['run_attempt']}"
        if hint.get("key") != key:
            raise ValueError
        if (
            not isinstance(source, AssessorSnapshot)
            or not isinstance(source.source, bytes)
            or not 0 < len(source.source) <= MAX_SOURCE_BYTES
            or hashlib.sha256(source.source).hexdigest() != source.script_sha256
            or not isinstance(source.source_commit, str)
            or not re.fullmatch(r"[a-f0-9]{40}", source.source_commit)
        ):
            raise ValueError
        if (
            not isinstance(executor_session_id, str)
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", executor_session_id)
            or not isinstance(deadline, datetime)
            or deadline.tzinfo is None
            or now.tzinfo is None
            or not 95 < (deadline - now).total_seconds() <= 900
            or not isinstance(identity, AgentIdentityV1)
            or not isinstance(work_loan, WorkLoanV1)
        ):
            raise ValueError
        work_key = f"dependency-completion:{key}:{head}"
        packet = WorkPacketV1(
            work_id="dependency-assessment-" + hashlib.sha256(work_key.encode()).hexdigest()[:32],
            work_key=work_key,
            intent={"dependency_completion": {field: hint[field] for field in fields}},
            execution={
                "adapter": "dependency-assessment",
                "executor_session_id": executor_session_id,
                "assessor_source": {"commit": source.source_commit, "sha256": source.script_sha256},
                "observed_heads": {"dependency_head": head},
            },
            initiator=identity,
            conductor=identity,
            required_capabilities=frozenset({"dependency-assessment"}),
            predicate=predicate,
            receipt_target=receipt_target,
            work_loan=work_loan,
            authority=AuthorityEnvelopeV1(repositories=frozenset({coordinate}), may_delegate=False),
            deadline=deadline,
            spend=SpendEnvelopeV1(limit=work_loan.budget_cost, reserve=work_loan.budget_cost),
            effect="read",
        )
        if packet_work_loan_missing(packet):
            raise ValueError
        return packet
    except (ValueError, TypeError, AttributeError, KeyError):
        raise AssessmentPacketError("assessment packet inputs are incomplete or invalid") from None
