from copy import deepcopy
from datetime import date, datetime, timezone

import pytest

from limen.models import Task
from limen.stale_claims import stale_claim_holds


NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def task(identity="stale", agent="any"):
    return Task(id=identity, title="Fixture", target_agent=agent, status="in_progress", created=date(2026, 1, 1))


class Broker:
    def __init__(self):
        self.calls = []
        self.capability = {
            "schema_version": "limen.conduct_capabilities.v1",
            "generated_at": NOW.isoformat(),
            "sessions": [{"session_id": "owner", "healthy": False, "human_protected": False}],
        }
        self.current = {"found": True, "task_id": "stale", "run_id": "run", "root_run_id": "run", "status": "failed"}
        self.current["schema_version"] = "limen.conduct_task_run.v1"
        self.node = {
            "run_id": "run",
            "packet": {"task_id": "stale"},
            "status": "failed",
            "conductor_session_id": "owner",
            "executor_session_id": "owner",
            "lease": {"state": "released", "run_id": "run", "executor": {"session_id": "owner", "agent": "codex"}},
        }

    def capabilities(self):
        self.calls.append("capabilities")
        return deepcopy(self.capability)

    def task_run(self, identity):
        self.calls.append(identity)
        return deepcopy(self.current)

    def graph(self, identity):
        self.calls.append("graph")
        return {"nodes": [deepcopy(self.node)]}


def test_terminal_run_with_inactive_unprotected_owners_allows_provider_routing():
    broker = Broker()
    agents = {}
    assert stale_claim_holds([task()], client=broker, now=NOW, resolved_agents=agents) == {"stale": None}
    assert agents == {"stale": "codex"}


@pytest.mark.parametrize(
    "field,reason", [("healthy", "conduct_owner_active"), ("human_protected", "conduct_human_protected")]
)
def test_live_or_protected_owner_holds_even_terminal_claim(field, reason):
    broker = Broker()
    broker.capability["sessions"][0][field] = True
    assert stale_claim_holds([task()], client=broker, now=NOW) == {"stale": reason}


def test_active_run_is_not_released_from_old_projection_age():
    broker = Broker()
    broker.current["status"] = broker.node["status"] = "running"
    broker.node["lease"]["state"] = "active"
    assert stale_claim_holds([task()], client=broker, now=NOW) == {"stale": "conduct_run_active"}


@pytest.mark.parametrize(
    "malformation",
    [
        "missing_owner",
        "unknown_protection",
        "stale_catalog",
        "missing_run",
        "wrong_task",
        "graph_failure",
        "duplicate_session",
    ],
)
def test_incomplete_broker_evidence_never_permits_release(malformation):
    broker = Broker()
    if malformation == "missing_owner":
        broker.capability["sessions"] = []
    elif malformation == "unknown_protection":
        del broker.capability["sessions"][0]["human_protected"]
    elif malformation == "stale_catalog":
        broker.capability["generated_at"] = "2026-01-01T00:00:00+00:00"
    elif malformation == "missing_run":
        broker.current["found"] = False
    elif malformation == "wrong_task":
        broker.node["packet"]["task_id"] = "other"
    elif malformation == "graph_failure":
        broker.graph = lambda _: (_ for _ in ()).throw(OSError("offline"))
    elif malformation == "duplicate_session":
        broker.capability["sessions"] *= 2
    assert stale_claim_holds([task()], client=broker, now=NOW) == {"stale": "conduct_unmeasured"}


def test_shared_deadline_stops_further_queries():
    broker = Broker()
    ticks = iter([0, 21])
    assert stale_claim_holds([task(), task("second")], client=broker, clock=lambda: next(ticks), now=NOW) == {
        "stale": "conduct_unmeasured",
        "second": "conduct_unmeasured",
    }
    assert broker.calls == ["capabilities"]


def test_broker_outage_is_one_read_not_per_task():
    broker = Broker()

    def unavailable():
        broker.calls.append("unavailable")
        raise OSError("offline")

    broker.capabilities = unavailable
    assert set(stale_claim_holds([task(), task("second")], client=broker, now=NOW).values()) == {"conduct_unmeasured"}
    assert broker.calls == ["unavailable"]


@pytest.mark.parametrize("protected", [True, False])
def test_release_apply_holds_without_any_transition(tmp_path, monkeypatch, protected):
    import limen.dispatch as dispatch
    from limen.io import save_limen_file
    from limen.models import LimenFile, Portal

    broker = Broker()
    broker.capability["sessions"][0]["human_protected"] = protected
    if not protected:
        broker.current["found"] = False
    board = LimenFile(portal=Portal(), tasks=[task()])
    path = tmp_path / "tasks.yaml"
    save_limen_file(path, board)
    before = path.read_bytes()
    monkeypatch.setattr(
        dispatch,
        "stale_claim_holds",
        lambda tasks, **kwargs: stale_claim_holds(tasks, client=broker, now=NOW, **kwargs),
    )
    monkeypatch.setattr(
        dispatch, "apply_limen_file_sync", lambda *_args, **_kwargs: pytest.fail("held claim cannot transition")
    )
    report = dispatch.release_stale_tasks(board, path, dry_run=False)
    assert report["held"] == ["stale"]
    assert report["released"] == []
    assert path.read_bytes() == before


