"""Explicit PASS/FAIL/SKIP semantics for source-owned live Omega predicates."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from limen.observatory import executive

ROOT = Path(__file__).resolve().parents[2]


def _script(name: str):
    path = ROOT / "scripts" / name
    module_name = name.replace("-", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(f"strict_source_{module_name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gitvs_strict_doctor_and_usage_report_unavailable(tmp_path, monkeypatch, capsys) -> None:
    gitvs = _script("gitvs.py")
    assert gitvs._verdict([], [], ["live unavailable"], "test", strict=False) == 0
    assert gitvs._verdict([], [], ["live unavailable"], "test", strict=True) == 77

    monkeypatch.setenv("LIMEN_OFFLINE", "1")
    assert gitvs.usage({}, check=True, print_json=False, strict=True) == 77

    monkeypatch.delenv("LIMEN_OFFLINE")
    monkeypatch.setenv("LIMEN_RUNNER_ADMISSION_PROBE_REPO", "private-owner/private-repo")
    monkeypatch.setattr(gitvs.shutil, "which", lambda _command: "/usr/bin/gh")
    monkeypatch.setattr(gitvs, "owners", lambda _estate: ["organvm"])
    monkeypatch.setattr(gitvs, "_usage_month", lambda *_args: {"net_usd_total": 0.0})
    monkeypatch.setattr(gitvs, "_runner_admission_observation", lambda _repo: (None, "private diagnostic detail"))
    monkeypatch.setattr(gitvs, "USAGE_DOC", tmp_path / "usage.json")
    monkeypatch.setattr(gitvs, "USAGE_STAMP", tmp_path / "usage-stamp.json")
    assert gitvs.usage({}, check=True, print_json=False, strict=True) == 77
    output = capsys.readouterr().out
    assert "private-owner/private-repo" not in output
    assert "private diagnostic detail" not in output


def test_artifact_backed_posture_checks_skip_only_when_evidence_is_absent(tmp_path, monkeypatch) -> None:
    seo = _script("seo-audit.py")
    experience = _script("experience-audit.py")
    monkeypatch.setattr(seo, "AUDIT", tmp_path / "seo.json")
    monkeypatch.setattr(experience, "AUDIT", tmp_path / "experience.json")
    assert seo.cmd_check({}, strict=True) == 77
    assert experience.cmd_check(strict=True) == 77

    seo.AUDIT.write_text(
        json.dumps({"schema": "limen.seo_audit.v1", "audited": 0, "failing": []}),
        encoding="utf-8",
    )
    experience.AUDIT.write_text(
        json.dumps({"schema": experience.SCHEMA, "audited": 0, "failing": []}),
        encoding="utf-8",
    )
    assert seo.cmd_check({}, strict=True) == 77
    assert experience.cmd_check(strict=True) == 77

    now = datetime.now(UTC).isoformat(timespec="seconds")
    seo.AUDIT.write_text(
        json.dumps(
            {
                "schema": "limen.seo_audit.v1",
                "generated_at": now,
                "audited": 1,
                "failing": [],
            }
        ),
        encoding="utf-8",
    )
    experience.AUDIT.write_text(
        json.dumps(
            {
                "schema": experience.SCHEMA,
                "generated_at": now,
                "audited": 1,
                "failing": [],
            }
        ),
        encoding="utf-8",
    )
    assert seo.cmd_check({}, strict=True) == 0
    assert experience.cmd_check(strict=True) == 0

    seo.AUDIT.write_text("{", encoding="utf-8")
    experience.AUDIT.write_text("{", encoding="utf-8")
    assert seo.cmd_check({}, strict=True) == 1
    assert experience.cmd_check(strict=True) == 1


def test_host_posture_sources_distinguish_unavailable_from_failure(tmp_path, monkeypatch) -> None:
    disk = _script("disk-capacity.py")
    custody = _script("horrevm-custody.py")
    storage = _script("cloud-storage-doctor.py")
    monkeypatch.setattr(disk, "_free_gib", lambda: None)
    monkeypatch.setattr(custody, "load_state", dict)
    monkeypatch.setattr(custody, "parked", lambda: True)
    assert disk.check(strict=True) == 77
    assert custody.status(strict=True) == 77
    monkeypatch.setattr(storage, "OUT", tmp_path / "storage.json")
    monkeypatch.setattr(storage, "load_registry", lambda: {"rails": {"archive": {}}})
    monkeypatch.setattr(storage, "_run", lambda *_args: (None, ""))
    monkeypatch.setattr(
        storage,
        "evaluate_rail",
        lambda *_args: {"verdict": "unknown", "declared": "offline", "drift": []},
    )
    monkeypatch.setattr(storage, "cloudstorage_census", lambda _rails: [])
    assert storage.check(strict=True) == 77

    overnight = _script("overnight-watch.py")
    missing = tmp_path / "missing-trial.json"
    assert (
        overnight.main(
            [
                "--check-trial",
                "--omega-strict",
                "--trial-output",
                str(missing),
            ]
        )
        == 77
    )
    missing.write_text("{}\n", encoding="utf-8")
    assert (
        overnight.main(
            [
                "--check-trial",
                "--omega-strict",
                "--trial-output",
                str(missing),
            ]
        )
        == 1
    )


def test_observatory_operational_check_requires_every_stage_ok(monkeypatch) -> None:
    observatory = _script("observatory-beat.py")
    monkeypatch.setattr(
        executive,
        "run_beat",
        lambda **_kwargs: {"stages": [{"stage": "collect", "status": "ok"}]},
    )
    assert observatory.main(["--check"]) == 0
    monkeypatch.setattr(
        executive,
        "run_beat",
        lambda **_kwargs: {"stages": [{"stage": "collect", "status": "pending"}]},
    )
    assert observatory.main(["--check"]) == 1
