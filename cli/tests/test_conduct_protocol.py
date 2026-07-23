from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from limen.conduct import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    ConductBroker,
    ConductConflict,
    ConductPrincipalV1,
    ExecutorAttemptV1,
    FanoutBoundsV1,
    MemoryStateStore,
    ResourceClaimV1,
    RetryPolicyV1,
    RunReceiptV1,
    SpendEnvelopeV1,
    WorkPacketV1,
)
from limen.conduct.models import PredicateEvidenceV1
from limen.conduct.models import canonical_hash
from limen.conduct.resources import resources_overlap
from limen.work_loan import WorkLoanV1


NOW = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)


def identity(agent: str, session_id: str | None = None) -> AgentIdentityV1:
    return AgentIdentityV1(agent=agent, surface="cli", session_id=session_id or f"{agent}-session")


def session(
    agent: str,
    *,
    session_id: str | None = None,
    capabilities: frozenset[str] = frozenset({"code", "conduct", "review"}),
    concurrency: int = 8,
    heartbeat_at: datetime = NOW,
    protected: bool = False,
) -> ConductorSessionV1:
    ident = identity(agent, session_id)
    return ConductorSessionV1(
        session_id=ident.session_id,
        identity=ident,
        origin="direct" if protected else "dispatched",
        capabilities=capabilities,
        concurrency=concurrency,
        heartbeat_at=heartbeat_at,
        human_protected=protected,
    )


def packet(
    *,
    work_id: str,
    conductor: AgentIdentityV1,
    resource: str = "task/T-1",
    work_key: str | None = None,
    parent_run_id: str | None = None,
    root_run_id: str | None = None,
    depth: int = 0,
    max_children: int = 3,
    max_depth: int = 3,
    preferred_agent: str | None = None,
    effect: str = "write",
    claims: tuple[ResourceClaimV1, ...] | None = None,
    authority: AuthorityEnvelopeV1 | None = None,
    spend_limit: int = 4,
    underwritten: bool = True,
) -> WorkPacketV1:
    return WorkPacketV1(
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
        work_id=work_id,
        work_key=work_key or work_id,
        intent={"objective": work_id},
        execution={"command": "pytest -q", "observed_heads": {"pr": "abc123"}},
        initiator=conductor,
        conductor=conductor,
        preferred_agent=preferred_agent,
        required_capabilities=frozenset({"code"}),
        resource_claims=claims if claims is not None else (ResourceClaimV1(key=resource),),
        predicate="pytest -q",
        receipt_target=f"github:organvm/limen:pull-request:{work_id}",
        work_loan=(
            WorkLoanV1(
                source_origin="human_prompt",
                horizon="present",
                value_case=f"Deliver the bounded conduct packet {work_id}",
                budget_cost=spend_limit,
                owner_surface="organvm/limen",
            )
            if underwritten
            else None
        ),
        authority=authority
        or AuthorityEnvelopeV1(
            actions=frozenset({"code", "review"}),
            repositories=frozenset({"organvm/limen"}),
            path_prefixes=frozenset({"cli"}),
            external_effects=frozenset(),
        ),
        deadline=NOW + timedelta(hours=1),
        spend=SpendEnvelopeV1(limit=spend_limit),
        retry=RetryPolicyV1(max_attempts=2),
        depth=depth,
        fanout=FanoutBoundsV1(max_children=max_children, max_depth=max_depth),
        effect=effect,
    )


def broker_with(*sessions: ConductorSessionV1) -> ConductBroker:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-capability-secret")
    for item in sessions:
        broker.register(item, now=NOW)
    return broker


def capability(broker: ConductBroker, reserved: dict) -> str:
    lease = reserved["lease"]
    return broker.claim(lease["lease_id"], lease["generation"], now=NOW)["capability_token"]


def principal(
    principal_id: str,
    agent: str,
    *roles: str,
) -> ConductPrincipalV1:
    return ConductPrincipalV1(
        principal_id=principal_id,
        agent=agent,
        surface="cloud",
        roles=frozenset(roles),
    )


def test_packet_hashes_are_canonical_and_mismatch_is_rejected() -> None:
    conductor = identity("codex")
    first = packet(work_id="hash-one", conductor=conductor)
    second = packet(work_id="hash-one", conductor=conductor)
    assert first.intent_hash == second.intent_hash
    assert first.execution_hash == second.execution_hash
    with pytest.raises(ValueError, match="intent_hash"):
        WorkPacketV1(**(first.model_dump() | {"intent_hash": "0" * 64}))


def test_rfc8785_hash_fixture_matches_worker_runtime() -> None:
    vectors_path = Path(__file__).resolve().parents[2] / "spec/contracts/conduct/rfc8785-vectors.json"
    vectors = json.loads(vectors_path.read_text())["vectors"]
    assert len(vectors) >= 2
    for vector in vectors:
        assert canonical_hash(vector["value"]) == vector["sha256"]


