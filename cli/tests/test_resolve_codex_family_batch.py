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


def test_repo_candidates_cover_redirected_family_roots():
    resolver = _load()

    cases = {
        "gen-organvm-i-theoria-scale-threshold-emergence-test-coverage-0620-86cd": [
            "organvm/scale-threshold-emergence"
        ],
        "gh-organvm-vi-koinonia-github-1-9bdf": [
            "organvm-vi-koinonia/.github",
            "organvm/dot-github--koinonia",
        ],
        "gh-organvm-iii-ergon-github-6-60b4": [
            "organvm-iii-ergon/.github",
            "organvm/dot-github--ergon",
        ],
        "gh-organvm-v-logos-github-6-bb3f": [
            "organvm-v-logos/.github",
            "organvm/dot-github--logos",
        ],
        "rev-hydra-stripe-sub-0a5d": ["organvm/card-trade-social"],
        "rev-exporter-gemini-adapter-67a2": ["organvm/a-i-chat--exporter"],
        "rev-mediaark-stripe-client-b01e": ["organvm/media-ark"],
        "rev-scrapper-tier-gate-3a82": ["organvm/public-record-data-scrapper"],
        "bld-tab-bookmark-manager-readme-a53a": ["organvm/tab-bookmark-manager"],
        "gh-organvm-i-theoria-growth-auditor-3-07bb": [
            "organvm/growth-auditor",
            "organvm-i-theoria/growth-auditor",
        ],
        "gh-4444j99-hokage-chess-21-61c1": ["4444J99/hokage-chess"],
        "discover-organvm-persona-fleet-4c28": ["organvm/persona-fleet"],
        "discover-organvm-cvrsvs-honorvm-fb46": ["organvm/cvrsvs-honorvm"],
        "discover-organvm-quick-fire--all-command-1053": ["organvm/quick-fire--all-command"],
        "gh-organvm-i-theoria-vigiles-aeternae-corpus-mythicum-4-5472": ["organvm/vigiles-aeternae--corpus-mythicum"],
        "gh-organvm-iii-ergon-sovereign-systems-elevate-align-20-3879": ["organvm/sovereign-systems--elevate-align"],
        "gh-organvm-iv-taxis-github-6-1f99": [
            "organvm-iv-taxis/.github",
            "organvm/dot-github--taxis",
        ],
        "discover-organvm-specvla-ergon--avditor-mvndi-2071": ["organvm/specvla-ergon--avditor-mvndi"],
        "gh-4444j99-relationship-pipeline-1-ae4d": [
            "organvm/relationship-pipeline",
            "4444J99/relationship-pipeline",
        ],
        "discover-organvm-conversation-corpus-engine-a600": [
            "organvm/conversation-corpus-engine",
            "organvm-i-theoria/conversation-corpus-engine",
        ],
        "rev-ledger-webhook-ratelimit-75f8": ["organvm/the-invisible-ledger"],
        "rev-ledger-postgres-adapter-ef35": [
            "organvm/the-invisible-ledger",
            "a-organvm/the-invisible-ledger",
        ],
        "rev-ledger-usage-tracker-f2b8": [
            "organvm/the-invisible-ledger",
            "a-organvm/the-invisible-ledger",
        ],
        "rev-ledger-stripe-org-setup-1af5": [
            "organvm/the-invisible-ledger",
            "a-organvm/the-invisible-ledger",
        ],
        "bld2-card-trade-social-billing-e47a": ["organvm/card-trade-social"],
        "gen-organvm-gamified-coach-interface-test-coverage-0620-6c74": ["organvm/gamified-coach-interface"],
        "gen-organvm-search-local--happy-hour-test-coverage-0620-d4d6": ["organvm/search-local--happy-hour"],
        "gen-organvm-select-or-left-or-right-or-test-coverage-0620-7740": ["organvm/select-or-left-or-right-or"],
        "gen-organvm-anon-hookup-now-test-coverage-0620-e77f": ["organvm/anon-hookup-now"],
        "gen-organvm-virgil-training-overlay-test-coverage-0620-8f15": ["organvm/virgil-training-overlay"],
        "rev-tabbookmark-freemium-e464": ["organvm/tab-bookmark-manager"],
        "gh-meta-organvm-github-10-7ca0": ["organvm/.github"],
        "gh-organvm-i-theoria-github-452-2e86": [
            "organvm-i-theoria/.github",
            "organvm/dot-github--theoria",
            "organvm/.github",
        ],
        "gh-organvm-ii-poiesis-github-6-98b7": [
            "organvm-ii-poiesis/.github",
            "organvm/dot-github--poiesis",
        ],
        "gh-organvm-vii-kerygma-github-7-1c2f": [
            "organvm-vii-kerygma/.github",
            "organvm/dot-github--kerygma",
        ],
        "gh-organvm-iv-taxis-org-dotgithub-2-1e9d": [
            "organvm-iv-taxis/.github",
            "organvm/dot-github--taxis",
        ],
        "gh-organvm-i-theoria-sovereign-ground-2-6dac": [
            "organvm-i-theoria/sovereign--ground",
            "organvm/sovereign--ground",
        ],
        "rev-domus-onboarding-041b": ["organvm/domus-genoma"],
        "rev-domus-billing-9bad": ["organvm/domus-genoma"],
        "gh-organvm-i-theoria-carrier-wave-zeitgeist-thesis-2-d6a2": ["organvm/carrier-wave--zeitgeist-thesis"],
        "bld-essay-pipeline-ci-1e41": ["organvm/essay-pipeline"],
        "discover-organvm-claude-runtime-state-8ac1": ["organvm/claude-runtime-state"],
        "rev-mirror-landing-0c22": ["organvm/mirror-mirror"],
        "rev-mirror-sharefile-oauth-706c": ["organvm/mirror-mirror"],
    }
    for root, expected in cases.items():
        assert resolver.repo_candidates(root) == expected


