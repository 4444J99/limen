from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRESHNESS = ROOT / "scripts" / "cloud-maintenance-freshness.py"
WORKFLOW = ROOT / ".github" / "workflows" / "cloud-maintenance.yml"


def _load_freshness():
    spec = importlib.util.spec_from_file_location("cloud_maintenance_freshness", FRESHNESS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Completed:
    def __init__(self, payload, returncode=0, stderr=""):
        self.returncode = returncode
        self.stdout = json.dumps(payload)
        self.stderr = stderr


def test_latest_success_queries_only_successful_manual_cloud_receipts(monkeypatch):
    module = _load_freshness()
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return _Completed(
            [
                {
                    "databaseId": 42,
                    "headSha": "a" * 40,
                    "updatedAt": "2026-08-20T18:00:00Z",
                    "url": "https://github.com/organvm/limen/actions/runs/42",
                }
            ]
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    receipt = module.latest_success("organvm/limen")

    assert receipt["databaseId"] == 42
    assert seen[0][seen[0].index("--workflow") + 1] == "cloud-maintenance.yml"
    assert seen[0][seen[0].index("--event") + 1] == "workflow_dispatch"
    assert seen[0][seen[0].index("--status") + 1] == "success"


def test_freshness_main_rejects_stale_success(monkeypatch, capsys):
    module = _load_freshness()
    stale = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    monkeypatch.setattr(
        module,
        "latest_success",
        lambda _repo: {"databaseId": 42, "headSha": "a" * 40, "updatedAt": stale, "url": "u"},
    )
    monkeypatch.setattr(module.sys, "argv", ["cloud-maintenance-freshness", "--max-age-seconds", "60"])

    assert module.main() == 1
    assert "stale" in capsys.readouterr().err


def test_cloud_maintenance_workflow_is_manual_exact_head_and_counts_only():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in source
    assert "schedule:" not in source
    assert "expected_sha:" in source
    assert 'test "${GITHUB_SHA}" = "${EXPECTED_SHA}"' in source
    assert "LIMEN_CONDUCT_URL: ${{ vars.LIMEN_API_URL }}" in source
    assert "LIMEN_CONDUCT_TOKEN: ${{ secrets.LIMEN_API_TOKEN }}" in source
    assert "cloud-maintenance-receipt.json" in source
    assert "tasks.yaml" not in source