def test_executor_attempt_schema_matches_python_runtime() -> None:
    schema_path = (
        Path(__file__).resolve().parents[2] / "spec" / "contracts" / "conduct" / "executor-attempt-v1.schema.json"
    )
    assert json.loads(schema_path.read_text(encoding="utf-8")) == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **ExecutorAttemptV1.model_json_schema(mode="validation"),
    }


def test_work_packet_schema_exposes_optional_work_loan_compatibly() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "spec" / "contracts" / "conduct" / "work-packet-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **WorkPacketV1.model_json_schema(mode="validation"),
    }
    assert "work_loan" not in schema["required"]


def test_broker_reserve_and_claim_fail_closed_with_stable_underwriting_denial() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    legacy = packet(work_id="legacy-readable", conductor=codex.identity, underwritten=False)

    assert legacy.work_loan is None
    with pytest.raises(
        ConductConflict,
        match=("^task-not-underwritten:source_origin,horizon,value_case,budget_cost,owner_surface$"),
    ):
        broker.submit(legacy, now=NOW)

    admitted = broker.submit(packet(work_id="underwritten", conductor=codex.identity), now=NOW)
    stored = broker.store.snapshot()["runs"][admitted["run_id"]]
    stored["packet"].pop("work_loan")
    broker.store = MemoryStateStore(broker.store.snapshot() | {"runs": {admitted["run_id"]: stored}})
    with pytest.raises(
        ConductConflict,
        match=("^task-not-underwritten:source_origin,horizon,value_case,budget_cost,owner_surface$"),
    ):
        broker.claim(admitted["lease"]["lease_id"], admitted["lease"]["generation"], now=NOW)


def test_path_prefix_overlap_and_review_writer_coexistence() -> None:
    assert resources_overlap(
        ResourceClaimV1(key="path/organvm/limen/main/cli"),
        ResourceClaimV1(key="path/organvm/limen/main/cli/src"),
    )
    assert not resources_overlap(
        ResourceClaimV1(key="path/organvm/limen/main/cli"),
        ResourceClaimV1(key="path/organvm/limen/main/web"),
    )
    assert not resources_overlap(
        ResourceClaimV1(key="pr/organvm/limen/7/write@abc"),
        ResourceClaimV1(key="pr/organvm/limen/7/review/copilot@abc"),
    )
    assert resources_overlap(
        ResourceClaimV1(key="pr/organvm/limen/7/review/copilot@abc"),
        ResourceClaimV1(key="pr/organvm/limen/7/review/copilot@abc"),
    )
    assert resources_overlap(
        ResourceClaimV1(key="pr/organvm/limen/7/review/copilot@abc", mode="shared"),
        ResourceClaimV1(key="pr/organvm/limen/7/review/copilot@abc", mode="shared"),
    )
    assert resources_overlap(
        ResourceClaimV1(key="repo/*/*/write"),
        ResourceClaimV1(key="branch/organvm/limen/main"),
    )
    assert not resources_overlap(
        ResourceClaimV1(key="repo/*/*/write"),
        ResourceClaimV1(key="pr/organvm/limen/7/review/claude@abc"),
    )


def test_fifty_conductors_race_one_task_gets_one_lease() -> None:
    sessions = [session(f"lane{i}", session_id=f"session{i}", concurrency=100) for i in range(50)]
    broker = broker_with(*sessions)

    def submit(index: int) -> dict:
        return broker.submit(
            packet(
                work_id=f"race-{index}",
                conductor=sessions[index].identity,
                resource="task/SAME",
                preferred_agent=sessions[index].identity.agent,
            ),
            now=NOW,
        )

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(submit, range(50)))
    assert [result["status"] for result in results].count("reserved") == 1
    assert [result["status"] for result in results].count("busy") == 49
    assert len({result["busy_receipt_id"] for result in results if result["status"] == "busy"}) == 49
    snapshot = broker.store.snapshot()
    assert len(snapshot["leases"]) == 1
    assert len([event for event in snapshot["events"] if event["kind"] == "run.reserved"]) == 1


