"""Test rebalance.py honors the lane-down filter (this session's change): open local-lane tasks
are fanned across the PRODUCTIVE lanes only — a down lane (logs/lanes-down.txt) never receives work
and its tasks are redistributed. _resolve_repo_dir is monkeypatched so the test needs no clones."""

import importlib.util
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rebalance.py"

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task  # noqa: E402


def test_rebalance_skips_down_lanes(tmp_path, monkeypatch):
    import datetime

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    today = datetime.date.today()
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(today)))),
        tasks=[
            Task(
                id=f"T{i}",
                title="t",
                repo="x/y",
                target_agent="codex",
                status="open",
                origin="human_prompt",
                horizon="present",
                value_case="rebalance lane coverage",
                budget_cost=1,
                predicate="python3 scripts/check.py",
                receipt_target=f"github:x/y:pull-request:T{i}",
                created=today,
            )
            for i in range(6)
        ],
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "lanes-down.txt").write_text("gemini\nagy\n")

    spec = importlib.util.spec_from_file_location("rebalance_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "_resolve_repo_dir", lambda t: tmp_path)  # always "cloned"
    monkeypatch.setattr(sys, "argv", ["rebalance", "--lanes", "codex,claude,gemini", "--apply"])
    m.main()

    lanes = Counter(t.target_agent for t in load_limen_file(tmp_path / "tasks.yaml").tasks)
    assert lanes.get("gemini", 0) == 0, f"down lane got work: {lanes}"
    assert set(lanes) == {"codex", "claude"}, f"expected only productive lanes: {lanes}"
    assert lanes["codex"] == 3 and lanes["claude"] == 3, f"not evenly fanned: {lanes}"


def test_rebalance_skips_unsafe_agy_registry_discovery(tmp_path, monkeypatch):
    import datetime

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    today = datetime.date.today()
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(today)))),
        tasks=[
            Task(
                id="DISCOVER-organvm-example",
                title="Discover value",
                repo="organvm/example",
                target_agent="opencode",
                status="open",
                origin="human_prompt",
                horizon="present",
                value_case="discover and promote repo value",
                context="Update value-repos.json and DISCOVERY.md if this repo is promoted.",
                budget_cost=1,
                predicate="python3 scripts/check.py",
                receipt_target="github:organvm/example:pull-request:DISCOVER-organvm-example",
                created=today,
            ),
            Task(
                id="HEAL-cifix-organvm-example-1",
                title="Fix CI",
                repo="organvm/example",
                target_agent="opencode",
                status="open",
                origin="human_prompt",
                horizon="present",
                value_case="fix CI for organvm/example",
                budget_cost=1,
                predicate="python3 scripts/check.py",
                receipt_target="github:organvm/example:pull-request:HEAL-cifix-organvm-example-1",
                created=today,
            ),
        ],
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir()

    spec = importlib.util.spec_from_file_location("rebalance_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "_resolve_repo_dir", lambda t: tmp_path)
    monkeypatch.setattr(sys, "argv", ["rebalance", "--lanes", "agy,opencode", "--apply"])
    m.main()

    tasks = {t.id: t for t in load_limen_file(tmp_path / "tasks.yaml").tasks}
    assert tasks["DISCOVER-organvm-example"].target_agent == "opencode"
    assert tasks["HEAL-cifix-organvm-example-1"].target_agent == "agy"


def test_rebalance_does_not_steal_timeout_to_jules_task(tmp_path, monkeypatch):
    import datetime

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(today)))),
        tasks=[
            Task(
                id="SLOW",
                title="slow timed out",
                repo="organvm/mirror-mirror",
                target_agent="codex",
                status="open",
                origin="human_prompt",
                horizon="present",
                value_case="fix slow timed-out CI",
                labels=["slow", "cifix"],
                budget_cost=1,
                predicate="python3 scripts/check.py",
                receipt_target="github:organvm/mirror-mirror:pull-request:SLOW",
                created=today,
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="opencode",
                        session_id="cli",
                        status="timeout->jules",
                    )
                ],
            ),
            Task(
                id="NORMAL",
                title="normal local work",
                repo="organvm/mirror-mirror",
                target_agent="codex",
                status="open",
                origin="human_prompt",
                horizon="present",
                value_case="normal local work item",
                budget_cost=1,
                predicate="python3 scripts/check.py",
                receipt_target="github:organvm/mirror-mirror:pull-request:NORMAL",
                created=today,
            ),
        ],
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir()

    spec = importlib.util.spec_from_file_location("rebalance_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "_resolve_repo_dir", lambda t: tmp_path)
    monkeypatch.setattr(sys, "argv", ["rebalance", "--lanes", "agy,opencode", "--apply"])
    m.main()

    tasks = {t.id: t for t in load_limen_file(tmp_path / "tasks.yaml").tasks}
    assert tasks["SLOW"].target_agent == "codex"
    assert tasks["NORMAL"].target_agent == "agy"
