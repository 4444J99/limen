"""`limen streams` — the advertised form of the stream launcher, a pure delegate."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from click.testing import CliRunner

from limen.cli import main


def test_streams_help_names_the_round_trip():
    result = CliRunner().invoke(main, ["streams", "--help"])
    assert result.exit_code == 0
    assert "REOPEN" in result.output
    assert "--status" in result.output
    assert "--family" in result.output


def test_streams_is_a_pure_delegate_to_the_one_launcher():
    """The CLI must never grow its own opening logic — one launcher, one story. Pin the
    delegation: exactly one subprocess call, and its target is open-streams.sh."""
    src = (ROOT / "cli" / "src" / "limen" / "cli.py").read_text()
    body = src.split('@main.command("streams")', 1)[1].split("@main.command", 1)[0]
    assert body.count("subprocess.run") == 1, "the verb grew execution paths beyond the delegate"
    assert "open-streams.sh" in body
    assert "new-window" not in body and "new-session" not in body, "the verb grew launcher logic of its own"


def test_streams_status_runs_end_to_end():
    proc = subprocess.run(
        [sys.executable, "-c", "from limen.cli import main; main()", "streams", "--status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": str(ROOT / "cli" / "src"),
            "PATH": __import__("os").environ["PATH"],
            "HOME": __import__("os").environ["HOME"],
        },
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "openable" in proc.stdout
