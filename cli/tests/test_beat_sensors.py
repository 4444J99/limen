"""Tests for scripts/beat-sensors.py — the SENSORS registry runner.

Loads the script via importlib (hyphenated filename) and drives it against a fixture registry, so the
tests never execute the real beat sensors.
"""

import importlib.util
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "beat-sensors.py"
REAL_REGISTRY = ROOT / "institutio" / "governance" / "sensors.yaml"

FIXTURE = """\
schema_version: 0.1
sensors:
  alpha:
    section: "0a"
    title: "alpha check"
    gate: LIMEN_ALPHA
    default: "1"
    source: [metabolize]
    steps:
      - command: "python3 scripts/alpha.py"
        severity: advisory
        escalation: "alpha failed"
  beta:
    section: "0b"
    title: "beta check"
    gate: LIMEN_BETA
    default: "0"
    source: [metabolize]
    steps:
      - command: "python3 scripts/beta.py"
        severity: silent
        escalation: "beta skipped"
  gamma:
    section: "0c"
    title: "gamma heartbeat-only"
    gate: null
    default: "1"
    source: [heartbeat]
    steps:
      - command: "python3 scripts/gamma.py"
        when_env: LIMEN_GAMMA_ON
        severity: advisory
        escalation: "gamma failed"
"""


