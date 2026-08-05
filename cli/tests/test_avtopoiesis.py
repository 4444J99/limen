"""AVTOPOIESIS gate — the durable predicate that the gate stays LIQUID, not a solid.

It proves the gate discovers its door-list from the living heartbeat (never a hand-roster),
includes ITSELF as a door (operational closure), scores three bounded tenses, regenerates an
identical verdict each run (idempotent), and that strict-mode's exit code tracks the audit.
"""

import importlib.util
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
        assert set(d["evidence"]) == {"past", "present", "future"}
        assert 0.0 <= d["score"] <= 1.0
        assert all(0.0 <= val <= 1.0 for val in d["tenses"].values())
        assert all(0.0 <= float(item["score"]) <= 1.0 for item in d["evidence"].values())
        assert d["primary_gap"]["tense"] in {"past", "present", "future"}
        assert 0.0 <= d["primary_gap"]["gap"] <= 1.0


def test_past_tense_resolves_scripts_from_heartbeat_commands():
    doors = {door["key"]: door for door in _audit()["doors"]}

    assert doors["hygiene"]["tenses"]["past"] == 1.0
    assert doors["governance"]["tenses"]["past"] == 1.0
    assert doors["health"]["tenses"]["past"] == 1.0
    assert doors["financial"]["tenses"]["past"] == 1.0
    assert doors["corpus_feed"]["tenses"]["past"] == 1.0
    assert doors["life"]["tenses"]["past"] == 1.0


def test_script_name_fallback_does_not_cross_feed_doors():
    spec = importlib.util.spec_from_file_location("avtopoiesis_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    feed_scripts = {path.name for path in module._door_scripts("feed")}

    assert "corpus-feed.py" not in feed_scripts


def test_scheduled_registry_door_and_script_survive_arbitrary_id_rename(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("avtopoiesis_registry_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.delenv("LIMEN_BEAT_DERIVE", raising=False)

    scripts = tmp_path / "scripts"
    governance = tmp_path / "institutio" / "governance"
    scripts.mkdir(parents=True)
    governance.mkdir(parents=True)
    (scripts / "heartbeat-loop.sh").write_text(
        'if [ "${LIMEN_BEAT_DERIVE:-0}" = "1" ]; then\n'
        '  python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source heartbeat --scheduled-only\n'
        "fi\n",
        encoding="utf-8",
    )
    (scripts / "renamed-scan.py").write_text("from pathlib import Path\nPath('.').glob('*')\n", encoding="utf-8")
    (governance / "sensors.yaml").write_text(
        """\
sensors:
  arbitrary.future.id:
    section: heartbeat
    title: arbitrary future sensor
    source: [heartbeat]
    cadence: {env: TEST_ARBITRARY_CADENCE, default: 5}
    steps:
      - command: "python3 scripts/renamed-scan.py"
        severity: silent
        escalation: skipped
""",
        encoding="utf-8",
    )
    canon = {
        "discovery": {
            "source": "scripts/heartbeat-loop.sh",
            "beat_pattern": r'C_([A-Z][A-Z_]*)="\$\{LIMEN_BEAT_\1:-(\d+)\}"(?:[^#\n]*#\s*([^\n]*))?',
            "gate_pattern": r'\[\s*"\$\{LIMEN_%s:-0\}"\s*=\s*"1"\s*\]',
        }
    }

    doors = {door["key"]: door for door in module.discover_doors(canon)}
    assert doors["arbitrary.future.id"]["cadence"] == 5
    assert doors["arbitrary.future.id"]["dormant"] is True  # global derive canary remains dark
    assert {path.name for path in module._sensor_scripts_for("arbitrary.future.id")} == {"renamed-scan.py"}


def test_future_tense_counts_exact_door_tokens_not_substrings(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("avtopoiesis_future_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "his-hand-levers.json").write_text(
        json.dumps(
            {
                "levers": [
                    {"id": "feedback-only", "label": "collect feedback"},
                    {"id": "email-only", "label": "send email"},
                    {"id": "explicit-feed", "door": "feed", "label": "human gate"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert module.sense_future({"key": "mail", "name": "MAIL"}, {"senses": {"future": {}}}) == 1.0
    assert module.sense_future({"key": "feed", "name": "FEED"}, {"senses": {"future": {}}}) == 0.5
    evidence = module.assess_future({"key": "feed", "name": "FEED"}, {"senses": {"future": {}}})
    encoded = json.dumps(evidence, sort_keys=True)
    assert evidence["open_levers"] == 1
    assert "explicit-feed" not in encoded
    assert "human gate" not in encoded


def test_summary_reports_distance_from_ideal():
    v = _audit()
    s = v["summary"]

    assert 0.0 <= s["alive_ratio"] <= 1.0
    assert 0.0 <= s["mean_score"] <= 1.0
    assert s["distance_from_ideal"] == round(1.0 - s["mean_score"], 3)
    assert set(s["tense_averages"]) == {"past", "present", "future"}
    assert s["weakest_tense"] in {"past", "present", "future"}
    assert sum(s["below_by_primary_gap"].values()) == s["below"]


def test_idempotent():
    assert _run("--json").stdout == _run("--json").stdout


def test_strict_exit_tracks_audit():
    v = _audit()
    assert _run("--strict").returncode == (1 if v["summary"]["below"] > 0 else 0)
