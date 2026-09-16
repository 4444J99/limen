"""Exercise actual broker admission, child execution, and callback replay fencing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from limen.conduct import ConductBroker, ConductorSessionV1, MemoryStateStore
from limen.conduct.assessment_executor import AssessmentExecutorError, execute_assessment_run
from limen.conduct.assessment_packet import compile_assessment_packet
from limen.conduct.assessor_source import AssessorSnapshot
from limen.conduct.client import HttpConductClient
from limen.conduct.models import AgentIdentityV1, ConductPrincipalV1
from limen.work_loan import WorkLoanV1


class BrokerTransport(HttpConductClient):
    def __init__(self, broker, principal):
        super().__init__("https://keeper.example.invalid", "fixture-only")
        self.broker = broker
        self.principal = principal
        self.lose_admission = False

    def graph(self, run_id):
        return self.broker.graph(run_id, principal=self.principal)

    def claim(self, lease_id, generation):
        return self.broker.claim(lease_id, generation, principal=self.principal)

    def heartbeat(self, lease_id, token, **kwargs):
        result = self.broker.heartbeat(lease_id, token, principal=self.principal, **kwargs)
        if self.lose_admission:
            self.lose_admission = False
            raise TimeoutError("private provider text")
        return result

    def report(self, lease_id, token, receipt, **kwargs):
        return self.broker.report(lease_id, token, receipt, principal=self.principal, **kwargs)


@pytest.fixture
def callback():
    broker = ConductBroker(MemoryStateStore())
    conductor = AgentIdentityV1(agent="codex", surface="test", session_id="assessment-conductor")
    executor = AgentIdentityV1(agent="codex", surface="test", session_id="assessment-executor")
    principals = {}
    for identity, role, caps in [
        (conductor, "conductor", {"conduct"}),
        (executor, "executor", {"dependency-assessment"}),
    ]:
        principal = ConductPrincipalV1(
            principal_id=identity.session_id,
            agent=identity.agent,
            surface=identity.surface,
            roles=frozenset({"observer", role}),
        )
        principals[role] = principal
        broker.register(
            ConductorSessionV1(
                session_id=identity.session_id, identity=identity, origin="dispatched", capabilities=frozenset(caps)
            ),
            principal=principal,
        )
    result = dict(
        status="REVIEW_READY",
        reason="EXACT_HEAD_ACTIONS_CI",
        automatic_acceptance=False,
        repository_id=1154799938,
        run_id=123,
        run_attempt=2,
        head="a" * 40,
        base_sha="b" * 40,
        pr=22,
    )
    data = ("import json; print(json.dumps(" + repr(result) + "))").encode()
    source = AssessorSnapshot("c" * 40, hashlib.sha256(data).hexdigest(), data)
    hint = dict(
        key="1154799938:123:2",
        repository_id=1154799938,
        run_id=123,
        run_attempt=2,
        head_sha="a" * 40,
        coordinate="organvm/.github",
        automatic_acceptance=False,
    )
    predicate = "python3 scripts/reviewed-assessor.py"
    packet = compile_assessment_packet(
        hint,
        source=source,
        identity=conductor,
        executor_session_id=executor.session_id,
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        predicate=predicate,
        receipt_target="git:organvm/.github:docs/receipts/assessment.json",
        work_loan=WorkLoanV1(
            source_origin="system_debt",
            horizon="present",
            budget_cost=1,
            value_case="Review dependency completion",
            owner_surface="github:organvm/.github:pull-request:26",
        ),
    )
    run = broker.submit(packet, principal=principals["conductor"])
    client = BrokerTransport(broker, principals["executor"])
    kwargs = dict(
        source=source,
        credential="fixture-explicit",
        repository="organvm/.github",
        repository_id=1154799938,
        executor=executor,
        predicate=predicate,
    )
    return client, run["run_id"], kwargs


def test_real_broker_and_child_settle_once_with_no_acceptance(callback):
    client, run_id, kwargs = callback
    result = execute_assessment_run(client, run_id, **kwargs)
    assert result["state"] == "reported"
    assert result["outcome"] == "succeeded"
    assert result["automatic_acceptance"] is False
    node = client.graph(run_id)["nodes"][0]
    assert len(node["attempts"]) == len(node["receipts"]) == 1
    assert node["attempts"][0]["status"] == "succeeded"
    receipt = node["receipts"][0]
    assert receipt["mutation_authorized"] is True
    assert json.loads(receipt["predicate"]["summary"])["automatic_acceptance"] is False
    with pytest.raises(AssessmentExecutorError):
        execute_assessment_run(client, run_id, **kwargs)
    assert len(client.graph(run_id)["nodes"][0]["attempts"]) == 1


@pytest.mark.parametrize(
    "override",
    [
        dict(repository_id=42),
        dict(repository="wrong/repository"),
        dict(predicate="unreviewed-command"),
        dict(credential=""),
        dict(executor=AgentIdentityV1(agent="codex", surface="test", session_id="wrong-session")),
    ],
)
def test_mismatched_deployment_never_starts_attempt(callback, override):
    client, run_id, kwargs = callback
    with pytest.raises(AssessmentExecutorError):
        execute_assessment_run(client, run_id, **{**kwargs, **override})
    assert not client.graph(run_id)["nodes"][0].get("attempts")


def test_lost_admission_never_executes_or_retries(callback, monkeypatch):
    client, run_id, kwargs = callback

    def forbidden(*args, **values):
        pytest.fail("ambiguous admission must not execute")

    monkeypatch.setattr("limen.conduct.assessment_executor.execute_assessor", forbidden)
    client.lose_admission = True
    for _ in range(2):
        with pytest.raises(AssessmentExecutorError, match="^assessment callback is unmeasured; no automatic retry$"):
            execute_assessment_run(client, run_id, **kwargs)
    assert len(client.graph(run_id)["nodes"][0]["attempts"]) == 1


def test_execution_failure_is_reported_as_blocked(callback, monkeypatch):
    from limen.conduct.assessor_execution import AssessorExecutionError

    client, run_id, kwargs = callback

    def fail(*args, **values):
        raise AssessorExecutionError("private source details")

    monkeypatch.setattr("limen.conduct.assessment_executor.execute_assessor", fail)
    result = execute_assessment_run(client, run_id, **kwargs)
    assert result["outcome"] == "blocked"
    assert "private" not in json.dumps(result)
    node = client.graph(run_id)["nodes"][0]
    assert node["status"] == "blocked"
    assert node["attempts"][0]["status"] == "blocked"


def test_simultaneous_callbacks_launch_exactly_once(callback, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    client, run_id, kwargs = callback
    original_graph = client.graph
    barrier = Barrier(2)
    launches = []

    def same_reserved_graph(identifier):
        result = original_graph(identifier)
        barrier.wait(timeout=5)
        return result

    def assess(*args, **values):
        launches.append(values["run_id"])
        return {"status": "REVIEW_READY", "reason": "EXACT_HEAD_ACTIONS_CI", "automatic_acceptance": False}

    monkeypatch.setattr(client, "graph", same_reserved_graph)
    monkeypatch.setattr("limen.conduct.assessment_executor.execute_assessor", assess)

    def invoke():
        try:
            return execute_assessment_run(client, run_id, **kwargs)["state"]
        except AssessmentExecutorError:
            return "unmeasured"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert sorted(results) == ["reported", "unmeasured"]
    assert launches == [123]
    node = original_graph(run_id)["nodes"][0]
    assert len(node["attempts"]) == len(node["receipts"]) == 1


def test_lost_report_response_preserves_accepted_receipt_without_reexecution(callback, monkeypatch):
    client, run_id, kwargs = callback
    original = client.report

    def lose_response(*args, **values):
        original(*args, **values)
        raise TimeoutError("private transport detail")

    monkeypatch.setattr(client, "report", lose_response)
    with pytest.raises(AssessmentExecutorError):
        execute_assessment_run(client, run_id, **kwargs)
    node = client.graph(run_id)["nodes"][0]
    assert node["status"] == "succeeded"
    assert len(node["receipts"]) == 1

    def forbidden(*args, **values):
        pytest.fail("settled callback must not relaunch")

    monkeypatch.setattr("limen.conduct.assessment_executor.execute_assessor", forbidden)
    with pytest.raises(AssessmentExecutorError):
        execute_assessment_run(client, run_id, **kwargs)


def test_callback_cli_requires_distinct_explicit_credentials(callback, tmp_path, monkeypatch):
    from click.testing import CliRunner
    from limen.conduct.cli import conduct_group

    client, run_id, kwargs = callback
    contract = dict(
        executor=kwargs["executor"].model_dump(mode="json"),
        source_commit=kwargs["source"].source_commit,
        script_sha256=kwargs["source"].script_sha256,
        repository=kwargs["repository"],
        repository_id=kwargs["repository_id"],
        predicate=kwargs["predicate"],
        broker_url="https://keeper.example.invalid",
        executor_credential_env="FIXTURE_ASSESSOR_EXECUTOR",
        read_credential_env="FIXTURE_ASSESSOR_READ",
    )
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    monkeypatch.setattr("limen.conduct.assessor_source.capture_assessor", lambda *a: kwargs["source"])

    def transport(url, token):
        assert url == contract["broker_url"]
        assert token == "fixture-executor-only"  # allow-secret: synthetic test value
        return client

    monkeypatch.setattr("limen.conduct.cli.HttpConductClient", transport)
    monkeypatch.setenv("FIXTURE_ASSESSOR_EXECUTOR", "fixture-executor-only")
    monkeypatch.setenv("GH_TOKEN", "ambient-must-not-authorize")
    arguments = [
        "execute-dependency-assessment",
        "--run-id",
        run_id,
        "--contract",
        str(path),
        "--source-repository",
        str(tmp_path),
    ]
    missing = CliRunner().invoke(conduct_group, arguments)
    assert missing.exit_code == 1
    assert not client.graph(run_id)["nodes"][0].get("attempts")
    monkeypatch.setenv("FIXTURE_ASSESSOR_READ", "fixture-read-only")
    result = CliRunner().invoke(conduct_group, arguments)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["automatic_acceptance"] is False
    assert "fixture-read-only" not in result.output
