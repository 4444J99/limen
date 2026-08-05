"""Track C closeout: non-noop vendor update ∧ normalized inventory green."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/tcc-track-c-closeout.py"


def _load_closeout():
    spec = importlib.util.spec_from_file_location("tcc_track_c_closeout", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


closeout = _load_closeout()


def _green_audit_payload(**overrides):
    payload = {
        "schema": "limen.tcc_identity_audit.v2",
        "ok": True,
        "status": "ok",
        "failures": [],
        "automatic_updates": {"enabled": True, "blockers": []},
        "stable_host": {"ok": True, "cdhash": "abc"},
        "summary": {
            "active_leaks": 0,
            "baseline_managed": 28,
            "new_managed": 0,
            "stable_host": 1,
            "unhosted_configured_ingresses": 0,
            "visible_app_management_path_rows": 0,
            "unrelated": 12,
        },
        "predicates": {
            "active_leaks": {"ok": True, "count": 0, "identities": []},
            "visible_app_management_path_rows": {
                "ok": True,
                "count": 0,
                "stable_host_grant_count": 1,
            },
            "unhosted_configured_ingresses": {"ok": True, "count": 0},
        },
        "unrelated_app_management_preservation": {"ok": True, "current_count": 12, "baseline_count": 12},
    }
    payload.update(overrides)
    return payload


def _red_audit_payload():
    payload = _green_audit_payload()
    payload["ok"] = False
    payload["status"] = "blocked"
    payload["failures"] = ["active_managed_tcc_leak"]
    payload["summary"]["active_leaks"] = 1
    payload["predicates"]["active_leaks"] = {"ok": False, "count": 1, "identities": []}
    return payload


class FakeRunner:
    def __init__(self, plan: list[tuple[tuple[str, ...], subprocess.CompletedProcess[str]]]):
        self.plan = list(plan)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *argv, env=None, timeout=120.0):  # noqa: ANN003
        key = tuple(str(part) for part in argv)
        self.calls.append(key)
        for pattern, result in self.plan:
            if _match(key, pattern):
                return result
        raise AssertionError(f"unexpected command: {key}\nknown: {[p for p, _ in self.plan]}")


def _match(actual: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    if pattern and pattern[0] == "...audit...":
        return any(part.endswith("tcc-identity-audit.py") for part in actual)
    if len(actual) < len(pattern):
        return False
    # suffix match for hosted commands / exact tail
    return actual[-len(pattern) :] == pattern or actual == pattern


def _cp(stdout: str = "", stderr: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


def test_parse_and_version_advanced():
    assert closeout.parse_claude_version("2.1.220 (Claude Code)") == "2.1.220"
    assert closeout.version_advanced("2.1.221") is True
    assert closeout.version_advanced("2.1.220") is False
    assert closeout.version_advanced("2.1.219") is False


def test_noop_update_is_external_vendor_wait(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tcc-identity-audit.py").write_text("# fixture\n", encoding="utf-8")
    host = tmp_path / "domus-agent-host"
    host.write_text("#!/bin/sh\n", encoding="utf-8")
    host.chmod(0o700)

    audit_json = json.dumps(_green_audit_payload())

    def runner(*argv, env=None, timeout=120.0):  # noqa: ANN003
        key = tuple(str(part) for part in argv)
        if "claude" in key and "--version" in key:
            return _cp("2.1.220 (Claude Code)\n")
        if "claude" in key and "update" in key:
            return _cp("Claude Code is up to date (2.1.220)\n")
        if any(part.endswith("tcc-identity-audit.py") for part in key):
            return _cp(audit_json + "\n")
        raise AssertionError(key)

    env = {
        **os.environ,
        "LIMEN_AGENT_HOST_BIN": str(host),
        "LIMEN_ROOT": str(repo),
    }
    receipt = closeout.run_closeout(
        mode="run",
        env=env,
        runner=runner,
        repo=repo,
        do_update=True,
        write=True,
    )
    track = receipt["track_c"]
    assert track["status"] == "external_vendor_wait"
    assert track["met"] is False
    assert track["non_noop"] is False
    assert "noop_update_proof_missing" in track["failure_classes"]
    assert closeout.exit_code_for(receipt) == 0
    assert (repo / "logs" / "tcc-track-c-status.json").is_file()
    assert (repo / "docs" / "receipts" / "tcc-track-c-1703" / "closeout-latest.json").is_file()


def test_version_advance_with_green_inventory_meets(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tcc-identity-audit.py").write_text("# fixture\n", encoding="utf-8")
    host = tmp_path / "domus-agent-host"
    host.write_text("#!/bin/sh\n", encoding="utf-8")
    host.chmod(0o700)

    audit_json = json.dumps(_green_audit_payload())
    versions = iter(
        [
            _cp("2.1.220 (Claude Code)\n"),
            _cp("2.1.221 (Claude Code)\n"),
        ]
    )
    audits = iter([_cp(audit_json + "\n"), _cp(audit_json + "\n")])

    def runner(*argv, env=None, timeout=120.0):  # noqa: ANN003
        key = tuple(str(part) for part in argv)
        if key[-2:] == ("claude", "--version") or (len(key) >= 4 and key[-2:] == ("claude", "--version")):
            return next(versions)
        if any(part.endswith("tcc-identity-audit.py") for part in key):
            return next(audits)
        if key[-2:] == ("claude", "update"):
            return _cp("Updating Claude Code to 2.1.221\n")
        raise AssertionError(key)

    env = {
        **os.environ,
        "LIMEN_AGENT_HOST_BIN": str(host),
        "LIMEN_ROOT": str(repo),
    }
    receipt = closeout.run_closeout(
        mode="run",
        env=env,
        runner=runner,
        repo=repo,
        do_update=True,
        write=True,
    )
    track = receipt["track_c"]
    assert track["met"] is True
    assert track["status"] == "met"
    assert track["non_noop"] is True
    assert track["version_after"] == "2.1.221"
    assert closeout.exit_code_for(receipt) == 0


def test_already_advanced_inventory_only_meets(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tcc-identity-audit.py").write_text("# fixture\n", encoding="utf-8")
    host = tmp_path / "domus-agent-host"
    host.write_text("#!/bin/sh\n", encoding="utf-8")
    host.chmod(0o700)
    audit_json = json.dumps(_green_audit_payload())

    def runner(*argv, env=None, timeout=120.0):  # noqa: ANN003
        key = tuple(str(part) for part in argv)
        if "claude" in key and "--version" in key:
            return _cp("2.1.300 (Claude Code)\n")
        if any(part.endswith("tcc-identity-audit.py") for part in key):
            return _cp(audit_json + "\n")
        raise AssertionError(key)

    receipt = closeout.run_closeout(
        mode="beat",
        env={"LIMEN_AGENT_HOST_BIN": str(host), "LIMEN_ROOT": str(repo), **os.environ},
        runner=runner,
        repo=repo,
        do_update=True,
        write=True,
    )
    assert receipt["track_c"]["met"] is True
    assert receipt["track_c"]["version_after"] == "2.1.300"


def test_advance_with_red_inventory_blocks(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tcc-identity-audit.py").write_text("# fixture\n", encoding="utf-8")
    host = tmp_path / "domus-agent-host"
    host.write_text("#!/bin/sh\n", encoding="utf-8")
    host.chmod(0o700)
    red = json.dumps(_red_audit_payload())

    def runner(*argv, env=None, timeout=120.0):  # noqa: ANN003
        key = tuple(str(part) for part in argv)
        if "claude" in key and "--version" in key:
            return _cp("2.1.300 (Claude Code)\n")
        if any(part.endswith("tcc-identity-audit.py") for part in key):
            return _cp(red + "\n", code=1)
        raise AssertionError(key)

    receipt = closeout.run_closeout(
        mode="beat",
        env={"LIMEN_AGENT_HOST_BIN": str(host), "LIMEN_ROOT": str(repo), **os.environ},
        runner=runner,
        repo=repo,
        write=True,
    )
    assert receipt["track_c"]["met"] is False
    assert receipt["track_c"]["status"] == "blocked"
    assert closeout.exit_code_for(receipt) == 1


def test_finalize_refuses_without_met_receipt(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "docs" / "receipts" / "tcc-track-c-1703").mkdir(parents=True)
    with pytest.raises(closeout.CloseoutError, match="no met Track C receipt"):
        closeout.finalize(repo=repo, write_lever=False)


def test_latest_met_receipt_never_pins_the_mutable_alias(tmp_path: Path):
    # closeout-latest.json sorts after closeout-2026… names, so an unfiltered
    # glob pins the beat-rewritten alias as discharge evidence — the 2026-08-05
    # defect where a later regression flipped the lever's cited receipt to
    # blocked. Only immutable timestamped receipts may qualify.
    repo = tmp_path / "repo"
    receipts = repo / "docs" / "receipts" / "tcc-track-c-1703"
    receipts.mkdir(parents=True)
    met = {"schema": closeout.SCHEMA, "track_c": {"met": True}}
    (receipts / "closeout-latest.json").write_text(json.dumps(met), encoding="utf-8")

    assert closeout.latest_met_receipt(repo) is None

    (receipts / "closeout-20260805T133718Z.json").write_text(json.dumps(met), encoding="utf-8")
    picked = closeout.latest_met_receipt(repo)
    assert picked is not None
    assert picked.name == "closeout-20260805T133718Z.json"


def test_finalize_discharges_lever_when_met(tmp_path: Path):
    repo = tmp_path / "repo"
    receipts = repo / "docs" / "receipts" / "tcc-track-c-1703"
    receipts.mkdir(parents=True)
    met = {
        "schema": closeout.SCHEMA,
        "track_c": {
            "met": True,
            "status": "met",
            "version_after": "2.1.221",
            "non_noop": True,
        },
        "next_commands": ["gh issue close 1703"],
    }
    (receipts / "closeout-met.json").write_text(json.dumps(met), encoding="utf-8")

    levers = {
        "levers": [
            {
                "id": "L-DOMUS-AGENT-HOST-TCC",
                "status": "open",
                "issue": 1703,
                "label": "open",
                "steps": [
                    "Completed: cutover",
                    "Pending external predicate: when a version newer than 2.1.220 is offered...",
                ],
            }
        ]
    }
    (repo / "his-hand-levers.json").write_text(json.dumps(levers), encoding="utf-8")
    cont = repo / "docs" / "continuations" / "tcc-app-management-closure-20260803"
    cont.mkdir(parents=True)
    (cont / "acceptance.json").write_text(
        json.dumps({"completion": {"complete": False, "status": "external_vendor_wait"}}),
        encoding="utf-8",
    )
    organs = repo / "institutio" / "registry"
    organs.mkdir(parents=True)
    (organs / "organs.yaml").write_text(
        'residual: "The 2026-08-03 local cutover passed: fixed-host signature unchanged, '
        "App Management has one host row and zero path rows, and the unrelated grant map is preserved. "
        "Keep alerting if an updater is disabled, any managed identity appears outside the redacted baseline, "
        "or a path client returns. Final acceptance waits for a real Claude version advance beyond 2.1.220 "
        'with the inventory still green. Never re-pin/re-disable a rotating tool."\n'
        'residual: "Local predicates passed 2026-08-03: ten managed GUI ingresses enter through '
        "domus-agent-host ensure; App Management has one enabled host row, zero path rows, and the "
        "baseline's unrelated bundle grants unchanged; renamed-runner and cold-start matrices added no "
        "identity. The real Claude vendor-update predicate remains open because 2.1.220 was already "
        "current. The three HEAL valves remain separately armed. No recurring cleanup, updater "
        'suppression, global TCC reset, direct database edit, or version pin is an accepted closure."\n',
        encoding="utf-8",
    )

    result = closeout.finalize(repo=repo, write_lever=True)
    assert result["lever_updated"] is True
    assert result["continuation_updated"] is True
    assert result["organs_updated"] is True
    registry = json.loads((repo / "his-hand-levers.json").read_text(encoding="utf-8"))
    row = registry["levers"][0]
    assert row["status"] == "discharged"
    assert row["discharged"]["version"] == "2.1.221"
    acceptance = json.loads((cont / "acceptance.json").read_text(encoding="utf-8"))
    assert acceptance["completion"]["complete"] is True


def test_cli_probe_exits_zero_on_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Smoke the CLI entry with injected env by invoking main() through run_closeout path.
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tcc-identity-audit.py").write_text("# fixture\n", encoding="utf-8")
    host = tmp_path / "domus-agent-host"
    host.write_text("#!/bin/sh\n", encoding="utf-8")
    host.chmod(0o700)
    audit_json = json.dumps(_green_audit_payload())

    def runner(*argv, env=None, timeout=120.0):  # noqa: ANN003
        key = tuple(str(part) for part in argv)
        if "claude" in key and "--version" in key:
            return _cp("2.1.220 (Claude Code)\n")
        if any(part.endswith("tcc-identity-audit.py") for part in key):
            return _cp(audit_json + "\n")
        raise AssertionError(key)

    monkeypatch.setenv("LIMEN_AGENT_HOST_BIN", str(host))
    monkeypatch.setenv("LIMEN_ROOT", str(repo))
    receipt = closeout.run_closeout(
        mode="probe",
        env=os.environ,
        runner=runner,
        repo=repo,
        do_update=False,
        write=True,
    )
    assert receipt["track_c"]["status"] == "external_vendor_wait"
    assert closeout.exit_code_for(receipt) == 0
