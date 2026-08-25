from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from limen.conduct import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    ConductBroker,
    ConductConflict,
    ConductPrincipalV1,
    FanoutBoundsV1,
    MemoryStateStore,
    ResourceClaimV1,
    RetryPolicyV1,
    RunReceiptV1,
    SpendEnvelopeV1,
    WorkPacketV1,
)
from limen.conduct.models import PredicateEvidenceV1
from limen.work_loan import WorkLoanV1

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def make_identity(agent: str, session_id: str | None = None, surface: str = "cli") -> AgentIdentityV1:
    return AgentIdentityV1(agent=agent, surface=surface, session_id=session_id or f"{agent}-session")


def make_principal(
    principal_id: str,
    agent: str,
    *roles: str,
    surface: str = "cli",
) -> ConductPrincipalV1:
    return ConductPrincipalV1(
        principal_id=principal_id,
        agent=agent,
        surface=surface,
        roles=frozenset(roles),
    )


def make_session(
    agent: str,
    *,
    session_id: str | None = None,
    capabilities: frozenset[str] = frozenset({"conduct", "code", "execute", "review"}),
    concurrency: int = 8,
    heartbeat_at: datetime = NOW,
    protected: bool = False,
    surface: str = "cli",
) -> ConductorSessionV1:
    ident = make_identity(agent, session_id=session_id, surface=surface)
    return ConductorSessionV1(
        session_id=ident.session_id,
        identity=ident,
        origin="direct" if protected else "dispatched",
        capabilities=capabilities,
        concurrency=concurrency,
        heartbeat_at=heartbeat_at,
        human_protected=protected,
    )


def make_packet(
    *,
    work_id: str,
    conductor: AgentIdentityV1,
    resource: str = "task/T-1",
    work_key: str | None = None,
    parent_run_id: str | None = None,
    root_run_id: str | None = None,
    depth: int = 0,
    preferred_agent: str | None = None,
    spend_limit: int = 4,
    deadline: datetime | None = None,
    task_id: str | None = None,
    max_children: int = 5,
    max_depth: int = 5,
    effect: str = "write",
    authority: AuthorityEnvelopeV1 | None = None,
    observed_heads: dict[str, str] | None = None,
) -> WorkPacketV1:
    heads = observed_heads if observed_heads is not None else {"pr": "abc123"}
    auth = authority or AuthorityEnvelopeV1(
        actions=frozenset({"code", "review"}),
        repositories=frozenset({"organvm/limen"}),
        path_prefixes=frozenset({"cli"}),
        external_effects=frozenset(),
    )
    return WorkPacketV1(
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
        work_id=work_id,
        work_key=work_key or work_id,
        intent={"objective": work_id},
        execution={"command": "pytest -q", "observed_heads": heads},
        initiator=conductor,
        conductor=conductor,
        preferred_agent=preferred_agent,
        required_capabilities=frozenset({"code"}),
        resource_claims=(ResourceClaimV1(key=resource),),
        predicate="pytest -q",
        receipt_target=f"github:organvm/limen:pull-request:{work_id}",
        work_loan=WorkLoanV1(
            source_origin="human_prompt",
            horizon="present",
            value_case=f"Deliver bounded packet {work_id}",
            budget_cost=spend_limit,
            owner_surface="organvm/limen",
        ),
        authority=auth,
        deadline=deadline or (NOW + timedelta(hours=1)),
        spend=SpendEnvelopeV1(limit=spend_limit),
        retry=RetryPolicyV1(max_attempts=2),
        depth=depth,
        fanout=FanoutBoundsV1(max_children=max_children, max_depth=max_depth),
        effect=effect,
        task_id=task_id,
    )