def test_principals_bind_sessions_and_executor_claims_without_leaking_tokens() -> None:
    broker = ConductBroker(
        MemoryStateStore(),
        capability_secret="principal-bound-capability-secret",
    )
    conductor_principal = principal("principal-conductor", "codex", "observer", "conductor")
    executor_principal = principal("principal-executor", "claude", "observer", "executor")
    attacker_principal = principal("principal-attacker", "opencode", "observer", "executor")
    attacker_conductor = principal(
        "principal-attacker-conductor",
        "opencode",
        "observer",
        "conductor",
    )
    requested_conductor = session("spoofed", session_id="conductor-session")
    requested_executor = session(
        "spoofed",
        session_id="executor-session",
        capabilities=frozenset({"code"}),
    )
    registered_conductor = ConductorSessionV1.model_validate(
        broker.register(requested_conductor, principal=conductor_principal, now=NOW)
    )
    broker.register(requested_executor, principal=executor_principal, now=NOW)
    assert registered_conductor.identity.agent == "codex"
    reserved = broker.submit(
        packet(
            work_id="principal-bound",
            conductor=registered_conductor.identity,
            preferred_agent="claude",
        ),
        principal=conductor_principal,
        now=NOW,
    )
    assert "capability_token" not in reserved
    assert "capability_token_hash" not in reserved["lease"]
    lease = reserved["lease"]
    with pytest.raises(ConductConflict, match="another executor principal"):
        broker.claim(
            lease["lease_id"],
            lease["generation"],
            principal=attacker_principal,
            now=NOW,
        )
    first = broker.claim(
        lease["lease_id"],
        lease["generation"],
        principal=executor_principal,
        now=NOW,
    )
    second = broker.claim(
        lease["lease_id"],
        lease["generation"],
        principal=executor_principal,
        now=NOW,
    )
    assert first["capability_token"] == second["capability_token"]
    with pytest.raises(ConductConflict, match="generation"):
        broker.heartbeat(
            lease["lease_id"],
            first["capability_token"],
            generation=lease["generation"] + 1,
            principal=executor_principal,
            now=NOW,
        )
    with pytest.raises(ConductConflict, match="authenticated principal"):
        broker.cancel(
            reserved["run_id"],
            registered_conductor.session_id,
            principal=attacker_conductor,
            now=NOW,
        )


def test_declared_conductor_identity_matches_after_principal_binding() -> None:
    """A client may submit the identity it declared, not the register echo (#1408).

    register() rebinds agent/surface to the token principal; submit must apply
    the same binding before comparing or the tabularius relay can never match.
    """
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-capability-secret")
    relay_principal = principal("principal-relay", "codex", "observer", "conductor")
    requested = session("claude", session_id="relay-session")
    broker.register(requested, principal=relay_principal, now=NOW)
    reserved = broker.submit(
        packet(work_id="relay-declared-identity", conductor=requested.identity),
        principal=relay_principal,
        now=NOW,
    )
    assert reserved["run_id"]
    with pytest.raises(ConductConflict, match="not bound to the authenticated principal"):
        broker.submit(
            packet(work_id="relay-imposter", conductor=requested.identity),
            principal=principal("principal-imposter", "codex", "observer", "conductor"),
            now=NOW,
        )
    with pytest.raises(ConductConflict, match="does not match its registered session"):
        broker.submit(
            packet(work_id="relay-foreign", conductor=requested.identity),
            principal=principal("principal-foreign", "opencode", "observer", "conductor"),
            now=NOW,
        )


def test_executor_attempts_are_capability_bound_idempotent_and_publicly_token_free() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(
        packet(work_id="attempt-bound", conductor=codex.identity),
        now=NOW,
    )
    lease = reserved["lease"]
    token = capability(broker, reserved)
    launching = ExecutorAttemptV1(
        attempt_id="attempt-bound-1",
        run_id=reserved["run_id"],
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=codex.identity,
        adapter="fixture-remote",
        status="launching",
        submitted_at=NOW,
        updated_at=NOW,
    )
    created = broker.heartbeat(
        lease["lease_id"],
        token,
        generation=lease["generation"],
        observed_heads={"pr": "abc123"},
        attempt=launching,
        now=NOW,
    )
    assert created["attempt_created"] is True
    submitted = launching.model_copy(
        update={
            "provider_run_id": "provider-run-1",
            "provider_run_url": "https://executor.example/runs/1",
            "status": "submitted",
        }
    )
    updated = broker.heartbeat(
        lease["lease_id"],
        token,
        generation=lease["generation"],
        observed_heads={"pr": "abc123"},
        attempt=submitted,
        now=NOW,
    )
    assert updated["attempt_created"] is False
    graph = broker.graph(reserved["run_id"])
    assert graph["nodes"][0]["attempts"] == [submitted.model_dump(mode="json")]
    assert "capability_token_hash" not in graph["nodes"][0]["lease"]
    with pytest.raises(ConductConflict, match="provider receipt identity changed"):
        broker.heartbeat(
            lease["lease_id"],
            token,
            generation=lease["generation"],
            observed_heads={"pr": "abc123"},
            attempt=submitted.model_copy(update={"provider_run_id": "provider-run-2"}),
            now=NOW,
        )


