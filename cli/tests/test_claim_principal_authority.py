"""Credential principal binding never silently changes a selected executor."""

import pytest

import limen.tabularius as tabularius
from limen.io import load_limen_file
from test_dispatch_claim_identity import _reservation
from test_tabularius import FakeConductClient, _task, _ticket


@pytest.mark.parametrize("target", ["jules", "any"])
def test_selected_executor_must_match_authenticated_registration_before_submit(target):
    base = _task("SELECTED", status="open", target_agent=target)
    remote = FakeConductClient([base], bound_agent="codex", bound_surface="credential-principal")
    ticket = _ticket(
        tabularius.INTENT_STATUS,
        task_id="SELECTED",
        agent="jules",
        patch={"status": "dispatched"},
        log={"agent": "jules", "status": "dispatched"},
    )
    with pytest.raises(tabularius.SelectedExecutorAuthorityUnavailable) as error:
        tabularius._relay_ticket(ticket, base, client=remote)
    assert error.value.status == 403
    assert error.value.reason_code == "selected_executor_authority_unavailable"
    assert remote.packets == []
    assert remote.tasks["SELECTED"] == base


def test_mixed_batch_authenticates_every_executor_before_any_task_submission(tmp_path, monkeypatch):
    path, desired = _reservation(tmp_path)
    original = path.read_bytes()
    tasks = [task.model_dump(mode="json", exclude_none=True) for task in load_limen_file(path).tasks]
    remote = FakeConductClient(tasks, bound_agent="codex", bound_surface="credential-principal")
    monkeypatch.setattr(tabularius, "client_from_env", lambda: remote)
    with pytest.raises(tabularius.SelectedExecutorAuthorityUnavailable):
        tabularius.apply_limen_file_sync(
            path, desired, agent="dispatch-parallel", claim_agents={"A": "codex", "B": "jules"}
        )
    assert len(remote.registered) == 2
    assert remote.packets == []
    assert all(task["status"] == "open" for task in remote.tasks.values())
    assert path.read_bytes() == original


def test_same_principal_claim_preserves_authenticated_actor_identity():
    base = _task("SELECTED", status="open")
    remote = FakeConductClient([base], bound_agent="codex", bound_surface="credential-principal")
    ticket = _ticket(tabularius.INTENT_STATUS, task_id="SELECTED", agent="codex", patch={"status": "dispatched"})
    result = tabularius._relay_ticket(ticket, base, client=remote)
    assert result["status"] == "dispatched"
    assert remote.packets[0].conductor.agent == "codex"
    assert remote.packets[0].conductor.surface == "credential-principal"


def test_captured_open_claim_preserves_exact_precondition_during_replay():
    base = _task("CAPTURED", status="open")
    ticket = _ticket(
        tabularius.INTENT_UPSERT,
        task_id="CAPTURED",
        patch={**base, "status": "dispatched"},
        precondition={"task_sha256": tabularius.task_state_sha256(base)},
    ).model_copy(update={"canonical_base": base})
    intent = tabularius._compatibility_intent(ticket, {**base, "status": "done", "updated": "2099-01-01"})
    assert intent["kind"] == "task.claim"
    assert intent["expected_status"] == "open"
    assert intent["expected_revision"] == base["created"]


@pytest.mark.parametrize("malformation", ["metadata", "status-intent", "wrong-hash"])
def test_captured_open_state_cannot_authorize_an_unrelated_transition(malformation):
    base = _task("CAPTURED", status="open")
    ticket = _ticket(
        tabularius.INTENT_UPSERT,
        task_id="CAPTURED",
        patch={**base, "status": "open" if malformation == "metadata" else "dispatched"},
        precondition={"task_sha256": "f" * 64 if malformation == "wrong-hash" else tabularius.task_state_sha256(base)},
    ).model_copy(update={"canonical_base": base})
    if malformation == "status-intent":
        ticket = ticket.model_copy(update={"intent": tabularius.INTENT_STATUS})
    with pytest.raises(ValueError, match="captured canonical claim"):
        tabularius._compatibility_intent(ticket, base)
