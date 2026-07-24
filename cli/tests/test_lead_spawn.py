from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "lead-spawn.py"


def load_module():
    spec = importlib.util.spec_from_file_location("lead_spawn_test_module", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(slug: str, prompt_file: Path, runway: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(slug=slug, prompt_file=str(prompt_file), runway=runway, dry_run=True)


def _mint_lead(
    repo: Path,
    slug: str = "lead-substrate",
    handle: str = "substrate",
    *,
    duration: int = 7 * 86400,
    deadline_epoch: float | None = None,
) -> Path:
    lead = repo / ".worktrees" / slug
    capsule = lead / ".limen-workstream"
    capsule.mkdir(parents=True)
    runway: dict = {"duration_seconds": duration, "deadline_epoch": deadline_epoch}
    (capsule / "workstream.json").write_text(json.dumps({"schema": "limen.workstream.contract.v1", "runway": runway}))
    receipt_dir = lead / "docs" / "continuations" / slug
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "workstream.json").write_text(
        json.dumps({"schema": "limen.workstream.receipt.v1", "slug": slug, "workstream": handle})
    )
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "start-worktree-session.sh").write_text("#!/bin/bash\n")
    return lead


def test_runway_parse_and_format_round_trip():
    module = load_module()
    assert module.parse_runway("8h") == 8 * 3600
    assert module.parse_runway("45m") == 45 * 60
    assert module.parse_runway("7d") == 7 * 86400
    assert module.format_runway(8 * 3600) == "8h"
    assert module.format_runway(90 * 60) == "90m"
    with pytest.raises(module.SpawnError):
        module.parse_runway("eight hours")
    with pytest.raises(module.SpawnError):
        module.format_runway(0)


def test_spawn_inherits_handle_and_clamps_nothing_when_lead_is_fresh(tmp_path: Path):
    module = load_module()
    lead = _mint_lead(tmp_path)
    intent = tmp_path / "battle.md"
    intent.write_text("# one bounded objective\n")
    command = module.build_command(_args("fix-admission-drift", intent), now=1_000.0, cwd=lead)
    assert command[command.index("--workstream") + 1] == "substrate"
    assert command[command.index("--runway") + 1] == "8h"
    assert command[-2:] == ["limen", "fix-admission-drift"]


def test_child_runway_clamped_to_lead_remaining(tmp_path: Path):
    module = load_module()
    now = 1_000_000.0
    lead = _mint_lead(tmp_path, deadline_epoch=now + 3600)
    intent = tmp_path / "battle.md"
    intent.write_text("x\n")
    command = module.build_command(_args("short-fight", intent, runway="8h"), now=now, cwd=lead)
    assert command[command.index("--runway") + 1] == "1h"


def test_exhausted_lead_refuses_and_names_the_successor_rule(tmp_path: Path):
    module = load_module()
    now = 1_000_000.0
    lead = _mint_lead(tmp_path, deadline_epoch=now - 1)
    intent = tmp_path / "battle.md"
    intent.write_text("x\n")
    with pytest.raises(module.SpawnError, match="successor"):
        module.build_command(_args("too-late", intent), now=now, cwd=lead)


def test_battle_cap_refused_with_live_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = load_module()
    monkeypatch.setenv("LIMEN_LEAD_MAX_BATTLES", "2")
    lead = _mint_lead(tmp_path)
    for name in ("battle-one", "battle-two"):
        receipt_dir = tmp_path / ".worktrees" / name / "docs" / "continuations" / name
        receipt_dir.mkdir(parents=True)
        (receipt_dir / "workstream.json").write_text(json.dumps({"workstream": "substrate"}))
    intent = tmp_path / "battle.md"
    intent.write_text("x\n")
    with pytest.raises(module.SpawnError, match="battle cap reached"):
        module.build_command(_args("battle-three", intent), now=1_000.0, cwd=lead)


def test_non_lead_capsule_is_refused(tmp_path: Path):
    module = load_module()
    tree = _mint_lead(tmp_path, slug="ordinary-battle")
    intent = tmp_path / "battle.md"
    intent.write_text("x\n")
    with pytest.raises(module.SpawnError, match="not a lead capsule"):
        module.build_command(_args("child", intent), now=1_000.0, cwd=tree)


def test_outside_any_capsule_is_refused(tmp_path: Path):
    module = load_module()
    intent = tmp_path / "battle.md"
    intent.write_text("x\n")
    with pytest.raises(module.SpawnError, match="not inside a lead capsule"):
        module.build_command(_args("child", intent), now=1_000.0, cwd=tmp_path)