def test_attempt_limit_is_keeper_enforced() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(packet(work_id="attempt-limit", conductor=codex.identity), now=NOW)
    lease = reserved["lease"]
    token = capability(broker, reserved)
    for number in (1, 2):
        attempt = ExecutorAttemptV1(
            attempt_id=f"attempt-limit-{number}",
            run_id=reserved["run_id"],
            lease_id=lease["lease_id"],
            lease_generation=lease["generation"],
            executor=codex.identity,
            adapter=f"fixture-{number}",
            status="failed",
            submitted_at=NOW,
            updated_at=NOW,
        )
        broker.heartbeat(
            lease["lease_id"],
            token,
            generation=lease["generation"],
            observed_heads={"pr": "abc123"},
            attempt=attempt,
            now=NOW,
        )
    third = ExecutorAttemptV1(
        attempt_id="attempt-limit-3",
        run_id=reserved["run_id"],
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=codex.identity,
        adapter="fixture-3",
        status="failed",
        submitted_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(ConductConflict, match="attempt limit"):
        broker.heartbeat(
            lease["lease_id"],
            token,
            generation=lease["generation"],
            observed_heads={"pr": "abc123"},
            attempt=third,
            now=NOW,
        )


def test_transient_attempt_reroutes_to_another_executor_principal() -> None:
    broker = ConductBroker(
        MemoryStateStore(),
        capability_secret="reroute-principal-capability-secret",
    )
    conductor_principal = principal("reroute-conductor", "codex", "observer", "conductor")
    first_principal = principal("reroute-first", "claude", "observer", "executor")
    second_principal = principal("reroute-second", "jules", "observer", "executor")
    conductor = ConductorSessionV1.model_validate(
        broker.register(
            session(
                "spoofed",
                session_id="reroute-conductor-session",
                capabilities=frozenset({"conduct"}),
            ),
            principal=conductor_principal,
            now=NOW,
        )
    )
    broker.register(
        session("spoofed", session_id="reroute-first-session", capabilities=frozenset({"code"})),
        principal=first_principal,
        now=NOW,
    )
    broker.register(
        session("spoofed", session_id="reroute-second-session", capabilities=frozenset({"code"})),
        principal=second_principal,
        now=NOW,
    )
    reserved = broker.submit(
        packet(
            work_id="attempt-reroute",
            conductor=conductor.identity,
            preferred_agent="claude",
        ),
        principal=conductor_principal,
        now=NOW,
    )
    old_lease = reserved["lease"]
    old_claim = broker.claim(
        old_lease["lease_id"],
        old_lease["generation"],
        principal=first_principal,
        now=NOW,
    )
    failed = ExecutorAttemptV1(
        attempt_id="attempt-reroute-1",
        run_id=reserved["run_id"],
        lease_id=old_lease["lease_id"],
        lease_generation=old_lease["generation"],
        executor=AgentIdentityV1.model_validate(old_lease["executor"]),
        adapter="fixture-first",
        status="failed",
        failure_class="transient",
        submitted_at=NOW,
        updated_at=NOW,
    )
    rerouted = broker.heartbeat(
        old_lease["lease_id"],
        old_claim["capability_token"],
        generation=old_lease["generation"],
        principal=first_principal,
        observed_heads={"pr": "abc123"},
        attempt=failed,
        now=NOW,
    )
    assert rerouted["status"] == "rerouted"
    assert rerouted["lease"]["generation"] > old_lease["generation"]
    assert rerouted["lease"]["executor"]["agent"] == "jules"
    with pytest.raises(ConductConflict, match="another executor principal"):
        broker.claim(
            rerouted["lease"]["lease_id"],
            rerouted["lease"]["generation"],
            principal=first_principal,
            now=NOW,
        )
    broker.claim(
        rerouted["lease"]["lease_id"],
        rerouted["lease"]["generation"],
        principal=second_principal,
        now=NOW,
    )
    graph = broker.graph(reserved["run_id"])
    assert graph["nodes"][0]["attempts"] == [failed.model_dump(mode="json")]
    assert "capability_token_hash" not in graph["nodes"][0]["lease"]


def test_spend_limit_and_permanent_failure_stop_retry() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    bounded = packet(work_id="attempt-spend", conductor=codex.identity).model_copy(
        update={
            "spend": SpendEnvelopeV1(limit=1),
            "work_loan": WorkLoanV1(
                source_origin="human_prompt",
                horizon="present",
                value_case="Exercise bounded retry spend enforcement",
                budget_cost=1,
                owner_surface="organvm/limen",
            ),
            "retry": RetryPolicyV1(max_attempts=2, transient_only=True),
        }
    )
    reserved = broker.submit(bounded, now=NOW)
    lease = reserved["lease"]
    token = capability(broker, reserved)
    failed = ExecutorAttemptV1(
        attempt_id="attempt-spend-1",
        run_id=reserved["run_id"],
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=codex.identity,
        adapter="fixture",
        status="failed",
        failure_class="permanent",
        submitted_at=NOW,
        updated_at=NOW,
    )
    heartbeat = broker.heartbeat(
        lease["lease_id"],
        token,
        generation=lease["generation"],
        observed_heads={"pr": "abc123"},
        attempt=failed,
        now=NOW,
    )
    assert heartbeat["status"] == "active"
    with pytest.raises(ConductConflict, match="spend limit"):
        broker.heartbeat(
            lease["lease_id"],
            token,
            generation=lease["generation"],
            observed_heads={"pr": "abc123"},
            attempt=failed.model_copy(update={"attempt_id": "attempt-spend-2"}),
            now=NOW,
        )


def test_read_receipt_cannot_change_paths_or_heads() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(
        packet(work_id="read-no-mutation", conductor=codex.identity, effect="read"),
        now=NOW,
    )
    lease = reserved["lease"]
    token = capability(broker, reserved)
    receipt = RunReceiptV1(
        receipt_id="receipt-read-mutated",
        run_id=reserved["run_id"],
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=codex.identity,
        observed_heads_before={"pr": "abc123"},
        observed_heads_after={"pr": "different"},
        changed_paths=("cli/changed.py",),
        predicate=PredicateEvidenceV1(command="pytest -q", exit_code=0),
        spend={"runs": 1},
        outcome="succeeded",
    )
    result = broker.report(
        lease["lease_id"],
        token,
        receipt,
        generation=lease["generation"],
        now=NOW,
    )
    assert result["mutation_authorized"] is False


def test_graph_submission_is_atomic_and_idempotent() -> None:
    codex = session("codex", concurrency=8)
    broker = broker_with(codex)
    root = packet(
        work_id="atomic-root",
        conductor=codex.identity,
        resource="task/atomic-root",
        spend_limit=4,
        effect="read",
    )
    root_run_id = ConductBroker._run_id(root)
    child_one = packet(
        work_id="atomic-child-one",
        conductor=codex.identity,
        resource="task/atomic-child-one",
        parent_run_id=root_run_id,
        root_run_id=root_run_id,
        depth=1,
        spend_limit=1,
        effect="read",
    )
    child_two = packet(
        work_id="atomic-child-two",
        conductor=codex.identity,
        resource="task/atomic-child-two",
        parent_run_id=root_run_id,
        root_run_id=root_run_id,
        depth=1,
        spend_limit=1,
        effect="read",
    )
    submitted = broker.submit_graph((root, child_one, child_two), now=NOW)
    assert submitted["status"] == "reserved"
    assert len(broker.graph(root_run_id)["nodes"]) == 3
    duplicate = broker.submit_graph((root, child_one, child_two), now=NOW)
    assert [run["status"] for run in duplicate["runs"]] == ["duplicate"] * 3

    conflicting_root = packet(
        work_id="rollback-root",
        conductor=codex.identity,
        resource="task/rollback-root",
        effect="read",
    )
    conflicting_root_id = ConductBroker._run_id(conflicting_root)
    conflicting_child = packet(
        work_id="rollback-child",
        conductor=codex.identity,
        resource="task/atomic-child-one",
        parent_run_id=conflicting_root_id,
        root_run_id=conflicting_root_id,
        depth=1,
        spend_limit=1,
        effect="read",
    )
    before = broker.store.snapshot()
    busy = broker.submit_graph((conflicting_root, conflicting_child), now=NOW)
    assert busy["status"] == "busy"
    assert broker.store.snapshot() == before


def test_unregistered_conductor_and_unknown_write_scope_fail_closed() -> None:
    codex = session("codex", concurrency=4)
    broker = broker_with(codex)
    impostor = identity("claude")
    with pytest.raises(ConductConflict, match="registered"):
        broker.submit(packet(work_id="unregistered", conductor=impostor), now=NOW)

    first = broker.submit(
        packet(
            work_id="unknown-one",
            conductor=codex.identity,
            resource="task/ONE",
        ),
        now=NOW,
    )
    second = broker.submit(
        packet(
            work_id="unknown-two",
            conductor=codex.identity,
            resource="task/TWO",
        ),
        now=NOW,
    )
    assert first["status"] == "reserved"
    assert second["status"] == "busy"
    assert ("repo/organvm/limen/write", "repo/organvm/limen/write") in second["conflicts"][0]["keys"]


def test_different_task_ids_cannot_race_one_pr_but_reviewers_coexist() -> None:
    codex = session("codex")
    claude = session("claude")
    copilot = session("copilot")
    broker = broker_with(codex, claude, copilot)
    writer = broker.submit(
        packet(
            work_id="writer-one",
            conductor=codex.identity,
            resource="pr/organvm/limen/77/write@abc",
            preferred_agent="codex",
        ),
        now=NOW,
    )
    assert writer["status"] == "reserved"
    second = broker.submit(
        packet(
            work_id="writer-two",
            conductor=claude.identity,
            resource="pr/organvm/limen/77/write@abc",
            preferred_agent="claude",
        ),
        now=NOW,
    )
    assert second["status"] == "busy"
    review = broker.submit(
        packet(
            work_id="review-one",
            conductor=copilot.identity,
            resource="pr/organvm/limen/77/review/copilot@abc",
            preferred_agent="copilot",
            effect="read",
        ),
        now=NOW,
    )
    assert review["status"] == "reserved"


def test_five_primary_agents_execute_disjoint_work_simultaneously() -> None:
    names = ["codex", "claude", "copilot", "agy", "opencode"]
    sessions = [session(name, concurrency=1) for name in names]
    broker = broker_with(*sessions)
    results = [
        broker.submit(
            packet(
                work_id=f"matrix-{name}",
                conductor=item.identity,
                resource=f"path/organvm/repo-{name}/main/src",
                preferred_agent=name,
                authority=AuthorityEnvelopeV1(
                    actions=frozenset({"code"}),
                    repositories=frozenset({f"organvm/repo-{name}"}),
                    path_prefixes=frozenset({"src"}),
                ),
            ),
            now=NOW,
        )
        for name, item in zip(names, sessions, strict=True)
    ]
    assert [result["status"] for result in results] == ["reserved"] * 5
    assert {result["lease"]["executor"]["agent"] for result in results} == set(names)


def test_complete_primary_initiator_target_matrix_preserves_native_identity() -> None:
    names = ["codex", "claude", "copilot", "agy", "opencode"]
    sessions = [session(name, concurrency=5) for name in names]
    broker = broker_with(*sessions)
    results = []
    for conductor in sessions:
        for target in names:
            result = broker.submit(
                packet(
                    work_id=f"matrix-{conductor.identity.agent}-to-{target}",
                    conductor=conductor.identity,
                    resource=(f"path/organvm/matrix-{conductor.identity.agent}-{target}/main/src"),
                    preferred_agent=target,
                    authority=AuthorityEnvelopeV1(
                        actions=frozenset({"code"}),
                        repositories=frozenset({f"organvm/matrix-{conductor.identity.agent}-{target}"}),
                        path_prefixes=frozenset({"src"}),
                    ),
                ),
                now=NOW,
            )
            results.append((conductor.identity.agent, target, result))
    assert len(results) == 25
    assert all(result["status"] == "reserved" for _, _, result in results)
    assert all(result["lease"]["executor"]["agent"] == target for _, target, result in results)
    snapshot = broker.store.snapshot()
    for conductor, target, result in results:
        run = snapshot["runs"][result["run_id"]]
        assert run["packet"]["conductor"]["agent"] == conductor
        assert run["packet"]["initiator"]["agent"] == conductor
        assert run["packet"]["preferred_agent"] == target


def test_child_authority_attenuates_and_cycles_are_rejected() -> None:
    codex = session("codex", concurrency=4)
    broker = broker_with(codex)
    parent_result = broker.submit(
        packet(
            work_id="root",
            work_key="root-key",
            conductor=codex.identity,
            resource="task/root",
            max_children=2,
            max_depth=2,
        ),
        now=NOW,
    )
    child = packet(
        work_id="child",
        work_key="child-key",
        conductor=codex.identity,
        resource="task/child",
        parent_run_id=parent_result["run_id"],
        root_run_id=parent_result["run_id"],
        depth=1,
        max_children=2,
        max_depth=2,
        spend_limit=1,
        effect="read",
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"code"}),
            repositories=frozenset({"organvm/limen"}),
            path_prefixes=frozenset({"cli/src"}),
            may_delegate=False,
        ),
    )
    assert broker.split(parent_result["run_id"], child, now=NOW)["status"] == "reserved"
    cycle = packet(
        work_id="cycle",
        work_key="root-key",
        conductor=codex.identity,
        resource="task/cycle",
        parent_run_id=parent_result["run_id"],
        root_run_id=parent_result["run_id"],
        depth=1,
        max_children=2,
        max_depth=2,
        spend_limit=1,
    )
    with pytest.raises(ConductConflict, match="cycle"):
        broker.split(parent_result["run_id"], cycle, now=NOW)
    escalated = child.model_copy(
        update={
            "work_id": "escalated",
            "work_key": "escalated",
            "authority": AuthorityEnvelopeV1(
                actions=frozenset({"code", "deploy"}),
                repositories=frozenset({"organvm/limen"}),
                path_prefixes=frozenset({"cli"}),
            ),
            "spend": SpendEnvelopeV1(limit=1),
        }
    )
    with pytest.raises(ConductConflict, match="authority"):
        broker.split(parent_result["run_id"], escalated, now=NOW)

    extended = child.model_copy(
        update={
            "work_id": "extended",
            "work_key": "extended",
            "deadline": NOW + timedelta(hours=2),
            "spend": SpendEnvelopeV1(limit=1),
        }
    )
    with pytest.raises(ConductConflict, match="deadline"):
        broker.split(parent_result["run_id"], extended, now=NOW)

    wider_fanout = child.model_copy(
        update={
            "work_id": "wider-fanout",
            "work_key": "wider-fanout",
            "fanout": FanoutBoundsV1(max_children=3, max_depth=3),
            "spend": SpendEnvelopeV1(limit=1),
        }
    )
    with pytest.raises(ConductConflict, match="fanout"):
        broker.split(parent_result["run_id"], wider_fanout, now=NOW)