def test_resolve_codex_family_batch_preserves_per_session_family(tmp_path: Path, monkeypatch):
    resolver = _load()
    resolver.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    resolver.PRIORITY_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    resolver.SESSION_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    resolver.LOCAL_WORKTREE_BASES = [tmp_path / ".limen-worktrees"]

    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    resolver.PRIORITY_INDEX.parent.mkdir(parents=True)
    resolver.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "review_batches": [
                    {
                        "id": "prompt-batch-medium-family-mixed",
                        "band": "medium",
                        "lane": "family",
                        "session_count": 2,
                        "prompt_events": 8,
                        "unique_prompt_hashes": 4,
                        "families": {"session_lifecycle": 1, "github_review": 1},
                        "sources": {"codex-sessions": 2},
                        "session_keys": ["session-a", "session-b"],
                    }
                ],
                "session_items": [
                    {
                        "session_key": "session-a",
                        "family": "session_lifecycle",
                        "worktree_slug": "limen-session",
                        "prompt_events": 4,
                        "prompt_hashes": ["hash-a", "hash-b"],
                    },
                    {
                        "session_key": "session-b",
                        "family": "github_review",
                        "worktree_slug": "limen-github",
                        "prompt_events": 4,
                        "prompt_hashes": ["hash-c", "hash-d"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    resolver.SESSION_INDEX.write_text(
        json.dumps(
            {
                "sessions": [
                    {"session_key": "session-a", "path": str(raw_source), "worktree_slug": "wrong-a"},
                    {"session_key": "session-b", "path": str(raw_source), "worktree_slug": "wrong-b"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(resolver, "resolve_repo", lambda root: ("organvm/limen", ["organvm/limen"]))
    monkeypatch.setattr(resolver, "branch_state", lambda _repo, _branch: None)
    monkeypatch.setattr(resolver, "exact_prs", lambda _repo, _branch: [])
    monkeypatch.setattr(resolver, "broad_pr_hit_count", lambda _repo, _root: 0)

    receipt = resolver.build_receipt("prompt-batch-medium-family-mixed")
    by_root = {root["root"]: root for root in receipt["roots"]}
    assert by_root["limen-session"]["family"] == "session_lifecycle"
    assert by_root["limen-github"]["family"] == "github_review"
    assert by_root["limen-session"]["prompt_event_count"] == 4
    assert "family mix session_lifecycle 1, github_review 1" in receipt["evidence"][0]
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(receipt)


def test_resolve_historical_worktree_batch_uses_historical_evidence(tmp_path: Path, monkeypatch):
    resolver = _load()
    resolver.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    resolver.PRIORITY_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    resolver.SESSION_INDEX = resolver.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    resolver.LOCAL_WORKTREE_BASES = [tmp_path / ".limen-worktrees"]

    raw_source = tmp_path / "raw-claude-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")
    resolver.PRIORITY_INDEX.parent.mkdir(parents=True)
    resolver.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "review_batches": [
                    {
                        "id": "prompt-batch-medium-historical-worktree-review-test",
                        "band": "medium",
                        "lane": "historical-worktree-review",
                        "session_count": 1,
                        "prompt_events": 2,
                        "unique_prompt_hashes": 2,
                        "families": {"uncategorized": 1},
                        "sources": {"claude-projects": 1},
                        "session_keys": ["session-a"],
                    }
                ],
                "session_items": [
                    {
                        "session_key": "session-a",
                        "family": "uncategorized",
                        "worktree_slug": "gh-4444j99-hokage-chess-21-61c1",
                        "prompt_events": 2,
                        "prompt_hashes": ["hash-a", "hash-b"],
                    }
                ],
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
                        "worktree_slug": "gh-4444j99-hokage-chess-21-61c1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(resolver, "resolve_repo", lambda _root: ("4444J99/hokage-chess", ["4444J99/hokage-chess"]))
    monkeypatch.setattr(resolver, "branch_state", lambda _repo, _branch: None)
    monkeypatch.setattr(resolver, "exact_prs", lambda _repo, _branch: [])
    monkeypatch.setattr(resolver, "broad_pr_hit_count", lambda _repo, _root: 0)

    receipt = resolver.build_receipt("prompt-batch-medium-historical-worktree-review-test")
    assert receipt["lane"] == "historical-worktree-review"
    assert "historical Claude-project worktree sessions" in receipt["evidence"][0]
    assert "under ~/.claude/projects" in receipt["evidence"][1]
    assert receipt["roots"][0]["repo"] == "4444J99/hokage-chess"
    assert receipt["roots"][0]["family"] == "uncategorized"
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(receipt)


def test_closed_pr_with_live_branch_requires_branch_review(tmp_path: Path, monkeypatch):
    resolver = _load()
    raw_source = tmp_path / "raw-session.jsonl"
    raw_source.write_text("RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR", encoding="utf-8")

    monkeypatch.setattr(resolver, "resolve_repo", lambda _root: ("organvm/limen", ["organvm/limen"]))
    monkeypatch.setattr(resolver, "branch_state", lambda _repo, branch: {"name": branch, "sha": "abcdef123456"})
    monkeypatch.setattr(
        resolver,
        "exact_prs",
        lambda _repo, _branch: [
            {
                "number": 12,
                "state": "CLOSED",
                "url": "https://github.com/organvm/limen/pull/12",
                "headRefOid": "abcdef123456",
            }
        ],
    )

    row = resolver.classify_root(
        "limen-closed",
        "session-a",
        "github_review",
        {"path": str(raw_source), "prompt_event_count": 1, "prompt_hashes": ["hash-a"]},
    )
    assert row["status"] == "closed_pr_recorded_with_branch"
    assert "Review the live branch" in row["next_action"]
    assert "RAW_PROMPT_TEXT_SHOULD_NOT_APPEAR" not in json.dumps(row)
