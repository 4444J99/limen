"""The pinned-interpreter estate. heartbeat-loop.sh must SELF-BOOTSTRAP its venv (573 WARNs
2026-07-09→07-14 while the prescribed remedy sat unrun — a sensor without an effector), and
reclaim-generated-state must never eat the pinned interpreters: ``.venv`` is on its
GENERATED_NAMES allowlist, so an unexempted bootstrap and the substrate reclaim would fight
forever (create → reclaim → recreate)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"
RECLAIM = ROOT / "scripts" / "reclaim-generated-state.py"


def test_loop_bootstraps_and_health_checks_the_pinned_venv():
    text = LOOP.read_text(encoding="utf-8")
    assert 'python3 -m venv --copies "$LIMEN_ROOT/.venv"' in text, "self-heal bootstrap missing"
    assert re.search(r"pip.+install.+--editable.+\$LIMEN_ROOT/cli", text), "editable limen install missing"
    # the health predicate must be import-based: a bare -x check passes a partial bootstrap
    # (venv created, pip failed) while every `python3 -m limen` beat step dies
    assert "import limen" in text, "venv health must verify the limen import, not just -x"
    # the WARN fallback (loud, never dead-stop) must survive as the bootstrap-failed path
    assert "using system python" in text, "fail-open WARN fallback removed"


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_reclaim_exempts_pinned_venvs_but_not_other_generated_state(tmp_path):
    repo = tmp_path / "limen"
    repo.mkdir()
    _git(["init", "-q"], repo)
    (repo / ".gitignore").write_text(".venv/\n__pycache__/\n")
    for d in (".venv", "cli/.venv", "web/.venv", "__pycache__"):
        (repo / d).mkdir(parents=True)
        (repo / d / "marker.txt").write_text("x")

    env = dict(os.environ, LIMEN_ROOT=str(repo))
    r = subprocess.run(
        [sys.executable, str(RECLAIM), "--root", str(repo), "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    samples = [line for row in payload["changed"] for line in row["sample"]]
    assert "Would remove __pycache__/" in samples, samples
    assert "Would remove web/.venv/" in samples, "a NON-pinned .venv is still generated debris"
    assert "Would remove .venv/" not in samples, "the pinned daemon venv must be exempt"
    assert "Would remove cli/.venv/" not in samples, "the editable-install venv must be exempt"
    # dry-run must not have deleted anything
    assert (repo / ".venv" / "marker.txt").exists()
