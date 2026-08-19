from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, local

import limen.conduct.canary as canary_module
import pytest
from limen.conduct.broker import ConductBroker, ConductError
from limen.conduct.canary import (
    ConductCanaryError,
    run_full_mesh_canary as _run_full_mesh_canary,
)
from limen.conduct.canary_executor import (
    NativeCanaryEdgeAck,
    execute_native_canary_edge,
)
from limen.conduct.client import HttpConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    ConductorSessionV1,
    ConductPrincipalV1,
)
from limen.conduct.store import MemoryStateStore

NOW = datetime(2026, 7, 30, 16, 0, tzinfo=UTC)
RUNTIME_SHA = "a" * 40
REAL_REPO_RECEIPT_TARGET = canary_module._repo_receipt_target
REAL_RESOLVE_NATIVE_CANARY_BRIDGE = canary_module.resolve_native_canary_bridge
_CALLBACK_CONTEXT = local()


def run_full_mesh_canary(**kwargs):
    """Route executor effects through the same isolated callback contract as production."""

    environment = kwargs.get("environ", os.environ)
    client = kwargs["client"]
    client_factory = kwargs.get("client_factory", HttpConductClient)
    predicate_runner = kwargs.pop("predicate_runner", subprocess.run)
    override = kwargs.pop("executor_waker", None)
    prior = getattr(_CALLBACK_CONTEXT, "value", None)
    _CALLBACK_CONTEXT.value = {
        "environment": environment,
        "client": client,
        "client_factory": client_factory,
        "predicate_runner": predicate_runner,
        "override": override,
    }
    try:
        return _run_full_mesh_canary(**kwargs)
    finally:
        _CALLBACK_CONTEXT.value = prior


@pytest.fixture(autouse=True)
def _repo_owned_receipt_paths(monkeypatch, tmp_path: Path) -> None:
    """Keep unit receipts isolated while preserving the production Git target shape."""

    def resolve(path: Path) -> tuple[Path, str]:
        canonical = path.expanduser().resolve(strict=False)
        try:
            relative = canonical.relative_to(tmp_path)
        except ValueError as exc:
            raise ConductCanaryError("canary receipt must remain inside its Git repository") from exc
        return canonical, f"git:organvm/limen:{relative.as_posix()}"

    monkeypatch.setattr(canary_module, "_repo_receipt_target", resolve)
    monkeypatch.setattr(
        canary_module,
        "resolve_native_canary_bridge",
        lambda _environment: ("test-native-canary-bridge", 1),
    )

    def wake(request, *, environ, resolved_bridge):
        assert resolved_bridge == ("test-native-canary-bridge", 1)
        context = _CALLBACK_CONTEXT.value
        if context["override"] is not None:
            return context["override"](request)
        callback_environment = dict(context["environment"])
        callback_environment.update(
            {
                "LIMEN_SESSION_ID": request.executor_session_id,
                "LIMEN_NATIVE_SESSION_ID": request.executor_native_session_id,
                "LIMEN_NATIVE_RUN_ID": request.executor_native_run_id,
                "LIMEN_CONDUCT_CANARY_CREDENTIAL_REF": request.executor_credential_ref,
            }
        )
        callback_client = context["client_factory"](
            context["client"].endpoint,
            context["environment"][request.executor_credential_ref],
            timeout=context["client"].timeout,
        )
        return execute_native_canary_edge(
            request,
            client=callback_client,
            environ=callback_environment,
            predicate_runner=context["predicate_runner"],
        )

    monkeypatch.setattr(canary_module, "wake_native_canary_edge", wake)


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
        clock: dict[str, datetime],
    ) -> None:
        super().__init__(endpoint, token, timeout=timeout)
        self.broker = broker
        self.principals = principals
        self.clock = clock

    @property
    def principal(self) -> ConductPrincipalV1:
        return self.principals[self.token]

    def capabilities(self):
        return self.broker.capabilities(principal=self.principal, now=self.clock["now"])

    def submit(self, packet):
        self.clock["now"] = packet.deadline - timedelta(minutes=15)
        return self.broker.submit(packet, principal=self.principal, now=self.clock["now"])

    def claim(self, lease_id, generation):
        return self.broker.claim(
            lease_id,
            generation,
            principal=self.principal,
            now=self.clock["now"],
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
            now=self.clock["now"],
        )

    def report(self, lease_id, capability_token, receipt, *, generation):
        return self.broker.report(
            lease_id,
            capability_token,
            receipt,
            generation=generation,
            principal=self.principal,
            now=self.clock["now"],
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
            native_run_id=f"{agent}-{role}-native-run",
        ),
        origin="relay",
        native_session_id=f"{agent}-provider-{role}-instance",
        native_run_id=f"{agent}-{role}-native-run",
        capabilities=frozenset({"conduct"} if role == "conductor" else {"execute"}),
        transport="authenticated-canary",
        concurrency=2,
        heartbeat_at=NOW,
        accepting_work=True,
    )


