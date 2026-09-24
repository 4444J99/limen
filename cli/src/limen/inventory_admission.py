"""Fail-closed inventory containment for Limen #269.

This module has no production authority adapter. Callers must obtain the private
canonical census, frozen repository IDs and generation through a trusted keeper
integration; task fields, local files and supplied receipts are not authority.
The default claim boundary rejects routine growth while that adapter is absent.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Mapping

from limen.github_estate_census import CONNECTION_KINDS, _canonical_sha256


POLICY_ISSUE = "https://github.com/4444J99/limen/issues/269"
INVENTORY_CEILING = 250
MAX_AGE_SECONDS = 900
_GENERATION = re.compile(r"[0-9a-f]{64}")


class InventoryAdmissionError(ValueError):
    """A safe public denial code; never include private census contents."""


def routine_inventory_growth(task: Mapping[str, Any]) -> bool:
    """Use stable generated IDs as well as the established build-out labels."""
    task_id = str(task.get("id") or "")
    labels = task.get("labels") or []
    return task_id.startswith(("GEN-", "BLD-", "BLD2-")) or (
        isinstance(labels, list) and "generated" in labels and "build-out" in labels
    )


def require_inventory_classification(prior: Mapping[str, Any], desired: Mapping[str, Any]) -> None:
    """Keep established routine classification until an authorized migration exists."""
    if routine_inventory_growth(prior) and not routine_inventory_growth(desired):
        raise InventoryAdmissionError("inventory_classification_change_unauthorized")


def _integer(value: Any, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InventoryAdmissionError(reason)
    return value


def _validate_connection_receipts(
    observation: Mapping[str, Any],
    cursors: list[Any],
    aliases: Mapping[str, str],
    expected_generation: str,
) -> None:
    """Use the emitter's existing global-to-repository receipt binding."""
    receipts = observation.get("repository_receipts")
    if not isinstance(receipts, list):
        raise InventoryAdmissionError("inventory_repository_receipts_required")
    rows_by_name: dict[str, list[dict[str, Any]]] = {name: [] for name in aliases}
    for cursor in cursors:
        if not isinstance(cursor, dict):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        name = cursor.get("repository")
        if not isinstance(name, str) or name not in rows_by_name:
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        rows_by_name[name].append(cursor)
    seen: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        name = receipt.get("repository")
        if not isinstance(name, str) or name not in aliases or name in seen:
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        seen.add(name)
        if (
            str(receipt.get("repository_id")) != aliases[name]
            or receipt.get("source_generation") != expected_generation
            or receipt.get("complete") is not True
        ):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        rows = rows_by_name[name]
        kinds = [row.get("kind") for row in rows]
        if len(rows) != len(CONNECTION_KINDS) or any(kinds.count(kind) != 1 for kind in CONNECTION_KINDS):
            raise InventoryAdmissionError("inventory_connection_partition_missing")
        if any(row.get("complete") is not True or row.get("exhaustive") is not True for row in rows):
            raise InventoryAdmissionError("inventory_connection_partition_incomplete")
        generations = [row.get("source_generation") for row in rows]
        if any(not isinstance(value, str) or not _GENERATION.fullmatch(value) for value in generations):
            raise InventoryAdmissionError("inventory_connection_generation_invalid")
        if any(value != generations[0] for value in generations[1:]):
            raise InventoryAdmissionError("inventory_connection_generation_invalid")
        try:
            digest = _canonical_sha256(rows)
        except (TypeError, ValueError):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid") from None
        if receipt.get("connection_receipt_digest") != digest:
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
    if seen != aliases.keys():
        raise InventoryAdmissionError("inventory_repository_receipts_required")


