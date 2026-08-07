"""The beat's rung runner — a rung that fails must say why, and the failure must have a reader.

Every organ call in ``heartbeat-loop.sh`` used to end ``2>&1 | tail -1 || true``. That idiom
destroys three things at once and they compound into total blindness:

  1. **The exit status.** A pipeline's ``$?`` is the LAST stage's, so it reports *tail's* status —
     essentially always 0. The trailing ``|| true`` is therefore decorative and nothing downstream
     can distinguish a hard failure from a clean run.
  2. **The diagnostic.** ``tail -1`` of a Python traceback is the closing line of the exception's own
     repr. When the exception carries a JSON body that is a bare ``}``.
  3. **The record.** Nothing is written down, so a rung can fail on every beat forever while the beat
     log, the enactment audit, and the organ-health face all stay green.

Measured 2026-08-07: the ``heal-board.py --canonical`` rung (#2014) failed on EVERY beat with
``conduct broker rejected request (500): Exceeded allowed rows written in Durable Objects free
tier``, emitting 61 diagnostic lines. The beat log received ``}``. Neither "Durable Objects" nor
"rejected request" appeared in ANY log file estate-wide, so twelve regressed board atoms stayed
regressed behind a rung that looked like it was working.

Like ``test_loop_self_load.py``, these tests EXTRACT the helper from the shipped script and execute
the real bytes rather than asserting on source text — a grep test would pass on a helper whose
branches had been reordered into uselessness.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"
GATE = ROOT / "scripts" / "check-beat-diagnostics.py"

ANCHOR_START = 'BEAT_RUNG_LOG="${LIMEN_BEAT_RUNG_LOG:-'
ANCHOR_END = "# BOUNDED WAKE"

# The real shape of the measured failure: a deep traceback whose FINAL line is the closing brace of
# a JSON error body, so `tail -1` yields `}` and the actual cause is one line above it.
QUOTA_BODY = (
    "Traceback (most recent call last):\n"
    '  File "client.py", line 46, in _request\n'
    "    with urllib.request.urlopen(request) as response:\n"
    "urllib.error.HTTPError: HTTP Error 500: Internal Server Error\n"
    "limen.conduct.broker.ConductError: conduct broker rejected request (500): {\n"
    '  "detail": "Exceeded allowed rows written in Durable Objects free tier."\n'
    "}"
)


def _helper_source() -> str:
    """The shipped rung runner, lifted verbatim from the loop.

    Raises rather than returning an empty string if the anchors move — a test that quietly stops
    covering anything is worse than a failing one.
    """
    text = LOOP.read_text()
    start = text.find(ANCHOR_START)
    assert start != -1, f"{ANCHOR_START!r} not found in {LOOP} — did the rung runner move?"
    end = text.find(ANCHOR_END, start)
    assert end != -1, f"{ANCHOR_END!r} not found after the rung runner in {LOOP}"
    body = text[start:end]
    assert "beat_run() {" in body and "trim_beat_rung_log() {" in body, "extraction missed a helper"
    return body


def _run(script: str, root: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Execute the extracted helper plus a caller snippet against a sandbox LIMEN_ROOT."""
    (root / "logs").mkdir(parents=True, exist_ok=True)
    full = f'LIMEN_ROOT="{root}"\n' + _helper_source() + "\n" + script
    return subprocess.run(
        ["bash", "-c", full],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LIMEN_ROOT": str(root), **(env or {})},
    )


def _ledger(root: Path) -> list[dict]:
    path = root / "logs" / "beat-rungs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ----------------------------------------------------------------- the happy path is unchanged
def test_succeeding_rung_still_prints_exactly_its_last_line(tmp_path):
    """Log volume must not change on the happy path, or the fix would not be adoptable."""
    res = _run('beat_run demo printf "one\\ntwo\\nthree\\n"', tmp_path)
    assert res.stdout == "three\n", res.stdout
    assert res.returncode == 0


def test_silent_rung_prints_nothing(tmp_path):
    res = _run("beat_run demo true", tmp_path)
    assert res.stdout == ""


# ------------------------------------------------------- the failure carries the real diagnostic
def test_failing_rung_surfaces_the_cause_not_the_last_line_of_its_repr(tmp_path):
    """The measured defect, directly: `tail -1` gave `}`; the runner must give the quota sentence."""
    body = tmp_path / "traceback.txt"
    body.write_text(QUOTA_BODY + "\n")
    res = _run(f"beat_run heal-board-canonical sh -c 'cat {body}; exit 1'", tmp_path)
    assert "Exceeded allowed rows written in Durable Objects free tier" in res.stdout
    assert "conduct broker rejected request (500)" in res.stdout
    assert "RUNG FAIL [heal-board-canonical] exit=1" in res.stdout
    # And the old behaviour is genuinely gone: the block is more than the bare closing brace.
    assert res.stdout.strip() != "}"


def test_failure_tail_is_bounded_by_its_parameter(tmp_path):
    """A noisy organ must not be able to flood the beat log."""
    body = "; ".join(f"echo line{i}" for i in range(200))
    res = _run(f"beat_run noisy sh -c '{body}; exit 3'", tmp_path, env={"LIMEN_RUNG_FAIL_LINES": "4"})
    assert "line199" in res.stdout
    assert "line150" not in res.stdout
    # banner + 4 lines + closing banner
    assert len([ln for ln in res.stdout.splitlines() if ln.startswith("line")]) == 4


def test_rung_failure_does_not_stop_the_beat(tmp_path):
    """`|| true` existed to keep the beat fail-open; the runner must preserve exactly that."""
    res = _run("beat_run boom false\necho SURVIVED", tmp_path)
    assert "SURVIVED" in res.stdout