def _mesh(
    tmp_path: Path,
    *,
    deployment_id: str = "deployment-fixture-42",
    lease_ttl: timedelta = timedelta(minutes=15),
):
    runtime_identity = {
        "schema_version": "limen.conduct_runtime_identity.v1",
        "git_sha": RUNTIME_SHA,
        "deployment_id": deployment_id,
    }
    broker = ConductBroker(
        MemoryStateStore(),
        capability_secret="full-mesh-capability-secret",
        lease_ttl=lease_ttl,
        runtime_identity=runtime_identity,
    )
    principals: dict[str, ConductPrincipalV1] = {}
    clock = {"now": NOW}
    credentials = []
    environment = {"LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY": json.dumps(runtime_identity)}
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
            clock=clock,
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
    assert receipt["receipt_target"] == "git:organvm/limen:mesh-receipt.json"
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
        and edge["native_executor_callback"]
        and edge["unchanged_heads"]
        and edge["empty_changed_paths"]
        and edge["conductor_harvest"]
        for edge in receipt["edges"]
    )
    assert all(
        run["packet"]["receipt_target"].startswith(f"{receipt['receipt_target']}#")
        for run in _broker.store.snapshot()["runs"].values()
    )
    rendered = receipt_path.read_text(encoding="utf-8")
    assert all(value not in rendered for key, value in environment.items() if key.startswith("LIMEN_FIXTURE_"))
    assert "LIMEN_FIXTURE_ALPHA_CONDUCTOR" in rendered
    assert "deployment-fixture-42" not in rendered


def test_missing_native_wake_bridge_fails_before_graph_writes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    monkeypatch.setattr(
        canary_module,
        "resolve_native_canary_bridge",
        REAL_RESOLVE_NATIVE_CANARY_BRIDGE,
    )

    with pytest.raises(ConductCanaryError, match="session-owned wake bridge"):
        _run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert broker.store.snapshot()["runs"] == {}


def test_callback_ack_for_another_edge_is_rejected(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)

    def wrong_edge(request):
        return replace(
            NativeCanaryEdgeAck.expected(request),
            edge_id="wrong-edge",
        )

    with pytest.raises(ConductCanaryError, match="acknowledged a different"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            executor_waker=wrong_edge,
            now=NOW,
        )

    assert not receipt_path.exists()
    assert all(run["status"] != "succeeded" for run in broker.store.snapshot()["runs"].values())


def test_callback_ack_without_terminal_report_is_rejected(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)

    with pytest.raises(ConductCanaryError, match="without a terminal accepted receipt"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            executor_waker=NativeCanaryEdgeAck.expected,
            now=NOW,
        )

    assert not receipt_path.exists()
    assert all(run["status"] != "succeeded" for run in broker.store.snapshot()["runs"].values())


