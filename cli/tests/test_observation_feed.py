"""Tests for Observation Organ Autonomous Self-Feed Loop and Telemetry Engine.

Verifies:
1. limen.observation collector, schema validation, and emission
2. scripts/observation-feed.py CLI (--emit, --check, --json, --quiet)
3. organs/observation/validate-observation.py governance rules #1-6
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.observation import (  # noqa: E402
    SCHEMA_V1,
    build_feed_record,
    check_feed,
    collect_bifrons,
    collect_observatory,
    collect_vitals,
    determine_status,
    emit_feed_record,
    validate_feed_record,
)

ROOT = Path(__file__).resolve().parents[2]
FEED_SCRIPT = ROOT / "scripts" / "observation-feed.py"
VALIDATOR_SCRIPT = ROOT / "organs" / "observation" / "validate-observation.py"


def run_feed_cli(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FEED_SCRIPT), *(str(arg) for arg in args)],
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_validator_cli(*args: str | Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT), *(str(arg) for arg in args)],
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


# ── Collector & Schema Validation Unit Tests ───────────────────────────────


def test_collect_vitals_returns_valid_structure():
    vitals = collect_vitals()
    assert isinstance(vitals, dict)
    assert isinstance(vitals["level"], int)
    assert vitals["action"] in ("ok", "throttle", "shed")
    assert isinstance(vitals["load_per_core"], (int, float))
    assert vitals["load_per_core"] >= 0.0
    if vitals["swap_used_gib"] is not None:
        assert isinstance(vitals["swap_used_gib"], (int, float))
    if vitals["ram_gib"] is not None:
        assert isinstance(vitals["ram_gib"], (int, float))


def test_collect_bifrons_returns_valid_structure():
    bifrons = collect_bifrons()
    assert isinstance(bifrons, dict)
    assert isinstance(bifrons["stars"], int)
    assert bifrons["stars"] >= 0
    assert isinstance(bifrons["dossiers"], int)
    assert isinstance(bifrons["resonance_edges"], int)
    assert isinstance(bifrons["awaiting_gate"], int)
    assert isinstance(bifrons["status"], str)


def test_collect_observatory_returns_valid_structure():
    obs = collect_observatory()
    assert isinstance(obs, dict)
    if obs["hero"] is not None:
        assert isinstance(obs["hero"], str)
    assert isinstance(obs["external_gaps"], int)
    assert obs["external_gaps"] >= 0
    assert isinstance(obs["internal_gaps"], int)
    assert obs["internal_gaps"] >= 0
    if obs["top_mechanism"] is not None:
        assert isinstance(obs["top_mechanism"], str)


def test_determine_status_logic():
    assert determine_status({"action": "ok", "status": "ok"}, {}, {"status": "ok"}) == "ok"
    assert determine_status({"action": "throttle", "status": "ok"}, {}, {"status": "ok"}) == "degraded"
    assert determine_status({"action": "shed", "status": "ok"}, {}, {"status": "ok"}) == "shed"
    assert determine_status({"action": "ok", "status": "degraded: err"}, {}, {"status": "ok"}) == "degraded"
    assert determine_status({"action": "ok", "status": "ok"}, {}, {"status": "degraded: err"}) == "degraded"


def test_build_feed_record_is_schema_valid():
    record = build_feed_record(source="test_source")
    assert record["schema"] == SCHEMA_V1
    assert record["source"] == "test_source"
    violations = validate_feed_record(record)
    assert violations == [], f"Validation violations found: {violations}"


def test_validate_feed_record_rejects_non_dict():
    violations = validate_feed_record("not a dict")
    assert any("not a dict" in v for v in violations)


def test_validate_feed_record_rejects_wrong_schema():
    record = build_feed_record()
    record["schema"] = "invalid.schema.v99"
    violations = validate_feed_record(record)
    assert any("invalid schema" in v for v in violations)


def test_validate_feed_record_rejects_malformed_timestamp():
    record = build_feed_record()
    record["observed_at"] = "not a valid timestamp"
    violations = validate_feed_record(record)
    assert any("observed_at" in v for v in violations)


def test_validate_feed_record_rejects_invalid_status():
    record = build_feed_record()
    record["status"] = "unknown_status"
    violations = validate_feed_record(record)
    assert any("status" in v for v in violations)


def test_validate_feed_record_rejects_negative_counts():
    record = build_feed_record()
    record["bifrons"]["stars"] = -5
    record["observatory"]["external_gaps"] = -1
    violations = validate_feed_record(record)
    assert any("bifrons.stars" in v for v in violations)
    assert any("observatory.external_gaps" in v for v in violations)


def test_emit_and_check_feed_lifecycle(tmp_path):
    # Emit first record
    record1, jsonl_path, latest_path = emit_feed_record(base_dir=tmp_path)
    assert jsonl_path.exists()
    assert latest_path.exists()

    latest_data = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest_data["schema"] == SCHEMA_V1
    assert latest_data == record1

    # Check feed passes
    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is True
    assert errors == []

    # Emit second record
    record2, _, _ = emit_feed_record(base_dir=tmp_path)
    lines = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0] == record1
    assert lines[1] == record2

    # Check feed still passes
    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is True


def test_emit_feed_record_raises_on_invalid_record(tmp_path):
    invalid_record = {"schema": "wrong"}
    with pytest.raises(ValueError, match="Invalid observation feed record"):
        emit_feed_record(record=invalid_record, base_dir=tmp_path)


def test_check_feed_detects_missing_files(tmp_path):
    empty_dir = tmp_path / "empty_logs"
    empty_dir.mkdir()
    ok, errors = check_feed(base_dir=empty_dir)
    assert ok is False
    assert any("missing feed-latest.json" in e for e in errors)
    assert any("missing feed.jsonl" in e for e in errors)


def test_check_feed_detects_corrupted_jsonl(tmp_path):
    emit_feed_record(base_dir=tmp_path)
    jsonl_path = tmp_path / "logs" / "observation" / "feed.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write("corrupted json not a dict\n")

    ok, errors = check_feed(base_dir=tmp_path)
    assert ok is False
    assert any("parse error" in e for e in errors)


# ── CLI Integration Tests ──────────────────────────────────────────────────


def test_cli_emit_and_check_flags(tmp_path):
    # Run CLI --emit
    emit_res = run_feed_cli("--emit", "--root", tmp_path)
    assert emit_res.returncode == 0, emit_res.stderr
    assert "emitted limen.observation.feed.v1" in emit_res.stdout

    # Run CLI --check
    check_res = run_feed_cli("--check", "--root", tmp_path)
    assert check_res.returncode == 0, check_res.stderr
    assert "check passed" in check_res.stdout


def test_cli_json_and_quiet_flags(tmp_path):
    # Run CLI --emit --json
    res_json = run_feed_cli("--emit", "--json", "--root", tmp_path)
    assert res_json.returncode == 0
    parsed = json.loads(res_json.stdout)
    assert parsed["schema"] == SCHEMA_V1

    # Run CLI --check --quiet
    res_quiet = run_feed_cli("--check", "--quiet", "--root", tmp_path)
    assert res_quiet.returncode == 0
    assert res_quiet.stdout.strip() == ""


def test_cli_check_fails_on_corrupt_feed(tmp_path):
    feed_dir = tmp_path / "logs" / "observation"
    feed_dir.mkdir(parents=True)
    latest_file = feed_dir / "feed-latest.json"
    latest_file.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")

    res = run_feed_cli("--check", "--root", tmp_path)
    assert res.returncode == 1
    assert "FAIL" in res.stderr


# ── Organ Validator Integration Tests ──────────────────────────────────────


def test_validator_bare_and_fleet_passes():
    res_bare = run_validator_cli()
    assert res_bare.returncode == 0, res_bare.stdout + res_bare.stderr
    assert "5/5 passed — Observation Organ fully valid." in res_bare.stdout

    res_fleet = run_validator_cli("--fleet", "--quiet")
    assert res_fleet.returncode == 0, res_fleet.stdout + res_fleet.stderr


def test_validator_checklist():
    res = run_validator_cli("--checklist")
    assert res.returncode == 0
    assert "Rule #1: Observation Standing" in res.stdout
    assert "Rule #2: Human Gate" in res.stdout
    assert "Rule #3: 5-Primitive Completeness" in res.stdout
    assert "Rule #4: Evidence Integrity" in res.stdout
    assert "Rule #5: No Overreach" in res.stdout
    assert "Rule #6: Feed Schema Validation" in res.stdout


def test_validator_rejects_missing_primitive(tmp_path):
    broken_file = tmp_path / "broken-primitive.yaml"
    broken_file.write_text(
        """
