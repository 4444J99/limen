"""Recognize past retirement without deleting paths or dropping original coverage."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from limen.portable_custody import PortableCustodyError, validate_bundle

SCHEMA = "limen.scope_retirement.v1"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PortableCustodyError(reason)


def _ids(value: Any, *, allowed: set[str], reason: str) -> set[str]:
    _require(
        isinstance(value, list)
        and bool(value)
        and all(isinstance(key, str) for key in value)
        and len(value) == len(set(value))
        and set(value) <= allowed,
        reason,
    )
    return set(value)


def _time(value: Any, *, now: datetime) -> datetime:
    _require(isinstance(value, str), "retirement observation time is missing")
    observed = datetime.fromisoformat(value)
    _require(observed.tzinfo is not None and observed <= now, "retirement observation time is invalid")
    return observed


def validate_retirement(
    payload: bytes,
    custody_payload: bytes,
    *,
    session_id: str,
    original_scope_paths: Mapping[str, str],
    absent_root_ids: set[str],
    read_evidence: Callable[[dict], bytes],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Consume complete custody and exact execution/dependency observations.

    The caller proves absence and observes processes against ALL original paths.
    The evidence reader requires committed, unchanged, remotely durable bytes.
    Historical summaries and old ``retired_ids`` lists are not promoted to this
    contract. Native hardlink dependencies must close inside the retired cut set.
    Recognizing a past effect grants no present-day retirement authority.
    """
    now = now or datetime.now(UTC)
    _require(now.tzinfo is not None, "retirement verification time has no timezone")
    record = json.loads(payload)
    scope = dict(original_scope_paths)
    custody_digest = hashlib.sha256(custody_payload).hexdigest()
    _require(
        isinstance(record, dict)
        and record.get("schema") == SCHEMA
        and record.get("session_id") == session_id
        and record.get("scope_paths") == scope
        and record.get("custody_sha256") == custody_digest,
        "retirement original scope or custody binding differs",
    )
    retired = _ids(record.get("retired_root_ids"), allowed=set(scope), reason="retirement roots are malformed")
    _require(retired == absent_root_ids, "retirement roots do not match measured absence")
    try:
        custody = validate_bundle(
            custody_payload, session_id=session_id, scope_paths=scope, read_evidence=read_evidence, now=now
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise PortableCustodyError("retirement full custody graph is incomplete") from exc

    def evidence(packet: Any, schema: str) -> dict:
        _require(isinstance(packet, dict), "retirement supporting evidence is absent")
        raw = read_evidence(packet)
        _require(hashlib.sha256(raw).hexdigest() == packet.get("sha256"), "retirement evidence digest differs")
        value = json.loads(raw)
        _require(
            isinstance(value, dict)
            and value.get("schema") == schema
            and value.get("session_id") == session_id
            and value.get("scope_paths") == scope
            and value.get("custody_sha256") == custody_digest,
            "retirement observation binding differs",
        )
        return value

    packets = record.get("executions")
    _require(isinstance(packets, list) and bool(packets), "retirement execution evidence is absent")
    covered: set[str] = set()
    for packet in packets:
        execution = evidence(packet, "limen.scope_retirement_execution.v1")
        identifiers = _ids(
            execution.get("retired_root_ids"), allowed=retired, reason="retirement execution roots differ"
        )
        _require(not covered & identifiers, "retirement execution roots overlap")
        _require(
            type(execution.get("exit_code")) is int
            and execution["exit_code"] == 0
            and execution.get("absence_measured") is True,
            "retirement execution is not measured terminal success",
        )
        executed = _time(execution.get("executed_at"), now=now)
        _require(
            all(proof.restored_at <= executed for proof in custody.restoration_proofs),
            "retirement execution precedes full custody restoration",
        )
        dependency = evidence(execution.get("dependencies"), "limen.scope_retirement_dependencies.v1")
        observed = _time(dependency.get("observed_at"), now=executed)
        _require(
            observed >= max(proof.restored_at for proof in custody.restoration_proofs),
            "retirement dependency observation precedes custody restoration",
        )
        _require(
            dependency.get("scope_root_ids") == sorted(scope)
            and dependency.get("retired_root_ids") == sorted(identifiers)
            and dependency.get("observation_complete") is True,
            "retirement dependency coverage is incomplete",
        )
        edges, external = dependency.get("git_store_consumers"), dependency.get("external_consumers")
        _require(isinstance(edges, list) and isinstance(external, list), "retirement consumers are unmeasured")
        _require(not external, "retirement has external surviving consumers")
        for edge in edges:
            _require(
                isinstance(edge, dict) and edge.get("store_root_id") in scope and edge.get("consumer_root_id") in scope,
                "retirement Git dependency is malformed or outside coverage",
            )
            _require(
                edge["store_root_id"] not in identifiers or edge["consumer_root_id"] in identifiers,
                "retirement Git store has a surviving consumer",
            )
        covered.update(identifiers)
    _require(covered == retired, "retirement execution denominator is incomplete")

    bundle = json.loads(custody_payload)
    native_packet = bundle["supporting_evidence"][custody.native_metadata_digest]
    native_raw = read_evidence(native_packet)
    _require(
        hashlib.sha256(native_raw).hexdigest() == custody.native_metadata_digest,
        "retirement original native evidence differs",
    )
    native = json.loads(native_raw)
    groups: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for identifier, rows in native["entries"].items():
        for name, entry in rows.items():
            metadata = entry["metadata"]
            if metadata["type"] != "file":
                continue
            group = metadata["hardlink_group"]
            if metadata["nlink"] > 1:
                _require(isinstance(group, str), "retirement hardlink membership is unmeasured")
            if group is not None:
                groups[group].append((identifier, name, metadata["nlink"]))
    for group, members in groups.items():
        if any(identifier in retired for identifier, _, _ in members):
            _require(
                group in {f"{identifier}/{name}" for identifier, name, _ in members}
                and all(identifier in retired and links == len(members) for identifier, _, links in members),
                "retirement hardlink dependencies escape the retired cut set",
            )
    return {
        "schema": SCHEMA,
        "session_id": session_id,
        "original_root_ids": sorted(scope),
        "retired_root_ids": sorted(retired),
        "custody_sha256": custody_digest,
        "recorded_retirement_verified": True,
        "retirement_authorized": False,
    }
