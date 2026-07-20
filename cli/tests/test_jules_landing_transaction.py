from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

import limen.jules_landing_custody as custody  # noqa: E402
import limen.jules_landing_transaction as transaction  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import (  # noqa: E402
    DispatchLogEntry,
    LimenFile,
    Task,
    dispatch_agent,
    dispatch_session_id,
)
from limen.tabularius import apply_limen_file_sync  # noqa: E402


def load_jules_land():
    return transaction


def test_named_older_session_pr_after_new_dispatch_does_not_claim_new_session() -> None:
    module = load_jules_land()
    now = datetime.now(timezone.utc)
    task = Task(
        id="T-ORDERED-SESSIONS",
        title="two completed sessions",
        repo="organvm/example",
        target_agent="jules",
        status="failed",
        created=date(2026, 7, 17),
        dispatch_log=[
            DispatchLogEntry(
                timestamp=now,
                agent="jules",
                session_id="123",
                status="dispatched",
            ),
            DispatchLogEntry(
                timestamp=now,
                agent="jules",
                session_id="456",
                status="dispatched",
            ),
            DispatchLogEntry(
                timestamp=now,
                agent="jules",
                session_id="https://github.com/organvm/example/pull/42",
                status="done",
                output="jules-land: landed session 123 as PR",
            ),
        ],
    )

    assert module.session_has_pr(task, "123") is True
    assert module.session_has_pr(task, "456") is False


def test_transaction_preserves_unrelated_concurrent_board_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-LAND",
                    title="land selected session",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                ),
                Task(
                    id="T-OTHER",
                    title="unrelated owner",
                    repo="organvm/other",
                    target_agent="codex",
                    status="open",
                    created=date(2026, 7, 17),
                ),
            ]
        ),
    )

    def land_with_concurrent_write(_task, _sid, _apply, **_kwargs):
        with module.queue_lock(tasks_path, timeout=1) as got:
            assert got
            before = load_limen_file(tasks_path)
            desired = before.model_copy(deep=True)
            other = next(task for task in desired.tasks if task.id == "T-OTHER")
            other.context = "concurrent owner write"
            result = apply_limen_file_sync(
                tasks_path,
                desired,
                agent="codex",
                session_id="concurrent-owner-write",
                before=before,
            )
            assert result.applied == 1
        return "LANDED T-LAND -> https://github.com/organvm/example/pull/50 ; retained"

    monkeypatch.setattr(module, "land_one", land_with_concurrent_write)

    assert (
        module.process_session(
            tasks_path,
            "T-LAND",
            "123",
            apply=True,
            recover=False,
        )
        is True
    )
    tasks = {task.id: task for task in load_limen_file(tasks_path).tasks}
    assert tasks["T-LAND"].status == "done"
    landed = tasks["T-LAND"].dispatch_log[-1]
    assert landed.agent == "jules"
    assert dispatch_agent(landed) == "jules"
    assert dispatch_session_id(landed) == "https://github.com/organvm/example/pull/50"
    assert tasks["T-OTHER"].context == "concurrent owner write"


def test_transaction_fences_same_id_changed_owner_and_session(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-CHANGED",
                    title="selected old session",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )

    def land_after_claim_changes(_task, _sid, _apply, **_kwargs):
        with module.queue_lock(tasks_path, timeout=1) as got:
            assert got
            before = load_limen_file(tasks_path)
            desired = before.model_copy(deep=True)
            changed = desired.tasks[0]
            changed.target_agent = "codex"
            changed.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=datetime.now(timezone.utc),
                    agent="codex",
                    session_id="456",
                    status="dispatched",
                    output="new owner/session won while old PR work ran",
                )
            )
            result = apply_limen_file_sync(
                tasks_path,
                desired,
                agent="codex",
                session_id="456",
                before=before,
            )
            assert result.applied == 1
        return "LANDED T-CHANGED -> https://github.com/organvm/example/pull/51 ; retained"

    monkeypatch.setattr(module, "land_one", land_after_claim_changes)

    assert (
        module.process_session(
            tasks_path,
            "T-CHANGED",
            "123",
            apply=True,
            recover=False,
        )
        is False
    )
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "dispatched"
    assert task.target_agent == "codex"
    assert dispatch_session_id(task.dispatch_log[-1]) == "456"
    assert all("/pull/51" not in dispatch_session_id(entry) for entry in task.dispatch_log)
    assert "FENCE T-CHANGED" in capsys.readouterr().out