def _repository_connection_generation(repository: dict[str, Any], expected_generation: str) -> str:
    """Bind collector connection facts to this repository and census generation.

    This checks consistency within the trusted private observation; the keeper
    still owns authentication of the observation and the expected generation.
    """
    inputs = repository.get("connection_generation_inputs")
    totals = repository.get("connection_totals")
    if not isinstance(inputs, dict) or not isinstance(totals, dict):
        raise InventoryAdmissionError("inventory_repository_generation_invalid")
    fields = {
        "source_generation",
        "repository",
        "repository_updated_at",
        "default_sha",
        "default_check_policy",
        "required_check_count",
        "check_total",
        "open_pr_total",
        "issue_total",
        "branch_total",
    }
    if (
        inputs.keys() != fields
        or inputs.get("source_generation") != expected_generation
        or inputs.get("repository") != repository.get("name_with_owner")
        or any(
            inputs.get(field) != repository.get(field)
            for field in ("default_sha", "default_check_policy", "required_check_count")
        )
    ):
        raise InventoryAdmissionError("inventory_repository_generation_invalid")
    for field, kind in (
        ("open_pr_total", "pull_requests"),
        ("issue_total", "issues"),
        ("branch_total", "branches"),
        ("check_total", "checks"),
    ):
        if _integer(inputs.get(field), "inventory_repository_generation_invalid") != _integer(
            totals.get(kind), "inventory_repository_generation_invalid"
        ):
            raise InventoryAdmissionError("inventory_repository_generation_invalid")
    try:
        generation = _canonical_sha256(inputs)
    except (TypeError, ValueError):
        raise InventoryAdmissionError("inventory_repository_generation_invalid") from None
    if repository.get("connection_generation") != generation:
        raise InventoryAdmissionError("inventory_repository_generation_invalid")
    return generation


def inventory_count(
    observation: Mapping[str, Any],
    *,
    expected_repository_ids: frozenset[str],
    expected_generation: str,
    now: datetime,
) -> int:
    """Validate the existing full census; count authored PRs by stable repo ID.

    Expected scope/generation must come from the keeper's authenticated collector
    state, never from the candidate observation. Redacted/truncated projections
    deliberately cannot satisfy this predicate.
    """
    if observation.get("schema") != "limen.github-estate-census.v1":
        raise InventoryAdmissionError("inventory_schema_invalid")
    report = observation.get("source_report")
    if not isinstance(report, dict) or report.get("exhaustive") is not True:
        raise InventoryAdmissionError("inventory_partial_or_unknown")
    if not isinstance(expected_generation, str) or not _GENERATION.fullmatch(expected_generation):
        raise InventoryAdmissionError("inventory_generation_changed")
    if report.get("source_generation") != expected_generation:
        raise InventoryAdmissionError("inventory_generation_changed")
    try:
        observed = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
        if observed.tzinfo is None or now.tzinfo is None:
            raise ValueError("timezone missing")
        age = (now.astimezone(UTC) - observed.astimezone(UTC)).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise InventoryAdmissionError("inventory_timestamp_invalid") from None
    if age < 0 or age > MAX_AGE_SECONDS:
        raise InventoryAdmissionError("inventory_stale")
    repositories = observation.get("repositories")
    cursors = observation.get("cursors")
    leaves = observation.get("leaves")
    if not isinstance(repositories, list) or not isinstance(cursors, list) or not isinstance(leaves, list):
        raise InventoryAdmissionError("inventory_private_full_facts_required")
    if _integer(report.get("normalized_leaf_count"), "inventory_leaf_count_invalid") != len(leaves) or report.get(
        "content_sha256"
    ) != _canonical_sha256(leaves):
        raise InventoryAdmissionError("inventory_content_changed")
    if observation.get("failures") != []:
        raise InventoryAdmissionError("inventory_partial_or_unknown")
    aliases: dict[str, str] = {}
    generations: dict[str, str] = {}
    repository_pr_totals: dict[str, int] = {}
    for repository in repositories:
        if not isinstance(repository, dict):
            raise InventoryAdmissionError("inventory_repository_identity_invalid")
        identity = repository.get("repository_id")
        name = repository.get("name_with_owner")
        if isinstance(identity, bool) or not isinstance(identity, (int, str)) or not str(identity):
            raise InventoryAdmissionError("inventory_repository_identity_invalid")
        if not isinstance(name, str) or name.count("/") != 1 or name in aliases:
            raise InventoryAdmissionError("inventory_repository_identity_invalid")
        aliases[name] = str(identity)
        generations[name] = _repository_connection_generation(repository, expected_generation)
        repository_pr_totals[name] = repository["connection_totals"]["pull_requests"]
    if not expected_repository_ids or set(aliases.values()) != expected_repository_ids:
        raise InventoryAdmissionError("inventory_scope_changed")
    cursor_summary = report.get("cursor")
    if not isinstance(cursor_summary, dict):
        raise InventoryAdmissionError("inventory_repository_pagination_incomplete")
    repository_cursor = cursor_summary.get("repository")
    if not isinstance(repository_cursor, dict) or repository_cursor.get("exhaustive") is not True:
        raise InventoryAdmissionError("inventory_repository_pagination_incomplete")
    if (
        _integer(repository_cursor.get("expected_total"), "inventory_repository_total_unknown") != len(repositories)
        or _integer(repository_cursor.get("known_count"), "inventory_repository_total_unknown") != len(repositories)
        or _integer(repository_cursor.get("page_count"), "inventory_repository_pagination_incomplete") == 0
    ):
        raise InventoryAdmissionError("inventory_repository_pagination_incomplete")
    _validate_connection_receipts(observation, cursors, aliases, expected_generation)
    counts: dict[str, int] = {}
    for cursor in cursors:
        if not isinstance(cursor, dict) or cursor.get("kind") != "pull_requests":
            continue
        name = cursor.get("repository")
        if not isinstance(name, str) or name not in aliases or name in counts:
            raise InventoryAdmissionError("inventory_pr_pagination_invalid")
        count = _integer(cursor.get("expected_total"), "inventory_pr_total_unknown")
        if (
            cursor.get("complete") is not True
            or cursor.get("exhaustive") is not True
            or _integer(cursor.get("known_count"), "inventory_pr_total_unknown") != count
            or repository_pr_totals[name] != count
            or cursor.get("page_cursor") is not None
            or cursor.get("source_generation") != generations[name]
            or (_integer(cursor.get("page_count"), "inventory_pr_pagination_invalid") == 0 and count != 0)
        ):
            raise InventoryAdmissionError("inventory_pr_pagination_incomplete")
        counts[name] = count
    if counts.keys() != aliases.keys():
        raise InventoryAdmissionError("inventory_pr_partition_missing")
    seen: dict[tuple[str, int], str] = {}
    observed_counts = dict.fromkeys(aliases, 0)
    seen_named: set[tuple[str, int]] = set()
    for leaf in leaves:
        if not isinstance(leaf, dict) or leaf.get("kind") != "pull_request":
            continue
        name = leaf.get("repository")
        number = _integer(leaf.get("number"), "inventory_pr_identity_invalid")
        author = leaf.get("author_login")
        if not isinstance(name, str) or name not in aliases or number == 0 or not isinstance(author, str) or not author:
            raise InventoryAdmissionError("inventory_pr_identity_or_author_unknown")
        if (name, number) in seen_named:
            raise InventoryAdmissionError("inventory_pr_duplicate")
        seen_named.add((name, number))
        observed_counts[name] += 1
        key = (aliases[name], number)
        if key in seen and seen[key] != author.lower():
            raise InventoryAdmissionError("inventory_migration_conflict")
        seen[key] = author.lower()
    if observed_counts != counts:
        raise InventoryAdmissionError("inventory_pr_total_changed")
    return sum(author == "4444j99" for author in seen.values())


