from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRESSURE_SCRIPT = ROOT / "scripts" / "session-lifecycle-pressure.py"
CAPABILITY_SCRIPT = ROOT / "scripts" / "capability-substrate-ledger.py"
BLOCKERS_SCRIPT = ROOT / "scripts" / "session-blockers-ledger.py"
ATTACK_PATHS_SCRIPT = ROOT / "scripts" / "session-attack-paths.py"
TRANCHE_SCRIPT = ROOT / "scripts" / "conductor-tranche.py"
ORIENT_SCRIPT = ROOT / "scripts" / "session-orient.py"


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


def test_capability_substrate_ledger_indexes_names_without_skill_bodies(tmp_path: Path):
    capability = _load(CAPABILITY_SCRIPT, "capability_substrate_ledger")
    capability.ROOT = tmp_path
    capability.HOME = tmp_path
    capability.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    capability.PRIVATE_INDEX = capability.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    capability.DOC_PATH = tmp_path / "docs" / "capability-substrate-ledger.md"
    capability.DEFAULT_CAPABILITY_ROOTS = (
        tmp_path / ".codex" / "skills",
        tmp_path / "Workspace" / "organvm" / "a-i--skills",
        tmp_path / "Workspace" / "organvm" / "claude-runtime-state",
    )

    local_skill = tmp_path / ".codex" / "skills" / "uma-ops-semantic-layer" / "SKILL.md"
    custom_skill = (
        tmp_path / "Workspace" / "organvm" / "a-i--skills" / "skills" / "tools" / "artifact-resurfacing" / "SKILL.md"
    )
    scheduled_skill = (
        tmp_path
        / "Workspace"
        / "organvm"
        / "claude-runtime-state"
        / "scheduled-tasks"
        / "daily-repo-hygiene"
        / "SKILL.md"
    )
    for path in (local_skill, custom_skill, scheduled_skill):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SECRET_BODY_TOKEN should never be indexed\n", encoding="utf-8")
    plugin = tmp_path / "Workspace" / "organvm" / "a-i--skills" / ".claude-plugin" / "plugin.json"
    plugin.parent.mkdir(parents=True)
    plugin.write_text('{"token":"SECRET_PLUGIN_TOKEN"}', encoding="utf-8")

    snapshot = capability.build_snapshot(limit=10)
    markdown = capability.render_markdown(snapshot, limit=10)
    capability.write_outputs(snapshot, markdown)

    assert snapshot["coverage"]["skill_files"] == 3
    assert snapshot["coverage"]["plugin_manifests"] == 1
    assert any(item["name"] == "artifact-resurfacing" for item in snapshot["activation_queue"])
    serialized = json.dumps(snapshot)
    assert "SECRET_BODY_TOKEN" not in serialized
    assert "SECRET_PLUGIN_TOKEN" not in serialized
    assert "SECRET_BODY_TOKEN" not in markdown
    assert "does not read or print `SKILL.md` bodies" in markdown
    assert capability.DOC_PATH.exists()
    assert capability.PRIVATE_INDEX.exists()