def test_process_session_lands_current_jules_claim_targeted_at_any(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-ANY",
                    title="Jules claimed a provider-neutral task",
                    repo="organvm/example",
                    target_agent="any",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )
    monkeypatch.setattr(
        module,
        "land_one",
        lambda *_args, **_kwargs: "LANDED T-ANY -> https://github.com/organvm/example/pull/59 ; retained",
    )

    assert (
        module.process_session(
            tasks_path,
            "T-ANY",
            "123",
            apply=True,
            recover=False,
        )
        is True
    )

    task = load_limen_file(tasks_path).tasks[0]
    assert task.target_agent == "any"
    assert task.status == "done"
    assert module.JULES_LANDING_HOLD_LABEL not in task.labels
    assert dispatch_session_id(task.dispatch_log[-1]) == "https://github.com/organvm/example/pull/59"
    rerouted = task.model_copy(update={"target_agent": "codex"})
    assert module._jules_claim_is_current(rerouted, "123") is False


def test_process_session_serializes_concurrent_landings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-CONCURRENT",
                    title="one external mutation",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )
    first_external = threading.Event()
    release_external = threading.Event()
    calls: list[str] = []

    def fake_land(_task, sid, _apply, **_kwargs):
        calls.append(sid)
        first_external.set()
        assert release_external.wait(timeout=5)
        return "LANDED T-CONCURRENT -> https://github.com/organvm/example/pull/60 ; retained"

    monkeypatch.setattr(module, "land_one", fake_land)
    results: list[bool] = []

    def run() -> None:
        results.append(
            module.process_session(
                tasks_path,
                "T-CONCURRENT",
                "123",
                apply=True,
                recover=False,
                lock_timeout_seconds=1,
            )
        )

    first = threading.Thread(target=run, name="first-landing")
    first.start()
    assert first_external.wait(timeout=5)
    started = time.monotonic()
    second_result = module.process_session(
        tasks_path,
        "T-CONCURRENT",
        "123",
        apply=True,
        recover=False,
        lock_timeout_seconds=0.05,
    )
    elapsed = time.monotonic() - started
    assert second_result is False
    assert elapsed < 0.5
    release_external.set()
    first.join(timeout=5)

    assert not first.is_alive()
    assert results == [True]
    assert calls == ["123"]
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "done"
    assert sum("/pull/60" in dispatch_session_id(entry) for entry in task.dispatch_log) == 1


