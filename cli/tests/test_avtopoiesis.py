"""AVTOPOIESIS gate — the durable predicate that the gate stays LIQUID, not a solid.

It proves the gate discovers its door-list from the living heartbeat (never a hand-roster),
includes ITSELF as a door (operational closure), scores three bounded tenses, regenerates an
identical verdict each run (idempotent), and that strict-mode's exit code tracks the audit.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "avtopoiesis.py"


def _run(*args):
    # pin LIMEN_ROOT to this repo so the gate is deterministic regardless of suite-wide env pollution
    env = {**os.environ, "LIMEN_ROOT": str(ROOT)}
    return subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True, env=env)


def _audit():
    r = _run("--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_discovers_doors_from_heartbeat():
    v = _audit()
    assert v["summary"]["total"] >= 5
    # discovered from the heartbeat, not a roster: known organs appear
    assert "nomenclator" in {d["key"] for d in v["doors"]}


def test_includes_itself():
    # operational closure — the gate is a door in its own audit
    assert "avtopoiesis" in {d["key"] for d in _audit()["doors"]}


def test_three_tenses_bounded():
    for d in _audit()["doors"]:
        assert set(d["tenses"]) == {"past", "present", "future"}
        assert 0.0 <= d["score"] <= 1.0
        assert all(0.0 <= val <= 1.0 for val in d["tenses"].values())


def test_idempotent():
    assert _run("--json").stdout == _run("--json").stdout


def test_strict_exit_tracks_audit():
    v = _audit()
    assert _run("--strict").returncode == (1 if v["summary"]["below"] > 0 else 0)