# --------------------------------------------------------------------- the failure has a READER
def test_ledger_records_the_rungs_own_exit_code_not_tails(tmp_path):
    """The whole point of the change: an outcome a later predicate can read."""
    _run("beat_run alpha true\nbeat_run beta sh -c 'exit 7'", tmp_path)
    rows = _ledger(tmp_path)
    assert [(r["rung"], r["exit"]) for r in rows] == [("alpha", 0), ("beta", 7)]
    assert all(r["ts"].endswith("Z") for r in rows)


def test_ledger_rows_are_valid_json_one_per_rung(tmp_path):
    _run("beat_run alpha true\nbeat_run alpha false\nbeat_run gamma true", tmp_path)
    assert len(_ledger(tmp_path)) == 3


def test_trim_keeps_the_most_recent_records(tmp_path):
    """A trim must never manufacture a clean history by discarding an ongoing failure streak."""
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    ledger = tmp_path / "logs" / "beat-rungs.jsonl"
    ledger.write_text("".join(f'{{"ts":"t","rung":"r{i}","exit":0}}\n' for i in range(50)))
    _run("trim_beat_rung_log", tmp_path, env={"LIMEN_BEAT_RUNG_LOG_MAX": "10", "LIMEN_BEAT_RUNG_LOG_KEEP": "5"})
    rows = _ledger(tmp_path)
    assert [r["rung"] for r in rows] == [f"r{i}" for i in range(45, 50)]


def test_trim_is_a_noop_below_the_threshold(tmp_path):
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    ledger = tmp_path / "logs" / "beat-rungs.jsonl"
    ledger.write_text('{"ts":"t","rung":"r","exit":0}\n' * 3)
    _run("trim_beat_rung_log", tmp_path, env={"LIMEN_BEAT_RUNG_LOG_MAX": "10", "LIMEN_BEAT_RUNG_LOG_KEEP": "5"})
    assert len(_ledger(tmp_path)) == 3


# ------------------------------------------------------------------------------- the shipped tree
def test_no_rung_in_the_shipped_loop_hides_its_failure():
    """The estate-wide claim, checked against the real file rather than remembered."""
    body = [ln for ln in LOOP.read_text().splitlines() if not ln.lstrip().startswith("#")]
    offenders = [ln.strip() for ln in body if "2>&1 | tail -1" in ln]
    assert offenders == [], offenders


def test_gate_passes_on_the_shipped_tree():
    res = subprocess.run([sys.executable, str(GATE), "--check"], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


# ----------------------------------------------------------------- the gate's own two rungs bite
def _gate_module(tmp_root: Path):
    spec = importlib.util.spec_from_file_location("cbd", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = tmp_root
    mod.BASELINE = tmp_root / "baseline.txt"
    mod.LOOP = tmp_root / "scripts" / "heartbeat-loop.sh"
    mod.COVERED = ["scripts/heartbeat-loop.sh"]
    return mod


@pytest.fixture
def gate_tree(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "heartbeat-loop.sh").write_text(LOOP.read_text())
    (tmp_path / "baseline.txt").write_text("scripts/heartbeat-loop.sh 0\n")
    return tmp_path


def test_ratchet_rejects_a_reintroduced_blind_rung(gate_tree, capsys):
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    loop.write_text(loop.read_text() + '\npython3 "$LIMEN_ROOT/scripts/new-organ.py" 2>&1 | tail -1 || true\n')
    assert _gate_module(gate_tree).main(["--check"]) == 1
    assert "new-organ.py" in capsys.readouterr().err


def test_helper_integrity_catches_a_simplification_back_to_one_line(gate_tree, capsys):
    """The evasion the ratchet alone cannot see: gut the helper, and every count stays at zero.

    The mutation keeps BOTH banners and only swaps the multi-line tail back to ``tail -1``. A
    string-matching integrity check passes on this — which is why the gate runs the helper.
    """
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    text = loop.read_text()
    text = text.replace(
        'tail -n "${LIMEN_RUNG_FAIL_LINES:-15}" "$_br_out" 2>/dev/null',
        'tail -1 "$_br_out" 2>/dev/null',
    )
    loop.write_text(text)
    mod = _gate_module(gate_tree)
    assert mod.main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "drops a failing rung's real output" in err


def test_helper_integrity_catches_a_ledger_reporting_the_pipelines_status(gate_tree, capsys):
    """The original defect in miniature: record `$?` after a pipe and it is always 0."""
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    text = loop.read_text().replace("  _br_rc=$?\n", "  _br_rc=0\n")
    loop.write_text(text)
    mod = _gate_module(gate_tree)
    assert mod.main(["--check"]) == 1
    assert "not the rung's" in capsys.readouterr().err


def test_helper_integrity_catches_a_helper_that_stops_the_beat(gate_tree, capsys):
    """`|| true` existed to keep the beat fail-open; losing that is worse than the blindness."""
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    text = loop.read_text().replace('  rm -f "$_br_out" 2>/dev/null || true\n  return 0\n', '  return "$_br_rc"\n')
    loop.write_text(text)
    mod = _gate_module(gate_tree)
    assert mod.main(["--check"]) == 1
    assert "fail-open" in capsys.readouterr().err


def test_update_refuses_to_grow_the_baseline(gate_tree, capsys):
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    loop.write_text(loop.read_text() + "\npython3 x.py 2>&1 | tail -1 || true\n")
    mod = _gate_module(gate_tree)
    assert mod.main(["--update"]) == 1
    out = capsys.readouterr().out
    assert "shrink-only" in out
    # and it must NOT have written
    assert (gate_tree / "baseline.txt").read_text() == "scripts/heartbeat-loop.sh 0\n"
