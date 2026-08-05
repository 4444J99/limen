"""Tests for scripts/tabularius-organ.py --preflight — the Auto-Scaler workflow's admission gate.

board_publication_preflight() (cli/src/limen/tabularius.py) is a permanent fail-closed stub: the
local board-publication writer it used to gate was retired for the remote conduct broker, and the
kernel correctly refuses to revive it rather than fake an answer. That is a "cannot answer" for a
workflow-level preflight, not a "not ready" — before this fix, the adapter read the kernel's fixed
stub reason as a hard failure (exit 2), which failed .github/workflows/auto-scale.yml on every one
of its 4-hourly scheduled runs with no way to ever pass. These tests pin the adapter's mapping from
each PreserveResult shape to the workflow's actual soft-skip contract (rc==75 -> ready=false, no job
failure) without touching the kernel stub itself.
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "tabularius-organ.py"


def _mod():
    spec = importlib.util.spec_from_file_location("tabularius_organ_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_preflight_clear_admits_work():
    m = _mod()
    m.board_publication_preflight = lambda *_a, **_k: SimpleNamespace(reason="preflight-clear")
    assert m.main(["--preflight"]) == 0


def test_preflight_published_and_deferred_soft_skips():
    m = _mod()
    m.board_publication_preflight = lambda *_a, **_k: SimpleNamespace(
        reason="publication-in-flight", published=True, deferred=True, pr_number=42
    )
    assert m.main(["--preflight"]) == 75


def test_preflight_retired_writer_stub_soft_skips_not_fails(capsys):
    """The regression: the kernel's fixed 'remote-keeper-preflight-required' stub answer must map
    to the workflow's soft-skip (75), not its hard-failure (2) — this is the exact shape
    board_publication_preflight() has returned unconditionally since the local writer retired, so
    a hard failure here means the scheduled workflow can NEVER pass."""
    m = _mod()
    m.board_publication_preflight = lambda *_a, **_k: SimpleNamespace(
        reason="remote-keeper-preflight-required", published=False, deferred=False, pr_number=0
    )
    assert m.main(["--preflight"]) == 75
    assert "deferred to the remote keeper" in capsys.readouterr().err


def test_preflight_genuine_failure_still_fails_closed():
    """A real, non-stub failure reason (e.g. GitHub unavailable) must still hard-fail — the fix
    above targets exactly the retired-writer sentinel, not every non-clear result."""
    m = _mod()
    m.board_publication_preflight = lambda *_a, **_k: SimpleNamespace(
        reason="github-unavailable: rate limited", published=False, deferred=False, pr_number=0
    )
    assert m.main(["--preflight"]) == 2


if __name__ == "__main__":
    sys.exit(0)
