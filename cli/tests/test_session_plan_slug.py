"""Tests for the two defects `scripts/session-plan.py open` showed on its first handoff use (2026-10-18).

A date-prefixed slug minted `2026-10-18-2026-10-18-<slug>.md` — a name PLAN_NAME_RE accepts and no check
flags — and a failed `ship-docs.sh` left the freshly written, untracked stub behind to be mistaken for a
shipped plan. Neither depends on the interpreter, so neither is hidden by the host shell's PATH.
"""

import argparse
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session-plan.py"


def _load():
    spec = importlib.util.spec_from_file_location("session_plan_slug_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def organ(tmp_path, monkeypatch):
    """The organ bound to a scratch tree whose `ship-docs.sh` exits with `$SHIP_RC` (default 0)."""
    module = _load()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    ship = tmp_path / "scripts" / "ship-docs.sh"
    ship.write_text('#!/bin/sh\nexit "${SHIP_RC:-0}"\n')
    ship.chmod(0o755)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PLANS", tmp_path / "docs" / "plans")
    return module


def _args(slug: str) -> argparse.Namespace:
    return argparse.Namespace(
        slug=slug,
        title="A title",
        body_file=None,
        objective=None,
        issue=1,
        dry_run=False,
        no_ship=False,
    )


def test_date_prefixed_slug_is_rejected_before_anything_is_written(organ):
    with pytest.raises(organ.ChainError, match="starts with a date"):
        organ.cmd_open(_args("2026-10-18-parity-rail-handoff-envelope"))
    assert list(organ.PLANS.iterdir()) == []


def test_bare_slug_still_opens_and_the_filename_carries_one_date(organ):
    assert organ.cmd_open(_args("parity-rail-handoff-envelope")) == 0
    (plan,) = organ.PLANS.iterdir()
    assert plan.name == f"{organ._today()}-parity-rail-handoff-envelope.md"


def test_failed_ship_removes_only_the_stub_it_created(organ, monkeypatch):
    existing = organ.PLANS / f"{organ._today()}-some-slug.md"
    existing.write_text("# shipped earlier\n")
    monkeypatch.setenv("SHIP_RC", "1")
    with pytest.raises(organ.ChainError, match="ship-docs.sh refused"):
        organ.cmd_open(_args("some-slug"))
    # The earlier plan is untouched; the `-v2` stub this call wrote is gone.
    assert [p.name for p in organ.PLANS.iterdir()] == [existing.name]
    assert existing.read_text() == "# shipped earlier\n"


def test_ship_exit_two_keeps_the_plan_because_the_pr_is_open(organ, monkeypatch):
    monkeypatch.setenv("SHIP_RC", "2")
    assert organ.cmd_open(_args("held-slug")) == 0
    assert len(list(organ.PLANS.iterdir())) == 1
