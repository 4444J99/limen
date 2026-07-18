import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.jules_remote import JulesRemoteSession, JulesRemoteSnapshot  # noqa: E402
from limen.models import (  # noqa: E402
    JULES_LANDING_HOLD_LABEL,
    Budget,
    BudgetTrack,
    DispatchLogEntry,
    LimenFile,
    Portal,
    Task,
)
from limen.workstream_contract import packet_contract  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "recover.py"
SID = "12345678901234567890"


def _load_recover(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_dispatched_claim(tasks_path: Path, *, target_agent: str = "jules") -> None:
    now = dt.datetime.now(dt.timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
            tasks=[
                Task(
                    id="STALE-CLAIM",
                    title="stale claim",
                    repo="organvm/example",
                    target_agent=target_agent,
                    status="dispatched",
                    created=now.date(),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent=target_agent,
                            session_id=SID if target_agent == "jules" else "local-session",
                            status="dispatched",
                        )
                    ],
                )
            ],
        ),
    )


def _run_recover_with_snapshot(tasks_path: Path, monkeypatch, snapshot: JulesRemoteSnapshot):
    module = _load_recover(f"recover_uut_{id(snapshot)}")
    monkeypatch.setattr(module, "live_jules_sessions", lambda _session_ids=(): snapshot)
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])
    assert module.main() == 0
    return load_limen_file(tasks_path).tasks[0]