def test_only_parent_executor_or_conductor_can_split_and_initiator_is_preserved() -> None:
    codex = session("codex", concurrency=4)
    claude = session("claude", concurrency=4)
    broker = broker_with(codex, claude)
    parent = broker.submit(
        packet(
            work_id="owned-parent",
            conductor=codex.identity,
            max_children=4,
            preferred_agent="codex",
        ),
        now=NOW,
    )
    unauthorized = packet(
        work_id="unauthorized-child",
        conductor=claude.identity,
        parent_run_id=parent["run_id"],
        root_run_id=parent["run_id"],
        depth=1,
        effect="read",
    ).model_copy(update={"initiator": codex.identity})
    with pytest.raises(ConductConflict, match="parent conductor or executor"):
        broker.split(parent["run_id"], unauthorized, now=NOW)

    wrong_initiator = packet(
        work_id="wrong-initiator",
        conductor=codex.identity,
        parent_run_id=parent["run_id"],
        root_run_id=parent["run_id"],
        depth=1,
        effect="read",
    ).model_copy(update={"initiator": claude.identity})
    with pytest.raises(ConductConflict, match="initiator"):
        broker.split(parent["run_id"], wrong_initiator, now=NOW)


def test_duplicate_work_keys_collapse_and_child_spend_is_aggregate_bounded() -> None:
    codex = session("codex", concurrency=8)
    broker = broker_with(codex)
    first_packet = packet(
        work_id="first-id",
        work_key="same-key",
        conductor=codex.identity,
        effect="read",
    )
    first = broker.submit(first_packet, now=NOW)
    duplicate_packet = first_packet.model_copy(update={"work_id": "second-id"})
    duplicate = broker.submit(duplicate_packet, now=NOW)
    assert duplicate["status"] == "duplicate"
    assert duplicate["run_id"] == first["run_id"]

    parent = broker.submit(
        packet(
            work_id="spend-parent",
            conductor=codex.identity,
            resource="task/spend-parent",
            spend_limit=3,
            max_children=3,
        ),
        now=NOW,
    )
    first_child = packet(
        work_id="spend-child-one",
        conductor=codex.identity,
        resource="task/spend-child-one",
        parent_run_id=parent["run_id"],
        root_run_id=parent["run_id"],
        depth=1,
        spend_limit=2,
        effect="read",
    )
    assert broker.split(parent["run_id"], first_child, now=NOW)["status"] == "reserved"
    second_child = packet(
        work_id="spend-child-two",
        conductor=codex.identity,
        resource="task/spend-child-two",
        parent_run_id=parent["run_id"],
        root_run_id=parent["run_id"],
        depth=1,
        spend_limit=2,
        effect="read",
    )
    with pytest.raises(ConductConflict, match="aggregate child spend"):
        broker.split(parent["run_id"], second_child, now=NOW)


