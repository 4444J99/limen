"""Bounded consumption delegates idempotency and acceptance to the keeper."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from limen.conduct.client import HttpConductClient
from limen.conduct.dependency_completion import CompletionContractError, consume_completion
from limen.conduct.models import WorkPacketV1

HEAD = "a" * 40
KEY = "1154799938:10:1"
HINT = {
    "key": KEY,
    "repository_id": 1154799938,
    "run_id": 10,
    "run_attempt": 1,
    "head_sha": HEAD,
    "coordinate": "organvm/.github",
    "automatic_acceptance": False,
}


def packet():
    identity = {"agent": "codex", "surface": "cli", "session_id": "completion-test"}
    return WorkPacketV1.model_validate(
        {
            "work_id": "completion-test",
            "work_key": f"dependency-completion:{KEY}:{HEAD}",
            "intent": {
                "dependency_completion": {
                    key: HINT[key] for key in ("repository_id", "run_id", "run_attempt", "head_sha")
                }
            },
            "execution": {"command": "trusted-assessor", "observed_heads": {"dependency_head": HEAD}},
            "initiator": identity,
            "conductor": identity,
            "predicate": "trusted-assessor",
            "receipt_target": "github:organvm/.github:pull-request:26",
            "effect": "read",
            "authority": {"repositories": ["organvm/.github"], "may_delegate": False},
            "deadline": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
    )


class KeeperFixture(HttpConductClient):
    def __init__(self):
        super().__init__("https://keeper.example", "fixture-only-token")
        self.hint = deepcopy(HINT)
        self.calls = []
        self.runs = {}
        self.reservations = 0
        self.lose_submit_response = False
        self.fail_reconcile = False

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET":
            return {
                "schema": "limen.dependency_completion_hints.v1",
                "automatic_acceptance": False,
                "hints": [deepcopy(self.hint)],
            }
        if path == "/api/conduct/runs":
            work_key = payload["work_key"]
            if work_key not in self.runs:
                self.runs[work_key] = "assessment-1"
                self.reservations += 1
            if self.lose_submit_response:
                self.lose_submit_response = False
                raise TimeoutError("private provider text")
            return {"run_id": self.runs[work_key]}
        if path == "/api/conduct/dependencies/assessments":
            if self.fail_reconcile:
                raise TimeoutError("private provider text")
            assert set(payload) == {"key", "run_id"}
            self.hint["broker_assessment"] = {
                "run_id": payload["run_id"],
                "status": "unmeasured",
                "automatic_acceptance": False,
            }
            return self.hint["broker_assessment"]
        raise AssertionError(path)


def test_one_submit_then_restart_reads_existing_binding_without_new_reservation():
    client = KeeperFixture()
    work = packet()
    result = consume_completion(client, KEY, work)
    assert result["state"] == "assessment_observed"
    assert result["automatic_acceptance"] is False
    assert client.reservations == 1
    before = len(client.calls)
    consume_completion(client, KEY, work)
    assert len(client.calls) - before == 2
    assert client.reservations == 1
    assert not any(path == "/api/conduct/runs" for _, path, _ in client.calls[before:])


def test_lost_submit_response_does_not_retry_and_later_identical_packet_recovers():
    client = KeeperFixture()
    work = packet()
    client.lose_submit_response = True
    result = consume_completion(client, KEY, work)
    assert result["state"] == "submission_unmeasured"
    assert len(client.calls) == 2
    assert "private" not in str(result)
    assert client.reservations == 1
    assert consume_completion(client, KEY, work)["state"] == "assessment_observed"
    assert client.reservations == 1


def test_reconciliation_failure_preserves_known_run_without_polling():
    client = KeeperFixture()
    client.fail_reconcile = True
    result = consume_completion(client, KEY, packet())
    assert result["state"] == "reconciliation_unmeasured"
    assert result["run_id"] == "assessment-1"
    assert len(client.calls) == 3


@pytest.mark.parametrize(
    "change",
    [
        {"effect": "write"},
        {"work_key": "unrelated"},
        {"intent": {"dependency_completion": {}}},
        {"execution": {"observed_heads": {"dependency_head": "b" * 40}}},
    ],
)
def test_wrong_contract_never_submits(change):
    client = KeeperFixture()
    work = packet().model_copy(update=change)
    assert consume_completion(client, KEY, work)["state"] == "unmeasured"
    assert len(client.calls) == 1
    assert client.reservations == 0


def test_local_adapter_is_not_a_fallback():
    with pytest.raises(CompletionContractError):
        consume_completion(object(), KEY, packet())


def test_publisher_and_reconciler_transport_do_not_accept_caller_receipts(monkeypatch):
    client = HttpConductClient("https://keeper.example", "fixture-only-token")
    calls = []
    monkeypatch.setattr(client, "_request", lambda *args: calls.append(args) or {})
    client.publish_dependency_completion_hint(HINT)
    client.reconcile_dependency_assessment(KEY, "assessment-1")
    assert calls == [
        ("POST", "/api/conduct/dependencies/completions", HINT),
        ("POST", "/api/conduct/dependencies/assessments", {"key": KEY, "run_id": "assessment-1"}),
    ]


def test_cli_submits_once_and_reports_pending_as_unmeasured(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from limen.conduct.cli import conduct_group

    client = KeeperFixture()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)

    def bounded(endpoint, token):
        assert endpoint == client.endpoint and token == client.token  # allow-secret: runtime fixture comparison
        return client

    monkeypatch.setattr("limen.conduct.assessment_transport.AssessmentHttpClient", bounded)
    path = tmp_path / "packet.json"
    path.write_text(packet().model_dump_json())
    result = CliRunner().invoke(conduct_group, ["consume-dependency-completion", "--key", KEY, "--packet", str(path)])
    assert result.exit_code == 77
    assert client.reservations == 1
    assert '"automatic_acceptance": false' in result.output