id: broken-prim
name: Missing primitive
member:
  repo: test
mandate:
  description: test
standing:
  current: OBSERVING
next_standing: ANALYZED
# missing standard & governance
""".lstrip()
    )
    res = run_validator_cli(broken_file)
    assert res.returncode == 1
    assert "Rule #3 violation: missing required primitive 'standard'" in res.stdout
    assert "Rule #3 violation: missing required primitive 'governance'" in res.stdout


def test_validator_rejects_invalid_standing(tmp_path):
    broken_file = tmp_path / "broken-standing.yaml"
    broken_file.write_text(
        """
id: broken-standing
name: Invalid standing
member:
  repo: test
mandate:
  description: test
standing:
  current: INVALID_STATE
next_standing: ANALYZED
standard:
  rubric: test
  evidence:
    - KERNEL.md
governance:
  human_gated: true
human_gates:
  - operator_approval
artifacts:
  next_reviewable_output: KERNEL.md
""".lstrip()
    )
    res = run_validator_cli(broken_file)
    assert res.returncode == 1
    assert "Rule #1 violation: standing 'INVALID_STATE' is not a valid observation standing" in res.stdout


def test_validator_rejects_non_advancing_standing(tmp_path):
    broken_file = tmp_path / "broken-advance.yaml"
    broken_file.write_text(
        """