def test_shared_write_claims_cannot_bypass_leases_and_external_claims_need_authority() -> None:
    codex = session("codex", concurrency=4)
    broker = broker_with(codex)
    shared_task = (ResourceClaimV1(key="task/shared-bypass", mode="shared"),)
    assert (
        broker.submit(
            packet(work_id="shared-one", conductor=codex.identity, claims=shared_task),
            now=NOW,
        )["status"]
        == "reserved"
    )
    assert (
        broker.submit(
            packet(work_id="shared-two", conductor=codex.identity, claims=shared_task),
            now=NOW,
        )["status"]
        == "busy"
    )

    with pytest.raises(ConductConflict, match="external resource"):
        broker.submit(
            packet(
                work_id="external-without-authority",
                conductor=codex.identity,
                claims=(ResourceClaimV1(key="external/deploy", mode="shared"),),
            ),
            now=NOW,
        )


def test_moved_head_fences_and_late_receipt_is_evidence_only() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(packet(work_id="head-fence", conductor=codex.identity), now=NOW)
    token = capability(broker, reserved)
    fenced = broker.heartbeat(
        reserved["lease"]["lease_id"],
        token,
        generation=reserved["lease"]["generation"],
        observed_heads={"pr": "moved"},
        now=NOW + timedelta(seconds=10),
    )
    assert fenced["status"] == "fenced"
    receipt = RunReceiptV1(
        receipt_id="receipt-head-fence",
        run_id=reserved["run_id"],
        lease_id=reserved["lease"]["lease_id"],
        lease_generation=reserved["lease"]["generation"],
        executor=codex.identity,
        observed_heads_before={"pr": "abc123"},
        predicate=PredicateEvidenceV1(command="pytest -q", exit_code=0),
        outcome="succeeded",
    )
    report = broker.report(
        reserved["lease"]["lease_id"],
        token,
        receipt,
        generation=reserved["lease"]["generation"],
        now=NOW + timedelta(seconds=20),
    )
    assert report["mutation_authorized"] is False
    assert report["run_status"] == "fenced"