def _mod():
    spec = importlib.util.spec_from_file_location("beat_sensors_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _registry(tmp_path):
    p = tmp_path / "sensors.yaml"
    p.write_text(FIXTURE, encoding="utf-8")
    return p


def test_list_counts_all_sensors(tmp_path, capsys):
    m = _mod()
    m.list_sensors(_registry(tmp_path))
    out = capsys.readouterr().out
    assert "3 sensors" in out
    assert "alpha" in out and "beta" in out and "gamma" in out


def test_dry_run_metabolize_respects_gate_default(tmp_path, capsys, monkeypatch):
    m = _mod()
    monkeypatch.delenv("LIMEN_ALPHA", raising=False)
    monkeypatch.delenv("LIMEN_BETA", raising=False)
    m.run("metabolize", dry_run=True, registry=_registry(tmp_path))
    out = capsys.readouterr().out
    # alpha default=1 → its command shows; beta default=0 → header only, no command
    assert "$ python3 scripts/alpha.py" in out
    assert "── 0b. beta check ──" in out
    assert "$ python3 scripts/beta.py" not in out


def test_gate_env_override_enables_beta(tmp_path, capsys, monkeypatch):
    m = _mod()
    monkeypatch.setenv("LIMEN_BETA", "1")
    m.run("metabolize", dry_run=True, registry=_registry(tmp_path))
    assert "$ python3 scripts/beta.py" in capsys.readouterr().out


def test_source_filter_and_when_env(tmp_path, capsys, monkeypatch):
    m = _mod()
    # gamma is heartbeat-only → absent from metabolize
    m.run("metabolize", dry_run=True, registry=_registry(tmp_path))
    assert "gamma" not in capsys.readouterr().out
    # in heartbeat, gamma's step only shows when LIMEN_GAMMA_ON is set
    monkeypatch.delenv("LIMEN_GAMMA_ON", raising=False)
    m.run("heartbeat", dry_run=True, registry=_registry(tmp_path))
    out = capsys.readouterr().out
    assert "── 0c. gamma heartbeat-only ──" in out
    assert "$ python3 scripts/gamma.py" not in out
    monkeypatch.setenv("LIMEN_GAMMA_ON", "1")
    m.run("heartbeat", dry_run=True, registry=_registry(tmp_path))
    assert "$ python3 scripts/gamma.py" in capsys.readouterr().out


def test_reload_env_loads_written_file(tmp_path):
    """reload_env re-sources a shell-style env file into os.environ (the creds-hydrate → ~/.limen.env
    ordering, now declared data). conftest autouse restores os.environ after the test."""
    m = _mod()
    envf = tmp_path / ".limen.env"
    envf.write_text('export FOO_RELOAD_KEY="bar123"\n# a comment\nBAZ_RELOAD=qux\n', encoding="utf-8")
    os.environ.pop("FOO_RELOAD_KEY", None)
    os.environ.pop("BAZ_RELOAD", None)
    m._load_env_file(envf)
    assert os.environ["FOO_RELOAD_KEY"] == "bar123"  # export + quotes stripped
    assert os.environ["BAZ_RELOAD"] == "qux"


def test_reload_env_missing_file_is_fail_open(tmp_path):
    m = _mod()
    m._load_env_file(tmp_path / "does-not-exist.env")  # must not raise


def test_real_registry_derives_nonempty_metabolize_loop(capsys):
    """Smoke test on the SHIPPED registry: metabolize.sh now derives its whole sensor loop from
    sensors.yaml (the hand-wired blocks were deleted once proven equivalent). A dry --run against the
    real registry must emit the full sensor pass (headers for ~20 sensors) and exit 0. Guards against a
    registry that becomes empty/unparseable and silently turns the live beat into a no-op sensor pass."""
    m = _mod()
    rc = m.run("metabolize", dry_run=True, registry=REAL_REGISTRY)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count("── ") >= 15
    assert "scripts/creds-hydrate.py --apply" in out


def test_scheduled_sensor_is_identity_agnostic_and_stamps_only_when_due(tmp_path, monkeypatch):
    m = _mod()
    registry = tmp_path / "scheduled.yaml"
    registry.write_text(
        """\
sensors:
  completely-renamed-sentinel:
    section: heartbeat
    title: renamed sentinel
    gate: null
    default: "1"
    source: [heartbeat]
    cadence: {env: TEST_SENTINEL_CADENCE, default: 3}
    timeout: {env: TEST_SENTINEL_TIMEOUT, default: 9}
    steps:
      - command: "python3 scripts/example.py"
        severity: silent
        escalation: skipped
""",
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(m, "_run_command", lambda command, **kwargs: calls.append((command, kwargs)) or 0)
    voice_dir = tmp_path / "voices"

    # No prior stamp closes the restart/starvation hole, even off modulo.
    assert m.run("heartbeat", registry=registry, scheduled_only=True, beat=1, loop_max=60, voice_dir=voice_dir) == 0
    assert len(calls) == 1
    assert calls[0][1]["timeout"] == 9
    assert (voice_dir / "completely-renamed-sentinel").exists()

    # Fresh stamp + off modulo skips; modulo cadence fires again.
    assert m.run("heartbeat", registry=registry, scheduled_only=True, beat=2, loop_max=60, voice_dir=voice_dir) == 0
    assert len(calls) == 1
    assert m.run("heartbeat", registry=registry, scheduled_only=True, beat=3, loop_max=60, voice_dir=voice_dir) == 0
    assert len(calls) == 2

    # A malformed live override degrades to the declared registry default; it never silently
    # removes the timeout/cadence ceiling.
    monkeypatch.setenv("TEST_SENTINEL_CADENCE", "not-a-number")
    monkeypatch.setenv("TEST_SENTINEL_TIMEOUT", "0")
    sensor = m.load_sensors(registry)["completely-renamed-sentinel"]
    assert m._cadence(sensor) == 3
    assert m._positive_int(sensor["timeout"]) == 9


def test_args_when_and_omega_capabilities_do_not_depend_on_sensor_id(tmp_path, monkeypatch, capsys):
    m = _mod()
    registry = tmp_path / "capabilities.yaml"
    registry.write_text(
        """\
sensors:
  arbitrary.future.id:
    section: heartbeat
    title: arbitrary future sensor
    gate: null
    source: [heartbeat]
    timeout: 7
    steps:
      - command: "python3 scripts/arbitrary.py base"
        args_when:
          - env: TEST_ARBITRARY_APPLY
            default: "0"
            equals: "1"
            args: ["--apply", "two words"]
        severity: silent
        escalation: skipped
    omega_eligible:
      - label: arbitrary parity
        tier: det
        command: "python3 scripts/arbitrary.py check"
""",
        encoding="utf-8",
    )
    step = m.load_sensors(registry)["arbitrary.future.id"]["steps"][0]
    monkeypatch.delenv("TEST_ARBITRARY_APPLY", raising=False)
    assert m._step_command(step) == "python3 scripts/arbitrary.py base"
    monkeypatch.setenv("TEST_ARBITRARY_APPLY", "1")
    assert m._step_command(step) == "python3 scripts/arbitrary.py base --apply 'two words'"

    assert m.list_omega(registry) == 0
    assert capsys.readouterr().out == (
        "arbitrary.future.id\t0\tdet\tarbitrary parity\tpython3 scripts/arbitrary.py check\t7\n"
    )
    calls = []
    monkeypatch.setattr(m, "_run_command", lambda command, **kwargs: calls.append((command, kwargs)) or 0)
    assert m.run_omega("arbitrary.future.id", 0, registry=registry) == 0
    assert calls == [("python3 scripts/arbitrary.py check", {"timeout": 7, "quiet": False})]


def test_renamed_omega_capability_without_timeout_is_typed_and_executes(tmp_path, monkeypatch, capsys):
    m = _mod()
    registry = tmp_path / "no-timeout-capability.yaml"
    registry.write_text(
        """\
sensors:
  independently.renamed.no-timeout.v47:
    section: heartbeat
    title: independently renamed future sensor
    gate: null
    source: [metabolize]
    steps:
      - command: "python3 scripts/arbitrary.py beat"
        severity: silent
        escalation: skipped
    omega_eligible:
      - label: independently renamed fixed point
        tier: det
        command: "python3 scripts/arbitrary.py verify"
""",
        encoding="utf-8",
    )

    assert m.list_omega(registry) == 0
    assert capsys.readouterr().out == (
        "independently.renamed.no-timeout.v47\t0\tdet\tindependently renamed fixed point\t"
        "python3 scripts/arbitrary.py verify\tnull\n"
    )

    calls = []
    monkeypatch.setattr(m, "_run_command", lambda command, **kwargs: calls.append((command, kwargs)) or 0)
    assert m.run_omega("independently.renamed.no-timeout.v47", 0, registry=registry) == 0
    assert calls == [("python3 scripts/arbitrary.py verify", {"timeout": None, "quiet": False})]


def test_command_timeout_kills_the_bounded_process_group():
    m = _mod()
    command = f"{sys.executable} -c 'import time; time.sleep(5)'"
    assert m._run_command(command, timeout=1, quiet=True) == 124


CANARY_FIXTURE = """\
sensors:
  live-lane-sensor:
    section: heartbeat
    title: live lane scheduled sensor
    gate: null
    source: [heartbeat]
    cadence: {env: TEST_CANARY_LIVE_CADENCE, default: 4}
    steps:
      - command: "python3 scripts/example.py"
        severity: silent
        escalation: skipped
  parked-organ:
    section: heartbeat
    title: metabolize-only scheduled organ (lever-parked)
    gate: null
    source: [metabolize]
    owner: observatory
    cadence: {env: TEST_CANARY_PARKED_CADENCE, default: 24}
    steps:
      - command: "python3 scripts/example.py"
        severity: silent
        escalation: skipped
  unscheduled:
    section: "0x"
    title: no cadence — outside the canary's scope
    gate: null
    source: [metabolize]
    steps:
      - command: "python3 scripts/example.py"
        severity: silent
        escalation: skipped
"""


def _canary_setup(tmp_path):
    registry = tmp_path / "canary.yaml"
    registry.write_text(CANARY_FIXTURE, encoding="utf-8")
    voice_dir = tmp_path / "voices"
    voice_dir.mkdir()
    return registry, voice_dir


def test_canary_never_ran_live_lane_exits_1_and_names_the_sensor(tmp_path, capsys):
    """The mechanized canary ritual: a live-lane (heartbeat-source) scheduled sensor with no voice
    stamp is exactly the post-#921 defect class — merged, declared, never observed live."""
    m = _mod()
    registry, voice_dir = _canary_setup(tmp_path)
    assert m.canary(registry=registry, loop_max=60, voice_dir=voice_dir) == 1
    out = capsys.readouterr().out
    assert "NEVER-RAN live-lane-sensor" in out
    assert "unscheduled" not in out  # no cadence → outside the canary's scope


def test_canary_fresh_stamps_are_green(tmp_path, capsys):
    m = _mod()
    registry, voice_dir = _canary_setup(tmp_path)
    for sid in ("live-lane-sensor", "parked-organ"):
        (voice_dir / sid).write_text("now\n", encoding="utf-8")
    assert m.canary(registry=registry, loop_max=60, voice_dir=voice_dir) == 0
    assert "sensor-canary: OK" in capsys.readouterr().out


def test_canary_stale_stamp_exits_1(tmp_path, capsys):
    """Bound is cadence × loop_max × 2 (twice the worst-case wall-clock for one cadence window):
    live-lane cadence 4 × loop_max 60 × 2 = 480 s — a stamp backdated past it must read STALE."""
    m = _mod()
    registry, voice_dir = _canary_setup(tmp_path)
    for sid in ("live-lane-sensor", "parked-organ"):
        stamp = voice_dir / sid
        stamp.write_text("old\n", encoding="utf-8")
    os.utime(voice_dir / "live-lane-sensor", (time.time() - 1000, time.time() - 1000))
    assert m.canary(registry=registry, loop_max=60, voice_dir=voice_dir) == 1
    out = capsys.readouterr().out
    assert "STALE live-lane-sensor" in out


def test_canary_metabolize_only_finding_is_owner_routed_not_red(tmp_path, capsys):
    """A metabolize-only scheduled sensor that never ran is usually an organ parked behind its
    activation lever (observatory-run) — the canary prints it routed to its owner but exits 0:
    a parked lever must never read as red every beat."""
    m = _mod()
    registry, voice_dir = _canary_setup(tmp_path)
    (voice_dir / "live-lane-sensor").write_text("now\n", encoding="utf-8")
    assert m.canary(registry=registry, loop_max=60, voice_dir=voice_dir) == 0
    out = capsys.readouterr().out
    assert "NEVER-RAN parked-organ" in out
    assert "owner observatory" in out