def test_recover_holds_non_exhaustive_catalog_miss(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    _write_dispatched_claim(tasks_path)
    other_sid = "99999999999999999999"
    snapshot = JulesRemoteSnapshot(
        available=True,
        sessions={other_sid: JulesRemoteSession(other_sid, "completed")},
        exhaustive=False,
    )

    task = _run_recover_with_snapshot(tasks_path, monkeypatch, snapshot)

    assert task.status == "dispatched"
    assert task.target_agent == "jules"


def test_recover_holds_present_unknown_and_completed_sessions(tmp_path, monkeypatch):
    for status in ("unknown", "in_progress", "completed"):
        tasks_path = tmp_path / status / "tasks.yaml"
        tasks_path.parent.mkdir()
        _write_dispatched_claim(tasks_path)
        snapshot = JulesRemoteSnapshot(
            available=True,
            sessions={SID: JulesRemoteSession(SID, status)},
            exhaustive=False,
        )

        task = _run_recover_with_snapshot(tasks_path, monkeypatch, snapshot)

        assert task.status == "dispatched"
        assert task.target_agent == "jules"


def test_recover_reopens_only_confirmed_absent_session(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    _write_dispatched_claim(tasks_path)
    snapshot = JulesRemoteSnapshot(available=True, sessions={}, exhaustive=True)

    task = _run_recover_with_snapshot(tasks_path, monkeypatch, snapshot)

    assert task.status == "open"
    assert task.target_agent == "jules"
    assert "orphaned" in task.dispatch_log[-1].output


def test_recover_populates_session_specific_absence_for_catalog_miss(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    _write_dispatched_claim(tasks_path)
    module = _load_recover("recover_session_absence_probe")
    catalog = JulesRemoteSnapshot(available=True, sessions={}, exhaustive=False)
    monkeypatch.setattr(module, "probe_jules_remote_sessions", lambda: catalog)

    def enrich(snapshot, session_ids):
        assert snapshot is catalog
        assert tuple(session_ids) == (SID,)
        return JulesRemoteSnapshot(
            available=True,
            sessions={},
            exhaustive=False,
            confirmed_absent=frozenset({SID}),
            absence_probe_outcomes={SID: "confirmed_absent"},
        )

    monkeypatch.setattr(module, "probe_jules_remote_session_absences", enrich)
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert "orphaned" in task.dispatch_log[-1].output


def test_recover_holds_when_jules_cli_is_unavailable(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    _write_dispatched_claim(tasks_path)
    snapshot = JulesRemoteSnapshot(available=False, sessions={}, error="not installed")

    task = _run_recover_with_snapshot(tasks_path, monkeypatch, snapshot)

    assert task.status == "dispatched"
    assert task.target_agent == "jules"


def test_recover_preserves_failed_and_dispatched_jules_landing_holds(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    tasks = [
        Task(
            id=f"LANDING-{status.upper()}",
            title="landing held",
            repo="organvm/example",
            target_agent="jules",
            status=status,
            labels=[JULES_LANDING_HOLD_LABEL],
            created=now.date(),
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=now,
                    agent="jules",
                    session_id=SID,
                    status="dispatched",
                )
            ],
        )
        for status in ("failed", "dispatched")
    ]
    save_limen_file(tasks_path, LimenFile(tasks=tasks))
    module = _load_recover("recover_jules_landing_hold")
    monkeypatch.setattr(
        module,
        "live_jules_sessions",
        lambda *_args, **_kwargs: pytest.fail("held landing must not probe or recover"),
    )
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0

    current = load_limen_file(tasks_path).tasks
    assert [task.status for task in current] == ["failed", "dispatched"]
    assert all(task.labels == [JULES_LANDING_HOLD_LABEL] for task in current)
    assert all(len(task.dispatch_log) == 1 for task in current)


def test_recover_does_not_apply_remote_logic_to_non_jules_claim(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    _write_dispatched_claim(tasks_path, target_agent="codex")
    snapshot = JulesRemoteSnapshot(available=True, sessions={}, exhaustive=True)

    task = _run_recover_with_snapshot(tasks_path, monkeypatch, snapshot)

    assert task.status == "dispatched"
    assert task.target_agent == "codex"


def test_recover_reopens_failed_jules_remote_session(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-rebase-organvm-public-record-data-scrapper-335",
                title="rebase public record",
                repo="organvm/public-record-data-scrapper",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="16647959386662614769",
                        status="dispatched",
                    )
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "live_jules_sessions",
        lambda _session_ids=(): {"16647959386662614769": "failed"},
    )
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert "is failed" in task.dispatch_log[-1].output


def test_recover_reopens_jules_session_awaiting_feedback(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-cifix-organvm-mirror-mirror-106",
                title="fix mirror CI",
                repo="organvm/mirror-mirror",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="15175913208909090857",
                        status="dispatched",
                    )
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut_feedback", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "live_jules_sessions",
        lambda _session_ids=(): {"15175913208909090857": "awaiting_user_feedback"},
    )
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert "awaiting_user_feedback" in task.dispatch_log[-1].output


def test_recover_reopens_jules_session_awaiting_plan_approval(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="REV-organvm-mirror-mirror-revenue-ship-0706",
                title="Drive Mirror Mirror to deploy-ready",
                repo="organvm/mirror-mirror",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="10569058041124478902",
                        status="dispatched",
                    )
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut_plan_approval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "live_jules_sessions",
        lambda _session_ids=(): {"10569058041124478902": "awaiting_plan_approval"},
    )
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert "awaiting_plan_approval" in task.dispatch_log[-1].output


def test_recover_task_id_limits_remote_reopen(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="REV-organvm-mirror-mirror-revenue-ship-0706",
                title="Drive Mirror Mirror to deploy-ready",
                repo="organvm/mirror-mirror",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="10569058041124478902",
                        status="dispatched",
                    )
                ],
            ),
            Task(
                id="HEAL-rebase-organvm-peer-audited--behavioral-blockchain-721",
                title="rebase peer audited",
                repo="organvm/peer-audited--behavioral-blockchain",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="14435689243703333273",
                        status="dispatched",
                    )
                ],
            ),
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut_task_id", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "live_jules_sessions",
        lambda _session_ids=(): {
            "10569058041124478902": "awaiting_plan_approval",
            "14435689243703333273": "awaiting_plan_approval",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["recover", "--tasks", str(tasks_path), "--task-id", "REV-organvm-mirror-mirror-revenue-ship-0706", "--apply"],
    )

    assert module.main() == 0
    mirror, peer = load_limen_file(tasks_path).tasks
    assert mirror.status == "open"
    assert mirror.target_agent == "codex"
    assert peer.status == "dispatched"
    assert peer.target_agent == "jules"


