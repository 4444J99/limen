from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRESSURE_SCRIPT = ROOT / "scripts" / "session-lifecycle-pressure.py"
BLOCKERS_SCRIPT = ROOT / "scripts" / "session-blockers-ledger.py"
ATTACK_PATHS_SCRIPT = ROOT / "scripts" / "session-attack-paths.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_session_lifecycle_pressure_summarizes_local_remote_without_raw_text(tmp_path: Path):
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure")
    pressure.ROOT = tmp_path
    pressure.WORKTREE_ROOT = tmp_path / ".limen-worktrees"
    pressure.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    pressure.PROMPT_INDEX = pressure.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    pressure.CORPUS_INVENTORY = pressure.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    pressure.run_worktree_debt = lambda: {
        "total": 2,
        "debt": 2,
        "limit": 1,
        "by_reason": {"dirty": 1, "not-merged-to-default": 1},
    }

    (pressure.WORKTREE_ROOT / "root-a").mkdir(parents=True)
    (pressure.WORKTREE_ROOT / "root-a" / "file.txt").write_text("worktree bytes", encoding="utf-8")
    (pressure.PRIVATE_ROOT / "objects" / "aa").mkdir(parents=True)
    (pressure.PRIVATE_ROOT / "objects" / "aa" / "digest").write_text("private bytes", encoding="utf-8")
    pressure.PROMPT_INDEX.parent.mkdir(parents=True)
    pressure.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "remote": {
                    "enabled": True,
                    "worktrees": {"remote_branches_present": 1, "remote_branches_missing": 1},
                    "task_prs": {"counts": {"ERROR": 1}},
                },
                "cloud": {"enabled": True, "runtime_url_configured": False},
            }
        ),
        encoding="utf-8",
    )

    snapshot = pressure.build_snapshot()
    rendered = pressure.render(snapshot)
    pressure.write_outputs(snapshot, rendered)

    assert snapshot["worktrees"]["debt"] == 2
    assert snapshot["worktrees"]["over_cap"] is True
    assert snapshot["remote"]["remote_branches_missing"] == 1
    assert "Lifecycle pressure" in rendered
    assert "remote branches present/missing 1/1" in rendered
    assert pressure.OUT_JSON.exists()
    assert pressure.OUT_MD.exists()


