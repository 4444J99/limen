"""The beat's rung runner — a rung that fails must say why, and the failure must have a reader.

Every organ call in ``heartbeat-loop.sh`` used to end ``2>&1 | tail -1 || true``. That idiom
destroys three things at once and they compound into total blindness:

  1. **The exit status — discarded, not destroyed** (corrected 2026-08-07). ``heartbeat-loop.sh``
     sets ``pipefail``, so the pipeline does exit with the ORGAN's status (measured: rc=9 through
     ``| tail -1`` under ``pipefail``, rc=0 without). The trailing ``|| true`` was load-bearing,
     and what it bore was dropping that status at the call site, uncaptured — so nothing
     downstream could distinguish a hard failure from a clean run.
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
def test_no_tail_1_rung_survives_in_the_shipped_loop():
    """The estate-wide claim, checked against the real file rather than remembered.

    Scoped to ``tail -1`` deliberately: that is what #2050 converted. The wider-N sites are
    counted by the gate's ratchet against a declared, non-zero ceiling — see
    ``test_the_gate_sees_every_tail_width``, which is the check this test used to stand in for
    and could not.
    """
    body = [ln for ln in LOOP.read_text().splitlines() if not ln.lstrip().startswith("#")]
    offenders = [ln.strip() for ln in body if "2>&1 | tail -1" in ln]
    assert offenders == [], offenders


def test_gate_passes_on_the_shipped_tree():
    res = subprocess.run([sys.executable, str(GATE), "--check"], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


# ----------------------------------------------------------------- the gate's own two rungs bite
def _bare_gate_module():
    """The gate as shipped, unpatched — for testing its DEFINITION rather than its verdicts."""
    spec = importlib.util.spec_from_file_location("cbd_bare", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    """A minimal loop: the shipped rung runner, and no blind sites at all.

    Built from the real helper rather than from the whole loop on purpose. Once the ratchet's
    definition widened to every ``tail -N``, a fixture holding the entire loop carried 19
    declared-and-baselined sites of its own — so a ratchet test asserting "the gate went red"
    passed on those instead of on the site the test itself adds. The verdict must be caused by
    the mutation under test.
    """
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "heartbeat-loop.sh").write_text(_helper_source() + "\n" + ANCHOR_END + "\n")
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


# ------------------------------------------------------ the diagnosis itself, measured not argued
def test_pipefail_is_why_the_status_was_discarded_rather_than_destroyed():
    """The corrected defect #1, pinned to observable behaviour instead of prose.

    The first version of this reasoning said a pipeline reports *tail's* status. Under
    ``pipefail`` it does not — it reports the organ's. That matters because it names the actual
    hole: the status EXISTED at the call site and ``|| true`` dropped it uncaptured, so the fix
    had to be a recorder, not a rescue. It also means removing ``pipefail`` from the loop would
    silently upgrade the estate to the harder defect, which is what this test guards.
    """
    fail = 'sh -c "echo boom; exit 9" 2>&1 | tail -1'
    with_pf = subprocess.run(["bash", "-c", f"set -uo pipefail; {fail}"], capture_output=True, text=True)
    without_pf = subprocess.run(["bash", "-c", fail], capture_output=True, text=True)
    assert with_pf.returncode == 9, "pipefail must carry the organ's status through tail"
    assert without_pf.returncode == 0, "without pipefail tail really does swallow the status"
    assert "set -uo pipefail" in LOOP.read_text(), "the loop lost pipefail — defect #1 is now real"


# ------------------------------------------- the definition itself, which was wrong once already
@pytest.mark.parametrize(
    "idiom",
    [
        "python3 organ.py 2>&1 | tail -1 || true",
        "python3 organ.py 2>&1 | tail -2 || true",
        "python3 organ.py 2>&1 | tail -6 || true",
        "python3 organ.py 2>&1 | tail -n 1 || true",
        "python3 organ.py 2>&1 | tail -n 3 || true",
        "python3 organ.py 2>&1|tail -4 || true",
        "python3 organ.py 2>&1 | tail",  # bare tail defaults to 10 and loses the status too
    ],
)
def test_the_gate_sees_every_tail_width(idiom):
    """The correction: the status is forfeited at EVERY N, so the pattern may not pin N.

    The first cut matched only ``-1``/``-n 1``. It therefore certified heartbeat-loop.sh as clean
    with 19 blind rungs in it, sync-release.sh and drain.sh among them.
    """
    assert _bare_gate_module().BLIND.search(idiom), idiom


@pytest.mark.parametrize(
    "benign",
    [
        'echo "$out" | tail -4',  # the loop's real case: tail an already-captured variable
        "git log --oneline | tail -3",
    ],
)
def test_a_display_pipe_without_stderr_merge_is_not_a_site(benign):
    """`2>&1` is the discriminator. Without it there is no organ status being thrown away."""
    assert not _bare_gate_module().BLIND.search(benign), benign


def test_ratchet_rejects_a_reintroduced_blind_rung_at_a_wider_width(gate_tree, capsys):
    """The exact regression the narrow pattern let through, now a red check."""
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    loop.write_text(loop.read_text() + '\nbash "$LIMEN_ROOT/scripts/new-organ.sh" 2>&1 | tail -3 || true\n')
    assert _gate_module(gate_tree).main(["--check"]) == 1
    assert "new-organ.sh" in capsys.readouterr().err


def test_the_report_does_not_claim_zero_while_sites_remain(gate_tree, capsys):
    """A gate that prints the all-clear over a non-zero count is how the blindness survived it."""
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    loop.write_text(loop.read_text() + '\nbash "$LIMEN_ROOT/scripts/held.sh" 2>&1 | tail -3 || true\n')
    (gate_tree / "baseline.txt").write_text("scripts/heartbeat-loop.sh 1\n")  # declared, not new
    mod = _gate_module(gate_tree)
    assert mod.main(["--check"]) == 0  # within its declared ceiling: not a violation
    out = capsys.readouterr().out
    assert "no rung hides the reason it failed" not in out
    assert "1 blind site(s) held at baseline, none new" in out


def test_the_report_claims_zero_only_when_it_is_true(gate_tree, capsys):
    """The fixture is already that state — the helper and no blind sites."""
    mod = _gate_module(gate_tree)
    assert mod.main(["--check"]) == 0
    assert "no rung hides the reason it failed" in capsys.readouterr().out


def test_update_refuses_to_grow_the_baseline(gate_tree, capsys):
    loop = gate_tree / "scripts" / "heartbeat-loop.sh"
    loop.write_text(loop.read_text() + "\npython3 x.py 2>&1 | tail -1 || true\n")
    mod = _gate_module(gate_tree)
    assert mod.main(["--update"]) == 1
    out = capsys.readouterr().out
    assert "shrink-only" in out
    # and it must NOT have written
    assert (gate_tree / "baseline.txt").read_text() == "scripts/heartbeat-loop.sh 0\n"