def make_receipt(
    run_id: str,
    lease_id: str,
    executor: AgentIdentityV1,
    generation: int = 1,
    outcome: str = "succeeded",
    observed_heads: dict[str, str] | None = None,
) -> RunReceiptV1:
    heads = observed_heads if observed_heads is not None else {"pr": "abc123"}
    return RunReceiptV1(
        receipt_id=f"receipt-{run_id}",
        run_id=run_id,
        lease_id=lease_id,
        lease_generation=generation,
        executor=executor,
        observed_heads_before=dict(heads),
        observed_heads_after=dict(heads),
        predicate=PredicateEvidenceV1(command="pytest -q", exit_code=0, summary="all passed"),
        outcome=outcome,
        completed_at=NOW,
    )


# ---------------------------------------------------------------------------
# 1. Local Principal Fallback & Least Privilege Tests
# ---------------------------------------------------------------------------


def test_local_principal_least_privilege_default_is_observer_only() -> None:
    ident = make_identity("anonymous", session_id="anon-session")
    local_p = ConductBroker._local_principal(ident)
    assert local_p.roles == frozenset({"observer"})
    assert local_p.principal_id == "local:anonymous:cli"
    assert local_p.agent == "anonymous"
    assert local_p.surface == "cli"


def test_local_principal_capability_derived_roles() -> None:
    ident = make_identity("worker", session_id="w-1")

    # Empty capabilities -> observer only
    p_none = ConductBroker._local_principal(ident, capabilities=frozenset())
    assert p_none.roles == frozenset({"observer"})

    # Conductor capabilities
    p_cond = ConductBroker._local_principal(ident, capabilities=frozenset({"conduct"}))
    assert p_cond.roles == frozenset({"observer", "conductor"})

    p_submit = ConductBroker._local_principal(ident, capabilities=frozenset({"task-submit"}))
    assert p_submit.roles == frozenset({"observer", "conductor"})

    p_split = ConductBroker._local_principal(ident, capabilities=frozenset({"split"}))
    assert p_split.roles == frozenset({"observer", "conductor"})

    # Executor capabilities
    p_exec = ConductBroker._local_principal(ident, capabilities=frozenset({"execute"}))
    assert p_exec.roles == frozenset({"observer", "executor"})

    p_code = ConductBroker._local_principal(ident, capabilities=frozenset({"code", "review"}))
    assert p_code.roles == frozenset({"observer", "executor"})

    # Both conductor and executor capabilities
    p_both = ConductBroker._local_principal(ident, capabilities=frozenset({"conduct", "code"}))
    assert p_both.roles == frozenset({"observer", "conductor", "executor"})

    # Compatibility is NEVER granted via local fallback
    assert "compatibility" not in p_both.roles


def test_principal_for_identity_and_session_always_enforces_ownership() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    ident = make_identity("agent1")
    sess = make_session("agent1")

    # When principal is provided
    p_auth = make_principal("p-auth", "agent1", "conductor")
    p_res, enforced = broker._principal_for_identity(ident, p_auth)
    assert p_res == p_auth
    assert enforced is True

    p_sess_res, sess_enforced = broker._principal_for_session(sess, p_auth)
    assert p_sess_res == p_auth
    assert sess_enforced is True

    # When principal is None, enforced is STILL True (no bypass)
    p_fallback, fb_enforced = broker._principal_for_identity(ident, None)
    assert fb_enforced is True
    assert p_fallback.roles == frozenset({"observer"})

    p_sess_fb, fb_sess_enforced = broker._principal_for_session(sess, None)
    assert fb_sess_enforced is True
    assert "conductor" in p_sess_fb.roles  # derived from session capabilities


# ---------------------------------------------------------------------------
# 2. Observer Role Permissions Matrix Tests
# ---------------------------------------------------------------------------