def test_session_blockers_records_hooks_disk_and_credentials_without_values(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_ledger")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.PROMPT_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    blockers.CODEX_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    blockers.CORPUS_INVENTORY = blockers.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    blockers.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    blockers.PROJECT_SETTINGS = tmp_path / ".claude" / "settings.json"
    blockers.DOC_PATH = tmp_path / "docs" / "session-lifecycle-blockers.md"
    capability_root = tmp_path / "capabilities"
    blockers.DEFAULT_CAPABILITY_ROOTS = (capability_root,)

    blockers.PROMPT_INDEX.parent.mkdir(parents=True)
    blockers.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [{"source": "codex-sessions", "files": 1, "prompt_events": 1}],
                "worktree_report": {"debt": 1, "total": 2},
                "remote": {
                    "enabled": True,
                    "worktrees": {"remote_branches_missing": 1},
                    "task_prs": {"counts": {"ERROR": 2}},
                },
                "cloud": {
                    "enabled": True,
                    "runtime_url_configured": False,
                    "public_surface_probes": [{"ok": True}],
                    "env_flags": {
                        "CLOUDFLARE_API_TOKEN": False,
                        "GOOGLE_APPLICATION_CREDENTIALS": False,
                        "LIMEN_API_TOKEN": False,
                        "LIMEN_CLIENT_TOKEN": False,
                        "NETLIFY_AUTH_TOKEN": False,
                        "VERCEL_TOKEN": False,
                        "LIMEN_WORKER_URL": False,
                        "NEXT_PUBLIC_API_URL": False,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    blockers.CODEX_INDEX.write_text(
        json.dumps({"session_count": 3, "families": [{"family": "auth_credentials", "sessions": 2}]}),
        encoding="utf-8",
    )
    blockers.CORPUS_INVENTORY.parent.mkdir(parents=True)
    blockers.CORPUS_INVENTORY.write_text(json.dumps({"organs": [], "materialization": {"copied": 0}}), encoding="utf-8")
    blockers.PRESSURE_INDEX.parent.mkdir(parents=True)
    blockers.PRESSURE_INDEX.write_text(
        json.dumps(
            {
                "worktrees": {"bytes": 100},
                "private_corpus": {"bytes": 200},
            }
        ),
        encoding="utf-8",
    )
    blockers.PROJECT_SETTINGS.parent.mkdir(parents=True)
    blockers.PROJECT_SETTINGS.write_text("session-lifecycle-pressure.sh", encoding="utf-8")
    (capability_root / "skills" / "local-skill").mkdir(parents=True)
    (capability_root / "skills" / "local-skill" / "SKILL.md").write_text("# Local Skill\n", encoding="utf-8")
    (capability_root / "plugin" / ".claude-plugin").mkdir(parents=True)
    (capability_root / "plugin" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (capability_root / "mcp.json").write_text("{}", encoding="utf-8")

    snapshot = blockers.build_snapshot()
    markdown = blockers.render_markdown(snapshot)
    blockers.write_outputs(snapshot, markdown)

    ids = {item["id"] for item in snapshot["blockers"]}
    assert "credential-codex-auth-sessions" in ids
    assert "cloud-credential-handles-unconfigured" in ids
    assert "capability-substrate-not-resurfaced" in ids
    assert "local-lifecycle-disk-pressure" in ids
    assert "session-pressure-hook-not-wired" not in ids
    assert snapshot["coverage"]["session_pressure_hook_wired"] is True
    assert snapshot["coverage"]["capability_substrate"]["skill_files"] == 1
    assert "Session pressure hook wired: `True`" in markdown
    assert "secret-value" not in markdown
    assert blockers.DOC_PATH.exists()
    assert blockers.PRIVATE_INDEX.exists()


def test_session_attack_paths_prioritize_system_clogs_before_delegation(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [{"source": "codex-sessions", "files": 1, "prompt_events": 10}],
                "worktree_report": {
                    "debt": 1,
                    "items": [
                        {
                            "name": "dirty-root",
                            "reason": "dirty",
                            "debt": True,
                            "path": str(tmp_path / ".limen-worktrees" / "dirty-root"),
                        }
                    ],
                },
                "sessions_by_worktree": {"dirty-root": 1},
                "prompt_events_by_worktree": {"dirty-root": 10},
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "receipts": [{"name": "dirty-root", "remote_branch": "missing", "prs": []}],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    attack.CODEX_INDEX.write_text(
        json.dumps(
            {
                "session_count": 20,
                "families": [
                    {"family": "auth_credentials", "sessions": 10, "states": {"PARKED": 10}, "prompt_events": 100},
                    {"family": "session_lifecycle", "sessions": 5, "states": {"STALLED": 2}, "prompt_events": 50},
                ],
            }
        ),
        encoding="utf-8",
    )
    attack.BLOCKER_INDEX.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "remote-task-pr-receipt-errors",
                        "category": "remote_receipt",
                        "status": "needs_refresh",
                        "route": "Refresh remote proof before closure.",
                    },
                    {
                        "id": "credential-codex-auth-sessions",
                        "category": "auth_credentials",
                        "status": "parked",
                        "route": "Park credentials.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(
        json.dumps({"worktrees": {"bytes": 2 * 1024**3}, "local_total_bytes": 3 * 1024**3}),
        encoding="utf-8",
    )

    snapshot = attack.build_snapshot()
    markdown = attack.render_markdown(snapshot, limit=10)
    attack.write_outputs(snapshot, markdown)

    ids_by_rank = [item["id"] for item in snapshot["ranked_paths"]]
    assert ids_by_rank.index("dirty-root") < ids_by_rank.index("auth_credentials")
    assert ids_by_rank.index("remote-task-pr-receipt-errors") < ids_by_rank.index("credential-codex-auth-sessions")
    assert "Highest priority: system clogs" in markdown
    assert "Do not assign Jules" in markdown
    assert attack.DOC_PATH.exists()
    assert attack.PRIVATE_INDEX.exists()


def test_session_attack_paths_treat_preserved_dirty_root_as_owner_blocker(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_receipts")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [{"source": "codex-sessions", "files": 1, "prompt_events": 20}],
                "worktree_report": {
                    "debt": 2,
                    "items": [
                        {"name": "preserved-root", "reason": "dirty", "debt": True},
                        {"name": "unpreserved-root", "reason": "dirty", "debt": True},
                    ],
                },
                "sessions_by_worktree": {"preserved-root": 1, "unpreserved-root": 1},
                "prompt_events_by_worktree": {"preserved-root": 100, "unpreserved-root": 20},
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "receipts": [
                            {"name": "preserved-root", "remote_branch": "missing", "prs": []},
                            {"name": "unpreserved-root", "remote_branch": "missing", "prs": []},
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(json.dumps({"blockers": []}), encoding="utf-8")
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"worktrees": {"bytes": 2 * 1024**3}}), encoding="utf-8")
    attack.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    attack.PRESERVATION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "preserved-root",
                        "status": "private_patch_preserved",
                        "private_receipt": ".limen-private/session-corpus/lifecycle/worktree-preserve/demo/receipt.json",
                        "next_action": "Classify owner intent before cleanup.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = attack.build_snapshot()
    markdown = attack.render_markdown(snapshot, limit=10)

    paths = {item["id"]: item for item in snapshot["ranked_paths"]}
    assert paths["preserved-root"]["lane"] == "owner-blocker"
    assert paths["preserved-root"]["preservation_status"] == "private_patch_preserved"
    assert paths["preserved-root"]["score"] < paths["unpreserved-root"]["score"]
    assert "receipt `private_patch_preserved`" in markdown
