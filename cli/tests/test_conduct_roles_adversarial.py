"""Adversarial stress-test harness for ConductBroker role enforcement and security boundaries.

Empirically tests:
1. Malformed roles, principal schema boundary validation, and bearer authentication.
2. Unauthenticated caller and local principal role escalation attacks.
3. Cross-principal lease hijacking, token forgery, replay, and generation attacks.
4. Information leakage and access control on graph, harvest, capabilities, and notification assignments.
5. Session hijacking, protection downgrade, absence proof bypass, and lineage attenuation bypass.
6. Transactional state isolation and fail-closed invariants under malformed payloads.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from limen.conduct import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    ConductBroker,
    ConductConflict,
    ConductError,
    ConductPrincipalV1,
    FanoutBoundsV1,
    MemoryStateStore,
    ResourceClaimV1,
    RetryPolicyV1,
    RunReceiptV1,
    SpendEnvelopeV1,
    WorkPacketV1,
)
from limen.conduct.auth import (
    ConductAuthenticationError,
    authenticate_principal,
    parse_principal_registry,
)
from limen.conduct.models import (
    CampaignPacketV1,
    CampaignReceiptV1,
    PredicateEvidenceV1,
)
from limen.work_loan import WorkLoanV1

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
TEST_SECRET = "adversarial-verification-secret-32b!"


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
        roles=frozenset(roles),  # type: ignore[arg-type]
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
    accepting_work: bool = True,
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
        accepting_work=accepting_work,
    )


def make_packet(
    *,
    work_id: str,
    conductor: AgentIdentityV1,
    resource: str = "task/T-ADV-1",
    work_key: str | None = None,
    parent_run_id: str | None = None,
    root_run_id: str | None = None,
    depth: int = 0,
    preferred_agent: str | None = None,
    spend_limit: int = 4,
    spend_reserve: int = 0,
    deadline: datetime | None = None,
    task_id: str | None = None,
    max_children: int = 5,
    max_depth: int = 5,
    effect: str = "write",
    authority: AuthorityEnvelopeV1 | None = None,
    observed_heads: dict[str, str] | None = None,
    campaign: CampaignPacketV1 | None = None,
) -> WorkPacketV1:
    heads = observed_heads if observed_heads is not None else {"pr": "head-001"}
    auth = authority or AuthorityEnvelopeV1(
        actions=frozenset({"code", "review"}),
        repositories=frozenset({"organvm/limen"}),
        path_prefixes=frozenset({"cli"}),
        external_effects=frozenset(),
        may_delegate=True,
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
            value_case=f"Adversarial verification packet {work_id}",
            budget_cost=spend_limit,
            owner_surface="organvm/limen",
        ),
        authority=auth,
        deadline=deadline or (NOW + timedelta(hours=1)),
        spend=SpendEnvelopeV1(limit=spend_limit, reserve=spend_reserve),
        retry=RetryPolicyV1(max_attempts=2),
        depth=depth,
        fanout=FanoutBoundsV1(max_children=max_children, max_depth=max_depth),
        effect=effect,
        task_id=task_id,
        campaign=campaign,
    )


def make_receipt(
    run_id: str,
    lease_id: str,
    executor: AgentIdentityV1,
    generation: int = 1,
    outcome: str = "succeeded",
    observed_heads: dict[str, str] | None = None,
    changed_paths: tuple[str, ...] = ("cli/src/file.py",),
    campaign: CampaignReceiptV1 | None = None,
    spend: dict[str, int | float | str] | None = None,
) -> RunReceiptV1:
    heads = observed_heads if observed_heads is not None else {"pr": "head-001"}
    return RunReceiptV1(
        receipt_id=f"receipt-{run_id}",
        run_id=run_id,
        lease_id=lease_id,
        lease_generation=generation,
        executor=executor,
        observed_heads_before=dict(heads),
        observed_heads_after=dict(heads),
        changed_paths=changed_paths,
        predicate=PredicateEvidenceV1(command="pytest -q", exit_code=0, summary="passed"),
        outcome=outcome,
        completed_at=NOW,
        campaign=campaign,
        spend=spend or {"runs": 1},
    )


# ===========================================================================
# SUITE 1: Malformed Roles & Principal Model Validation Attack Probes
# ===========================================================================


class TestSuite1PrincipalValidationAndAuth:
    """Stress-test principal creation, role enforcement, and bearer authentication."""

    def test_forged_roles_rejected_by_pydantic_schema(self) -> None:
        """Attempting to create a principal with unauthorized/forged roles must fail validation."""
        for invalid_role in [
            "admin",
            "root",
            "god_mode",
            "superuser",
            "CONDUCTOR",
            " conductor",
            "observer ",
            "executor\0",
        ]:
            with pytest.raises(ValidationError):
                ConductPrincipalV1(
                    principal_id="p-attacker",
                    agent="attacker",
                    surface="cli",
                    roles=frozenset({invalid_role}),  # type: ignore[arg-type]
                )

    def test_empty_roles_rejected_by_principal_model(self) -> None:
        """Principal must have at least one valid role."""
        with pytest.raises(ValidationError, match="conduct principal must have at least one role"):
            ConductPrincipalV1(
                principal_id="p-empty",
                agent="empty",
                surface="cli",
                roles=frozenset(),
            )

    def test_require_role_helper_rejects_missing_roles(self) -> None:
        """ConductBroker._require_role must raise ConductConflict on disjoint role sets."""
        p_obs = make_principal("p-obs", "agent", "observer")
        p_exec = make_principal("p-exec", "agent", "executor")

        # Observer asking for conductor -> rejected
        with pytest.raises(ConductConflict, match="lacks required conductor role"):
            ConductBroker._require_role(p_obs, "conductor")

        # Executor asking for observer/conductor -> rejected
        with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
            ConductBroker._require_role(p_exec, "observer", "conductor")

    def test_auth_registry_parsing_and_bearer_bounds(self) -> None:
        """Bearer token length boundaries and schema validation in parse_principal_registry."""
        # 1. Bearer too short (< 24 chars)
        short_registry = {
            "schema_version": "limen.conduct_principal_registry.v1",
            "principals": [
                {
                    "principal_id": "p-1",
                    "agent": "codex",
                    "surface": "cli",
                    "roles": ["conductor"],
                    "bearer": "too-short",
                }
            ],
        }
        with pytest.raises(ConductAuthenticationError, match="bounded secret"):
            parse_principal_registry(json.dumps(short_registry))

        # 2. Bearer too long (> 4096 chars)
        long_registry = {
            "schema_version": "limen.conduct_principal_registry.v1",
            "principals": [
                {
                    "principal_id": "p-1",
                    "agent": "codex",
                    "surface": "cli",
                    "roles": ["conductor"],
                    "bearer": "a" * 4097,
                }
            ],
        }
        with pytest.raises(ConductAuthenticationError, match="bounded secret"):
            parse_principal_registry(json.dumps(long_registry))

        # 3. Duplicate principal or bearer hash
        valid_bearer = "secret-token-at-least-24-chars-long!"
        dup_registry = {
            "schema_version": "limen.conduct_principal_registry.v1",
            "principals": [
                {
                    "principal_id": "p-1",
                    "agent": "codex",
                    "surface": "cli",
                    "roles": ["conductor"],
                    "bearer": valid_bearer,
                },
                {
                    "principal_id": "p-2",
                    "agent": "codex",
                    "surface": "cli",
                    "roles": ["conductor"],
                    "bearer": valid_bearer,
                },
            ],
        }
        with pytest.raises(ConductAuthenticationError, match="duplicate"):
            parse_principal_registry(json.dumps(dup_registry))

    def test_authenticate_principal_constant_time_comparison(self) -> None:
        """Valid bearer authenticates; invalid or empty bearer fails closed."""
        valid_bearer = "secret-token-at-least-24-chars-long-12345"
        registry_json = (
            '{"schema_version": "limen.conduct_principal_registry.v1", "principals": ['
            '{"principal_id": "p-auth", "agent": "codex", "surface": "cli", "roles": ["conductor"], '
            f'"bearer": "{valid_bearer}"'
            "}]}"
        )
        # Valid bearer
        principal = authenticate_principal(registry_json, valid_bearer)
        assert principal.principal_id == "p-auth"
        assert principal.roles == frozenset({"conductor"})

        # Invalid bearer
        with pytest.raises(ConductAuthenticationError, match="invalid conduct bearer"):
            authenticate_principal(registry_json, "wrong-bearer-that-is-at-least-24-chars-long!")

        # Empty bearer
        with pytest.raises(ConductAuthenticationError, match="missing conduct bearer"):
            authenticate_principal(registry_json, "")


# ===========================================================================
# SUITE 2: Unauthenticated Caller & Forged Local Principal Escalation Probes
# ===========================================================================


class TestSuite2UnauthenticatedCallerEscalation:
    """Verify that unauthenticated callers cannot bypass roles or hijack authenticated state."""

    def test_unauthenticated_session_registration_with_zero_capabilities_rejected(self) -> None:
        """Unauthenticated caller without conduct/execute capabilities gets observer-only and cannot register."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        s_bare = make_session("anonymous", capabilities=frozenset())

        # Unauthenticated register defaults to observer role -> must be rejected
        with pytest.raises(ConductConflict, match="lacks required conductor/executor role"):
            broker.register(s_bare, principal=None, now=NOW)

    def test_unauthenticated_caller_cannot_submit_with_authenticated_session(self) -> None:
        """An unauthenticated caller cannot submit work claiming to be a registered authenticated conductor."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_auth = make_principal("p-auth-conductor", "codex", "conductor")
        s_cond = make_session("codex", session_id="s-auth-cond")

        # 1. Registered by authenticated principal
        broker.register(s_cond, principal=p_auth, now=NOW)

        # 2. Unauthenticated caller attempts to submit packet using s-auth-cond
        wp = make_packet(work_id="adv-unauth-submit", conductor=s_cond.identity)
        with pytest.raises(ConductConflict, match="packet conductor is not bound to the authenticated principal"):
            broker.submit(wp, principal=None, now=NOW)

    def test_unauthenticated_caller_cannot_claim_authenticated_lease(self) -> None:
        """An unauthenticated caller cannot claim a lease assigned to an authenticated executor."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp = make_packet(work_id="adv-unauth-claim", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]

        # Unauthenticated claim attempt -> fails closed
        with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
            broker.claim(lease["lease_id"], lease["generation"], principal=None, now=NOW)

    def test_unauthenticated_caller_cannot_heartbeat_or_report(self) -> None:
        """Even if an unauthenticated caller obtains a token, heartbeat/report must fail closed."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp = make_packet(work_id="adv-unauth-hb", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]

        claim_res = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)
        cap_token = claim_res["capability_token"]

        # Unauthenticated heartbeat
        with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
            broker.heartbeat(lease["lease_id"], cap_token, principal=None, now=NOW)

        # Unauthenticated report
        receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity)
        with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
            broker.report(lease["lease_id"], cap_token, receipt, principal=None, now=NOW)


# ===========================================================================
# SUITE 3: Cross-Principal Lease Hijacking & Capability Token Tampering Probes
# ===========================================================================


class TestSuite3CrossPrincipalHijackingAndTokens:
    """Adversarial testing of lease ownership, token forgery, replay, and generation pinning."""

    def test_cross_principal_lease_claim_hijacking_rejected(self) -> None:
        """Attacker principal C cannot claim lease reserved for executor principal B."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec_b = make_principal("p-exec-b", "jules", "executor")
        p_attacker_c = make_principal("p-attacker-c", "attacker", "executor")

        s_cond = make_session("codex")
        s_exec_b = make_session("jules")
        s_attacker_c = make_session("attacker")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec_b, principal=p_exec_b, now=NOW)
        broker.register(s_attacker_c, principal=p_attacker_c, now=NOW)

        wp = make_packet(work_id="adv-hijack-claim", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]

        # Attacker C attempts to claim lease
        with pytest.raises(ConductConflict, match="lease belongs to another executor principal"):
            broker.claim(lease["lease_id"], lease["generation"], principal=p_attacker_c, now=NOW)

    def test_forged_capability_token_rejected_on_heartbeat_and_report(self) -> None:
        """Random or forged capability tokens are rejected via constant-time HMAC check."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp = make_packet(work_id="adv-token-forgery", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]

        forged_tokens = [
            "completely-fake-token-value-1234567890",
            base64.urlsafe_b64encode(b"random-bytes-not-signed-by-broker-secret").decode().rstrip("="),
            "",
            "A" * 64,
        ]

        for fake_token in forged_tokens:
            with pytest.raises(ConductConflict, match="invalid lease capability token"):
                broker.heartbeat(lease["lease_id"], fake_token, principal=p_exec, now=NOW)

            receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity)
            with pytest.raises(ConductConflict, match="invalid lease capability token"):
                broker.report(lease["lease_id"], fake_token, receipt, principal=p_exec, now=NOW)

    def test_cross_lease_token_replay_rejected(self) -> None:
        """Token from Lease 1 cannot be used to operate on Lease 2."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp1 = make_packet(
            work_id="adv-replay-1", conductor=s_cond.identity, preferred_agent="jules", resource="task/1", effect="read"
        )
        wp2 = make_packet(
            work_id="adv-replay-2", conductor=s_cond.identity, preferred_agent="jules", resource="task/2", effect="read"
        )

        sub1 = broker.submit(wp1, principal=p_cond, now=NOW)
        sub2 = broker.submit(wp2, principal=p_cond, now=NOW)

        lease1 = sub1["lease"]
        lease2 = sub2["lease"]

        token1 = broker.claim(lease1["lease_id"], lease1["generation"], principal=p_exec, now=NOW)["capability_token"]
        broker.claim(lease2["lease_id"], lease2["generation"], principal=p_exec, now=NOW)

        # Attempt to use token1 on lease2
        with pytest.raises(ConductConflict, match="invalid lease capability token"):
            broker.heartbeat(lease2["lease_id"], token1, principal=p_exec, now=NOW)

        # Attempt to report on lease2 using token1
        receipt2 = make_receipt(sub2["run_id"], lease2["lease_id"], s_exec.identity)
        with pytest.raises(ConductConflict, match="invalid lease capability token"):
            broker.report(lease2["lease_id"], token1, receipt2, principal=p_exec, now=NOW)

    def test_generation_mismatch_rejected_on_claim_and_heartbeat(self) -> None:
        """Claim and heartbeat with wrong generation numbers fail closed."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp = make_packet(work_id="adv-gen-test", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]
        gen = lease["generation"]

        # Wrong generation on claim
        for bad_gen in [gen - 1, gen + 1, 0, 999]:
            with pytest.raises(ConductConflict, match="lease generation does not match the claim"):
                broker.claim(lease["lease_id"], bad_gen, principal=p_exec, now=NOW)

        # Valid claim
        cap_token = broker.claim(lease["lease_id"], gen, principal=p_exec, now=NOW)["capability_token"]

        # Wrong generation on heartbeat
        with pytest.raises(ConductConflict, match="lease generation does not match the request"):
            broker.heartbeat(lease["lease_id"], cap_token, generation=gen + 1, principal=p_exec, now=NOW)

        # Wrong generation on report
        receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity, generation=gen)
        with pytest.raises(ConductConflict, match="lease generation does not match the request"):
            broker.report(lease["lease_id"], cap_token, receipt, generation=gen + 1, principal=p_exec, now=NOW)


# ===========================================================================
# SUITE 4: Unauthorized Information Leakage & Query Authorization Probes
# ===========================================================================


class TestSuite4InformationLeakageAndAuthorization:
    """Verify authorization checks and isolation on query endpoints."""

    def test_notifications_list_assignments_strictly_rejects_executor_and_compatibility(self) -> None:
        """Notification assignment enumeration requires observer or conductor; executor/compatibility rejected."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")
        p_compat = make_principal("p-compat", "legacy", "compatibility")
        p_obs = make_principal("p-obs", "auditor", "observer")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        # 1. Executor rejected
        with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
            broker.list_notification_assignments(principal=p_exec, now=NOW)

        with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
            broker.list_assignments(principal=p_exec, now=NOW)

        # 2. Compatibility rejected
        with pytest.raises(ConductConflict, match="lacks required observer/conductor role"):
            broker.list_notification_assignments(principal=p_compat, now=NOW)

        # 3. Observer and conductor allowed
        obs_res = broker.list_notification_assignments(principal=p_obs, now=NOW)
        assert len(obs_res["assignments"]) == 2

        cond_res = broker.list_notification_assignments(principal=p_cond, now=NOW)
        assert len(cond_res["assignments"]) == 2

    def test_capabilities_query_authenticated_session_isolation(self) -> None:
        """Capabilities endpoint isolates authenticated_session_ids to the calling principal only."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p1 = make_principal("p1", "codex", "conductor")
        p2 = make_principal("p2", "jules", "executor")

        s1 = make_session("codex", session_id="s1")
        s2 = make_session("jules", session_id="s2")

        broker.register(s1, principal=p1, now=NOW)
        broker.register(s2, principal=p2, now=NOW)

        # Principal 1 query
        caps1 = broker.capabilities(principal=p1, now=NOW)
        assert caps1["authenticated_principal"]["principal_id"] == "p1"
        assert caps1["authenticated_session_ids"] == ["s1"]

        # Principal 2 query
        caps2 = broker.capabilities(principal=p2, now=NOW)
        assert caps2["authenticated_principal"]["principal_id"] == "p2"
        assert caps2["authenticated_session_ids"] == ["s2"]

        # Anonymous query
        caps_anon = broker.capabilities(principal=None, now=NOW)
        assert caps_anon["authenticated_principal"] is None
        assert caps_anon["authenticated_session_ids"] == []

    def test_non_existent_ids_fail_cleanly_without_unhandled_exceptions(self) -> None:
        """Non-existent run/lease/task queries fail closed without unhandled exceptions or state corruption."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_obs = make_principal("p-obs", "auditor", "observer")
        p_exec = make_principal("p-exec", "jules", "executor")

        # 1. Unknown graph
        with pytest.raises(ConductError, match="unknown run: run-non-existent"):
            broker.graph("run-non-existent", principal=p_obs)

        # 2. Unknown harvest
        with pytest.raises(ConductError, match="unknown run: run-non-existent"):
            broker.harvest("run-non-existent", principal=p_obs)

        # 3. Unknown task_run -> returns found=False
        task_res = broker.task_run("NON-EXISTENT-TASK-999", principal=p_obs)
        assert task_res["found"] is False

        # 4. Unknown lease claim
        with pytest.raises(ConductError, match="unknown lease: lease-non-existent"):
            broker.claim("lease-non-existent", 1, principal=p_exec, now=NOW)