def test_observer_role_can_read_graph_harvest_task_run_and_capabilities() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")
    p_obs = make_principal("p-obs", "auditor", "observer")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    wp = make_packet(
        work_id="obs-test",
        conductor=s_cond.identity,
        preferred_agent="jules",
        task_id="TASK-OBS-1",
    )
    sub = broker.submit(wp, principal=p_cond, now=NOW)

    # 1. Capabilities query with observer principal
    caps = broker.capabilities(principal=p_obs, now=NOW)
    assert caps["schema_version"] == "limen.conduct_capabilities.v1"
    assert caps["authenticated_principal"]["principal_id"] == "p-obs"

    # 2. Graph query with observer principal
    graph = broker.graph(sub["run_id"], principal=p_obs)
    assert graph["schema_version"] == "limen.conduct_graph.v1"
    assert len(graph["nodes"]) == 1

    # 3. Harvest query with observer principal
    harvest = broker.harvest(sub["run_id"], principal=p_obs)
    assert harvest["schema_version"] == "limen.conduct_harvest.v1"
    assert harvest["run_count"] == 1

    # 4. Task run query with observer principal
    task_res = broker.task_run("TASK-OBS-1", principal=p_obs)
    assert task_res["schema_version"] == "limen.conduct_task_run.v1"
    assert task_res["found"] is True

    # 5. List notification assignments with observer principal
    notifs = broker.list_notification_assignments(principal=p_obs, now=NOW)
    assert notifs["schema_version"] == "limen.notification_assignments.v1"
    assert len(notifs["assignments"]) == 2


def test_observer_role_cannot_perform_mutations() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_obs = make_principal("p-obs", "auditor", "observer")
    s_obs = make_session("auditor")

    # 1. Cannot register
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.register(s_obs, principal=p_obs, now=NOW)

    # Setup a valid registered environment for other checks
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")
    s_cond = make_session("codex")
    s_exec = make_session("jules")
    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    wp = make_packet(work_id="obs-mutate", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    lease = sub["lease"]

    # 2. Observer cannot submit
    wp2 = make_packet(work_id="obs-submit", conductor=s_cond.identity)
    with pytest.raises(ConductConflict, match="lacks required conductor/compatibility role"):
        broker.submit(wp2, principal=p_obs, now=NOW)

    # 3. Observer cannot split
    child_wp = make_packet(
        work_id="obs-split-child",
        conductor=s_cond.identity,
        parent_run_id=sub["run_id"],
        root_run_id=sub["root_run_id"],
        depth=1,
    )
    with pytest.raises(ConductConflict, match="lacks required conductor/compatibility role"):
        broker.split(sub["run_id"], child_wp, principal=p_obs, now=NOW)

    # 4. Observer cannot submit_graph
    with pytest.raises(ConductConflict, match="lacks required conductor role"):
        broker.submit_graph((wp2,), principal=p_obs, now=NOW)

    # 5. Observer cannot claim lease
    with pytest.raises(ConductConflict, match="lacks required executor/compatibility role"):
        broker.claim(lease["lease_id"], lease["generation"], principal=p_obs, now=NOW)

    # Claim with valid executor for capability token
    cap_token = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)["capability_token"]

    # 6. Observer cannot heartbeat lease
    with pytest.raises(ConductConflict, match="lacks required executor/compatibility role"):
        broker.heartbeat(lease["lease_id"], cap_token, principal=p_obs, now=NOW)

    # 7. Observer cannot report receipt
    receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity)
    with pytest.raises(ConductConflict, match="lacks required executor/compatibility role"):
        broker.report(lease["lease_id"], cap_token, receipt, principal=p_obs, now=NOW)

    # 8. Observer cannot adopt
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.adopt(sub["run_id"], s_cond.session_id, principal=p_obs, now=NOW)

    # 9. Observer cannot cancel
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.cancel(sub["run_id"], s_cond.session_id, principal=p_obs, now=NOW)

    # 10. Observer cannot request_stop
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.request_stop(sub["run_id"], s_cond.session_id, principal=p_obs, now=NOW)


# ---------------------------------------------------------------------------
# 3. Conductor Role Permissions Matrix Tests
# ---------------------------------------------------------------------------


