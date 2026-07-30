from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest

import limen.conduct.canary as canary_module
from limen.conduct.broker import ConductBroker, ConductError
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


@pytest.mark.parametrize(
    "tamper",
    [
        "schema",
        "runtime",
        "lanes",
        "edge_id",
        "run_id",
        "pair",
        "digest",
        "boolean",
    ],
)
def test_existing_receipt_tampering_fails_closed(tmp_path: Path, tamper: str) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if tamper == "schema":
        receipt["schema_version"] = "limen.conduct_full_mesh_canary.v0"
    elif tamper == "runtime":
        receipt["runtime_identity"]["deployment_id_sha256"] = "0" * 64
    elif tamper == "lanes":
        receipt["lanes"][0]["executor_session_sha256"] = "0" * 64
    elif tamper == "edge_id":
        receipt["edges"][0]["edge_id"] = "0" * 64
    elif tamper == "run_id":
        receipt["edges"][1]["run_id"] = receipt["edges"][0]["run_id"]
    elif tamper == "pair":
        receipt["edges"][1]["executor_lane"] = receipt["edges"][0]["executor_lane"]
    elif tamper == "digest":
        receipt["edges"][0]["accepted_receipt_sha256"] = "0" * 64
    else:
        receipt["edges"][0]["heartbeat"] = False
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ConductCanaryError):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )


def test_existing_receipt_observed_at_tampering_fails_closed(tmp_path: Path) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["observed_at"] = (datetime.fromisoformat(receipt["observed_at"]) + timedelta(seconds=1)).isoformat()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ConductCanaryError, match="deadline does not match"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )


@pytest.mark.parametrize("tamper", ["work_key", "intent", "intent_hash", "executor"])
def test_harvested_edge_tampering_fails_closed(tmp_path: Path, tamper: str) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    receipt = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    run_id = receipt["edges"][0]["run_id"]
    with broker.store.transaction() as state:
        run = state["runs"][run_id]
        if tamper == "work_key":
            run["packet"]["work_key"] = "conduct-canary:altered"
        elif tamper == "intent":
            run["packet"]["intent"]["edge_id"] = "0" * 64
        elif tamper == "intent_hash":
            run["packet"]["intent_hash"] = "0" * 64
        else:
            run["executor_session_id"] = "zeta-canary-executor"

    with pytest.raises(ConductCanaryError):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )


def test_harvested_packet_deadline_tampering_fails_closed(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    receipt = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    run_id = receipt["edges"][0]["run_id"]
    with broker.store.transaction() as state:
        packet = state["runs"][run_id]["packet"]
        packet["deadline"] = (datetime.fromisoformat(packet["deadline"]) + timedelta(seconds=1)).isoformat()

    with pytest.raises(ConductCanaryError, match="deadline does not match"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )


def test_interrupted_after_submit_recovers_duplicate_without_new_run(monkeypatch, tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    original_submit = BrokerHttpClient.submit
    interrupted = False

    def lose_first_submit_ack(self, packet):
        nonlocal interrupted
        result = original_submit(self, packet)
        if not interrupted:
            interrupted = True
            raise ConductError("simulated lost submit acknowledgement")
        return result

    monkeypatch.setattr(BrokerHttpClient, "submit", lose_first_submit_ack)
    with pytest.raises(ConductError, match="lost submit acknowledgement"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )
    assert not receipt_path.exists()
    assert len(broker.store.snapshot()["runs"]) == 1

    monkeypatch.setattr(BrokerHttpClient, "submit", original_submit)
    receipt = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )

    assert receipt["status"] == "passed"
    assert len(broker.store.snapshot()["runs"]) == 4


def test_missing_local_receipt_recovers_terminal_duplicates(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    first = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    receipt_path.unlink()

    recovered = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )

    assert recovered == first
    assert len(broker.store.snapshot()["runs"]) == 4


def test_concurrent_different_identities_cannot_overwrite_receipt(monkeypatch, tmp_path: Path) -> None:
    broker_one, client_one, factory_one, environment_one, receipt_path = _mesh(tmp_path)
    broker_two, client_two, factory_two, environment_two, _same_path = _mesh(tmp_path)
    runtime_two = json.loads(environment_two["LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY"])
    runtime_two["deployment_id"] = "deployment-fixture-99"
    environment_two = copy.deepcopy(environment_two)
    environment_two["LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY"] = json.dumps(runtime_two)
    barrier = Barrier(2)
    original_commit = canary_module._commit_receipt

    def synchronized_commit(path, payload):
        barrier.wait(timeout=5)
        return original_commit(path, payload)

    monkeypatch.setattr(canary_module, "_commit_receipt", synchronized_commit)

    def run_one():
        return run_full_mesh_canary(
            client=client_one,
            receipt_path=receipt_path,
            environ=environment_one,
            client_factory=factory_one,
            now=NOW,
        )

    def run_two():
        return run_full_mesh_canary(
            client=client_two,
            receipt_path=receipt_path,
            environ=environment_two,
            client_factory=factory_two,
            now=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_one), pool.submit(run_two)]
        successes = []
        failures = []
        for future in futures:
            try:
                successes.append(future.result())
            except ConductCanaryError as exc:
                failures.append(exc)

    assert len(successes) == 1
    assert len(failures) == 1
    assert "another canary identity" in str(failures[0])
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == successes[0]
    assert len(broker_one.store.snapshot()["runs"]) == 4
    assert len(broker_two.store.snapshot()["runs"]) == 4
    assert list(tmp_path.glob(".limen-conduct-canary-*.lock")) == []


def test_full_mesh_canary_rejects_non_http_clients(tmp_path: Path) -> None:
    with pytest.raises(ConductCanaryError, match="local SQLite is rejected"):
        run_full_mesh_canary(
            client=object(),
            receipt_path=tmp_path / "receipt.json",
            environ={},
        )
