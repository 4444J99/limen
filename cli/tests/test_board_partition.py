"""The public board must not gain new client content.

``tasks.yaml`` is tracked in a PUBLIC repo and was a consumer of no publication gate, while
``scripts/publication-policy.py`` -- which thirteen other scripts derive from -- already declared
that named third parties stay off a public head. This suite covers the predicate that finally
makes the board a consumer of that rule.

The predicate is exercised through its CLI rather than by importing it: ``ROOT`` and ``BOARD`` are
resolved from the environment at import time, and a subprocess is the only way to test that
resolution honestly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-board-partition.py"
BASELINE = ROOT / "institutio" / "governance" / "board-partition-baseline.txt"


# A verification unit with no deadline is not a verification unit. Without `timeout=` a wedged CLI
# hangs the whole suite instead of failing one test, and a hang reports as "still running", never as
# red — the same shape as a check that cannot fail. 60s is far above the real runtime (these parse a
# tmp_path board of a few rows) and far below any CI patience.
_RUN_TIMEOUT_SECONDS = 60


def _run(board: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LIMEN_TASKS": str(board), "HOME": str(Path.home())},
        cwd=str(ROOT),
        timeout=_RUN_TIMEOUT_SECONDS,
    )


def _board(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "tasks.yaml"
    path.write_text(yaml.safe_dump({"tasks": rows}, sort_keys=False))
    return path


# --- the gate ---------------------------------------------------------------------------------


def test_the_shipped_board_is_green_against_its_baseline() -> None:
    """The pinned state. A red here means a NEW leak landed, which is the whole point."""
    result = _run(ROOT / "tasks.yaml", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_new_client_row_fails_the_gate(tmp_path: Path) -> None:
    board = _board(tmp_path, [{"id": "NEW-CLIENT-ROW", "title": "t", "repo": "organvm/victoroff-os"}])
    result = _run(board, "--check")
    assert result.returncode == 1
    assert "NEW-CLIENT-ROW" in result.stdout


def test_a_new_client_row_under_the_post_transfer_owner_also_fails(tmp_path: Path) -> None:
    """A rename must not launder a lane past the gate."""
    board = _board(tmp_path, [{"id": "NEW-CLIENT-ROW", "title": "t", "repo": "4444J99/victoroff-os"}])
    assert _run(board, "--check").returncode == 1


def test_the_operators_own_work_is_not_a_finding(tmp_path: Path) -> None:
    board = _board(
        tmp_path,
        [
            {"id": "MINE-1", "title": "t", "repo": "organvm/limen", "context": "surface the blocker"},
            {"id": "MINE-2", "title": "t", "repo": "organvm/domus-genoma", "context": "custody"},
        ],
    )
    result = _run(board, "--check")
    assert result.returncode == 0, result.stdout


def test_the_stale_owner_is_reported_as_its_own_finding_class(tmp_path: Path) -> None:
    """The root cause gets its own name, because it is what hid the other two.

    estate.yaml keys victoroff-os' private override on ``4444J99/``; the board still writes
    ``organvm/``, which misses the override and globs to ``governed_public``.
    """
    board = _board(tmp_path, [{"id": "STALE", "title": "t", "repo": "organvm/victoroff-os"}])
    out = _run(board).stdout
    assert "slug board-partition: STALE" in out
    assert "row board-partition: STALE" in out


# --- the marker rule --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "hydrate the credentials via creds-hydrate",  # "hydration" — an elevate-align keyword
        "record the podcast intro",  # "podcast" — a hospes keyword
        "the salon booking flow",  # "salon" — a mirror-mirror keyword
        "spiral out the retry backoff",  # "spiral" — an elevate-align keyword
        "potato masher refactor",  # "potato" — a micro-tato keyword
    ],
)
def test_routing_vocabulary_is_not_a_disclosure_marker(tmp_path: Path, text: str) -> None:
    """The register's keywords exist for routing, not confidentiality.

    Treating them as leak evidence is the same category error that put a client engagement at the
    top of the dispatch queue: a word list built for one purpose used as proof for another. These
    five produced 5 of the first run's 21 content findings, all false.
    """
    board = _board(tmp_path, [{"id": "GENERIC", "title": "t", "repo": "organvm/limen", "context": text}])
    result = _run(board, "--check")
    assert result.returncode == 0, f"{text!r} should not be a marker\n{result.stdout}"


@pytest.mark.parametrize("text", ["the Victoroff contract", "victoroff-os handoff", "Elevate Align parity"])
def test_a_token_that_names_a_lane_is_a_disclosure_marker(tmp_path: Path, text: str) -> None:
    board = _board(tmp_path, [{"id": "NAMES-A-LANE", "title": "t", "repo": "organvm/limen", "context": text}])
    result = _run(board, "--check")
    assert result.returncode == 1, f"{text!r} should be a marker\n{result.stdout}"


def test_content_findings_never_quote_the_content(tmp_path: Path) -> None:
    """Findings land in the same public repo, so a line that quoted the leak would republish it."""
    secret = "BBNC executive transformation proposal"
    board = _board(
        tmp_path,
        [{"id": "LEAK", "title": secret, "repo": "organvm/limen", "context": f"victoroff — {secret}"}],
    )
    out = _run(board).stdout
    assert "LEAK" in out
    assert secret not in out
    assert "BBNC" not in out


# --- baseline semantics -----------------------------------------------------------------------


def test_the_baseline_only_shrinks(tmp_path: Path) -> None:
    """A cleared finding is reported as stale, never as a failure -- the ratchet turns one way."""
    board = _board(tmp_path, [{"id": "MINE-1", "title": "t", "repo": "organvm/limen"}])
    result = _run(board, "--check")
    assert result.returncode == 0
    assert "no longer reproduces" in result.stdout


def test_the_shipped_baseline_is_parseable_and_carries_no_titles() -> None:
    lines = [
        line.strip() for line in BASELINE.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines, "baseline is empty — the pinned leak should be recorded"
    assert all(line.split(" ", 1)[0] in {"row", "content", "slug"} for line in lines)


# --- the --update ratchet ---------------------------------------------------------------------
#
# `test_the_baseline_only_shrinks` above asserts the ratchet at the `--check` surface, where a cleared
# finding is reported stale instead of failing. That surface cannot violate the invariant — it never
# writes. `--update` is the only write this predicate makes, and it re-pinned to whatever was on the
# board, additions included, while the module docstring, the baseline header, and that test's own name
# all said the list may only shrink. These tests cover the write.
#
# They redirect the baseline via LIMEN_BOARD_PARTITION_BASELINE rather than LIMEN_ROOT: relocating the
# root moves the partner-lane registries too, so `findings()` raises before any baseline logic runs.
# That un-redirectable write target is why the invariant went untested in the first place.


def _run_with_baseline(board: Path, baseline: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Deliberately NOT named `_run`: that name is taken above and Python resolves it at call time,
    so a second `_run` here would silently hijack all nine of the earlier call sites."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "LIMEN_TASKS": str(board),
            "LIMEN_BOARD_PARTITION_BASELINE": str(baseline),
            "HOME": str(Path.home()),
        },
        cwd=str(ROOT),
        timeout=_RUN_TIMEOUT_SECONDS,
    )


def _run_update(board: Path, baseline: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_with_baseline(board, baseline, "--update", *args)


def _client_row(task_id: str) -> dict[str, object]:
    return {"id": task_id, "title": "t", "repo": "4444J99/victoroff-os"}


def test_update_refuses_to_grow_the_baseline(tmp_path: Path) -> None:
    """The defect. A re-pin that ADDS a finding accepts a new public disclosure — it must not be silent."""
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# empty\n")
    board = _board(tmp_path, [_client_row("VIC-NEW-1")])

    result = _run_update(board, baseline)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "would GROW the baseline" in result.stdout
    assert "VIC-NEW-1" in result.stdout
    # The refusal must leave the file untouched — a partial write is the same leak, just quieter.
    assert baseline.read_text() == "# empty\n"


def test_update_still_shrinks_without_a_flag(tmp_path: Path) -> None:
    """Dropping a cleared entry tightens the gate, which is the direction the ratchet turns."""
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("row board-partition: GONE-1 is attributed to partner lane 4444J99/victoroff-os\n")
    board = _board(tmp_path, [{"id": "MINE-1", "title": "t", "repo": "organvm/limen"}])

    result = _run_update(board, baseline)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 dropped" in result.stdout
    assert "GONE-1" not in baseline.read_text()


def test_update_grows_only_when_the_disclosure_is_accepted_out_loud(tmp_path: Path) -> None:
    """Growth stays possible for a genuinely accepted disclosure, but the command has to say so."""
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# empty\n")
    board = _board(tmp_path, [_client_row("VIC-NEW-2")])

    result = _run_update(board, baseline, "--accept-new-disclosures")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ACCEPTED new disclosure" in result.stdout
    assert "VIC-NEW-2" in baseline.read_text()


def test_a_refused_growth_does_not_quietly_bank_the_shrink(tmp_path: Path) -> None:
    """Mixed state: the refusal keeps cleared entries pinned rather than half-applying the re-pin.

    Otherwise `--update` would be partly effective on exactly the runs where it was refused, and the
    baseline would drift under a command that reported failure.
    """
    baseline = tmp_path / "baseline.txt"
    original = "row board-partition: GONE-2 is attributed to partner lane 4444J99/victoroff-os\n"
    baseline.write_text(original)
    board = _board(tmp_path, [_client_row("VIC-NEW-3")])

    result = _run_update(board, baseline)

    assert result.returncode == 1
    assert "would have been dropped" in result.stdout
    assert baseline.read_text() == original


def test_accepting_disclosures_without_update_is_refused_not_ignored(tmp_path: Path) -> None:
    """The false green. Parsed alone the flag accepted nothing and could still exit 0.

    That is the worst possible pairing: the riskiest flag in this script returning SUCCESS for a
    decision it never recorded. A caller re-pinning a scrub would read the zero and believe the
    disclosure was banked. argparse's own error path exits 2 and writes to stderr.
    """
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# empty\n")
    board = _board(tmp_path, [{"id": "MINE-3", "title": "t", "repo": "organvm/limen"}])

    result = _run_with_baseline(board, baseline, "--accept-new-disclosures")

    assert result.returncode != 0, result.stdout + result.stderr
    assert "only means anything with --update" in result.stderr
    assert baseline.read_text() == "# empty\n"


def test_a_failed_baseline_write_leaves_the_previous_baseline_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomicity, proven where it matters: the ratchet FLOOR must never be readable half-written.

    `Path.write_text` truncated the target before writing, so an interrupted re-pin could leave an
    empty or partial floor — which either reddens every published row as "new" (a gate nobody can
    clear) or silently accepts whatever the truncation dropped. The write now lands via a temp file
    plus `os.replace`; this simulates the crash at the rename and asserts the old bytes survive.

    This one test imports the module rather than driving the CLI — the exception has to be injected
    mid-write, which no subprocess can do. `monkeypatch` is not optional here: `module.os` IS the
    stdlib `os`, so a bare assignment would break `os.replace` for every later test in the session.
    """
    import importlib.util

    baseline = tmp_path / "baseline.txt"
    original = "row board-partition: KEEP-1 is attributed to partner lane 4444J99/victoroff-os\n"
    baseline.write_text(original)

    monkeypatch.setenv("LIMEN_BOARD_PARTITION_BASELINE", str(baseline))
    spec = importlib.util.spec_from_file_location("_bp_atomic", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.BASELINE == baseline

    def _boom(src: object, dst: object) -> None:
        raise OSError("simulated crash between write and rename")

    monkeypatch.setattr(module.os, "replace", _boom)
    with pytest.raises(OSError):
        module._write_baseline(["row board-partition: NEW-1 is attributed to partner lane x/y"])

    # The floor is exactly what it was, and no temp file is left lying beside it.
    assert baseline.read_text() == original
    assert not list(tmp_path.glob(".*.tmp"))


def test_the_shipped_baseline_path_is_still_the_default(tmp_path: Path) -> None:
    """The redirect is for tests; an unset env var must resolve to the tracked file, not a temp path."""
    board = _board(tmp_path, [{"id": "MINE-2", "title": "t", "repo": "organvm/limen"}])
    out = _run(board).stdout
    assert "board-partition:" in out
    # A run with no redirect reports against the real baseline's contents (many pinned findings).
    assert "no longer reproduces" in out
