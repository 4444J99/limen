from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "merge-drain.py"


def _load():
    spec = importlib.util.spec_from_file_location("merge_drain_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _R:
    def __init__(self, out: str):
        self.returncode = 0
        self.stdout = out
        self.stderr = ""


def test_conflict_wins_over_stale_failing_checks(monkeypatch):
    mod = _load()

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps({
                "state": "OPEN",
                "isDraft": False,
                "mergeable": "CONFLICTING",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            }))
        raise AssertionError(f"unexpected gh call: {args!r}")

    monkeypatch.setattr(mod, "gh", fake_gh)

    assert mod.assess(("organvm/domus-genoma", 185)) == (
        "organvm/domus-genoma",
        185,
        "CONFLICT",
    )