def test_heartbeat_omitting_an_exact_head_fences_the_lease() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(packet(work_id="head-omitted", conductor=codex.identity), now=NOW)
    token = capability(broker, reserved)
    fenced = broker.heartbeat(
        reserved["lease"]["lease_id"],
        token,
        generation=reserved["lease"]["generation"],
        observed_heads={},
        now=NOW,
    )
    assert fenced["status"] == "fenced"
    assert "omitted" in fenced["reason"]


def test_receipts_are_idempotent_and_failed_predicates_cannot_succeed() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(
        packet(work_id="receipt-idempotency", conductor=codex.identity),
        now=NOW,
    )
    receipt = RunReceiptV1(
        receipt_id="receipt-idempotency",
        run_id=reserved["run_id"],
        lease_id=reserved["lease"]["lease_id"],
        lease_generation=reserved["lease"]["generation"],
        executor=codex.identity,
        observed_heads_before={"pr": "abc123"},
        predicate=PredicateEvidenceV1(command="pytest -q", exit_code=1),
        outcome="succeeded",
    )
    token = capability(broker, reserved)
    first = broker.report(
        reserved["lease"]["lease_id"],
        token,
        receipt,
        generation=reserved["lease"]["generation"],
        now=NOW,
    )
    second = broker.report(
        reserved["lease"]["lease_id"],
        token,
        receipt,
        generation=reserved["lease"]["generation"],
        now=NOW,
    )
    assert first == second
    assert first["mutation_authorized"] is False
    snapshot = broker.store.snapshot()
    assert len(snapshot["runs"][reserved["run_id"]]["receipts"]) == 1