def require_inventory_admission(
    prior: Mapping[str, Any],
    desired: Mapping[str, Any],
    *,
    observation: Mapping[str, Any] | None = None,
    expected_repository_ids: frozenset[str] | None = None,
    expected_generation: str | None = None,
    active_reservations: int = 0,
    now: datetime | None = None,
) -> None:
    """Guard new claims inside the existing keeper transaction, before debit.

    Settlement and existing launches must remain possible. Exceptions/overrides
    need an authenticated owner decision in the future adapter; mutable task
    labels, supplied receipt fields and environment variables cannot override.
    Outstanding growth reservations must be counted in the same transaction.
    """
    require_inventory_classification(prior, desired)
    if prior.get("status") != "open" or desired.get("status") not in {"dispatched", "in_progress"}:
        return
    if not (routine_inventory_growth(prior) or routine_inventory_growth(desired)):
        return
    if observation is None or expected_repository_ids is None or expected_generation is None:
        raise InventoryAdmissionError("inventory_admission_adapter_unavailable")
    count = inventory_count(
        observation,
        expected_repository_ids=expected_repository_ids,
        expected_generation=expected_generation,
        now=now or datetime.now(UTC),
    )
    reservations = _integer(active_reservations, "inventory_reservations_unknown")
    if count + reservations >= INVENTORY_CEILING:
        raise InventoryAdmissionError("inventory_growth_ceiling")


