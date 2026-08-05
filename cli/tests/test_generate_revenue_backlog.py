"""Regression tests for scripts/generate-revenue-backlog.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from limen.models import Task

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-revenue-backlog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_revenue_backlog_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _task(status: str, lever: str, repo: str = "organvm/a-i-chat--exporter", suffix: str = "0703") -> Task:
    return Task(
        id=f"REV-{repo.replace('/', '-')}-{lever}-{suffix}",
        title="seed",
        repo=repo,
        type="code",
        target_agent="codex",
        priority="high",
        budget_cost=2,
        status=status,
        labels=[lever, "revenue", "product", "ship-order", "generated"],
        urls=[],
        context="seed",
        depends_on=[],
        created="2026-07-03",
        dispatch_log=[],
    )


def test_done_deploy_ready_artifact_suppresses_later_duplicate(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("LIMEN_DISPATCH_LANES", "codex")
    monkeypatch.setattr(mod, "_avg_headroom_pct", lambda: None)
    monkeypatch.setattr(
        mod,
        "_products",
        lambda: [
            {
                "repo": "organvm/a-i-chat--exporter",
                "stage": "deploy-ready",
                "rank": 1,
                "product": "ChatGPT Exporter",
                "first_dollar_path": "the paid tier",
            }
        ],
    )

    new, _info = mod._plan(
        [_task("done", "revenue-launch-post", suffix="0702")],
        floor_base=4,
        max_new=4,
    )

    levers = {t.labels[0] for t in new}
    assert "revenue-launch-post" not in levers
    assert levers == {"revenue-funding", "revenue-pro-tier", "revenue-landing"}


def test_done_building_pass_remains_repeatable_when_ladder_still_building(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("LIMEN_DISPATCH_LANES", "codex")
    monkeypatch.setattr(mod, "_avg_headroom_pct", lambda: None)
    monkeypatch.setattr(
        mod,
        "_products",
        lambda: [
            {
                "repo": "organvm/mirror",
                "stage": "building",
                "rank": 1,
                "product": "Mirror",
                "first_dollar_path": "the first paid workflow",
            }
        ],
    )

    new, _info = mod._plan(
        [_task("done", "revenue-readiness", repo="organvm/mirror", suffix="0702")],
        floor_base=2,
        max_new=2,
    )

    assert {t.labels[0] for t in new} == {"revenue-ship", "revenue-readiness"}


def test_products_fail_open_on_wrong_ladder_shapes(monkeypatch, tmp_path, capsys):
    mod = _load_module()
    ladder = tmp_path / "revenue-ladder.json"
    monkeypatch.setenv("LIMEN_REVENUE_LADDER", str(ladder))

    ladder.write_text("[]")
    assert mod._products() == []
    assert "root is list" in capsys.readouterr().err

    ladder.write_text(json.dumps({"products": {"repo": "organvm/a-i-chat--exporter"}}))
    assert mod._products() == []
    assert "products is dict" in capsys.readouterr().err


def test_avg_headroom_accepts_numeric_strings_and_rejects_bad_values(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "ok-string": {"headroom_pct": "75.5"},
                    "ok-number": {"headroom_pct": 24.5},
                    "bool": {"headroom_pct": True},
                    "nan": {"headroom_pct": "NaN"},
                    "bad": {"headroom_pct": "not-a-number"},
                }
            }
        )
    )

    assert mod._avg_headroom_pct() == 50.0


def test_positive_int_uses_default_for_invalid_values():
    mod = _load_module()

    assert mod._positive_int("9", 12) == 9
    assert mod._positive_int("bad", 12) == 12
    assert mod._positive_int("0", 12) == 12
    assert mod._positive_int("-4", 12) == 12
    assert mod._positive_int(True, 12) == 12