def test_executor_mutations_occur_only_inside_the_native_callback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    callback_active = False
    calls: list[tuple[str, str, bool]] = []

    for method_name in ("capabilities", "claim", "heartbeat", "report"):
        original = getattr(BrokerHttpClient, method_name)

        def record(self, *args, __method=method_name, __original=original, **kwargs):
            role = "executor" if "executor" in self.principal.roles else "conductor"
            calls.append((role, __method, callback_active))
            return __original(self, *args, **kwargs)

        monkeypatch.setattr(BrokerHttpClient, method_name, record)

    def native_callback(request):
        nonlocal callback_active
        callback_environment = dict(environment)
        callback_environment.update(
            {
                "LIMEN_SESSION_ID": request.executor_session_id,
                "LIMEN_NATIVE_SESSION_ID": request.executor_native_session_id,
                "LIMEN_NATIVE_RUN_ID": request.executor_native_run_id,
                "LIMEN_CONDUCT_CANARY_CREDENTIAL_REF": request.executor_credential_ref,
            }
        )
        callback_client = factory(
            client.endpoint,
            environment[request.executor_credential_ref],
            timeout=client.timeout,
        )
        callback_active = True
        try:
            return execute_native_canary_edge(
                request,
                client=callback_client,
                environ=callback_environment,
            )
        finally:
            callback_active = False

    run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        executor_waker=native_callback,
        now=NOW,
    )

    executor_mutations = [
        callback
        for role, method, callback in calls
        if role == "executor" and method in {"claim", "heartbeat", "report"}
    ]
    assert executor_mutations
    assert all(executor_mutations)
    assert ("executor", "capabilities", False) in calls


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

    def unexpected_wake(_request):
        raise AssertionError("fixed-point reuse must not wake native executors")

    second = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        executor_waker=unexpected_wake,
        now=NOW,
    )

    assert second == first
    assert receipt_path.read_bytes() == before
    assert len(broker.store.snapshot()["runs"]) == run_count == 4


def test_each_edge_gets_a_fresh_injected_deadline(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    instants = iter(NOW + timedelta(seconds=offset) for offset in range(4))

    receipt = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        clock=lambda: next(instants),
    )

    assert [edge["packet_deadline"] for edge in receipt["edges"]] == [
        (NOW + timedelta(minutes=15, seconds=offset)).isoformat() for offset in range(4)
    ]
    assert len(broker.store.snapshot()["runs"]) == 4


def test_receipt_target_changes_canary_and_packet_identity(tmp_path: Path) -> None:
    broker, client, factory, environment, first_path = _mesh(tmp_path)
    first = run_full_mesh_canary(
        client=client,
        receipt_path=first_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    second_path = tmp_path / "other-receipt.json"
    second = run_full_mesh_canary(
        client=client,
        receipt_path=second_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )

    assert first["receipt_target"] != second["receipt_target"]
    assert first["canary_id"] != second["canary_id"]
    assert {edge["run_id"] for edge in first["edges"]}.isdisjoint(edge["run_id"] for edge in second["edges"])
    assert len(broker.store.snapshot()["runs"]) == 8


def test_re_registered_native_session_instance_cannot_reuse_prior_receipt(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    with broker.store.transaction() as state:
        state["sessions"]["alpha-canary-conductor"]["native_session_id"] = "alpha-provider-conductor-reopened"

    with pytest.raises(ConductCanaryError, match="another canary identity"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW + timedelta(minutes=1),
        )


@pytest.mark.parametrize("field", ["native_session_id", "native_run_id"])
def test_canary_requires_live_native_session_instance_binding(
    tmp_path: Path,
    field: str,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    with broker.store.transaction() as state:
        state["sessions"]["alpha-canary-conductor"][field] = None

    with pytest.raises(ConductCanaryError, match=field):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert broker.store.snapshot()["runs"] == {}


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
        "packet_deadline",
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
    elif tamper == "packet_deadline":
        deadline = datetime.fromisoformat(receipt["edges"][0]["packet_deadline"])
        receipt["edges"][0]["packet_deadline"] = (deadline + timedelta(seconds=1)).isoformat()
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

    with pytest.raises(ConductCanaryError, match="observed_at"):
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


def test_elapsed_retry_recovers_live_duplicate_and_third_run_byte_reuses(monkeypatch, tmp_path: Path) -> None:
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
        now=NOW + timedelta(minutes=1),
    )
    before = receipt_path.read_bytes()
    third = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=2),
    )

    assert receipt["status"] == "passed"
    assert third == receipt
    assert receipt_path.read_bytes() == before
    assert {edge["packet_deadline"] for edge in receipt["edges"]} == {
        (NOW + timedelta(minutes=15)).isoformat(),
        (NOW + timedelta(minutes=16)).isoformat(),
    }
    assert receipt["observed_at"] == (NOW + timedelta(minutes=1)).isoformat()
    assert len(broker.store.snapshot()["runs"]) == 4


