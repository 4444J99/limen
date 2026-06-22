"""Regression tests for the atomic queue-write primitive.

Context: on 2026-06-19 tasks.yaml was truncated to 0 bytes by a non-atomic write race,
and — separately — the heartbeat read the file *mid-write* as None, saw total=0 open=0,
and went idle (the downtime). save_limen_file was made atomic; these tests pin that
behavior AND assert load_limen_file refuses a None/empty file instead of crashing the
fleet downstream. Every tasks.yaml writer (route.py / batch-dispatch.py / auto-scale.py /
append-tasks.py) now routes through atomic_write_text — see limen/io.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from limen.io import atomic_write_text, load_limen_file, save_limen_file
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

    with mock.patch("limen.io.os.replace", boom):
        with pytest.raises(OSError):
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


def test_load_refuses_empty_file(tmp_path: Path) -> None:
    """An empty/whitespace queue file is corruption, not an empty queue. load_limen_file
    must raise (so the caller restores from git) rather than return None and let the
    heartbeat report total=0 and idle."""
    target = tmp_path / "tasks.yaml"
    target.write_text("   \n")
    with pytest.raises(ValueError):
        load_limen_file(target)
