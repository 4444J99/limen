from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "resolve-legacy-session-batch.py"


def _load():
    spec = importlib.util.spec_from_file_location("resolve_legacy_session_batch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_legacy_session_batch_classifies_branch_proof_without_raw_text(tmp_path: Path, monkeypatch):
    resolver = _load()
    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")

    scan = {
        "batch": "prompt-batch-medium-legacy-session-review-test",
        "batch_summary": {
            "band": "medium",
            "lane": "legacy-session-review",
            "session_count": 4,
            "prompt_events": 12,
            "unique_prompt_hashes": 10,
            "owner_lanes": {
                "limen-root-subagent-cluster": 2,
                "external-local-project": 1,
                "limen-subagent-secret": 1,
            },
            "anchor_kinds": {},
            "repo_refs": {},
            "duplicate_session_keys": {},
        },
        "sessions": [
            {
                "root": "legacy-session-a",
                "session_key": "session-a",
                "source_exists": True,
                "owner_lane": "limen-root-subagent-cluster",
                "git_branches": ["feat/done"],
                "sensitive_keyword_counts": {"credential": 0},
            },
            {
                "root": "legacy-session-b",
                "session_key": "session-b",
                "source_exists": True,
                "owner_lane": "limen-root-subagent-cluster",
                "git_branches": ["feat/closed"],
                "sensitive_keyword_counts": {"credential": 0},
            },
            {
                "root": "legacy-session-c",
                "session_key": "session-c",
                "source_exists": True,
                "owner_lane": "external-local-project",
                "git_branches": ["HEAD"],
                "sensitive_keyword_counts": {"credential": 0},
            },
            {
                "root": "legacy-session-d",
                "session_key": "session-d",
                "source_exists": True,
                "owner_lane": "limen-subagent-secret",
                "git_branches": ["worktree-secret"],
                "sensitive_keyword_counts": {"credential": 3},
            },
        ],
    }

    class FakeScanner:
        @staticmethod
        def build_scan(_batch_id: str):
            return scan

    def branch_proof(branch: str):
        if branch == "feat/done":
            return {
                "branch": branch,
                "live_sha": None,
                "prs": [{"number": 10, "state": "MERGED", "url": "https://github.com/organvm/limen/pull/10"}],
            }
        if branch == "feat/closed":
            return {
                "branch": branch,
                "live_sha": None,
                "prs": [{"number": 11, "state": "CLOSED", "url": "https://github.com/organvm/limen/pull/11"}],
            }
        return {"branch": branch, "live_sha": None, "prs": []}

    monkeypatch.setattr(resolver, "load_scanner", lambda: FakeScanner)
    monkeypatch.setattr(resolver, "branch_proof", branch_proof)

    receipt = resolver.build_receipt("prompt-batch-medium-legacy-session-review-test")
    statuses = {root["session_key"]: root["status"] for root in receipt["roots"]}
    assert statuses == {
        "session-a": "legacy_session_pr_routed",
        "session-b": "legacy_session_closed_pr_recorded",
        "session-c": "legacy_session_external_context_recorded",
        "session-d": "legacy_session_sensitive_context_recorded",
    }
    assert receipt["status"] == "owner-recorded"
    assert "closed unmerged PR receipts" in " ".join(receipt["evidence"])
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(receipt)
