"""Exercise the Python keeper and actual Worker completion store together."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from limen.conduct import ConductBroker, ConductorSessionV1, MemoryStateStore
from limen.conduct.assessment_executor import execute_assessment_run
from limen.conduct.assessment_packet import compile_assessment_packet
from limen.conduct.assessor_source import AssessorSnapshot
from limen.conduct.client import HttpConductClient
from limen.conduct.dependency_completion import consume_completion
from limen.conduct.models import AgentIdentityV1, ConductPrincipalV1, ExecutorAttemptV1, RunReceiptV1, WorkPacketV1
from limen.work_loan import WorkLoanV1

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = r"""
import { readFileSync } from 'node:fs';
const input = JSON.parse(readFileSync(0, 'utf8'));
const api = await import(input.module);
const data = input.state;
const storage = {
  async get(key) { return data[key]; },
  async put(key, value) { data[key] = value; },
  async transaction(fn) { return fn(storage); },
};
const conductor = { roles: ['conductor'] };
let result;
if (input.operation === 'submit') {
  result = await api.submitCompletionHint(storage,
    { roles: ['dependency_observer'], principal_id: input.policy.principal_id }, input.hint, input.policy);
} else if (input.operation === 'read') {
  result = await api.readCompletionHints(storage, conductor, input.policy);
} else {
  result = await api.reconcileCompletionAssessment(storage, conductor, input.key,
    input.run_id, async () => input.graph, input.policy);
}
process.stdout.write(JSON.stringify({ result, state: data }));
"""


class WorkerStore:
    def __init__(self):
        self.state = {}
        self.policy = json.loads((ROOT / "institutio/github/dependency-completion.json").read_text())
        # Only this isolated test object is installed. The production file stays disabled.
        self.policy["installed"] = True

    def call(self, operation, **kwargs):
        node = shutil.which("node")
        assert node, "the integration gate requires the repository-declared Node runtime"
        request = dict(
            operation=operation,
            state=self.state,
            policy=self.policy,
            module=(ROOT / "web/worker/src/conduct/dependency-completion.js").as_uri(),
            **kwargs,
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", BRIDGE],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        response = json.loads(completed.stdout)
        self.state = response["state"]
        return response["result"]


class KeeperTransport(HttpConductClient):
    def __init__(self, broker, principal, worker):
        super().__init__("https://keeper.example.invalid", "fixture-only")
        self.broker, self.principal, self.worker = broker, principal, worker
        self.submission_calls = 0

    def _request(self, method, path, payload=None):
        if path == "/api/conduct/sessions":
            return self.broker.register(ConductorSessionV1.model_validate(payload), principal=self.principal)
        if path == "/api/conduct/dependencies/completions":
            return self.worker.call("read")
        if path == "/api/conduct/runs":
            self.submission_calls += 1
            return self.broker.submit(WorkPacketV1.model_validate(payload), principal=self.principal)
        if path == "/api/conduct/dependencies/assessments":
            graph = self.broker.graph(payload["run_id"], principal=self.principal)
            return self.worker.call("reconcile", **payload, graph=graph)
        if path.endswith("/graph"):
            return self.broker.graph(path.split("/")[-2], principal=self.principal)
        lease_id = path.split("/")[-2]
        if path.endswith("/claim"):
            return self.broker.claim(lease_id, payload["generation"], principal=self.principal)
        if path.endswith("/heartbeat"):
            return self.broker.heartbeat(
                lease_id,
                payload["capability_token"],
                generation=payload["generation"],
                observed_heads=payload["observed_heads"],
                attempt=ExecutorAttemptV1.model_validate(payload["attempt"]) if "attempt" in payload else None,
                principal=self.principal,
            )
        if path.endswith("/receipt"):
            return self.broker.report(
                lease_id,
                payload["capability_token"],
                RunReceiptV1.model_validate(payload["receipt"]),
                generation=payload["generation"],
                principal=self.principal,
            )
        raise AssertionError("unexpected protocol route")


@pytest.mark.parametrize("protected_executor", [False, True])
def test_registered_executor_handoff_settles_actual_worker_hint_once(protected_executor):
    broker = ConductBroker(MemoryStateStore())
    worker = WorkerStore()
    clients, identities = {}, {}
    for role, capabilities in [("conductor", {"conduct"}), ("executor", {"dependency-assessment"})]:
        identity = AgentIdentityV1(agent="codex", surface="test", session_id="integration-" + role)
        principal = ConductPrincipalV1(
            principal_id="integration-" + role, agent="codex", surface="test", roles=frozenset({"observer", role})
        )
        client = KeeperTransport(broker, principal, worker)
        registered = client.register(
            ConductorSessionV1(
                session_id=identity.session_id,
                identity=identity,
                origin="direct" if role == "conductor" or protected_executor else "relay",
                human_protected=role == "conductor" or protected_executor,
                native_session_id="fixture-native-" + role,
                concurrency=1,
                capabilities=frozenset(capabilities),
            )
        )
        assert registered["identity"] == identity.model_dump(mode="json")
        clients[role], identities[role] = client, identity
    hint = dict(repository_id=1154799938, run_id=123, run_attempt=2, head_sha="a" * 40)
    published = worker.call("submit", hint=hint)
    assert published["automatic_acceptance"] is False
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
    predicate = "limen conduct execute-dependency-assessment"
    packet = compile_assessment_packet(
        published,
        source=source,
        identity=identities["conductor"],
        executor_session_id=identities["executor"].session_id,
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        predicate=predicate,
        receipt_target="git:organvm/.github:docs/receipts/assessment.json",
        work_loan=WorkLoanV1(
            source_origin="system_debt",
            horizon="present",
            budget_cost=1,
            value_case="Assess one completion",
            owner_surface="github:organvm/.github:pull-request:26",
        ),
    )
    pending = consume_completion(clients["conductor"], published["key"], packet)
    if protected_executor:
        assert pending["state"] == "submission_unmeasured"
        assert "run_id" not in pending
        assert "broker_assessment" not in worker.call("read")["hints"][0]
        return
    assert pending["assessment"]["status"] == "unmeasured"
    assert clients["conductor"].submission_calls == 1
    run_id = pending["run_id"]
    graph = clients["executor"].graph(run_id)
    assert graph["nodes"][0]["status"] == "reserved"
    assert graph["nodes"][0]["attempts"] == []
    callback = execute_assessment_run(
        clients["executor"],
        run_id,
        source=source,
        credential="fixture-read-only",
        repository="organvm/.github",
        repository_id=1154799938,
        executor=identities["executor"],
        predicate=predicate,
    )
    assert callback["state"] == "reported"
    reconciled = consume_completion(clients["conductor"], published["key"], packet)
    assert reconciled["assessment"]["status"] == "reported"
    assert reconciled["assessment"]["outcome"] == "succeeded"
    assert reconciled["assessment"]["receipt_id"] == callback["receipt_id"]
    assert reconciled["automatic_acceptance"] is False
    # A new reader/consumer retains the same keeper run and terminal observation.
    restarted = KeeperTransport(broker, clients["conductor"].principal, worker)
    assert consume_completion(restarted, published["key"], packet)["assessment"] == reconciled["assessment"]
    assert restarted.submission_calls == 0
    assert worker.call("submit", hint=hint)["duplicate"] is True
    assert len(worker.call("read")["hints"]) == 1
    assert len(clients["executor"].graph(run_id)["nodes"][0]["attempts"]) == 1