# ===========================================================================
# SUITE 5: Session Hijacking, Protection & Attenuation Probes
# ===========================================================================


class TestSuite5SessionProtectionAndAttenuation:
    """Verify protected sessions, absence proof gating, and lineage attenuation."""

    def test_human_protected_session_downgrade_and_hijacking_prevented(self) -> None:
        """A human-protected session cannot be downgraded, adopted, cancelled, or stopped autonomously."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_human = make_principal("p-human", "human-op", "conductor")
        p_auto = make_principal("p-auto", "autonomous-agent", "conductor")

        s_human = make_session("human-op", session_id="s-human", protected=True)
        s_auto = make_session("autonomous-agent", session_id="s-auto")

        broker.register(s_human, principal=p_human, now=NOW)
        broker.register(s_auto, principal=p_auto, now=NOW)

        # 1. Downgrade attempt via re-registration
        s_downgrade = make_session("human-op", session_id="s-human", protected=False)
        reg = broker.register(s_downgrade, principal=p_human, now=NOW + timedelta(minutes=1))
        assert reg["human_protected"] is True  # preserved

        # 2. Submit packet under human conductor
        wp = make_packet(work_id="adv-human-run", conductor=s_human.identity, preferred_agent="autonomous-agent")
        sub = broker.submit(wp, principal=p_human, now=NOW)
        run_id = sub["run_id"]

        # 3. Autonomous agent cannot adopt human session even after 1 hour
        future = NOW + timedelta(hours=1)
        broker.register(s_auto, principal=p_auto, now=future)
        with pytest.raises(ConductConflict, match="protected human session cannot be adopted"):
            broker.adopt(run_id, s_auto.session_id, principal=p_auto, now=future)

        # 4. Autonomous conductor cannot cancel human session
        with pytest.raises(ConductConflict, match="protected human session cannot be cancelled"):
            broker.cancel(run_id, s_human.session_id, principal=p_human, now=NOW)

        # 5. Autonomous conductor cannot request_stop human session
        with pytest.raises(ConductConflict, match="protected human session cannot be signalled"):
            broker.request_stop(run_id, s_human.session_id, principal=p_human, now=NOW)

    def test_lineage_authority_attenuation_enforced(self) -> None:
        """Child packet cannot escalate actions, path prefixes, spend, or fanout depth beyond parent."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        parent_auth = AuthorityEnvelopeV1(
            actions=frozenset({"code"}),
            repositories=frozenset({"organvm/limen"}),
            path_prefixes=frozenset({"cli/src"}),
            external_effects=frozenset(),
            may_delegate=True,
        )
        wp_parent = make_packet(
            work_id="adv-parent",
            conductor=s_cond.identity,
            authority=parent_auth,
            spend_limit=4,
            max_depth=2,
            max_children=2,
            preferred_agent="jules",
        )
        sub_parent = broker.submit(wp_parent, principal=p_cond, now=NOW)
        parent_run_id = sub_parent["run_id"]

        # 1. Action escalation in child
        child_auth_escalate = AuthorityEnvelopeV1(
            actions=frozenset({"code", "admin", "publish"}),
            repositories=frozenset({"organvm/limen"}),
            path_prefixes=frozenset({"cli/src"}),
            external_effects=frozenset(),
        )
        wp_child_action = make_packet(
            work_id="adv-child-action",
            conductor=s_cond.identity,
            parent_run_id=parent_run_id,
            root_run_id=sub_parent["root_run_id"],
            depth=1,
            authority=child_auth_escalate,
            resource="task/child-1",
        )
        with pytest.raises(ConductConflict, match="child authority does not attenuate the parent"):
            broker.split(parent_run_id, wp_child_action, principal=p_cond, now=NOW)

        # 2. Path prefix expansion in child (parent has cli/src, child asks for cli or .)
        child_auth_path = AuthorityEnvelopeV1(
            actions=frozenset({"code"}),
            repositories=frozenset({"organvm/limen"}),
            path_prefixes=frozenset({"cli"}),  # broader than cli/src
            external_effects=frozenset(),
        )
        wp_child_path = make_packet(
            work_id="adv-child-path",
            conductor=s_cond.identity,
            parent_run_id=parent_run_id,
            root_run_id=sub_parent["root_run_id"],
            depth=1,
            authority=child_auth_path,
            resource="task/child-2",
        )
        with pytest.raises(ConductConflict, match="child authority does not attenuate the parent"):
            broker.split(parent_run_id, wp_child_path, principal=p_cond, now=NOW)

        # 3. Spend limit inflation in child (parent limit is 4, child asks for 10)
        wp_child_spend = make_packet(
            work_id="adv-child-spend",
            conductor=s_cond.identity,
            parent_run_id=parent_run_id,
            root_run_id=sub_parent["root_run_id"],
            depth=1,
            spend_limit=10,
            authority=parent_auth,
            resource="task/child-3",
        )
        with pytest.raises(ConductConflict, match="child spend does not attenuate the parent"):
            broker.split(parent_run_id, wp_child_spend, principal=p_cond, now=NOW)

        # 4. Depth violation in child (parent max_depth is 2, child depth claims 3)
        wp_child_depth = make_packet(
            work_id="adv-child-depth",
            conductor=s_cond.identity,
            parent_run_id=parent_run_id,
            root_run_id=sub_parent["root_run_id"],
            depth=3,
            authority=parent_auth,
            resource="task/child-4",
        )
        with pytest.raises(ConductConflict, match="child depth exceeds the parent fanout envelope"):
            broker.split(parent_run_id, wp_child_depth, principal=p_cond, now=NOW)