def test_conductor_role_permitted_operations() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    # 1. Register with conductor role
    reg = broker.register(s_cond, principal=p_cond, now=NOW)
    assert reg["session_id"] == s_cond.session_id
    broker.register(s_exec, principal=p_exec, now=NOW)

    # 2. Submit packet
    wp = make_packet(work_id="cond-submit", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    assert sub["status"] == "reserved"

    # 3. Split child packet
    child_wp = make_packet(
        work_id="cond-child",
        conductor=s_cond.identity,
        parent_run_id=sub["run_id"],
        root_run_id=sub["root_run_id"],
        depth=1,
        preferred_agent="jules",
        effect="read",
        resource="task/T-child",
    )
    split_res = broker.split(sub["run_id"], child_wp, principal=p_cond, now=NOW)
    assert split_res["status"] == "reserved"

    # 4. Cancel reservation
    cancel_res = broker.cancel(sub["run_id"], s_cond.session_id, principal=p_cond, now=NOW)
    assert cancel_res["status"] == "cancelled"

    # 5. Request stop on active run
    wp_stop = make_packet(work_id="cond-stop-target", conductor=s_cond.identity, preferred_agent="jules")
    sub_stop = broker.submit(wp_stop, principal=p_cond, now=NOW)
    lease_stop = sub_stop["lease"]
    tok = broker.claim(lease_stop["lease_id"], lease_stop["generation"], principal=p_exec, now=NOW)["capability_token"]
    broker.heartbeat(
        lease_stop["lease_id"], tok, principal=p_exec, observed_heads={"pr": "abc123"}, now=NOW
    )  # move to running
    stop_res = broker.request_stop(sub_stop["run_id"], s_cond.session_id, principal=p_cond, now=NOW)
    assert stop_res["status"] == "stop_requested"

    # 6. Read methods
    assert broker.graph(sub["run_id"], principal=p_cond)["schema_version"] == "limen.conduct_graph.v1"
    assert broker.harvest(sub["run_id"], principal=p_cond)["schema_version"] == "limen.conduct_harvest.v1"
    assert (
        broker.list_notification_assignments(principal=p_cond, now=NOW)["schema_version"]
        == "limen.notification_assignments.v1"
    )


def test_conductor_role_cannot_perform_executor_operations() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")
    s_cond = make_session("codex")
    s_exec = make_session("jules")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    wp = make_packet(work_id="cond-no-exec", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    lease = sub["lease"]

    # Conductor cannot claim lease
    with pytest.raises(ConductConflict, match="lacks required executor/compatibility role"):
        broker.claim(lease["lease_id"], lease["generation"], principal=p_cond, now=NOW)

    # Valid claim by executor
    cap_token = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)["capability_token"]

    # Conductor cannot heartbeat lease
    with pytest.raises(ConductConflict, match="lacks required executor/compatibility role"):
        broker.heartbeat(lease["lease_id"], cap_token, principal=p_cond, now=NOW)

    # Conductor cannot report receipt
    receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity)
    with pytest.raises(ConductConflict, match="lacks required executor/compatibility role"):
        broker.report(lease["lease_id"], cap_token, receipt, principal=p_cond, now=NOW)


# ---------------------------------------------------------------------------
# 4. Executor Role Permissions Matrix Tests
# ---------------------------------------------------------------------------