def test_session_blockers_records_hooks_disk_and_credentials_without_values(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_ledger")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.CAPABILITY_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
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
    assert snapshot["coverage"]["capability_substrate"]["receipt"]["present"] is False
    assert "Session pressure hook wired: `True`" in markdown
    assert "secret-value" not in markdown
    assert blockers.DOC_PATH.exists()
    assert blockers.PRIVATE_INDEX.exists()


def test_session_blockers_clears_capability_blocker_with_current_receipt(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_capability_receipt")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.CAPABILITY_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
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
                "sources": [],
                "worktree_report": {"debt": 0, "total": 0},
                "remote": {"enabled": True, "worktrees": {}, "task_prs": {"counts": {}}},
                "cloud": {"enabled": True, "runtime_url_configured": True, "env_flags": {}},
            }
        ),
        encoding="utf-8",
    )
    blockers.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    blockers.CORPUS_INVENTORY.parent.mkdir(parents=True)
    blockers.CORPUS_INVENTORY.write_text(json.dumps({"organs": [], "materialization": {"copied": 0}}), encoding="utf-8")
    blockers.PRESSURE_INDEX.parent.mkdir(parents=True)
    blockers.PRESSURE_INDEX.write_text(
        json.dumps({"worktrees": {"bytes": 0}, "private_corpus": {"bytes": 0}}), encoding="utf-8"
    )
    blockers.PROJECT_SETTINGS.parent.mkdir(parents=True)
    blockers.PROJECT_SETTINGS.write_text("session-lifecycle-pressure.sh", encoding="utf-8")
    (capability_root / "skills" / "artifact-resurfacing").mkdir(parents=True)
    (capability_root / "skills" / "artifact-resurfacing" / "SKILL.md").write_text("# Body not read\n", encoding="utf-8")
    (capability_root / ".claude-plugin").mkdir()
    (capability_root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

    capability = blockers.capability_substrate_snapshot()
    blockers.CAPABILITY_INDEX.parent.mkdir(parents=True, exist_ok=True)
    blockers.CAPABILITY_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T00:00:00+00:00",
                "coverage": {
                    "roots_seen": capability["roots_seen"],
                    "skill_files": capability["skill_files"],
                    "plugin_manifests": capability["plugin_manifests"],
                    "mcp_acp_markers": capability["mcp_acp_markers"],
                },
                "activation_queue": [{"name": "artifact-resurfacing"}],
                "activation_groups": {"session_corpus": ["artifact-resurfacing"]},
            }
        ),
        encoding="utf-8",
    )

    snapshot = blockers.build_snapshot()
    markdown = blockers.render_markdown(snapshot)

    ids = {item["id"] for item in snapshot["blockers"]}
    assert "capability-substrate-not-resurfaced" not in ids
    assert snapshot["coverage"]["capability_substrate"]["receipt"]["current"] is True
    assert "Capability resurfacing receipt present/current: `True`/`True`" in markdown


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


def test_conductor_tranche_selects_actionable_packet_with_receipts(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche")
    tranche.ROOT = tmp_path
    tranche.HOME = tmp_path
    tranche.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    tranche.ATTACK_INDEX = tranche.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    tranche.DOC_PATH = tmp_path / "docs" / "conductor-tranche.md"
    tranche.PRIVATE_INDEX = tranche.PRIVATE_ROOT / "lifecycle" / "conductor-tranche.json"
    tranche.PORTVS_PATH = tmp_path / "Workspace" / "4444J99" / "portvs"

    tranche.ATTACK_INDEX.parent.mkdir(parents=True)
    tranche.ATTACK_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T12:00:00+00:00",
                "ranked_paths": [
                    {
                        "id": "credential-codex-auth-sessions",
                        "kind": "blocker",
                        "lane": "parked",
                        "category": "auth_credentials",
                        "score": 99,
                        "next_action": "Keep parked.",
                    },
                    {
                        "id": "local-lifecycle-disk-pressure",
                        "kind": "blocker",
                        "lane": "drain",
                        "category": "local_lean",
                        "score": 74,
                        "agent_fit": "codex",
                        "next_action": "Drain only after remote/default preservation proof.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()
    markdown = tranche.render_markdown(snapshot)
    tranche.write_outputs(snapshot, markdown)

    packet = snapshot["packet"]
    assert packet["id"] == "tranche-local-lifecycle-disk-pressure"
    assert packet["selected_path_id"] == "local-lifecycle-disk-pressure"
    assert "docs/worktree-lifecycle-ledger.md" in packet["allowed_files"]
    assert str(tranche.PORTVS_PATH) in packet["forbidden"]
    assert "credential-codex-auth-sessions" in snapshot["skipped_unactionable_path_ids"]
    assert "one-to-two-hour direct-session tranche" in markdown
    assert "Drain only after remote/default preservation proof." in markdown
    assert tranche.DOC_PATH.exists()
    assert tranche.PRIVATE_INDEX.exists()


def test_session_orientation_board_counts_tasks_not_dispatch_logs(tmp_path: Path):
    orient = _load(ORIENT_SCRIPT, "session_orient_board")
    orient.ROOT = tmp_path
    (tmp_path / "tasks.yaml").write_text(
        """
portal:
  budget: {}
tasks:
  - id: A
    status: open
    dispatch_log:
      - status: dispatched
      - status: in_progress
  - id: B
    status: done
    dispatch_log:
      - status: open
      - status: done
  - id: C
    status: in_progress
""",
        encoding="utf-8",
    )

    board = orient.section_board()

    assert board == "**Board** — 1 open · 1 in_progress · 1 done"
