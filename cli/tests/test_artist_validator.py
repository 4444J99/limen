import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "organs" / "artist" / "validate-artist.py"


def run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_artist_chamber_fleet_passes():
    result = run_validator("--fleet", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_artist_validator_rejects_missing_artist_gate(tmp_path):
    chamber = tmp_path / "broken-chamber.yaml"
    chamber.write_text(
        """
id: broken
name: Broken chamber
member:
  body: test body
mandate:
  description: stage a review package
standing:
  current: RAW
next_standing: CATALOGED
standard:
  rubric: real rubric
  evidence:
    - KERNEL.md
governance:
  artist_gate: false
human_gates:
  - artist approval
artifacts:
  next_reviewable_output: test review packet
""".lstrip()
    )

    result = run_validator(chamber)
    assert result.returncode == 1
    assert "Rule #2 violation: governance.artist_gate must be true" in result.stdout
