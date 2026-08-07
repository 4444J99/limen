"""The metabolize sensor pass must KEEP what its sensors say, not just prove they ran.

``heartbeat-loop.sh`` runs the ``source:[metabolize]`` registry sensors hourly. Fifty-seven of them
emit well over a hundred lines, and the rung piped the whole pass through ``| tail -5`` — so every
finding from every sensor but the last was produced and immediately discarded.

Measured 2026-08-07: the ``review-harvest`` sensor (§0g3a, line 32 of the pass) ran in the 17:49
pass carrying unresolved agent findings, and no log anywhere in the estate recorded a word of it.
That sensor exists specifically to prove an agent review finding gets CONSUMED rather than merged
past; its own finding was thrown away by its runner. ``beat-sensors.py`` persists nothing itself —
a voice stamp records that a sensor VISITED, never what it said — which is the same
liveness-substituted-for-consumption defect one layer down, and it is why no stamp check would have
caught this.

The rung is tested by EXTRACTING it from the shipped script and executing it against a stub sensor
runner, in the same style as ``test_loop_self_load.py``. A grep-based test would pass on a rung whose
redirect had been reverted to a pipe inside a conditional; this one runs the real bytes and reads the
file that results.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"

GUARD_OPEN = 'if [ "${LIMEN_BEAT_DERIVE:-1}" = "1" ] && metabolize_pass_due; then'
LOG_REL = "logs/metabolize-sensors.log"

# The stub prints this many lines. It must exceed the old `tail -5` bound by enough that an
# early-sensor line is unambiguously outside the window — five would prove nothing.
STUB_LINES = 40
FIRST_MARKER = "0g3a-review-harvest-FINDING"  # printed FIRST, i.e. exactly what the pipe ate


def _rung_source() -> str:
    """The shipped rung, lifted verbatim from the loop body.

    Anchored on the guard's own opening line and closed at the next dedent to the loop body's four
    -space indent. Raises rather than returning an empty string if the rung moves — a test that
    silently stops covering anything is worse than a failing one.
    """
    lines = LOOP.read_text().splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == GUARD_OPEN), None)
    assert start is not None, f"guard line not found in {LOOP} — did the rung move?"
    for end in range(start + 1, len(lines)):
        if lines[end] == "    fi":
            return "\n".join(line[4:] if line.startswith("    ") else line for line in lines[start : end + 1])
    raise AssertionError("rung's closing `fi` not found at loop-body indent")


def _run(tmp_path: Path, *, lines: int = STUB_LINES, runs: int = 1) -> tuple[str, str]:
    """Execute the real rung with a stub sensor runner; return (stdout, durable-log-contents).

    The stub stands in for ``beat-sensors.py`` at the exact path the rung invokes, so the rung's own
    argv and redirect are what get exercised — not a paraphrase of them.
    """
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)

    stub = root / "scripts" / "beat-sensors.py"
    stub.write_text(
        "import sys\n"
        f"print({FIRST_MARKER!r})\n"
        f"for i in range({lines} - 1):\n"
        "    print(f'sensor line {i}')\n"
        # Non-zero on purpose: a pass reporting findings exits non-zero, and the rung's `|| true`
        # must keep the beat alive WITHOUT that becoming a reason to drop the output.
        "sys.exit(1)\n"
    )

    harness = tmp_path / "rung.sh"
    harness.write_text(
        "set -u\n"
        f'LIMEN_ROOT="{root}"\n'
        'VOICED="$LIMEN_ROOT/logs/.voice"\n'
        "c=1\n"
        "MAX=120\n"
        "metabolize_pass_due() { return 0; }\n"
        "stamp() { :; }\n" + ("\n".join([_rung_source()] * runs)) + "\n"
    )

    proc = subprocess.run(
        ["bash", str(harness)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "LIMEN_BEAT_DERIVE": "1"},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    log = root / LOG_REL
    return proc.stdout, (log.read_text() if log.is_file() else "")


def test_the_full_pass_output_lands_in_a_durable_log(tmp_path: Path) -> None:
    """All of it, not a window. The pass is the estate's hourly read of 57 sensors."""
    _, log = _run(tmp_path)
    assert log, f"nothing was written to {LOG_REL} — the pass has no durable home again"
    assert len(log.splitlines()) == STUB_LINES


def test_an_early_sensors_finding_survives_the_rung(tmp_path: Path) -> None:
    """THE regression. review-harvest is line 32 of 117; under `| tail -5` its finding vanished."""
    _, log = _run(tmp_path)
    assert FIRST_MARKER in log, "the first sensor's finding was discarded — this is the 2026-08-07 defect"


def test_the_beat_log_stays_terse(tmp_path: Path) -> None:
    """Keeping the output must not mean dumping 120 lines into the beat log every hour.

    The five-line window was never the mistake — piping the ONLY copy through it was.
    """
    out, _ = _run(tmp_path)
    assert len(out.splitlines()) <= 5, out


def test_the_terse_summary_is_read_back_from_the_durable_log(tmp_path: Path) -> None:
    """The beat log's tail and the file must agree, or the summary is describing something else."""
    out, log = _run(tmp_path)
    assert out.splitlines() == log.splitlines()[-5:]


def test_the_log_is_truncated_not_appended(tmp_path: Path) -> None:
    """Bounded by construction — there is no rotation organ, and the latest pass is the answer."""
    _, log = _run(tmp_path, runs=2)
    assert len(log.splitlines()) == STUB_LINES, "the log grew across passes — it will grow forever"


def test_a_failing_pass_still_leaves_its_findings_behind(tmp_path: Path) -> None:
    """The stub exits 1. `|| true` keeps the beat alive; it must not also cost us the output."""
    out, log = _run(tmp_path)
    assert FIRST_MARKER in log
    assert out.strip(), "a non-zero pass printed nothing to the beat log"


def test_the_rung_does_not_pipe_the_sensor_runner_anywhere() -> None:
    """Guards the fix itself, scoped to CODE — the rung's comment quotes `| tail -5` deliberately.

    Three assertions in this lineage have already had to be narrowed for exactly this reason: a
    file-wide grep for the defect flags the documentation OF the defect. The invariant is about what
    the rung executes, so only non-comment lines are read.

    And `||` is not a pipe. The first cut of this assertion searched the runner region for `|` and
    fired on the rung's own `|| true` guard — the same over-broad-match mistake one character wide,
    which is why the logical-or is removed before the pipe is looked for rather than the region
    being hand-trimmed to dodge it.
    """
    code = [ln for ln in _rung_source().splitlines() if not ln.lstrip().startswith("#")]
    joined = "\n".join(code)
    assert "beat-sensors.py" in joined, "extraction lost the sensor runner — the rung moved"
    runner_region = joined.split("beat-sensors.py", 1)[1].split("stamp metabolize_pass", 1)[0]
    piped = runner_region.replace("||", "")
    assert "|" not in piped, f"the sensor runner is piped again: {runner_region!r}"
    assert LOG_REL in joined, "the rung no longer writes the durable pass log"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
