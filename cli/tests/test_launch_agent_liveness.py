"""Tests for scripts/launch-agent-liveness.py — the critical launchd-agent liveness invariant.

The launchctl and http-probe boundaries are monkeypatched (a stateful fake launchd), and the
active/quarantine plist dirs are redirected to tmp via env, so the tests are deterministic and
never touch the host's real launchd or ~/Library/LaunchAgents. Restore is proven by the fake's
recorded bootstrap/kickstart calls + the plist actually being copied out of quarantine.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "scripts" / "launch-agent-liveness.py"


class FakeLaunchctl:
    """Stateful launchd: `print` reports loaded-ness; `bootstrap`/`kickstart` mark a label loaded."""

    def __init__(self, loaded=None):
        self.loaded = set(loaded or [])
        self.calls = []

    def __call__(self, args, timeout=15):
        self.calls.append(list(args))
        verb = args[0]
        if verb == "print":
            label = args[1].split("/")[-1]
            return SimpleNamespace(returncode=0 if label in self.loaded else 1, stdout="", stderr="")
        if verb == "bootstrap":
            self.loaded.add(Path(args[2]).name[: -len(".plist")])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if verb == "kickstart":
            self.loaded.add(args[-1].split("/")[-1])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def load_module(tmp_path, monkeypatch, *, loaded=None):
    active = tmp_path / "LaunchAgents"
    disabled = tmp_path / "LaunchAgents.disabled"
    active.mkdir(exist_ok=True)
    disabled.mkdir(exist_ok=True)
    monkeypatch.setenv("LIMEN_LAUNCHAGENTS_DIR", str(active))
    monkeypatch.setenv("LIMEN_LAUNCHAGENTS_DISABLED_DIR", str(disabled))
    monkeypatch.setenv("LIMEN_LAUNCHCTL_UID", "501")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("lal_under_test", SPEC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.IS_DARWIN = True  # exercise the darwin path deterministically on any host
    m.time.sleep = lambda *a, **k: None  # no real settle delay
    fake = FakeLaunchctl(loaded=loaded)
    m._launchctl = fake
    return m, active, disabled, fake


def write_manifest(tmp_path, agents):
    p = tmp_path / "agents.json"
    p.write_text(json.dumps({"agents": agents}), encoding="utf-8")
    return p


def quarantined_plist(disabled, label):
    p = disabled / f"{label}.plist.20260709T145722Z"
    p.write_text("<plist/>", encoding="utf-8")
    return p


LOADED_AGENT = {"label": "com.x.loaded", "role": "loaded organ", "probe": {"kind": "launchd_loaded"}}


def test_all_alive_is_green(tmp_path, monkeypatch):
    m, *_ = load_module(tmp_path, monkeypatch, loaded={"com.x.loaded"})
    mani = write_manifest(tmp_path, [LOADED_AGENT])
    assert m.main(["--check", "--agents-file", str(mani)]) == 0


def test_down_recoverable_check_reds(tmp_path, monkeypatch):
    m, _active, disabled, _fake = load_module(tmp_path, monkeypatch, loaded=set())
    quarantined_plist(disabled, "com.x.loaded")
    mani = write_manifest(tmp_path, [LOADED_AGENT])
    # not loaded and no --apply → RED
    assert m.main(["--check", "--agents-file", str(mani)]) == 1


def test_apply_restores_from_quarantine(tmp_path, monkeypatch):
    m, active, disabled, fake = load_module(tmp_path, monkeypatch, loaded=set())
    quarantined_plist(disabled, "com.x.loaded")
    mani = write_manifest(tmp_path, [LOADED_AGENT])
    # effector: restore then re-check → GREEN (0)
    assert m.main(["--apply", "--check", "--agents-file", str(mani)]) == 0
    # the quarantined plist was placed active
    assert (active / "com.x.loaded.plist").exists()
    # launchd was actually driven
    verbs = [c[0] for c in fake.calls]
    assert "bootstrap" in verbs and "kickstart" in verbs
    assert "com.x.loaded" in fake.loaded


def test_unrecoverable_stays_red(tmp_path, monkeypatch):
    m, _active, _disabled, _fake = load_module(tmp_path, monkeypatch, loaded=set())
    # no plist anywhere → genuinely unrecoverable
    mani = write_manifest(tmp_path, [LOADED_AGENT])
    assert m.main(["--apply", "--check", "--agents-file", str(mani)]) == 1
    stamp = json.loads((tmp_path / "logs" / "launch-agent-liveness.json").read_text())
    assert stamp["unrecoverable"] == ["com.x.loaded"]


def test_apply_idempotent_when_alive(tmp_path, monkeypatch):
    m, _active, _disabled, fake = load_module(tmp_path, monkeypatch, loaded={"com.x.loaded"})
    mani = write_manifest(tmp_path, [LOADED_AGENT])
    assert m.main(["--apply", "--check", "--agents-file", str(mani)]) == 0
    # nothing to restore → no launchd mutation, only the read-only `print` probes
    assert [c for c in fake.calls if c[0] in ("bootstrap", "kickstart")] == []


def test_dry_run_makes_no_mutation(tmp_path, monkeypatch):
    m, active, disabled, fake = load_module(tmp_path, monkeypatch, loaded=set())
    quarantined_plist(disabled, "com.x.loaded")
    mani = write_manifest(tmp_path, [LOADED_AGENT])
    m.main(["--apply", "--dry-run", "--agents-file", str(mani)])
    assert not (active / "com.x.loaded.plist").exists()  # not copied
    assert [c for c in fake.calls if c[0] in ("bootstrap", "kickstart")] == []  # launchd untouched


def test_http_probe_down_detected(tmp_path, monkeypatch):
    m, *_ = load_module(tmp_path, monkeypatch, loaded=set())
    m._probe_http = lambda url, expect, timeout=6: False  # mint origin unreachable
    mani = write_manifest(
        tmp_path,
        [{"label": "com.x.mint", "role": "mint", "probe": {"kind": "http", "url": "http://localhost:8787/health"}}],
    )
    assert m.main(["--check", "--agents-file", str(mani)]) == 1


def test_registry_declares_live_loop_reachability():
    """The liveness rung must be REACHABLE from the live loop. The founding defect (2026-07-13):
    the registry declared `source: [metabolize]` with no cadence while the daemon's only derive call
    is `--run --source heartbeat --scheduled-only`, which runs cadence-declaring heartbeat sensors
    only — so the rung guarding the revenue rail had zero live executions ever. Reachability needs
    BOTH heartbeat in source AND a positive cadence, with the override envs declared in the panel.
    The sensor is found by capability (the step invoking this script), never by id."""
    registry = yaml.safe_load((ROOT / "institutio/governance/sensors.yaml").read_text(encoding="utf-8"))
    panel = yaml.safe_load((ROOT / "institutio/governance/parameters.yaml").read_text(encoding="utf-8"))
    matches = [
        sensor
        for sensor in registry["sensors"].values()
        if any("launch-agent-liveness.py" in str(step.get("command", "")) for step in sensor.get("steps") or [])
    ]
    assert len(matches) == 1, "exactly one sensor must own the liveness predicate"
    sensor = matches[0]
    assert "heartbeat" in (sensor.get("source") or []), "not reachable from the live scheduled lane"
    for capability in ("cadence", "timeout"):
        spec = sensor.get(capability)
        assert isinstance(spec, dict), f"{capability} must be a scheduled {{env, default}} mapping"
        assert int(spec["default"]) > 0
        assert spec["env"] in panel["parameters"], f"{spec['env']} not declared in parameters.yaml"
