from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "github-contribution-balance.py"


def load_balance_module():
    spec = importlib.util.spec_from_file_location("github_contribution_balance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_screenshot_mix_prioritizes_reviews_and_commit_overage() -> None:
    mod = load_balance_module()
    counts = {"commits": 76, "issues": 11, "pull_requests": 12, "reviews": 1}

    report = mod.build_report(counts, login="4444j99", from_date=None, to_date=None)

    assert report["status"] == "needs_balance"
    assert report["actions"][0]["lane"] == "reviews"
    assert "Review an existing PR" in report["next_action"]
    assert {action["lane"] for action in report["actions"]} == {
        "commits",
        "issues",
        "pull_requests",
        "reviews",
    }


def test_balanced_mix_passes() -> None:
    mod = load_balance_module()
    counts = {"commits": 50, "issues": 20, "pull_requests": 20, "reviews": 10}

    report = mod.build_report(counts, login="4444j99", from_date=None, to_date=None)

    assert report["status"] == "balanced"
    assert report["actions"] == []
    assert "issue -> PR -> review" in report["next_action"]


def test_normalize_graphql_response() -> None:
    mod = load_balance_module()
    payload = {
        "data": {
            "viewer": {
                "login": "4444j99",
                "contributionsCollection": {
                    "totalCommitContributions": 76,
                    "totalIssueContributions": 11,
                    "totalPullRequestContributions": 12,
                    "totalPullRequestReviewContributions": 1,
                },
            }
        }
    }

    assert mod.normalize_counts(payload) == {
        "commits": 76,
        "issues": 11,
        "pull_requests": 12,
        "reviews": 1,
    }
