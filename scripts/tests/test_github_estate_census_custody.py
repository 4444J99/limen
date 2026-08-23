"""Custody regressions for the private GitHub estate census receipt."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("github_estate_census", ROOT / "scripts" / "github-estate-census.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_private_receipt_replaces_permissive_file_with_owner_only_mode(tmp_path: Path):
    target = tmp_path / "private-census.json"
    target.write_text("stale", encoding="utf-8")
    target.chmod(0o644)

    MODULE._write_private_json(target, {"private_rows": 79})

    assert _mode(target) == 0o600
    assert json.loads(target.read_text(encoding="utf-8")) == {"private_rows": 79}


def test_private_receipt_replaces_symlink_without_touching_its_target(tmp_path: Path):
    external = tmp_path / "external.json"
    external.write_text("unchanged", encoding="utf-8")
    target = tmp_path / "private-census.json"
    target.symlink_to(external)

    MODULE._write_private_json(target, {"private_rows": 79})

    assert not target.is_symlink()
    assert _mode(target) == 0o600
    assert external.read_text(encoding="utf-8") == "unchanged"


def test_repository_only_check_accepts_complete_denominator_with_partial_leaf_connections(monkeypatch):
    full = {
        "source_report": {
            "exhaustive": False,
            "cursor": {
                "repository": {
                    "exhaustive": True,
                    "expected_total": 314,
                    "known_count": 314,
                }
            },
        }
    }
    tracked = {"summary": {"repository_count": 314}}
    monkeypatch.setattr(MODULE, "collect", lambda **_kwargs: (full, tracked))
    monkeypatch.setattr(sys, "argv", ["github-estate-census.py", "--check-repositories", "--json"])

    assert MODULE.main() == 0


def test_repository_only_check_rejects_incomplete_denominator(monkeypatch):
    full = {
        "source_report": {
            "exhaustive": False,
            "cursor": {
                "repository": {
                    "exhaustive": True,
                    "expected_total": 314,
                    "known_count": 313,
                }
            },
        }
    }
    tracked = {"summary": {"repository_count": 313}}
    monkeypatch.setattr(MODULE, "collect", lambda **_kwargs: (full, tracked))
    monkeypatch.setattr(sys, "argv", ["github-estate-census.py", "--check-repositories", "--json"])

    assert MODULE.main() == 1


def test_metadata_carries_live_default_commit_oid_into_generation_input():
    tip = "a" * 40

    class Gitvs:
        @staticmethod
        def _gh_user(_args, timeout):
            assert timeout == 90
            payload = {
                "data": {
                    "repository": {
                        "issues": {"totalCount": 0},
                        "refs": {"totalCount": 1},
                        "defaultBranchRef": {
                            "name": "main",
                            "target": {"oid": tip, "statusCheckRollup": {"state": "SUCCESS"}},
                        },
                    }
                }
            }
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    result = MODULE._metadata(Gitvs(), "organvm/limen")

    assert result is not None
    assert result["default_sha"] == tip