def execution_policy(root=None) -> dict:
    """Read the existing host autonomy authority; missing/corrupt is contained."""
    import json
    import os
    from pathlib import Path

    root = Path(
        root or os.environ.get("LIMEN_LIVE_ROOT") or os.environ.get("LIMEN_ROOT") or Path.home() / "Workspace" / "limen"
    )
    try:
        value = json.loads((root / "logs" / "autonomy-policy.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def require_approved_priority(work_key: str | None, *, root=None) -> dict:
    policy = execution_policy(root)
    priorities = policy.get("approved_priorities", [])
    priority = next(
        (
            row
            for row in priorities
            if isinstance(row, dict) and work_key in row.get("work_keys", []) and row.get("enabled") is True
        ),
        None,
    )
    if priority is None:
        raise InventoryAdmissionError("execution_priority_not_approved")
    if policy.get("mode") != "dispatch" and not (policy.get("mode") == "recovery" and priority.get("recovery") is True):
        raise InventoryAdmissionError("execution_contained")
    return priority


def reserve_growth(action: str, identity: str, *, work_key: str | None = None, root=None) -> None:
    """One shared durable allowance across issue/branch/worktree producers.

    Charge before the effect. Ambiguous or failed effects retain their charge;
    restarting a producer never resets its limit. This is runtime evidence under
    the existing autonomy policy, not another task registry.
    """
    # Production producers share the authenticated keeper, including remote lanes.
    # Explicit root is the isolated local fixture adapter; no production caller
    # supplies it and absence of keeper credentials never falls back to local state.
    if root is None:
        import hashlib
        import os
        from limen.conduct.client import client_from_env, HttpConductClient

        client = client_from_env()
        if not isinstance(client, HttpConductClient):
            raise InventoryAdmissionError("execution_remote_keeper_required")
        key = work_key or os.environ.get("LIMEN_WORK_KEY")
        if not key:
            raise InventoryAdmissionError("execution_work_key_required")
        client.reserve_growth(key, action, hashlib.sha256(identity.encode()).hexdigest())
        return
    import fcntl
    import hashlib
    import json
    import os
    from pathlib import Path

    root = Path(
        root or os.environ.get("LIMEN_LIVE_ROOT") or os.environ.get("LIMEN_ROOT") or Path.home() / "Workspace" / "limen"
    )
    priority = require_approved_priority(work_key or os.environ.get("LIMEN_WORK_KEY"), root=root)
    if action not in {"issue", "branch", "worktree"}:
        raise InventoryAdmissionError("execution_resource_unknown")
    limit = priority.get("resource_limits", {}).get(action, 0)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise InventoryAdmissionError("execution_resource_not_approved")
    directory = root / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "autonomy-growth-reservations.json"
    with (directory / "autonomy-growth-reservations.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            ledger = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, ValueError) as exc:
            raise InventoryAdmissionError("execution_resource_ledger_unavailable") from exc
        key = hashlib.sha256(f"{priority['outcome_id']}:{action}:{identity}".encode()).hexdigest()
        # Repeated reservation is denied: the prior external effect may have happened.
        if key in ledger:
            raise InventoryAdmissionError("execution_resource_already_reserved")
        used = sum(row["outcome_id"] == priority["outcome_id"] and row["action"] == action for row in ledger.values())
        if used >= limit:
            raise InventoryAdmissionError("execution_resource_budget_exhausted")
        ledger[key] = {"outcome_id": priority["outcome_id"], "action": action}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(ledger, sort_keys=True) + "\n")
        os.replace(temporary, path)


def admit_execution(
    policy: dict | None, state: dict, packet: dict, now: datetime, *, waiting=False, retained=None, legacy=False
) -> dict | None:
    """Reserve bounded outcome capacity in the broker's existing run ledger."""
    if policy is None:
        return None
    parent = state["runs"].get(packet.get("parent_run_id"))
    inherited = (parent or {}).get("execution_admission") or {}
    priority = next(
        (
            row
            for row in policy.get("approved_priorities", [])
            if (parent and row["outcome_id"] == inherited.get("outcome_id"))
            or (
                not parent
                and (
                    packet["work_key"] in row.get("work_keys", []) or packet.get("task_id") in row.get("work_keys", [])
                )
            )
        ),
        None,
    )

    def require(ok, code):
        if not ok:
            raise InventoryAdmissionError(code)

    if priority is None or priority.get("enabled") is not True:
        raise InventoryAdmissionError("execution_priority_not_approved")
    require(
        policy.get("mode") == "dispatch" or (policy.get("mode") == "recovery" and priority.get("recovery") is True),
        "execution_contained",
    )
    runs = list(state["runs"].values())
    require(
        waiting
        or sum(
            execution_occupied(r, now)
            or (not r.get("execution_admission") and r["status"] in {"reserved", "running", "stop_requested"})
            for r in runs
            if r["packet"].get("intent", {}).get("kind") != "fanout-root"
        )
        < (1 if policy.get("mode") == "recovery" else 2),
        "execution_concurrency_exhausted",
    )
    prior = [r for r in runs if (r.get("execution_admission") or {}).get("outcome_id") == priority["outcome_id"]]
    require(
        sum(r["execution_admission"]["reserved_seconds"] for r in prior) + 1800 <= 7200,
        "execution_outcome_budget_exhausted",
    )
    input_hash = (
        packet.get("intent", {}).get("log", {}).get("execution_contract_hash") if legacy else packet["execution_hash"]
    )
    require(isinstance(input_hash, str) and bool(input_hash), "execution_input_fingerprint_required")
    if not parent:
        roots = [r for r in prior if not r.get("parent_run_id")]
        require(len(roots) < 2, "execution_corrective_retry_exhausted")
        require(
            all(r["execution_admission"].get("input_hash", r["packet"]["execution_hash"]) != input_hash for r in roots),
            "execution_retry_inputs_unchanged",
        )
    require(packet["retry"]["max_attempts"] <= 1, "execution_retry_requires_changed_inputs")
    from datetime import timedelta

    deadline = min(datetime.fromisoformat(packet["deadline"].replace("Z", "+00:00")), now + timedelta(minutes=30))
    if retained:
        deadline = min(deadline, datetime.fromisoformat(retained["attempt_deadline"].replace("Z", "+00:00")))
    if parent:
        deadline = min(
            deadline,
            datetime.fromisoformat(
                inherited.get("attempt_deadline", parent["packet"]["deadline"]).replace("Z", "+00:00")
            ),
        )
    require(deadline > now, "execution_attempt_exhausted")
    deadline_policy = priority.get("deadline_policy", "hard_deadline")
    require(deadline_policy in {"hard_deadline", "fenced_async"}, "execution_deadline_policy_invalid")
    if inherited:
        require(
            deadline_policy == inherited.get("deadline_policy", "hard_deadline"), "execution_deadline_policy_changed"
        )
    return {
        "deadline_policy": deadline_policy,
        "outcome_id": priority["outcome_id"],
        "reserved_seconds": 1800,
        "attempt_deadline": deadline.isoformat(),
        "verification_seconds": 600,
        "input_hash": input_hash,
        "legacy_active": legacy,
        "resource_reservations": (retained or {}).get("resource_reservations", []),
    }


def projection_execution_status(packet):
    intent = packet.get("intent") or {}
    if intent.get("kind") == "task.claim":
        return "dispatched"
    return intent.get("status") or (intent.get("patch") or {}).get("status") or (intent.get("task") or {}).get("status")


def execution_active(run, now):
    admission = run.get("execution_admission")
    if not admission or datetime.fromisoformat(admission["attempt_deadline"].replace("Z", "+00:00")) <= now:
        return False
    return admission.get("legacy_active") is True or run["status"] in {"reserved", "running", "stop_requested"}


def pending_remote_attempts(run):
    """An expired local lease is not proof that uncancellable Jules work stopped.

    Old records without provider_state remain unknown; only explicit terminal
    observation or a definite pre-submission refusal releases remote occupancy.
    """
    return [
        attempt
        for attempt in run.get("attempts", [])
        if attempt.get("adapter") == "jules-api"
        and attempt.get("provider_state", "unknown") not in {"not_started", "terminal"}
    ]


def execution_occupied(run, now):
    """Capacity accounting only. Never use this as permission to execute or land."""
    return execution_active(run, now) or bool(pending_remote_attempts(run))