def test_executor_role_permitted_operations() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    # 1. Register with executor role
    reg = broker.register(s_exec, principal=p_exec, now=NOW)
    assert reg["session_id"] == s_exec.session_id
    broker.register(s_cond, principal=p_cond, now=NOW)

    wp = make_packet(work_id="exec-flow", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    lease = sub["lease"]

    # 2. Claim lease
    claim_res = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)
    assert "capability_token" in claim_res
    cap_token = claim_res["capability_token"]

    # 3. Heartbeat lease
    hb = broker.heartbeat(lease["lease_id"], cap_token, principal=p_exec, observed_heads={"pr": "abc123"}, now=NOW)
    assert hb["status"] == "active"

    # 4. Report receipt
    receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity)
    rep = broker.report(lease["lease_id"], cap_token, receipt, principal=p_exec, now=NOW)
    assert rep["run_status"] == "succeeded"
    assert rep["mutation_authorized"] is True

    # 5. Read methods
    assert broker.graph(sub["run_id"], principal=p_exec)["schema_version"] == "limen.conduct_graph.v1"
    assert broker.harvest(sub["run_id"], principal=p_exec)["schema_version"] == "limen.conduct_harvest.v1"


def test_executor_role_cannot_submit_or_list_notifications() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    wp = make_packet(work_id="exec-no-submit", conductor=s_cond.identity)

    # 1. Executor cannot submit
    with pytest.raises(ConductConflict, match="lacks required conductor/compatibility role"):
        broker.submit(wp, principal=p_exec, now=NOW)

    # 2. Executor cannot split
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    child_wp = make_packet(
        work_id="exec-child",
        conductor=s_cond.identity,
        parent_run_id=sub["run_id"],
        root_run_id=sub["root_run_id"],
        depth=1,
    )
    with pytest.raises(ConductConflict, match="lacks required conductor/compatibility role"):
        broker.split(sub["run_id"], child_wp, principal=p_exec, now=NOW)

    # 3. Executor cannot submit_graph
    with pytest.raises(ConductConflict, match="lacks required conductor role"):
        broker.submit_graph((wp,), principal=p_exec, now=NOW)

    # 4. Executor cannot list notification assignments (requires observer or conductor)
    with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
        broker.list_notification_assignments(principal=p_exec, now=NOW)


# ---------------------------------------------------------------------------
# 5. Compatibility Role Permissions Matrix Tests
# ---------------------------------------------------------------------------


def test_compatibility_role_permitted_operations() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    # Compatibility role can submit and claim
    s_compat = make_session("legacy-adapter", capabilities=frozenset({"conduct", "code"}))
    p_compat_cond = make_principal("p-compat-cond", "legacy-adapter", "conductor", "compatibility")
    broker.register(s_compat, principal=p_compat_cond, now=NOW)

    wp = make_packet(work_id="compat-submit", conductor=s_compat.identity, preferred_agent="legacy-adapter")
    sub = broker.submit(wp, principal=p_compat_cond, now=NOW)
    assert sub["status"] == "reserved"

    lease = sub["lease"]
    p_compat_exec = make_principal("p-compat-cond", "legacy-adapter", "compatibility")
    claim_res = broker.claim(lease["lease_id"], lease["generation"], principal=p_compat_exec, now=NOW)
    assert "capability_token" in claim_res
    cap_token = claim_res["capability_token"]

    # Compatibility role can heartbeat & report
    hb = broker.heartbeat(
        lease["lease_id"], cap_token, principal=p_compat_exec, observed_heads={"pr": "abc123"}, now=NOW
    )
    assert hb["status"] == "active"

    receipt = make_receipt(sub["run_id"], lease["lease_id"], s_compat.identity)
    rep = broker.report(lease["lease_id"], cap_token, receipt, principal=p_compat_exec, now=NOW)
    assert rep["run_status"] == "succeeded"
    assert rep["mutation_authorized"] is True

    # Compatibility role can read graph and harvest
    assert broker.graph(sub["run_id"], principal=p_compat_exec)["schema_version"] == "limen.conduct_graph.v1"
    assert broker.harvest(sub["run_id"], principal=p_compat_exec)["schema_version"] == "limen.conduct_harvest.v1"