def test_protected_registration_cannot_be_downgraded_or_share_a_worktree() -> None:
    broker = ConductBroker(MemoryStateStore())
    human = session("codex", protected=True).model_copy(update={"worktree": "/tmp/mesh"})
    registered = broker.register(human, now=NOW)
    assert registered["human_protected"] is True
    downgraded = human.model_copy(update={"human_protected": False})
    assert broker.register(downgraded, now=NOW)["human_protected"] is True
    other = session("claude").model_copy(update={"worktree": "/tmp/mesh"})
    with pytest.raises(ConductConflict, match="already owned"):
        broker.register(other, now=NOW)


def test_dead_parent_does_not_cancel_children_and_graph_is_adoptable() -> None:
    stale = session("codex", heartbeat_at=NOW - timedelta(hours=1), concurrency=4)
    stale = stale.model_copy(update={"heartbeat_at": NOW})
    claude = session("claude", concurrency=4)
    broker = broker_with(stale, claude)
    parent = broker.submit(packet(work_id="parent-adopt", conductor=stale.identity), now=NOW)
    child = packet(
        work_id="child-alive",
        conductor=stale.identity,
        resource="task/child-alive",
        parent_run_id=parent["run_id"],
        root_run_id=parent["run_id"],
        depth=1,
        effect="read",
    )
    child_result = broker.submit(child, now=NOW)
    with broker.store.transaction() as state:
        old = ConductorSessionV1.model_validate(state["sessions"][stale.session_id])
        state["sessions"][stale.session_id] = old.model_copy(
            update={"heartbeat_at": NOW - timedelta(hours=1)}
        ).model_dump(mode="json")
    adopted = broker.adopt(parent["run_id"], claude.session_id, now=NOW)
    assert adopted["status"] == "adopted"
    graph = broker.graph(parent["run_id"])
    assert {node["run_id"] for node in graph["nodes"]} == {parent["run_id"], child_result["run_id"]}
    child_node = next(node for node in graph["nodes"] if node["run_id"] == child_result["run_id"])
    assert child_node["status"] == "reserved"


def test_protected_human_session_cannot_be_targeted_or_adopted() -> None:
    human = session("codex", protected=True, concurrency=4)
    claude = session("claude", concurrency=4)
    broker = broker_with(human, claude)
    result = broker.submit(
        packet(work_id="protected-self", conductor=human.identity, preferred_agent="codex"),
        now=NOW,
    )
    with broker.store.transaction() as state:
        protected = ConductorSessionV1.model_validate(state["sessions"][human.session_id])
        state["sessions"][human.session_id] = protected.model_copy(
            update={"heartbeat_at": NOW - timedelta(hours=1)}
        ).model_dump(mode="json")
    with pytest.raises(ConductConflict, match="protected"):
        broker.adopt(result["run_id"], claude.session_id, now=NOW)
    with pytest.raises(ConductConflict, match="protected"):
        broker.cancel(result["run_id"], human.session_id, now=NOW)


def test_cancel_is_reserved_only_and_request_stop_is_cooperative() -> None:
    codex = session("codex")
    broker = broker_with(codex)
    reserved = broker.submit(packet(work_id="cancel-me", conductor=codex.identity), now=NOW)
    assert broker.cancel(reserved["run_id"], codex.session_id, now=NOW)["status"] == "cancelled"
    running = broker.submit(packet(work_id="stop-me", conductor=codex.identity, resource="task/stop"), now=NOW)
    token = capability(broker, running)
    broker.heartbeat(
        running["lease"]["lease_id"],
        token,
        generation=running["lease"]["generation"],
        observed_heads={"pr": "abc123"},
        now=NOW,
    )
    assert broker.request_stop(running["run_id"], codex.session_id, now=NOW)["cooperative"] is True
    with pytest.raises(ConductConflict, match="reserved"):
        broker.cancel(running["run_id"], codex.session_id, now=NOW)