def test_any_target_resolves_jules_before_provider_absence_check(tmp_path, monkeypatch):
    import limen.dispatch as dispatch
    from limen.io import save_limen_file
    from limen.jules_remote import JulesRemoteSnapshot
    from limen.models import LimenFile, Portal

    broker = Broker()
    broker.node["lease"]["executor"]["agent"] = "jules"
    board = LimenFile(portal=Portal(), tasks=[task()])
    path = tmp_path / "tasks.yaml"
    save_limen_file(path, board)
    before = path.read_bytes()
    monkeypatch.setattr(
        dispatch,
        "stale_claim_holds",
        lambda tasks, **kwargs: stale_claim_holds(tasks, client=broker, now=NOW, **kwargs),
    )
    report = dispatch.release_stale_tasks(
        board, path, dry_run=True, jules_snapshot=JulesRemoteSnapshot(available=False, sessions={})
    )
    assert report["held"] == ["stale"]
    assert report["released"] == []
    assert report["remote_probe"]["status"] == "unavailable"
    assert report["candidates"][0]["target_agent"] == "any"
    assert report["candidates"][0]["executor_agent"] == "jules"
    assert path.read_bytes() == before


@pytest.mark.parametrize("payload", [None, {}, {"tasks": []}, {"tasks": [{"id": "stale", "status": "failed"}]}])
def test_unavailable_or_incomplete_canonical_read_never_falls_back_to_local(tmp_path, monkeypatch, payload):
    from contextlib import contextmanager

    import limen.dispatch as dispatch
    from limen.io import save_limen_file
    from limen.models import LimenFile, Portal

    broker = Broker()
    board = LimenFile(portal=Portal(), tasks=[task()])
    path = tmp_path / "tasks.yaml"
    save_limen_file(path, board)
    before = path.read_bytes()
    inside_lock = False
    reads_outside_lock = []

    @contextmanager
    def queue_lock(_path):
        nonlocal inside_lock
        inside_lock = True
        try:
            yield True
        finally:
            inside_lock = False

    class Canonical:
        def private_board(self):
            reads_outside_lock.append(not inside_lock)
            if payload is None:
                raise OSError("unavailable")
            return payload

    monkeypatch.setattr(dispatch, "client_from_env", Canonical)
    monkeypatch.setattr(dispatch, "_queue_lock", queue_lock)
    monkeypatch.setattr(
        dispatch,
        "stale_claim_holds",
        lambda tasks, **kwargs: stale_claim_holds(tasks, client=broker, now=NOW, **kwargs),
    )
    monkeypatch.setattr(
        dispatch,
        "apply_limen_file_sync",
        lambda *_args, **_kwargs: pytest.fail("unknown canonical state cannot transition"),
    )
    report = dispatch.release_stale_tasks(board, path, dry_run=False)
    assert report["held"] == ["stale"]
    assert report["candidates"][0]["remote_status"] == "conduct_canonical_unmeasured"
    assert reads_outside_lock == [True]
    assert path.read_bytes() == before


def test_interrupted_relist_still_requires_jules_absence(tmp_path, monkeypatch):
    import limen.dispatch as dispatch
    from limen.io import save_limen_file
    from limen.jules_remote import JulesRemoteSnapshot
    from limen.models import LimenFile, Portal

    broker = Broker()
    broker.node["lease"]["executor"]["agent"] = "jules"
    board = LimenFile(portal=Portal(), tasks=[task()])
    path = tmp_path / "tasks.yaml"
    save_limen_file(path, board)

    class Canonical:
        def private_board(self):
            return {"tasks": [task().model_copy(update={"status": "failed"}).model_dump(mode="json")]}

    monkeypatch.setattr(dispatch, "client_from_env", Canonical)
    monkeypatch.setattr(
        dispatch,
        "stale_claim_holds",
        lambda tasks, **kwargs: stale_claim_holds(tasks, client=broker, now=NOW, **kwargs),
    )
    monkeypatch.setattr(
        dispatch, "apply_limen_file_sync", lambda *_args, **_kwargs: pytest.fail("relist cannot bypass absence")
    )
    report = dispatch.release_stale_tasks(
        board, path, dry_run=False, jules_snapshot=JulesRemoteSnapshot(available=False, sessions={})
    )
    assert report["held"] == ["stale"]
    assert report["released"] == []


def test_claim_appearing_after_broker_snapshot_is_held(tmp_path, monkeypatch):
    import limen.dispatch as dispatch
    from limen.io import save_limen_file
    from limen.models import LimenFile, Portal

    broker = Broker()
    broker.capability["sessions"][0]["human_protected"] = True
    initial = LimenFile(portal=Portal(), tasks=[task()])
    fresh = LimenFile(portal=Portal(), tasks=[task(), task("new-claim")])
    path = tmp_path / "tasks.yaml"
    save_limen_file(path, fresh)
    before = path.read_bytes()
    monkeypatch.setattr(
        dispatch,
        "stale_claim_holds",
        lambda tasks, **kwargs: stale_claim_holds(tasks, client=broker, now=NOW, **kwargs),
    )
    monkeypatch.setattr(
        dispatch, "apply_limen_file_sync", lambda *_args, **_kwargs: pytest.fail("unobserved claim cannot transition")
    )
    report = dispatch.release_stale_tasks(initial, path, dry_run=False)
    assert report["held"] == ["stale", "new-claim"]
    assert report["released"] == []
    assert path.read_bytes() == before
