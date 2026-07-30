from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from limen.conduct.broker import ConductBroker
from limen.conduct.canary import ConductCanaryError, run_full_mesh_canary
from limen.conduct.client import HttpConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    ConductorSessionV1,
    ConductPrincipalV1,
)
from limen.conduct.store import MemoryStateStore


NOW = datetime(2026, 7, 30, 16, 0, tzinfo=timezone.utc)
RUNTIME_SHA = "a" * 40


class BrokerHttpClient(HttpConductClient):
    """Authenticated HTTP-shaped test client backed by the parity kernel."""

    def __init__(
        self,
        endpoint: str,
        token: str,  # allow-secret: inert test-client parameter
        *,
        timeout: int = 30,
        broker: ConductBroker,
        principals: dict[str, ConductPrincipalV1],
    ) -> None:
        super().__init__(endpoint, token, timeout=timeout)
        self.broker = broker
        self.principals = principals

    @property
    def principal(self) -> ConductPrincipalV1:
        return self.principals[self.token]

    def capabilities(self):
        return self.broker.capabilities(now=NOW)

    def submit(self, packet):
        return self.broker.submit(packet, principal=self.principal, now=NOW)

    def claim(self, lease_id, generation):
        return self.broker.claim(
            lease_id,
            generation,
            principal=self.principal,
            now=NOW,
        )

    def heartbeat(
        self,
        lease_id,
        capability_token,
        *,
        generation,
        observed_heads=None,
        attempt=None,
    ):
        return self.broker.heartbeat(
            lease_id,
            capability_token,
            generation=generation,
            principal=self.principal,
            observed_heads=observed_heads,
            attempt=attempt,
            now=NOW,
        )

    def report(self, lease_id, capability_token, receipt, *, generation):
        return self.broker.report(
            lease_id,
            capability_token,
            receipt,
            generation=generation,
            principal=self.principal,
            now=NOW,
        )

    def harvest(self, root_run_id):
        return self.broker.harvest(root_run_id)


def _principal(principal_id: str, agent: str, role: str) -> ConductPrincipalV1:
    return ConductPrincipalV1(
        principal_id=principal_id,
        agent=agent,
        surface=f"canary-{role}",
        roles=frozenset({"observer", role}),
    )


def _session(agent: str, role: str) -> ConductorSessionV1:
    session_id = f"{agent}-canary-{role}"
    return ConductorSessionV1(
        session_id=session_id,
        identity=AgentIdentityV1(
            agent=agent,
            surface=f"canary-{role}",
            session_id=session_id,
        ),
        origin="relay",
        capabilities=frozenset({"conduct"} if role == "conductor" else {"execute"}),
        transport="authenticated-canary",
        concurrency=1,
        heartbeat_at=NOW,
        accepting_work=True,
    )


def _mesh(tmp_path: Path):
    broker = ConductBroker(
        MemoryStateStore(),
        capability_secret="full-mesh-capability-secret",
    )
    principals: dict[str, ConductPrincipalV1] = {}
    credentials = []
    environment = {
        "LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY": json.dumps(
            {
                "schema_version": "limen.conduct_runtime_identity.v1",
                "git_sha": RUNTIME_SHA,
                "deployment_id": "deployment-fixture-42",
            }
        )
    }
    for agent in ("alpha", "zeta"):
        for role in ("conductor", "executor"):
            token_env = f"LIMEN_FIXTURE_{agent.upper()}_{role.upper()}"
            token = f"{agent}-{role}-credential-at-least-24-characters"  # allow-secret: inert fixture
            principal = _principal(f"{agent}-{role}-principal", agent, role)
            principals[token] = principal
            environment[token_env] = token
            session = _session(agent, role)
            broker.register(session, principal=principal, now=NOW)
            credentials.append(
                {
                    "session_id": session.session_id,
                    "role": role,
                    "token_env": token_env,
                }
            )
    environment.update(
        {
            "LIMEN_CONDUCT_CANARY_CREDENTIAL_REFS": json.dumps(
                {
                    "schema_version": "limen.conduct_canary_credential_refs.v1",
                    "credentials": credentials,
                }
            )
        }
    )

    def factory(endpoint, token, *, timeout):
        return BrokerHttpClient(
            endpoint,
            token,
            timeout=timeout,
            broker=broker,
            principals=principals,
        )

    bootstrap = factory(
        "https://limen-runtime.example",
        environment["LIMEN_FIXTURE_ALPHA_CONDUCTOR"],
        timeout=17,
    )
    return broker, bootstrap, factory, environment, tmp_path / "mesh-receipt.json"


def test_full_mesh_canary_covers_every_ordered_edge_and_redacts_credentials(tmp_path: Path) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)

    receipt = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )

    assert receipt["schema_version"] == "limen.conduct_full_mesh_canary.v1"
    assert receipt["status"] == "passed"
    assert receipt["lane_count"] == 2
    assert receipt["edge_count_required"] == 4
    assert receipt["edge_count_succeeded"] == 4
    assert {(edge["conductor_lane"], edge["executor_lane"]) for edge in receipt["edges"]} == {
        ("alpha", "alpha"),
        ("alpha", "zeta"),
        ("zeta", "alpha"),
        ("zeta", "zeta"),
    }
    assert all(
        edge["reservation"]
        and edge["executor_only_claim"]
        and edge["heartbeat"]
        and edge["unchanged_heads"]
        and edge["empty_changed_paths"]
        and edge["conductor_harvest"]
        for edge in receipt["edges"]
    )
    rendered = receipt_path.read_text(encoding="utf-8")
    assert all(value not in rendered for key, value in environment.items() if key.startswith("LIMEN_FIXTURE_"))
    assert "LIMEN_FIXTURE_ALPHA_CONDUCTOR" in rendered
    assert "deployment-fixture-42" not in rendered


def test_same_canary_identity_is_byte_idempotent_and_creates_no_new_runs(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    first = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    before = receipt_path.read_bytes()
    run_count = len(broker.store.snapshot()["runs"])

    second = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )

    assert second == first
    assert receipt_path.read_bytes() == before
    assert len(broker.store.snapshot()["runs"]) == run_count == 4


def test_full_mesh_canary_rejects_non_http_clients(tmp_path: Path) -> None:
    with pytest.raises(ConductCanaryError, match="local SQLite is rejected"):
        run_full_mesh_canary(
            client=object(),
            receipt_path=tmp_path / "receipt.json",
            environ={},
        )
