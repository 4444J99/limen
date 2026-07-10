"""Focused tests for exact, dynamically paginated GITVS estate observations."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gitvs.py"


def _load():
    spec = importlib.util.spec_from_file_location("gitvs_uut", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(payload: dict, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, json.dumps(payload), "")


def test_owner_open_pr_counts_paginates_repository_totals(monkeypatch) -> None:
    module = _load()
    pages = [
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {"nameWithOwner": "example/a", "pullRequests": {"totalCount": 2}},
                            {"nameWithOwner": "example/b", "pullRequests": {"totalCount": 0}},
                        ],
                        "pageInfo": {"hasNextPage": True, "endCursor": "next-page"},
                    }
                }
            }
        },
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [{"nameWithOwner": "example/c", "pullRequests": {"totalCount": 7}}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        },
    ]
    calls: list[list[str]] = []

    def fake_gh(args, _token, timeout=60):
        calls.append(args)
        return _result(pages.pop(0))

    monkeypatch.setattr(module, "_gh", fake_gh)

    assert module._owner_open_pr_counts("example", "opaque") == {
        "example/a": 2,
        "example/b": 0,
        "example/c": 7,
    }
    assert "cursor=next-page" in calls[1]
    assert all("--author" not in call for call in calls)
    query = next(arg.removeprefix("query=") for arg in calls[0] if arg.startswith("query="))
    assert query.count("{") == query.count("}")


def test_owner_open_pr_counts_blocks_on_incomplete_remote_evidence(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_gh",
        lambda _args, _token, timeout=60: subprocess.CompletedProcess([], 1, "", "unavailable"),
    )
    assert module._owner_open_pr_counts("example", "opaque") is None
