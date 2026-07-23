"""Regression tests for the atomic queue-write primitive.

Context: on 2026-06-19 tasks.yaml was truncated to 0 bytes by a non-atomic write race,
and — separately — the heartbeat read the file *mid-write* as None, saw total=0 open=0,
and went idle (the downtime). save_limen_file was made atomic; these tests pin that
behavior AND assert load_limen_file refuses a None/empty file instead of crashing the
fleet downstream. The authenticated remote keeper now owns lifecycle projection; this module's
serializer remains for explicitly noncanonical cache/export files and rejects the canonical target.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import yaml
from limen.io import (
    _board_guard_config,
    _queue_lock_stale_seconds,
    atomic_write_text,
    load_limen_file,
    load_limen_text,
    save_derived_limen_projection,
    save_limen_file,
)
from limen.models import LimenFile


def _board(tasks=None) -> dict:
    return {
        "version": "1.0",
        "portal": {
            "name": "Universal Task Intake",
            "budget": {
                "daily": 100,
                "unit": "runs",
                "per_agent": {"jules": 100, "codex": 2},
                "track": {"date": "", "spent": 0, "per_agent": {}},
            },
        },
        "tasks": tasks or [],
    }


def test_atomic_write_replaces_contents(tmp_path: Path) -> None:
    target = tmp_path / "tasks.yaml"
    target.write_text("old contents")
    atomic_write_text(target, "new contents")
    assert target.read_text() == "new contents"


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "tasks.yaml"
    atomic_write_text(target, "hello")
    # the temp file is created in the SAME dir (so os.replace is atomic) and must be gone.
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "tasks.yaml"]
    assert leftovers == [], f"temp files leaked: {leftovers}"


def test_atomic_write_never_truncates_on_failure(tmp_path: Path) -> None:
    """If the write blows up mid-flight, the ORIGINAL file must be untouched — never a
    0-byte/partial file. This is the exact race that emptied the queue and idled the
    heartbeat."""
    target = tmp_path / "tasks.yaml"
    target.write_text("good queue with 691 tasks")

    def boom(src, dst):  # explode after the temp file exists, before the swap
        raise OSError("simulated crash mid-write")

    with mock.patch("limen.io.os.replace", boom), pytest.raises(OSError):
        atomic_write_text(target, "this should never land")

    # original survives intact, and the temp file was cleaned up
    assert target.read_text() == "good queue with 691 tasks"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "tasks.yaml"]
    assert leftovers == [], f"temp files leaked after failure: {leftovers}"


def test_save_then_load_roundtrips(tmp_path: Path) -> None:
    target = tmp_path / "tasks.yaml"
    model = LimenFile.model_validate(_board())
    save_limen_file(target, model)
    loaded = load_limen_file(target)
    assert isinstance(loaded, LimenFile)


def test_derived_projection_cannot_target_canonical_board(tmp_path: Path) -> None:
    canonical = tmp_path / "tasks.yaml"
    model = LimenFile.model_validate(_board())
    canonical.write_text("canonical bytes\n")

    with pytest.raises(ValueError, match="canonical tasks.yaml"):
        save_derived_limen_projection(
            canonical,
            model,
            canonical_path=canonical,
        )

    assert canonical.read_text() == "canonical bytes\n"


def test_derived_projection_writes_only_a_distinct_export(tmp_path: Path) -> None:
    canonical = tmp_path / "tasks.yaml"
    export = tmp_path / "channel.yaml"
    canonical.write_text("canonical bytes\n")
    model = LimenFile.model_validate(_board())

    save_derived_limen_projection(export, model, canonical_path=canonical)

    assert canonical.read_text() == "canonical bytes\n"
    assert load_limen_file(export).model_dump(mode="json") == model.model_dump(mode="json")


def test_save_then_load_preserves_board_extensions(tmp_path: Path) -> None:
    target = tmp_path / "tasks.yaml"
    model = LimenFile.model_validate(
        _board(
            tasks=[
                {
                    "id": "T-1",
                    "title": "t",
                    "target_agent": "jules",
                    "created": "2026-07-01",
                    "custom_extension": {"keep": True},
                }
            ]
        )
    )
    model.portal.agents["opencode"] = {"status": "idle", "clock_health": "ok"}
    save_limen_file(target, model)
    raw = yaml.safe_load(target.read_text())
    loaded = load_limen_file(target)

    assert raw["portal"]["agents"]["opencode"] == {"status": "idle", "clock_health": "ok"}
    assert raw["tasks"][0]["custom_extension"] == {"keep": True}
    assert loaded.portal.agents["opencode"]["status"] == "idle"
    assert loaded.tasks[0].model_extra["custom_extension"] == {"keep": True}


def test_load_refuses_empty_file(tmp_path: Path) -> None:
    """An empty/whitespace queue file is corruption, not an empty queue. load_limen_file
    must raise (so the caller restores from git) rather than return None and let the
    heartbeat report total=0 and idle."""
    target = tmp_path / "tasks.yaml"
    target.write_text("   \n")
    with pytest.raises(ValueError):
        load_limen_file(target)


def test_load_text_matches_load_file(tmp_path: Path) -> None:
    """load_limen_text(bytes) must parse identically to load_limen_file(path) for the same
    content — the refactor that lets a caller read the board exactly once is behavior-preserving."""
    target = tmp_path / "tasks.yaml"
    model = LimenFile.model_validate(
        _board(tasks=[{"id": "T-1", "title": "t", "target_agent": "jules", "created": "2026-07-01"}])
    )
    save_limen_file(target, model)
    text = target.read_text()
    from_file = load_limen_file(target)
    from_text = load_limen_text(text)
    assert from_text.model_dump(mode="json") == from_file.model_dump(mode="json")


def test_load_text_refuses_empty() -> None:
    """The empty/corruption guard holds on the string entry point too."""
    with pytest.raises(ValueError):
        load_limen_text("   \n", name="tasks.yaml")


def test_io_numeric_env_knobs_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_QUEUE_LOCK_STALE_SEC", "bad")
    monkeypatch.setenv("LIMEN_BOARD_SHRINK_FLOOR", "bad")
    monkeypatch.setenv("LIMEN_BOARD_SHRINK_FRACTION", "nan")

    assert _queue_lock_stale_seconds() == 900
    assert _board_guard_config() == (True, 5, 0.10)

    monkeypatch.setenv("LIMEN_BOARD_SHRINK_FRACTION", "inf")
    assert _board_guard_config() == (True, 5, 0.10)


def test_io_numeric_env_knobs_reject_nonpositive_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_QUEUE_LOCK_STALE_SEC", "0")
    monkeypatch.setenv("LIMEN_BOARD_SHRINK_FLOOR", "-2")
    monkeypatch.setenv("LIMEN_BOARD_SHRINK_FRACTION", "-0.5")

    assert _queue_lock_stale_seconds() == 900
    assert _board_guard_config() == (True, 5, 0.10)


def test_task_model_rejects_invalid_ids() -> None:
    with pytest.raises(ValueError):
        LimenFile.model_validate(
            _board(tasks=[{"id": "bad id!", "title": "t", "target_agent": "jules", "created": "2026-07-01"}])
        )


@pytest.mark.parametrize("budget_cost", [True, False, 0, -1])
def test_task_model_rejects_invalid_budget_cost(budget_cost) -> None:
    with pytest.raises(ValueError):
        LimenFile.model_validate(
            _board(
                tasks=[
                    {
                        "id": "T-1",
                        "title": "t",
                        "target_agent": "jules",
                        "created": "2026-07-01",
                        "budget_cost": budget_cost,
                    }
                ]
            )
        )


def test_load_text_reads_a_frozen_snapshot(tmp_path: Path) -> None:
    """The whole point of the single-read path: parsing a captured buffer is immune to a concurrent
    rewrite of the file. Load from a snapshot string, then mutate the file on disk — the parsed board
    still reflects the snapshot, never the later write (the TOCTOU false-negative --verify hit on the
    live daemon-churned board)."""
    target = tmp_path / "tasks.yaml"
    save_limen_file(
        target,
        LimenFile.model_validate(
            _board(tasks=[{"id": "A", "title": "a", "target_agent": "jules", "created": "2026-07-01"}])
        ),
    )
    snapshot = target.read_text()
    # a "concurrent writer" replaces the file after we captured the snapshot
    save_limen_file(
        target,
        LimenFile.model_validate(
            _board(tasks=[{"id": "B", "title": "b", "target_agent": "jules", "created": "2026-07-01"}])
        ),
    )
    board = load_limen_text(snapshot, name=target.name)
    assert [t.id for t in board.tasks] == ["A"]