def test_post_pr_receipt_failure_retries_by_adopting_existing_pr(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    repo = tmp_path / "repo"
    repo.mkdir()
    custody.WT_ROOT = tmp_path / "worktrees"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-ADOPT",
                    title="adopt after receipt failure",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )
    state = {
        "pulled": False,
        "committed": False,
        "remote": False,
        "pr": False,
        "creates": 0,
    }

    def fake_git(args, cwd, timeout=30):
        if args[:2] == ["ls-remote", "--exit-code"]:
            return subprocess.CompletedProcess(
                args,
                0 if state["remote"] else 2,
                "",
                "",
            )
        if args[:2] == ["show-ref", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:2] == ["worktree", "add"]:
            Path(args[4]).mkdir(parents=True, exist_ok=True)
        elif args == ["status", "--porcelain"]:
            dirty = state["pulled"] and not state["committed"]
            return subprocess.CompletedProcess(
                args,
                0,
                " M patch.py\n" if dirty else "",
                "",
            )
        elif args == ["diff", "--cached", "--quiet"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        elif args[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "commit\n" if state["committed"] else "base\n",
                "",
            )
        elif args[-2:] == ["rev-parse", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "base\n", "")
        elif "commit" in args:
            state["committed"] = True
        elif args[:2] == ["push", "-u"]:
            state["remote"] = True
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        if args[:3] == [custody.JULES, "remote", "pull"]:
            state["pulled"] = True
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "commit\n", "")
        if args[:3] == ["gh", "pr", "list"]:
            rows = (
                [
                    {
                        "url": "https://github.com/organvm/example/pull/61",
                        "state": "OPEN",
                        "mergedAt": None,
                        "headRefName": custody.landing_branch(
                            "T-ADOPT",
                            "123",
                        ),
                        "headRefOid": "commit",
                        "headRepositoryOwner": {"login": "organvm"},
                    }
                ]
                if state["pr"]
                else []
            )
            return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")
        if args[:3] == ["gh", "pr", "create"]:
            state["creates"] += 1
            state["pr"] = True
            return subprocess.CompletedProcess(
                args,
                0,
                "https://github.com/organvm/example/pull/61\n",
                "",
            )
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(custody, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(custody, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(custody, "_git", fake_git)
    monkeypatch.setattr(custody.subprocess, "run", fake_run)
    real_commit = module.commit_landing_receipt
    commit_attempts = 0

    def fail_first_receipt(*args, **kwargs):
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 1:
            return False
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(module, "commit_landing_receipt", fail_first_receipt)

    assert (
        module.process_session(
            tasks_path,
            "T-ADOPT",
            "123",
            apply=True,
            recover=False,
        )
        is False
    )
    after_failure = load_limen_file(tasks_path).tasks[0]
    assert after_failure.status == "dispatched"
    assert dispatch_session_id(after_failure.dispatch_log[-1]).startswith("jules-land-intent:")
    assert module.JULES_LANDING_HOLD_LABEL in after_failure.labels

    assert (
        module.process_session(
            tasks_path,
            "T-ADOPT",
            "123",
            apply=True,
            recover=False,
        )
        is True
    )
    assert state["creates"] == 1
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "done"
    assert module.JULES_LANDING_HOLD_LABEL not in task.labels
    assert dispatch_session_id(task.dispatch_log[-1]) == "https://github.com/organvm/example/pull/61"


@pytest.mark.parametrize(
    ("status", "recover"),
    [("failed", False), ("done", True), ("dispatched", False)],
)
def test_landing_intent_preserves_lifecycle_status(
    status: str,
    recover: bool,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-HOLD",
                    title="preserve lifecycle",
                    repo="organvm/example",
                    target_agent="jules",
                    status=status,
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status=status,
                        )
                    ],
                )
            ]
        ),
    )

    plan, note = module.prepare_landing_intent(
        tasks_path,
        "T-HOLD",
        "123",
        apply=True,
        recover=recover,
    )

    assert note == ""
    assert plan is not None
    held = load_limen_file(tasks_path).tasks[0]
    assert held.status == status
    assert module.JULES_LANDING_HOLD_LABEL in held.labels
    assert held.dispatch_log[-1].status == status
    assert getattr(held.dispatch_log[-1], "landing_event") == "intent"


@pytest.mark.parametrize(
    ("message", "expected_status", "outcome"),
    [
        ("no-op T-FIXED: Jules produced no diff", "failed", "noop"),
        (
            "BLOCKED T-FIXED: retained worktree is ambiguous",
            "failed_blocked",
            "blocked",
        ),
    ],
)
def test_terminal_non_pr_outcome_is_a_rerun_fixed_point(
    message: str,
    expected_status: str,
    outcome: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-FIXED",
                    title="terminal landing outcome",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )
    calls = 0

    def fake_land(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return message

    monkeypatch.setattr(module, "land_one", fake_land)

    assert (
        module.process_session(
            tasks_path,
            "T-FIXED",
            "123",
            apply=True,
            recover=False,
        )
        is False
    )
    assert (
        module.process_session(
            tasks_path,
            "T-FIXED",
            "123",
            apply=True,
            recover=False,
        )
        is False
    )

    assert calls == 1
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == expected_status
    assert module.JULES_LANDING_HOLD_LABEL not in task.labels
    assert getattr(task.dispatch_log[-1], "landing_terminal") is True
    assert getattr(task.dispatch_log[-1], "landing_outcome") == outcome


def test_transient_failures_reach_finite_terminal_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    monkeypatch.setattr(module, "LANDING_RETRY_LIMIT", 2)
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-RETRY",
                    title="bounded retries",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        )
                    ],
                )
            ]
        ),
    )
    calls = 0

    def fail(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "FAIL T-RETRY: transient provider error"

    monkeypatch.setattr(module, "land_one", fail)

    for _ in range(3):
        assert (
            module.process_session(
                tasks_path,
                "T-RETRY",
                "123",
                apply=True,
                recover=False,
            )
            is False
        )

    assert calls == 2
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "failed"
    assert module.JULES_LANDING_HOLD_LABEL not in task.labels
    attempts = [entry for entry in task.dispatch_log if getattr(entry, "landing_event", None) == "attempt"]
    assert [getattr(entry, "landing_attempt") for entry in attempts] == [1, 2]
    assert getattr(task.dispatch_log[-1], "landing_outcome") == "failed"
    assert getattr(task.dispatch_log[-1], "landing_attempt_count") == 2