# ===========================================================================
# SUITE 6: Concurrency, Malformed Payloads & Rollback Probes
# ===========================================================================


class TestSuite6TransactionsAndRollback:
    """Verify transactional consistency, rollback on error, and fail-closed state."""

    def test_submit_graph_atomic_rollback_on_conflict(self) -> None:
        """If any packet in submit_graph fails or conflicts, the keeper must be byte-for-byte unchanged."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp1 = make_packet(
            work_id="adv-atom-1",
            conductor=s_cond.identity,
            resource="task/shared-res",
            preferred_agent="jules",
        )
        # wp2 tries to claim the same exclusive resource task/shared-res -> will conflict
        wp2 = make_packet(
            work_id="adv-atom-2",
            conductor=s_cond.identity,
            resource="task/shared-res",
            preferred_agent="jules",
        )

        res = broker.submit_graph((wp1, wp2), principal=p_cond, now=NOW)
        # Should return busy status on conflict
        assert res["status"] == "busy"

        # Verify no partial runs were created in state
        with broker.store.transaction() as state:
            assert "adv-atom-1" not in state.get("work_index", {})
            assert "adv-atom-2" not in state.get("work_index", {})
            assert len(state.get("runs", {})) == 0

    def test_state_rollback_on_transaction_exception(self) -> None:
        """When an operation raises an exception inside a transaction, all mutated state is rolled back."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        s_cond = make_session("codex")
        broker.register(s_cond, principal=p_cond, now=NOW)

        # Snapshot initial state
        initial_events_count = len(broker.store.snapshot()["events"])

        # Packet with passed deadline raises ConductError
        wp_expired = make_packet(
            work_id="adv-expired",
            conductor=s_cond.identity,
            deadline=NOW - timedelta(minutes=10),
        )
        with pytest.raises(ConductError, match="deadline has already passed"):
            broker.submit(wp_expired, principal=p_cond, now=NOW)

        # State is clean
        assert len(broker.store.snapshot()["events"]) == initial_events_count
        assert "adv-expired" not in broker.store.snapshot()["work_index"]