def test_recover_defaults_to_local_tasks_yaml(tmp_path, monkeypatch):
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-cifix-organvm-a-i-chat--exporter-49",
                title="fix exporter CI",
                repo="organvm/a-i-chat--exporter",
                target_agent="jules",
                status="failed",
                created=now.date(),
            )
        ],
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    spec = importlib.util.spec_from_file_location("recover_uut_default_tasks", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIMEN_TASKS", raising=False)
    monkeypatch.setattr(sys, "argv", ["recover", "--apply"])

    assert module.main() == 0
    task = load_limen_file(tmp_path / "tasks.yaml").tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"


def test_recover_holds_successor_required_task_at_fixed_point(tmp_path, monkeypatch, capsys):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    contract = packet_contract("15m", now_epoch=1_000)
    save_limen_file(
        tasks_path,
        LimenFile(
            portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
            tasks=[
                Task(
                    id="WORKSTREAM-SUCCESSOR-REQUIRED",
                    title="continue through a separately admitted successor",
                    repo="organvm/limen",
                    target_agent="codex",
                    status="failed",
                    labels=["workstream:successor-required", "tried:codex"],
                    created=now.date(),
                    workstream_contract=contract,
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="codex",
                            session_id="expired-workstream",
                            status="failed",
                            output="successor workstream required: workstream packet runway is exhausted",
                        )
                    ],
                ),
                Task(
                    id="WORKSTREAM-SUCCESSOR-DISPATCHED",
                    title="stale status cannot bypass the successor boundary",
                    repo="organvm/limen",
                    target_agent="jules",
                    status="dispatched",
                    labels=["workstream:successor-required"],
                    created=now.date(),
                    workstream_contract=contract,
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="12345",
                            status="dispatched",
                            output="stale writer flipped the expired owner row",
                        )
                    ],
                ),
            ],
        ),
    )
    original = tasks_path.read_bytes()

    for pass_number in range(2):
        module = _load_recover(f"recover_successor_fixed_point_{pass_number}")
        monkeypatch.setattr(
            module,
            "live_jules_sessions",
            lambda *_args, **_kwargs: pytest.fail("held successor row must not probe Jules"),
        )
        monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

        assert module.main() == 0
        tasks = {task.id: task for task in load_limen_file(tasks_path).tasks}
        task = tasks["WORKSTREAM-SUCCESSOR-REQUIRED"]
        assert task.status == "failed"
        assert task.target_agent == "codex"
        assert task.labels == ["workstream:successor-required", "tried:codex"]
        assert task.workstream_contract == contract
        assert len(task.dispatch_log) == 1
        dispatched = tasks["WORKSTREAM-SUCCESSOR-DISPATCHED"]
        assert dispatched.status == "dispatched"
        assert dispatched.target_agent == "jules"
        assert dispatched.labels == ["workstream:successor-required"]
        assert len(dispatched.dispatch_log) == 1
        assert tasks_path.read_bytes() == original

    assert capsys.readouterr().out.count("2 successor-required held") == 2


def test_recover_reopens_first_noop_failure(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-cifix-organvm-domus-genoma-172",
                title="fix domus CI",
                repo="organvm/domus-genoma",
                target_agent="codex",
                status="failed",
                labels=["noop", "tried:codex"],
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="codex",
                        session_id="result-lifecycle-guard",
                        status="failed",
                        output="No-op result; failed for recovery instead of archived",
                    )
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut_first_noop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert task.labels == ["noop"]
    assert task.dispatch_log[-1].status == "open"


def test_recover_escalates_repeated_noop_failures(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-cifix-organvm-domus-genoma-172",
                title="fix domus CI",
                repo="organvm/domus-genoma",
                target_agent="codex",
                status="failed",
                labels=["noop", "tried:codex"],
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="codex",
                        session_id="result-lifecycle-guard",
                        status="failed",
                        output="No-op result; failed for recovery instead of archived",
                    ),
                    DispatchLogEntry(
                        timestamp=now,
                        agent="limen",
                        session_id="heal",
                        status="open",
                        output="recover: reopened failed -> fresh cascade",
                    ),
                    DispatchLogEntry(
                        timestamp=now,
                        agent="codex",
                        session_id="result-lifecycle-guard",
                        status="failed",
                        output="no-op HEAL-cifix-organvm-domus-genoma-172: agent made no changes -- no PR opened",
                    ),
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut_repeated_noop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "failed_blocked"  # fleet debt (repeated no-op), off the human surface
    assert task.target_agent == "codex"
    assert task.labels == ["noop", "tried:codex", "chronic-fleet-debt"]
    assert task.dispatch_log[-1].status == "failed_blocked"
    assert "repeated no-op failures (2)" in task.dispatch_log[-1].output
    assert "failed_blocked" in task.dispatch_log[-1].output
