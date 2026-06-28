from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "resolve-codex-family-batch.py"


def _load():
    spec = importlib.util.spec_from_file_location("resolve_codex_family_batch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_codex_family_batch_records_public_proof_without_raw_text(tmp_path: Path, monkeypatch):
    resolver = _load()
    resolver.ROOT = tmp_path
    resolver.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    resolver.PRIORITY_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    resolver.SESSION_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    resolver.BATCH_RESOLUTION_RECEIPTS = tmp_path / "docs" / "prompt-batch-resolution-receipts.json"
    resolver.LOCAL_WORKTREE_BASES = [tmp_path / ".limen-worktrees"]

    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    resolver.PRIORITY_INDEX.parent.mkdir(parents=True)
    resolver.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "review_batches": [
                    {
                        "id": "prompt-batch-medium-family-test",
                        "band": "medium",
                        "lane": "family",
                        "session_count": 3,
                        "prompt_events": 6,
                        "unique_prompt_hashes": 4,
                        "families": {"session_lifecycle": 3},
                        "sources": {"codex-sessions": 3},
                        "session_keys": ["session-a", "session-b", "session-c"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    resolver.SESSION_INDEX.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "session_key": "session-a",
                        "path": str(raw_source),
                        "prompt_event_count": 2,
                        "prompt_hashes": ["hash-a", "hash-b"],
                        "worktree_slug": "limen-open",
                    },
                    {
                        "session_key": "session-b",
                        "path": str(raw_source),
                        "prompt_event_count": 3,
                        "prompt_hashes": ["hash-c"],
                        "worktree_slug": "limen-merged",
                    },
                    {
                        "session_key": "session-c",
                        "path": str(raw_source),
                        "prompt_event_count": 1,
                        "prompt_hashes": ["hash-d"],
                        "worktree_slug": "limen-absent",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(resolver, "resolve_repo", lambda root: ("organvm/limen", ["organvm/limen"]))
    monkeypatch.setattr(
        resolver,
        "branch_state",
        lambda repo, branch: {"name": branch, "sha": "abcdef123456"} if branch.endswith("limen-open") else None,
    )

    def exact_prs(_repo: str, branch: str):
        if branch.endswith("limen-open"):
            return [
                {
                    "number": 10,
                    "state": "OPEN",
                    "mergeStateStatus": "DIRTY",
                    "url": "https://github.com/organvm/limen/pull/10",
                    "headRefOid": "abcdef123456",
                }
            ]
        if branch.endswith("limen-merged"):
            return [
                {
                    "number": 11,
                    "state": "MERGED",
                    "url": "https://github.com/organvm/limen/pull/11",
                    "headRefOid": "123456abcdef",
                }
            ]
        return []

    monkeypatch.setattr(resolver, "exact_prs", exact_prs)
    monkeypatch.setattr(resolver, "broad_pr_hit_count", lambda _repo, root: 2 if root == "limen-absent" else 0)

    receipt = resolver.build_receipt("prompt-batch-medium-family-test")
    statuses = {root["root"]: root["status"] for root in receipt["roots"]}
    assert statuses == {
        "limen-open": "remote_pr_preserved",
        "limen-merged": "remote_pr_merged",
        "limen-absent": "owner_repo_routed_absent_branch",
    }
    assert receipt["status"] == "owner-recorded"
    assert receipt["roots"][2]["non_exact_broad_pr_hits"] == 2
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(receipt)

    resolver.BATCH_RESOLUTION_RECEIPTS.parent.mkdir(parents=True)
    resolver.BATCH_RESOLUTION_RECEIPTS.write_text(
        json.dumps({"version": 1, "generated_at": "old", "receipts": []}), encoding="utf-8"
    )
    resolver.append_receipt(receipt, replace=False)
    written = json.loads(resolver.BATCH_RESOLUTION_RECEIPTS.read_text(encoding="utf-8"))
    assert written["receipts"][0]["batch"] == "prompt-batch-medium-family-test"
    assert resolver.receipt_exists("prompt-batch-medium-family-test")