def test_elapsed_retry_recovers_terminal_duplicates_and_third_run_byte_reuses(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    first = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    first_bytes = receipt_path.read_bytes()
    receipt_path.unlink()

    recovered = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=1),
    )
    recovered_bytes = receipt_path.read_bytes()
    third = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=2),
    )

    assert recovered == first
    assert third == recovered
    assert recovered_bytes == first_bytes
    assert receipt_path.read_bytes() == recovered_bytes
    assert {edge["packet_deadline"] for edge in recovered["edges"]} == {(NOW + timedelta(minutes=15)).isoformat()}
    assert len(broker.store.snapshot()["runs"]) == 4


def test_concurrent_different_identities_cannot_overwrite_receipt(monkeypatch, tmp_path: Path) -> None:
    lock_root = tmp_path / "runtime-locks"
    monkeypatch.setenv(canary_module._LOCK_ROOT_ENV, str(lock_root))
    broker_one, client_one, factory_one, environment_one, receipt_path = _mesh(tmp_path)
    broker_two, client_two, factory_two, environment_two, _same_path = _mesh(
        tmp_path,
        deployment_id="deployment-fixture-99",
    )
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
    lock_files = list(lock_root.glob("*.lock"))
    assert len(lock_files) == 1
    assert lock_files[0].is_file()
    assert lock_files[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("token_env", "extra_role"),
    [
        ("LIMEN_FIXTURE_ALPHA_CONDUCTOR", "executor"),
        ("LIMEN_FIXTURE_ALPHA_EXECUTOR", "conductor"),
    ],
)
def test_canary_rejects_overprivileged_authenticated_principals(
    tmp_path: Path,
    token_env: str,
    extra_role: str,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    token = environment[token_env]  # allow-secret: inert fixture selected by its environment reference
    original = client.principals[token]
    client.principals[token] = ConductPrincipalV1(
        principal_id=original.principal_id,
        agent=original.agent,
        surface=original.surface,
        roles=frozenset({*original.roles, extra_role}),
    )

    with pytest.raises(ConductCanaryError, match="overprivileged"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert broker.store.snapshot()["runs"] == {}


@pytest.mark.parametrize("credential_ref", ["LIMEN_CONDUCT_TOKEN", "HOME", "PATH"])
def test_canary_rejects_reserved_executor_credential_references_before_graph_writes(
    tmp_path: Path,
    credential_ref: str,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    manifest = json.loads(environment["LIMEN_CONDUCT_CANARY_CREDENTIAL_REFS"])
    executor = next(row for row in manifest["credentials"] if row["role"] == "executor")
    environment[credential_ref] = environment[executor["token_env"]]
    executor["token_env"] = credential_ref
    environment["LIMEN_CONDUCT_CANARY_CREDENTIAL_REFS"] = json.dumps(manifest)

    with pytest.raises(ConductCanaryError, match="executor credential reference token_env is reserved"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert broker.store.snapshot()["runs"] == {}


def test_principal_mismatch_is_not_accepted_as_executor_role_rejection() -> None:
    assert canary_module._executor_only_rejection(
        ConductError("authenticated principal lacks required executor/compatibility role")
    )
    assert not canary_module._executor_only_rejection(ConductError("lease belongs to another executor principal"))


@pytest.mark.parametrize("failure", ["missing", "mismatch"])
def test_canary_requires_exact_keeper_authenticated_runtime(
    tmp_path: Path,
    failure: str,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    if failure == "missing":
        broker.runtime_identity = None
    else:
        installed = json.loads(environment["LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY"])
        installed["deployment_id"] = "self-asserted-other-deployment"
        environment = dict(environment)
        environment["LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY"] = json.dumps(installed)

    with pytest.raises(ConductCanaryError, match="runtime identit"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert broker.store.snapshot()["runs"] == {}


def test_capabilities_bind_runtime_principal_and_registered_sessions(tmp_path: Path) -> None:
    _broker, client, _factory, environment, _receipt_path = _mesh(tmp_path)
    capabilities = client.capabilities()

    assert capabilities["runtime_identity"] == json.loads(environment["LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY"])
    assert capabilities["authenticated_principal"] == {
        "schema_version": "limen.conduct_principal.v1",
        "principal_id": "alpha-conductor-principal",
        "agent": "alpha",
        "surface": "canary-conductor",
        "roles": ["conductor", "observer"],
    }
    assert capabilities["authenticated_session_ids"] == ["alpha-canary-conductor"]


def test_saturated_executor_is_excluded_from_the_live_denominator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    original = BrokerHttpClient.capabilities

    def saturated(self):
        capabilities = original(self)
        for session in capabilities["sessions"]:
            if session["session_id"] == "alpha-canary-executor":
                session["active_leases"] = session["concurrency"]
        return capabilities

    monkeypatch.setattr(BrokerHttpClient, "capabilities", saturated)
    with pytest.raises(ConductCanaryError, match="ineligible for the executor role"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert broker.store.snapshot()["runs"] == {}


def test_each_edge_executes_and_persists_its_observed_predicate(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def runner(command, **kwargs):
        calls.append((tuple(command), kwargs))
        return subprocess.CompletedProcess(command, 0)

    receipt = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
        predicate_runner=runner,
    )

    assert len(calls) == receipt["edge_count_succeeded"] == 4
    assert {command for command, _kwargs in calls} == {("/bin/test", RUNTIME_SHA, "=", RUNTIME_SHA)}
    assert all(
        kwargs
        == {
            "check": False,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "timeout": 10,
        }
        for _command, kwargs in calls
    )
    for run in broker.store.snapshot()["runs"].values():
        persisted = run["receipts"][0]
        assert persisted["predicate"]["command"] == f"/bin/test {RUNTIME_SHA} = {RUNTIME_SHA}"
        assert persisted["predicate"]["exit_code"] == 0
        assert persisted["checks"][0]["name"] == "conduct-canary-conductor-claim-rejected"


def test_failed_edge_predicate_cannot_be_reported_as_success(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)

    def fail(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1)

    with pytest.raises(ConductCanaryError, match="predicate failed"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
            predicate_runner=fail,
        )

    assert not receipt_path.exists()
    assert all(run["status"] != "succeeded" for run in broker.store.snapshot()["runs"].values())


def test_expired_duplicate_uses_one_deterministic_retry_and_then_byte_reuses(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(
        tmp_path,
        lease_ttl=timedelta(seconds=30),
    )
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

    monkeypatch.setattr(BrokerHttpClient, "submit", original_submit)
    recovered = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=1),
    )
    recovered_bytes = receipt_path.read_bytes()
    reused = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=2),
    )

    assert [edge["retry_generation"] for edge in recovered["edges"]].count(1) == 1
    assert [edge["retry_generation"] for edge in recovered["edges"]].count(0) == 3
    assert len(broker.store.snapshot()["runs"]) == 5
    assert reused == recovered
    assert receipt_path.read_bytes() == recovered_bytes


def test_expired_retry_generation_cannot_retry_without_bound(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker, client, factory, environment, receipt_path = _mesh(
        tmp_path,
        lease_ttl=timedelta(seconds=30),
    )
    original_submit = BrokerHttpClient.submit
    first_interrupted = False

    def lose_first_submit_ack(self, packet):
        nonlocal first_interrupted
        result = original_submit(self, packet)
        if not first_interrupted:
            first_interrupted = True
            raise ConductError("simulated generation-zero lost acknowledgement")
        return result

    monkeypatch.setattr(BrokerHttpClient, "submit", lose_first_submit_ack)
    with pytest.raises(ConductError, match="generation-zero"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    def lose_retry_submit_ack(self, packet):
        result = original_submit(self, packet)
        if packet.intent["retry_generation"] == 1:
            raise ConductError("simulated generation-one lost acknowledgement")
        return result

    monkeypatch.setattr(BrokerHttpClient, "submit", lose_retry_submit_ack)
    with pytest.raises(ConductError, match="generation-one"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW + timedelta(minutes=1),
        )

    monkeypatch.setattr(BrokerHttpClient, "submit", original_submit)
    with pytest.raises(ConductCanaryError, match="exhausted its single bounded retry"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW + timedelta(minutes=2),
        )

    assert not receipt_path.exists()
    assert len(broker.store.snapshot()["runs"]) == 2


def test_fixed_point_reuse_is_harvest_only_and_never_reclaims(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    first = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    counts = {"submit": 0, "claim": 0, "harvest": 0}
    original_submit = BrokerHttpClient.submit
    original_claim = BrokerHttpClient.claim
    original_harvest = BrokerHttpClient.harvest

    def count_submit(self, packet):
        counts["submit"] += 1
        return original_submit(self, packet)

    def count_claim(self, lease_id, generation):
        counts["claim"] += 1
        return original_claim(self, lease_id, generation)

    def count_harvest(self, run_id):
        counts["harvest"] += 1
        return original_harvest(self, run_id)

    monkeypatch.setattr(BrokerHttpClient, "submit", count_submit)
    monkeypatch.setattr(BrokerHttpClient, "claim", count_claim)
    monkeypatch.setattr(BrokerHttpClient, "harvest", count_harvest)
    second = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=1),
    )

    assert second == first
    assert counts == {"submit": 0, "claim": 0, "harvest": 4}


def test_terminal_duplicate_recovery_does_not_repeat_negative_claim(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    receipt_path.unlink()
    original_claim = BrokerHttpClient.claim
    claim_count = 0

    def count_claim(self, lease_id, generation):
        nonlocal claim_count
        claim_count += 1
        return original_claim(self, lease_id, generation)

    monkeypatch.setattr(BrokerHttpClient, "claim", count_claim)
    run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW + timedelta(minutes=1),
    )

    assert claim_count == 0


def test_public_receipt_has_no_bearer_derived_verifier_and_survives_rotation(tmp_path: Path) -> None:
    broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    first = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=environment,
        client_factory=factory,
        now=NOW,
    )
    rendered = receipt_path.read_text(encoding="utf-8")
    tokens = [value for key, value in environment.items() if key.startswith("LIMEN_FIXTURE_")]
    assert all(token not in rendered for token in tokens)
    assert all(hashlib.sha256(token.encode()).hexdigest() not in rendered for token in tokens)
    assert "conductor_credential_sha256" not in rendered
    assert "executor_credential_sha256" not in rendered
    assert "capability_token" not in rendered

    rotated = dict(environment)
    token_env = "LIMEN_FIXTURE_ALPHA_CONDUCTOR"
    old_token = rotated[token_env]
    new_token = "alpha-conductor-rotated-credential-at-least-24-characters"
    client.principals[new_token] = client.principals[old_token]
    rotated[token_env] = new_token
    before = receipt_path.read_bytes()
    second = run_full_mesh_canary(
        client=client,
        receipt_path=receipt_path,
        environ=rotated,
        client_factory=factory,
        now=NOW + timedelta(minutes=1),
    )

    assert second == first
    assert receipt_path.read_bytes() == before
    assert len(broker.store.snapshot()["runs"]) == 4


@pytest.mark.parametrize("surface", ["submit", "harvest"])
def test_nested_public_lease_capability_material_is_rejected(
    monkeypatch,
    tmp_path: Path,
    surface: str,
) -> None:
    _broker, client, factory, environment, receipt_path = _mesh(tmp_path)
    original = getattr(BrokerHttpClient, surface)

    if surface == "submit":

        def leak(self, packet):
            response = original(self, packet)
            response["lease"]["nested"] = {"capability_token": "public-leak"}
            return response

    else:

        def leak(self, run_id):
            response = original(self, run_id)
            response["nodes"][0]["lease"]["nested"] = {"capability_token": "public-leak"}
            return response

    monkeypatch.setattr(BrokerHttpClient, surface, leak)
    with pytest.raises(ConductCanaryError, match="capability material"):
        run_full_mesh_canary(
            client=client,
            receipt_path=receipt_path,
            environ=environment,
            client_factory=factory,
            now=NOW,
        )


@pytest.mark.parametrize("kind", ["fifo", "device"])
def test_existing_receipt_must_be_a_regular_file(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "receipt.json"
    with pytest.raises(ConductCanaryError, match="regular file"):
        if kind == "fifo":
            os.mkfifo(path)
            canary_module._read_existing_receipt(path)
        else:
            canary_module._existing_receipt(Path("/dev/null"))


def test_existing_receipt_read_has_a_true_byte_bound(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(b"x" * (canary_module._MAX_RECEIPT_BYTES + 1))

    with pytest.raises(ConductCanaryError, match="bounded size"):
        canary_module._read_existing_receipt(path)


def test_existing_receipt_growth_during_read_fails_closed(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "limen.conduct_full_mesh_canary.v1",
                "status": "passed",
            }
        ),
        encoding="utf-8",
    )
    original_read = canary_module.os.read
    grew = False

    def grow_after_read(descriptor, size):
        nonlocal grew
        chunk = original_read(descriptor, size)
        if not grew:
            with path.open("ab") as handle:
                handle.write(b" ")
                handle.flush()
                os.fsync(handle.fileno())
            grew = True
        return chunk

    monkeypatch.setattr(canary_module.os, "read", grow_after_read)
    with pytest.raises(ConductCanaryError, match="changed while it was read"):
        canary_module._existing_receipt(path)


def test_symlink_aliases_share_one_os_released_persistent_lock(monkeypatch, tmp_path: Path) -> None:
    lock_root = tmp_path / "runtime-locks"
    monkeypatch.setenv(canary_module._LOCK_ROOT_ENV, str(lock_root))
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    alias_directory = tmp_path / "alias"
    alias_directory.symlink_to(real_directory, target_is_directory=True)
    real_path = real_directory / "receipt.json"
    alias_path = alias_directory / "receipt.json"
    first_acquired = Event()
    release_first = Event()
    second_acquired = Event()

    def hold_first():
        with canary_module._receipt_path_lock(real_path):
            first_acquired.set()
            assert release_first.wait(timeout=5)

    def acquire_alias():
        assert first_acquired.wait(timeout=5)
        with canary_module._receipt_path_lock(alias_path):
            second_acquired.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(hold_first)
        second = pool.submit(acquire_alias)
        assert first_acquired.wait(timeout=5)
        assert not second_acquired.wait(timeout=0.05)
        release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert list(real_directory.glob(".limen-conduct-canary-*.lock")) == []
    lock_files = list(lock_root.glob("*.lock"))
    assert len(lock_files) == 1
    assert stat.S_ISREG(lock_files[0].stat().st_mode)
    assert lock_files[0].stat().st_mode & 0o777 == 0o600


def test_receipt_replace_fsyncs_file_and_canonical_parent(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    modes: list[int] = []
    original_fsync = canary_module.os.fsync

    def record_fsync(descriptor):
        modes.append(os.fstat(descriptor).st_mode)
        return original_fsync(descriptor)

    monkeypatch.setattr(canary_module.os, "fsync", record_fsync)
    canary_module._write_receipt(path, {"schema_version": "test"})

    assert any(stat.S_ISREG(mode) for mode in modes)
    assert any(stat.S_ISDIR(mode) for mode in modes)


def test_full_mesh_canary_rejects_non_http_clients(tmp_path: Path) -> None:
    with pytest.raises(ConductCanaryError, match="local SQLite is rejected"):
        run_full_mesh_canary(
            client=object(),
            receipt_path=tmp_path / "receipt.json",
            environ={},
        )


@pytest.mark.parametrize(
    ("origin", "repository"),
    [
        ("git@github.com:organvm/limen.git", "organvm/limen"),
        ("https://github.com/fork-owner/renamed-limen.git", "fork-owner/renamed-limen"),
    ],
)
def test_repo_receipt_target_derives_exact_git_owner_path(
    tmp_path: Path,
    origin: str,
    repository: str,
) -> None:
    root = tmp_path / "limen"
    root.mkdir()
    receipt = root / "docs" / "receipts" / "conduct-canary" / f"{RUNTIME_SHA}.json"

    def git_runner(command, **kwargs):
        assert kwargs == {
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": 5,
        }
        if command[-2:] == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(command, 0, f"{root}\n", "")
        if command[-3:] == ("remote", "get-url", "origin"):
            return subprocess.CompletedProcess(command, 0, f"{origin}\n", "")
        raise AssertionError(command)

    canonical, target = REAL_REPO_RECEIPT_TARGET(receipt, git_runner=git_runner)

    assert canonical == receipt
    assert target == f"git:{repository}:docs/receipts/conduct-canary/{RUNTIME_SHA}.json"


def test_repo_receipt_target_rejects_non_github_origin(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    root.mkdir()

    def git_runner(command, **_kwargs):
        if command[-2:] == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(command, 0, f"{root}\n", "")
        return subprocess.CompletedProcess(command, 0, "file:///private/other/limen.git\n", "")

    with pytest.raises(ConductCanaryError, match="exact GitHub origin"):
        REAL_REPO_RECEIPT_TARGET(root / "receipt.json", git_runner=git_runner)


@pytest.mark.parametrize(
    "receipt_name",
    ["receipt.txt", ".git/receipt.json", "receipt#other.json"],
)
def test_repo_receipt_target_rejects_invalid_repo_paths(tmp_path: Path, receipt_name: str) -> None:
    root = tmp_path / "limen"
    root.mkdir()

    def git_runner(command, **_kwargs):
        if command[-2:] == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(command, 0, f"{root}\n", "")
        return subprocess.CompletedProcess(command, 0, "https://github.com/organvm/limen.git\n", "")

    with pytest.raises(ConductCanaryError, match="repository-owned JSON target"):
        REAL_REPO_RECEIPT_TARGET(root / receipt_name, git_runner=git_runner)


def test_repo_receipt_target_rejects_outside_path_before_remote_read(monkeypatch, tmp_path: Path) -> None:
    _broker, client, factory, environment, _receipt_path = _mesh(tmp_path)
    reads = 0

    def capabilities():
        nonlocal reads
        reads += 1
        return {}

    monkeypatch.setattr(client, "capabilities", capabilities)

    def reject(_path: Path):
        raise ConductCanaryError("canary receipt must remain inside its Git repository")

    monkeypatch.setattr(canary_module, "_repo_receipt_target", reject)
    with pytest.raises(ConductCanaryError, match="inside"):
        run_full_mesh_canary(
            client=client,
            receipt_path=tmp_path.parent / "outside.json",
            environ=environment,
            client_factory=factory,
            now=NOW,
        )

    assert reads == 0
