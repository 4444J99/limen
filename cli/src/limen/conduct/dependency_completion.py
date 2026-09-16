"""One bounded dependency-hint consumption through the authenticated broker.

The caller supplies the reviewed assessment packet. This module neither chooses
executable policy nor runs candidate code. Work admission, debit and replay
semantics remain broker-owned; no hint or receipt is merge authority.
"""

from __future__ import annotations

import re
from typing import Any

from .client import HttpConductClient
from .models import WorkPacketV1


class CompletionContractError(ValueError):
    """The input cannot identify one source-bound, read-only assessment."""


def _require(condition: bool) -> None:
    if not condition:
        raise CompletionContractError("dependency completion contract is unmeasured")


def consume_completion(client: HttpConductClient, key: str, packet: WorkPacketV1) -> dict[str, Any]:
    """Read once, submit at most once if unbound, reconcile once; never poll.

    A lost submit response is ambiguous. Retrying this function later must use
    the same immutable packet; the broker's deterministic work-key index owns
    deduplication across the submit/association crash boundary.
    """
    _require(isinstance(client, HttpConductClient))
    _require(isinstance(packet, WorkPacketV1) and isinstance(key, str))
    result: dict[str, Any] = {"key": key, "state": "unmeasured", "automatic_acceptance": False}
    try:
        response = client.dependency_completion_hints()
        rows = response.get("hints")
        _require(response.get("schema") == "limen.dependency_completion_hints.v1")
        if not isinstance(rows, list):
            raise CompletionContractError("dependency completion hints are unmeasured")
        _require(response.get("automatic_acceptance") is False and len(rows) <= 100)
        _require(all(isinstance(row, dict) for row in rows))
        matches = [row for row in rows if row.get("key") == key]
        _require(len(matches) == 1)
        hint = matches[0]
        fields = ("repository_id", "run_id", "run_attempt", "head_sha")
        _require(all(type(hint.get(field)) is int and 0 < hint[field] < 2**53 for field in fields[:3]))
        _require(isinstance(hint.get("head_sha"), str) and bool(re.fullmatch(r"[a-f0-9]{40}", hint["head_sha"])))
        _require(key == f"{hint['repository_id']}:{hint['run_id']}:{hint['run_attempt']}")
        _require(hint.get("automatic_acceptance") is False)
        binding = packet.intent.get("dependency_completion")
        _require(isinstance(binding, dict) and all(binding.get(field) == hint[field] for field in fields))
        _require(packet.work_key == f"dependency-completion:{key}:{hint['head_sha']}")
        _require(
            packet.effect == "read" and not packet.authority.may_delegate and not packet.authority.external_effects
        )
        _require(packet.authority.repositories == frozenset({hint.get("coordinate")}))
        _require(packet.parent_run_id is None and packet.root_run_id is None)
        _require(packet.fanout.max_children == 0 and packet.fanout.max_depth == 0)
        _require(packet.execution.get("observed_heads", {}).get("dependency_head") == hint["head_sha"])
        prior = hint.get("broker_assessment")
        if prior is not None:
            _require(isinstance(prior, dict) and prior.get("automatic_acceptance") is False)
            run_id = prior.get("run_id")
        else:
            # No blind retries even if transport fails after the keeper commits.
            result["state"] = "submission_unmeasured"
            submitted = client.submit(packet)
            run_id = submitted.get("run_id")
        _require(isinstance(run_id, str) and bool(re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", run_id)))
        result.update(state="reconciliation_unmeasured", run_id=run_id)
        assessment = client.reconcile_dependency_assessment(key, run_id)
        _require(assessment.get("run_id") == run_id and assessment.get("automatic_acceptance") is False)
        _require(assessment.get("status") in {"unmeasured", "reported"})
        result.update(state="assessment_observed", assessment=assessment)
    except (CompletionContractError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
        # Provider details and credentials are never copied into the outcome.
        return result
    return result