def test_compatibility_role_forbidden_operations() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")
    p_compat = make_principal("p-compat", "legacy", "compatibility")

    s_cond = make_session("codex")
    s_exec = make_session("jules")
    s_compat = make_session("legacy")

    # 1. Compatibility role alone cannot register (requires conductor or executor)
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.register(s_compat, principal=p_compat, now=NOW)

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    wp = make_packet(work_id="compat-forbidden", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)

    # 2. Compatibility role cannot submit_graph (requires conductor)
    with pytest.raises(ConductConflict, match="lacks required conductor role"):
        broker.submit_graph((wp,), principal=p_compat, now=NOW)

    # 3. Compatibility role cannot adopt (requires conductor or executor)
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.adopt(sub["run_id"], s_cond.session_id, principal=p_compat, now=NOW)

    # 4. Compatibility role cannot cancel (requires conductor or executor)
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.cancel(sub["run_id"], s_cond.session_id, principal=p_compat, now=NOW)

    # 5. Compatibility role cannot request_stop (requires conductor or executor)
    with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
        broker.request_stop(sub["run_id"], s_cond.session_id, principal=p_compat, now=NOW)

    # 6. Compatibility role cannot list notification assignments (requires observer or conductor)
    with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
        broker.list_notification_assignments(principal=p_compat, now=NOW)


# ---------------------------------------------------------------------------
# 6. Identity Binding & Cross-Principal Spoofing Prevention Tests
# ---------------------------------------------------------------------------


def test_session_cannot_be_re_registered_to_different_principal() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p1 = make_principal("principal-1", "codex", "conductor")
    p2 = make_principal("principal-2", "codex", "conductor")
    s = make_session("codex", session_id="shared-session")

    # Initial registration with Principal 1
    broker.register(s, principal=p1, now=NOW)

    # Re-registration with same Principal 1 succeeds (heartbeat update)
    broker.register(s, principal=p1, now=NOW + timedelta(minutes=1))

    # Re-registration with Principal 2 fails
    with pytest.raises(ConductConflict, match="session_id is already bound to another principal"):
        broker.register(s, principal=p2, now=NOW + timedelta(minutes=2))


def test_submit_rejects_conductor_session_bound_to_different_principal() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p1 = make_principal("principal-1", "codex", "conductor")
    p2 = make_principal("principal-2", "attacker", "conductor")
    p3_same_agent = make_principal("principal-3", "codex", "conductor")

    s1 = make_session("codex", session_id="s1")
    s2 = make_session("attacker", session_id="s2")

    broker.register(s1, principal=p1, now=NOW)
    broker.register(s2, principal=p2, now=NOW)

    # 1. Principal 2 (different agent name) attempts to submit naming s1 as conductor
    wp_spoof1 = make_packet(work_id="spoofed-submit-1", conductor=s1.identity)
    with pytest.raises(ConductConflict, match="packet conductor identity does not match its registered session"):
        broker.submit(wp_spoof1, principal=p2, now=NOW)

    # 2. Principal 3 (same agent name "codex" but different principal_id) attempts to submit naming s1
    wp_spoof2 = make_packet(work_id="spoofed-submit-2", conductor=s1.identity)
    with pytest.raises(ConductConflict, match="packet conductor is not bound to the authenticated principal"):
        broker.submit(wp_spoof2, principal=p3_same_agent, now=NOW)


def test_claim_rejects_unauthorized_principal() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec1 = make_principal("p-exec-1", "jules", "executor")
    p_exec2 = make_principal("p-exec-2", "attacker", "executor")

    s_cond = make_session("codex")
    s_exec1 = make_session("jules")
    s_exec2 = make_session("attacker")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec1, principal=p_exec1, now=NOW)
    broker.register(s_exec2, principal=p_exec2, now=NOW)

    wp = make_packet(work_id="claim-spoof", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    lease = sub["lease"]

    # Principal 2 tries to claim Principal 1's lease
    with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
        broker.claim(lease["lease_id"], lease["generation"], principal=p_exec2, now=NOW)

    # Unauthenticated caller tries to claim Principal 1's lease
    with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
        broker.claim(lease["lease_id"], lease["generation"], principal=None, now=NOW)

    # Authorized claim succeeds
    claim_res = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec1, now=NOW)
    assert "capability_token" in claim_res