id: broken-advance
name: Regressing standing
member:
  repo: test
mandate:
  description: test
standing:
  current: ANALYZED
next_standing: OBSERVING
standard:
  rubric: test
  evidence:
    - KERNEL.md
governance:
  human_gated: true
human_gates:
  - operator_approval
artifacts:
  next_reviewable_output: KERNEL.md
""".lstrip()
    )
    res = run_validator_cli(broken_file)
    assert res.returncode == 1
    assert "Rule #1 violation: next_standing 'OBSERVING' does not advance 'ANALYZED'" in res.stdout


def test_validator_rejects_missing_human_gate(tmp_path):
    broken_file = tmp_path / "broken-gate.yaml"
    broken_file.write_text(
        """
id: broken-gate
name: Missing human gate
member:
  repo: test
mandate:
  description: test
standing:
  current: OBSERVING
next_standing: ANALYZED
standard:
  rubric: test
  evidence:
    - KERNEL.md
governance:
  human_gated: false
human_gates: []
artifacts:
  next_reviewable_output: KERNEL.md
""".lstrip()
    )
    res = run_validator_cli(broken_file)
    assert res.returncode == 1
    assert "Rule #2 violation: governance.human_gated must be true" in res.stdout
    assert "Rule #2 violation: human_gates must name at least one human gate" in res.stdout


def test_validator_rejects_placeholder_evidence(tmp_path):
    broken_file = tmp_path / "broken-evidence.yaml"
    broken_file.write_text(
        """
id: broken-ev
name: Placeholder evidence
member:
  repo: test
mandate:
  description: test
standing:
  current: OBSERVING
next_standing: ANALYZED
standard:
  rubric: test
  evidence:
    - "TODO: add real evidence"
governance:
  human_gated: true
human_gates:
  - operator_approval
artifacts:
  next_reviewable_output: KERNEL.md
""".lstrip()
    )
    res = run_validator_cli(broken_file)
    assert res.returncode == 1
    assert "Rule #4 violation: evidence item" in res.stdout
    assert "contains placeholder 'todo'" in res.stdout


def test_validator_rejects_overreach_claim(tmp_path):
    broken_file = tmp_path / "broken-overreach.yaml"
    broken_file.write_text(
        """
id: broken-overreach
name: Overreach claim
member:
  repo: test
mandate:
  description: autonomous send to public channels
standing:
  current: OBSERVING
next_standing: ANALYZED
standard:
  rubric: test
  evidence:
    - KERNEL.md
governance:
  human_gated: true
human_gates:
  - operator_approval
artifacts:
  next_reviewable_output: KERNEL.md
""".lstrip()
    )
    res = run_validator_cli(broken_file)
    assert res.returncode == 1
    assert "Rule #5 violation: overreach claim present: 'autonomous send'" in res.stdout