# ===========================================================================
# SUITE 7: Campaign Evidence, Ancestry Cycles & Lifecycle State Edge Cases
# ===========================================================================


class TestSuite7CampaignAndCycleProbes:
    """Stress-test campaign evidence validation, work loan requirements, and ancestry loop prevention."""

    def test_missing_work_loan_rejected(self) -> None:
        """WorkPacket without a valid work loan must be rejected with ConductConflict."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        s_cond = make_session("codex")
        broker.register(s_cond, principal=p_cond, now=NOW)

        # Create packet with work_loan=None and non-projection intent
        auth = AuthorityEnvelopeV1(
            actions=frozenset({"code"}),
            repositories=frozenset({"organvm/limen"}),
            path_prefixes=frozenset({"cli"}),
            external_effects=frozenset(),
        )
        wp_no_loan = WorkPacketV1(
            work_id="adv-no-loan",
            work_key="adv-no-loan",
            intent={"objective": "no loan"},
            initiator=s_cond.identity,
            conductor=s_cond.identity,
            required_capabilities=frozenset({"code"}),
            predicate="pytest -q",
            receipt_target="github:organvm/limen:pull-request:1",
            work_loan=None,  # missing work loan
            authority=auth,
            deadline=NOW + timedelta(hours=1),
            spend=SpendEnvelopeV1(limit=1),
            retry=RetryPolicyV1(max_attempts=1),
        )
        with pytest.raises(ConductConflict, match="task-not-underwritten"):
            broker.submit(wp_no_loan, principal=p_cond, now=NOW)

    def test_ancestry_work_key_cycle_rejected(self) -> None:
        """A child packet attempting to reuse an ancestor's work_key must be rejected."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp_root = make_packet(
            work_id="adv-root-cycle",
            work_key="KEY-ROOT-CYCLE",
            conductor=s_cond.identity,
            preferred_agent="jules",
            effect="read",
            resource="task/root-cycle",
        )
        sub_root = broker.submit(wp_root, principal=p_cond, now=NOW)
        root_run_id = sub_root["run_id"]

        # Child 1
        wp_child1 = make_packet(
            work_id="adv-child-1-cycle",
            work_key="KEY-CHILD-1",
            conductor=s_cond.identity,
            parent_run_id=root_run_id,
            root_run_id=sub_root["root_run_id"],
            depth=1,
            preferred_agent="jules",
            effect="read",
            resource="task/child-1-cycle",
        )
        sub_child1 = broker.split(root_run_id, wp_child1, principal=p_cond, now=NOW)
        child1_run_id = sub_child1["run_id"]

        # Child 2 attempting to reuse ancestor's work_key (KEY-ROOT-CYCLE)
        wp_child2_cyclic = make_packet(
            work_id="adv-child-2-cyclic",
            work_key="KEY-ROOT-CYCLE",  # cycle!
            conductor=s_cond.identity,
            parent_run_id=child1_run_id,
            root_run_id=sub_root["root_run_id"],
            depth=2,
            preferred_agent="jules",
            effect="read",
            resource="task/child-2-cycle",
        )
        with pytest.raises(ConductConflict, match="repeated ancestry work_key/cycle rejected"):
            broker.split(child1_run_id, wp_child2_cyclic, principal=p_cond, now=NOW)

    def test_cancel_non_reserved_work_rejected(self) -> None:
        """Cancel is only valid for reserved work; active or terminal work cannot be cancelled."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp = make_packet(work_id="adv-cancel-active", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]

        cap_token = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)["capability_token"]
        # Heartbeat transitions run from reserved to running
        broker.heartbeat(lease["lease_id"], cap_token, principal=p_exec, observed_heads={"pr": "head-001"}, now=NOW)

        # Attempt to cancel running work -> rejected
        with pytest.raises(ConductConflict, match="only reserved, not-started work may be cancelled"):
            broker.cancel(sub["run_id"], s_cond.session_id, principal=p_cond, now=NOW)

    def test_request_stop_on_terminal_work_rejected(self) -> None:
        """Request stop on an already succeeded or terminal run is rejected."""
        broker = ConductBroker(MemoryStateStore(), capability_secret=TEST_SECRET)
        p_cond = make_principal("p-cond", "codex", "conductor")
        p_exec = make_principal("p-exec", "jules", "executor")

        s_cond = make_session("codex")
        s_exec = make_session("jules")

        broker.register(s_cond, principal=p_cond, now=NOW)
        broker.register(s_exec, principal=p_exec, now=NOW)

        wp = make_packet(work_id="adv-stop-terminal", conductor=s_cond.identity, preferred_agent="jules")
        sub = broker.submit(wp, principal=p_cond, now=NOW)
        lease = sub["lease"]

        cap_token = broker.claim(lease["lease_id"], lease["generation"], principal=p_exec, now=NOW)["capability_token"]
        receipt = make_receipt(sub["run_id"], lease["lease_id"], s_exec.identity)
        broker.report(lease["lease_id"], cap_token, receipt, principal=p_exec, now=NOW)

        # Attempt to request stop on succeeded run
        with pytest.raises(ConductConflict, match="terminal work cannot receive a stop request"):
            broker.request_stop(sub["run_id"], s_cond.session_id, principal=p_cond, now=NOW)