def test_heartbeat_and_report_reject_foreign_principal() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec1 = make_principal("p-exec-1", "jules", "executor")
    p_exec2 = make_principal("p-exec-2", "attacker", "executor")

    s_cond = make_session("codex")
    s_exec1 = make_session("jules")
    s_exec2 = make_session("attacker")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec1, principal=p_exec1, now=NOW)
    broker.register(s_exec2, principal=p_exec2, now=NOW)

    wp = make_packet(work_id="hb-spoof", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    lease = sub["lease"]

    cap_token = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec1, now=NOW)["capability_token"]

    # Foreign principal tries to heartbeat
    with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
        broker.heartbeat(lease["lease_id"], cap_token, principal=p_exec2, now=NOW)

    # Foreign principal tries to report
    receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec1.identity)
    with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
        broker.report(lease["lease_id"], cap_token, receipt, principal=p_exec2, now=NOW)


def test_adopt_cancel_and_request_stop_reject_unauthorized_principals() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond1 = make_principal("p-cond-1", "codex", "conductor")
    p_cond2 = make_principal("p-cond-2", "attacker", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")

    s_cond1 = make_session("codex", session_id="s-cond-1")
    s_cond2 = make_session("attacker", session_id="s-cond-2")
    s_exec = make_session("jules", session_id="s-exec")

    broker.register(s_cond1, principal=p_cond1, now=NOW)
    broker.register(s_cond2, principal=p_cond2, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    wp = make_packet(work_id="mgmt-spoof", conductor=s_cond1.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond1, now=NOW)
    run_id = sub["run_id"]

    # 1. Principal 2 tries to cancel Principal 1's run using s-cond-1
    with pytest.raises(ConductConflict, match="requester session is not bound to the authenticated principal"):
        broker.cancel(run_id, s_cond1.session_id, principal=p_cond2, now=NOW)

    # 2. Principal 2 tries to cancel using its own session s-cond-2
    with pytest.raises(ConductConflict, match="only the current conductor may cancel a reservation"):
        broker.cancel(run_id, s_cond2.session_id, principal=p_cond2, now=NOW)

    # 3. Principal 2 tries to request stop using s-cond-1
    with pytest.raises(ConductConflict, match="requester session is not bound to the authenticated principal"):
        broker.request_stop(run_id, s_cond1.session_id, principal=p_cond2, now=NOW)

    # 4. Principal 2 tries to adopt without proven absence
    with pytest.raises(ConductConflict, match="conductor absence has not been proven"):
        broker.adopt(run_id, s_cond2.session_id, principal=p_cond2, now=NOW)

    # Prove absence (> adoption_after which is 10 minutes)
    future = NOW + timedelta(minutes=15)
    # Re-register / heartbeat adopter s_cond2 at future so adopter is healthy
    broker.register(s_cond2, principal=p_cond2, now=future)

    # Adopt with bound principal p_cond2 succeeds
    adopt_res = broker.adopt(run_id, s_cond2.session_id, principal=p_cond2, now=future)
    assert adopt_res["status"] == "adopted"
    assert adopt_res["conductor_session_id"] == s_cond2.session_id

    # Now s-cond-2 / p_cond2 can cancel the reserved run
    cancel_res = broker.cancel(run_id, s_cond2.session_id, principal=p_cond2, now=future)
    assert cancel_res["status"] == "cancelled"


# ---------------------------------------------------------------------------
# 7. Notification Assignment Authorization Tests
# ---------------------------------------------------------------------------


def test_notifications_list_assignments_role_validation() -> None:
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")
    p_cond = make_principal("p-cond", "codex", "conductor")
    p_exec = make_principal("p-exec", "jules", "executor")
    p_obs = make_principal("p-obs", "auditor", "observer")
    p_compat = make_principal("p-compat", "legacy", "compatibility")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    broker.register(s_cond, principal=p_cond, now=NOW)
    broker.register(s_exec, principal=p_exec, now=NOW)

    # Observer can list assignments
    res_obs = broker.list_notification_assignments(principal=p_obs, now=NOW)
    assert len(res_obs["assignments"]) == 2
    assert res_obs["assignments"][0]["agent"] in {"codex", "jules"}

    # Conductor can list assignments
    res_cond = broker.list_notification_assignments(principal=p_cond, now=NOW)
    assert len(res_cond["assignments"]) == 2

    # list_assignments alias works identically
    assert broker.list_assignments(principal=p_obs, now=NOW) == res_obs

    # Unauthenticated caller defaults to observer fallback and succeeds
    res_anon = broker.list_notification_assignments(principal=None, now=NOW)
    assert len(res_anon["assignments"]) == 2

    # Executor alone is rejected
    with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
        broker.list_notification_assignments(principal=p_exec, now=NOW)

    with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
        broker.list_assignments(principal=p_exec, now=NOW)

    # Compatibility alone is rejected
    with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
        broker.list_notification_assignments(principal=p_compat, now=NOW)


# ---------------------------------------------------------------------------
# 8. End-to-End Multi-Role Lifecycle Integration Test
# ---------------------------------------------------------------------------


def test_end_to_end_conduct_lifecycle_with_isolated_roles() -> None:
    """Full lifecycle verifying that each role operates only within its authority."""
    broker = ConductBroker(MemoryStateStore(), capability_secret="test-secret")

    p_cond = make_principal("p-conductor", "codex", "conductor")
    p_exec = make_principal("p-executor", "jules", "executor")
    p_obs = make_principal("p-observer", "auditor", "observer")

    s_cond = make_session("codex")
    s_exec = make_session("jules")

    # Step 1: Conductor registers its session
    broker.register(s_cond, principal=p_cond, now=NOW)

    # Step 2: Executor registers its session
    broker.register(s_exec, principal=p_exec, now=NOW)

    # Step 3: Conductor submits a work packet
    wp = make_packet(work_id="e2e-work", conductor=s_cond.identity, preferred_agent="jules")
    sub = broker.submit(wp, principal=p_cond, now=NOW)
    assert sub["status"] == "reserved"
    run_id = sub["run_id"]
    lease = sub["lease"]

    # Step 4: Observer inspects the initial graph
    g1 = broker.graph(run_id, principal=p_obs)
    assert g1["nodes"][0]["status"] == "reserved"

    # Step 5: Executor claims the lease
    claim = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)
    assert "capability_token" in claim
    cap_token = claim["capability_token"]

    # Step 6: Executor sends heartbeats during work
    t1 = NOW + timedelta(minutes=1)
    hb = broker.heartbeat(lease["lease_id"], cap_token, principal=p_exec, observed_heads={"pr": "abc123"}, now=t1)
    assert hb["status"] == "active"

    # Step 7: Observer verifies state transition to running
    g2 = broker.graph(run_id, principal=p_obs)
    assert g2["nodes"][0]["status"] == "running"

    # Step 8: Executor reports successful receipt
    t2 = NOW + timedelta(minutes=5)
    receipt = make_receipt(run_id, lease["lease_id"], s_exec.identity)
    rep = broker.report(lease["lease_id"], cap_token, receipt, principal=p_exec, now=t2)
    assert rep["run_status"] == "succeeded"
    assert rep["mutation_authorized"] is True

    # Step 9: Observer harvests final results
    harvest = broker.harvest(run_id, principal=p_obs)
    assert harvest["receipt_count"] == 1
    assert harvest["by_status"] == {"succeeded": 1}
    assert harvest["unharvested"] == []
