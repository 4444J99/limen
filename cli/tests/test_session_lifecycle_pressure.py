from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRESSURE_SCRIPT = ROOT / "scripts" / "session-lifecycle-pressure.py"
CAPABILITY_SCRIPT = ROOT / "scripts" / "capability-substrate-ledger.py"
BLOCKERS_SCRIPT = ROOT / "scripts" / "session-blockers-ledger.py"
ATTACK_PATHS_SCRIPT = ROOT / "scripts" / "session-attack-paths.py"
TRANCHE_SCRIPT = ROOT / "scripts" / "conductor-tranche.py"
ORIENT_SCRIPT = ROOT / "scripts" / "session-orient.py"
DONE_ORIENT_SCRIPT = ROOT / "scripts" / "done-session-orient.sh"
CONSOLIDATION_GATES_SCRIPT = ROOT / "scripts" / "consolidation-gates.py"
NETWORK_HEALTH_SCRIPT = ROOT / "scripts" / "network-health.py"
DISPATCH_HEALTH_SCRIPT = ROOT / "scripts" / "dispatch-health.py"
LIVE_ROOT_GATE_SCRIPT = ROOT / "scripts" / "live-root-gate.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_consolidation_gates_parse_read_only_probes(tmp_path: Path):
    gates = _load(CONSOLIDATION_GATES_SCRIPT, "consolidation_gates")
    gates.ROOT = tmp_path
    gates.DOC_PATH = tmp_path / "docs" / "consolidation" / "GATES.md"
    gates.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    gates.PRIVATE_INDEX = gates.PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"
    gates.RUNBOOK = tmp_path / "docs" / "consolidation" / "RUNBOOK.md"
    gates.COLLISION_RENAMES = tmp_path / "docs" / "consolidation" / "COLLISION-RENAMES.md"
    gates.SCOPE_AND_APP = tmp_path / "docs" / "consolidation" / "SCOPE-AND-APP.md"

    def fake_run_command(args, *, env=None, timeout=180):
        text = " ".join(args)
        if "consolidate-github.py" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": """=== consolidation plan -> organvm ===
  34 repos across 10 owners
  name collisions (must rename before transfer): 13
    ! '.github': organvm-i-theoria/.github, organvm-ii-poiesis/.github

DRY-RUN - nothing executed. Collisions above must be resolved first.
""",
                "stderr": "",
                "timed_out": False,
            }
        if "rewrite-owners.py" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": """[1] tasks.yaml repo: refs to rewrite = 49
[2] deploy-api.yml LIMEN_GITHUB_REPO literal: none (already organvm or absent)
[3] git checkouts under /tmp with origin on an OLD owner = 8 (emit-only, never run)
DRY-RUN - nothing written.
""",
                "stderr": "",
                "timed_out": False,
            }
        if "gh-app-token.sh" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": "pat (GITHUB_TOKEN fallback)\n",
                "stderr": "",
                "timed_out": False,
            }
        return {
            "args": args,
            "returncode": 0,
            "stdout": "claude\ngoogle-labs-jules\n",
            "stderr": "",
            "timed_out": False,
        }

    gates.run_command = fake_run_command

    snapshot = gates.build_snapshot()
    markdown = gates.render_markdown(snapshot)
    gates.write_outputs(snapshot, markdown)

    assert snapshot["consolidation"]["source_repos"] == 34
    assert snapshot["consolidation"]["collision_groups"] == 13
    assert snapshot["owner_rewrite"]["task_repo_refs_to_rewrite"] == 49
    assert snapshot["owner_rewrite"]["local_remotes_to_rewrite"] == 8
    assert snapshot["app_identity"]["app_token_wired"] is False
    assert "name-collisions" in snapshot["gates"]["blocking"]
    assert "limen-bot-token-not-wired" in snapshot["gates"]["blocking"]
    assert "Human approval is still required" in markdown
    assert gates.DOC_PATH.exists()
    assert gates.PRIVATE_INDEX.exists()


def test_consolidation_gates_validate_complete_collision_packet(tmp_path: Path):
    gates = _load(CONSOLIDATION_GATES_SCRIPT, "consolidation_gates_collision_packet")
    gates.ROOT = tmp_path
    gates.DOC_PATH = tmp_path / "docs" / "consolidation" / "GATES.md"
    gates.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    gates.PRIVATE_INDEX = gates.PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"
    gates.RUNBOOK = tmp_path / "docs" / "consolidation" / "RUNBOOK.md"
    gates.COLLISION_RENAMES = tmp_path / "docs" / "consolidation" / "COLLISION-RENAMES.md"
    gates.SCOPE_AND_APP = tmp_path / "docs" / "consolidation" / "SCOPE-AND-APP.md"
    gates.COLLISION_RENAMES.parent.mkdir(parents=True)
    gates.COLLISION_RENAMES.write_text(
        """# Collision Rename Packet

| Collision | Keeper |
|---|---|
| `demo-repo` | `keeper-org/demo-repo` |

```bash
gh repo rename demo-repo--source-org-legacy --repo source-org/demo-repo
```
""",
        encoding="utf-8",
    )

    def fake_run_command(args, *, env=None, timeout=180):
        text = " ".join(args)
        if args[:3] == ["gh", "repo", "view"]:
            return {
                "args": args,
                "returncode": 1,
                "stdout": "",
                "stderr": "GraphQL: Could not resolve to a Repository with the name 'source-org/demo-repo--source-org-legacy'. (repository)",
                "timed_out": False,
            }
        if "consolidate-github.py" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": """=== consolidation plan -> organvm ===
  2 repos across 2 owners
  name collisions (must rename before transfer): 1
    ! 'demo-repo': source-org/demo-repo, keeper-org/demo-repo

DRY-RUN - nothing executed. Collisions above must be resolved first.
""",
                "stderr": "",
                "timed_out": False,
            }
        if "rewrite-owners.py" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": """[1] tasks.yaml repo: refs to rewrite = 0
[2] deploy-api.yml LIMEN_GITHUB_REPO literal: none (already organvm or absent)
[3] git checkouts under /tmp with origin on an OLD owner = 0 (emit-only, never run)
DRY-RUN - nothing written.
""",
                "stderr": "",
                "timed_out": False,
            }
        if "gh-app-token.sh" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": "app (limen[bot] installation token)\n",
                "stderr": "",
                "timed_out": False,
            }
        return {"args": args, "returncode": 0, "stdout": "limen-bot\n", "stderr": "", "timed_out": False}

    gates.run_command = fake_run_command

    snapshot = gates.build_snapshot()
    markdown = gates.render_markdown(snapshot)

    assert snapshot["collision_packet"]["complete"] is True
    assert snapshot["collision_packet"]["rename_commands"] == 1
    assert snapshot["collision_packet"]["required_rename_commands"] == 1
    assert snapshot["collision_packet"]["target_conflicts"] == []
    assert snapshot["gates"]["blocking"] == ["name-collisions"]
    assert "Collision packet complete | `True`" in markdown


def test_consolidation_gates_treats_zero_collision_dry_run_as_resolved_packet(tmp_path: Path):
    gates = _load(CONSOLIDATION_GATES_SCRIPT, "consolidation_gates_zero_collisions")
    gates.ROOT = tmp_path
    gates.DOC_PATH = tmp_path / "docs" / "consolidation" / "GATES.md"
    gates.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    gates.PRIVATE_INDEX = gates.PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"
    gates.RUNBOOK = tmp_path / "docs" / "consolidation" / "RUNBOOK.md"
    gates.COLLISION_RENAMES = tmp_path / "docs" / "consolidation" / "COLLISION-RENAMES.md"
    gates.SCOPE_AND_APP = tmp_path / "docs" / "consolidation" / "SCOPE-AND-APP.md"
    gates.COLLISION_RENAMES.parent.mkdir(parents=True)
    gates.COLLISION_RENAMES.write_text(
        """# Collision Rename Packet

| Collision | Keeper |
|---|---|
| `demo-repo` | `keeper-org/demo-repo` |

```bash
gh repo rename demo-repo--source-org-legacy --repo source-org/demo-repo
```
""",
        encoding="utf-8",
    )

    def fake_run_command(args, *, env=None, timeout=180):
        text = " ".join(args)
        if args[:3] == ["gh", "repo", "view"]:
            return {
                "args": args,
                "returncode": 0,
                "stdout": '{"nameWithOwner":"source-org/demo-repo--source-org-legacy"}',
                "stderr": "",
                "timed_out": False,
            }
        if "consolidate-github.py" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": """=== consolidation plan -> organvm ===
  2 repos across 2 owners
  name collisions (must rename before transfer): 0

DRY-RUN - nothing executed.
""",
                "stderr": "",
                "timed_out": False,
            }
        if "rewrite-owners.py" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": """[1] tasks.yaml repo: refs to rewrite = 0
[2] deploy-api.yml LIMEN_GITHUB_REPO literal: none (already organvm or absent)
[3] git checkouts under /tmp with origin on an OLD owner = 0 (emit-only, never run)
DRY-RUN - nothing written.
""",
                "stderr": "",
                "timed_out": False,
            }
        if "gh-app-token.sh" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": "app (limen[bot] installation token)\n",
                "stderr": "",
                "timed_out": False,
            }
        return {"args": args, "returncode": 0, "stdout": "limen-bot\n", "stderr": "", "timed_out": False}

    gates.run_command = fake_run_command

    snapshot = gates.build_snapshot()
    markdown = gates.render_markdown(snapshot)

    assert snapshot["consolidation"]["collision_groups"] == 0
    assert snapshot["collision_packet"]["complete"] is True
    assert snapshot["collision_packet"]["rename_commands"] == 1
    assert snapshot["collision_packet"]["required_rename_commands"] == 0
    assert snapshot["collision_packet"]["target_conflicts"] == []
    assert "collision-packet-incomplete" not in snapshot["gates"]["blocking"]
    assert "Rename target conflicts: `0`" in markdown
    assert "Collision names are resolved" in markdown
    assert "1. Resolve collision names" not in markdown


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
    assert snapshot["worktrees"]["debt_target"] == 0
    assert snapshot["worktrees"]["complete"] is False  # exact-zero completion; any nonzero debt is open
    assert snapshot["remote"]["remote_branches_missing"] == 1
    assert "Lifecycle pressure" in rendered
    assert "debt 2 (target 0)" in rendered
    assert "remote branches present/missing 1/1" in rendered
    assert pressure.OUT_JSON.exists()
    assert pressure.OUT_MD.exists()


def test_session_lifecycle_pressure_records_worktree_debt_timeout(monkeypatch, tmp_path: Path):
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure_timeout")
    pressure.ROOT = tmp_path
    pressure.WORKTREE_ROOT = tmp_path / ".limen-worktrees"
    pressure.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    pressure.PROMPT_INDEX = pressure.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    pressure.CORPUS_INVENTORY = pressure.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    pressure.WORKTREE_DEBT_TIMEOUT = 2

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or args[0], timeout=2)

    monkeypatch.setattr(pressure.subprocess, "run", timeout_run)

    snapshot = pressure.build_snapshot()
    rendered = pressure.render(snapshot)

    assert snapshot["worktrees"]["error"] == "worktree-debt timed out after 2s"
    assert "worktree debt scan unavailable" in snapshot["pressure"]
    assert rendered.endswith("state: runtime unconfigured, worktree debt scan unavailable")


def test_session_lifecycle_pressure_closes_raw_remote_missing_with_live_scanner_receipt(tmp_path: Path):
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure_remote_closed")
    pressure.ROOT = tmp_path
    pressure.WORKTREE_ROOT = tmp_path / ".limen-worktrees"
    pressure.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    pressure.PROMPT_INDEX = pressure.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    pressure.CORPUS_INVENTORY = pressure.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    pressure.run_worktree_debt = lambda: {
        "total": 1,
        "debt": 0,
        "by_reason": {"owner-blocker": 1},
        "items": [{"name": "owner-blocked-root", "reason": "owner-blocker", "debt": False}],
    }

    pressure.WORKTREE_ROOT.mkdir(parents=True)
    pressure.PROMPT_INDEX.parent.mkdir(parents=True)
    pressure.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "remote_branches_present": 0,
                        "remote_branches_missing": 1,
                        "receipts": [{"name": "owner-blocked-root", "remote_branch": "missing"}],
                    },
                    "task_prs": {"counts": {}},
                },
                "cloud": {"enabled": True, "runtime_url_configured": True},
            }
        ),
        encoding="utf-8",
    )

    snapshot = pressure.build_snapshot()
    rendered = pressure.render(snapshot)

    assert snapshot["remote"]["remote_branches_missing"] == 1
    assert snapshot["remote"]["remote_branches_unresolved_missing"] == 0
    assert snapshot["remote"]["remote_branches_closed_by_live_scanner"] == 1
    assert "remote branch gaps" not in snapshot["pressure"]
    assert "remote branches present/missing 0/1 (unresolved 0)" in rendered
    assert rendered.endswith("state: within guardrails")


def test_session_lifecycle_pressure_counts_scanned_worktree_targets(tmp_path: Path):
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure_target_bytes")
    pressure.ROOT = tmp_path
    pressure.WORKTREE_ROOT = tmp_path / ".limen-worktrees"
    pressure.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    pressure.PROMPT_INDEX = pressure.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    pressure.CORPUS_INVENTORY = pressure.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    old_root = pressure.WORKTREE_ROOT / "old-root"
    repo_local = tmp_path / "Workspace" / "portvs" / ".worktrees" / "triptych-story"
    sibling = tmp_path / "Workspace" / "limen-main-trench-20260628"
    old_root.mkdir(parents=True)
    repo_local.mkdir(parents=True)
    sibling.mkdir(parents=True)
    (old_root / "old.bin").write_bytes(b"a" * 3)
    (repo_local / "clip.bin").write_bytes(b"b" * 5)
    (sibling / "state.bin").write_bytes(b"c" * 7)
    pressure.run_worktree_debt = lambda: {
        "total": 3,
        "debt": 0,
        "by_reason": {"clean+merged+idle": 3},
        "items": [
            {"name": "old-root", "path": str(old_root), "reason": "clean+merged+idle", "debt": False},
            {"name": "triptych-story", "path": str(repo_local), "reason": "clean+merged+idle", "debt": False},
            {
                "name": "limen-main-trench-20260628",
                "path": str(sibling),
                "reason": "clean+merged+idle",
                "debt": False,
            },
        ],
    }

    snapshot = pressure.build_snapshot()

    assert snapshot["worktrees"]["roots"] == 3
    assert snapshot["worktrees"]["bytes"] == 15


def test_session_lifecycle_pressure_closes_reclaimed_remote_missing_from_receipt(tmp_path: Path):
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure_reclaimed_receipt")
    pressure.ROOT = tmp_path
    pressure.WORKTREE_ROOT = tmp_path / ".limen-worktrees"
    pressure.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    pressure.PROMPT_INDEX = pressure.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    pressure.CORPUS_INVENTORY = pressure.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    pressure.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    pressure.run_worktree_debt = lambda: {
        "total": 0,
        "debt": 0,
        "by_reason": {},
        "items": [],
    }
    pressure.PROMPT_INDEX.parent.mkdir(parents=True)
    pressure.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "remote_branches_present": 0,
                        "remote_branches_missing": 1,
                        "receipts": [{"name": "reclaimed-root", "remote_branch": "missing"}],
                    },
                    "task_prs": {"counts": {}},
                },
                "cloud": {"enabled": True, "runtime_url_configured": True},
            }
        ),
        encoding="utf-8",
    )
    pressure.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    pressure.PRESERVATION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "reclaimed-root",
                        "lane": "remote-default-proof",
                        "status": "default_branch_preserved",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = pressure.build_snapshot()

    assert snapshot["remote"]["remote_branches_missing"] == 1
    assert snapshot["remote"]["remote_branches_unresolved_missing"] == 0
    assert snapshot["remote"]["remote_branches_closed_roots"] == ["reclaimed-root"]


def test_session_lifecycle_pressure_throttle_skips_census_when_snapshot_fresh(tmp_path: Path, monkeypatch):
    """The SessionEnd hook runs this every session and its census shells out to git per worktree —
    on a large estate that grinds the CPU (the machine 'crawls'). With a fresh snapshot and a throttle
    window, main() must SKIP the expensive build_snapshot() entirely and echo the cached line."""
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure_throttle_skip")
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    pressure.OUT_JSON.parent.mkdir(parents=True)
    pressure.OUT_JSON.write_text('{"cached": true}', encoding="utf-8")  # age ≈ 0 < throttle
    pressure.OUT_MD.write_text("**Lifecycle pressure** — cached line", encoding="utf-8")

    def boom():
        raise AssertionError("build_snapshot() must NOT run when the snapshot is fresh within the throttle")

    monkeypatch.setattr(pressure, "build_snapshot", boom)
    monkeypatch.setattr(sys, "argv", ["session-lifecycle-pressure.py", "--throttle", "3600"])

    assert pressure.main() == 0  # short-circuits; boom never raised


def test_session_lifecycle_pressure_throttle_zero_always_runs_census(tmp_path: Path, monkeypatch):
    """--throttle 0 (or LIMEN_LIFECYCLE_PRESSURE_THROTTLE=0) restores the old always-run behavior."""
    pressure = _load(PRESSURE_SCRIPT, "session_lifecycle_pressure_throttle_zero")
    pressure.OUT_JSON = tmp_path / "logs" / "session-lifecycle-pressure.json"
    pressure.OUT_MD = tmp_path / "logs" / "session-lifecycle-pressure.md"
    pressure.OUT_JSON.parent.mkdir(parents=True)
    pressure.OUT_JSON.write_text('{"cached": true}', encoding="utf-8")

    ran = {"build": False}

    def fake_build():
        ran["build"] = True
        return {"stub": True}

    monkeypatch.setattr(pressure, "build_snapshot", fake_build)
    monkeypatch.setattr(pressure, "render", lambda _snap: "rendered")
    monkeypatch.setattr(sys, "argv", ["session-lifecycle-pressure.py", "--throttle", "0"])

    assert pressure.main() == 0
    assert ran["build"] is True  # throttle 0 → census always runs


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


def test_network_health_records_static_and_live_netmode_safety(tmp_path: Path):
    network = _load(NETWORK_HEALTH_SCRIPT, "network_health")
    network.ROOT = tmp_path
    network.HOME = tmp_path
    network.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    network.PRIVATE_INDEX = network.PRIVATE_ROOT / "lifecycle" / "network-health.json"
    network.DOC_PATH = tmp_path / "docs" / "network-health.md"
    network.NETMODE_SCRIPT = tmp_path / "scripts" / "netmode.sh"
    network.NETMETER_PLIST = tmp_path / "container" / "launchd" / "com.user.netmeter.plist"
    network.LIVE_NETMODE_SCRIPT = tmp_path / "Library" / "Application Support" / "netmeter" / "netmode.sh"
    network.LIVE_MODE_FILE = tmp_path / "Library" / "Application Support" / "netmeter" / "mode"

    netmode_text = """
BACKGROUND_SWITCHING=0
background_switching_enabled() { [ "${BACKGROUND_SWITCHING:-0}" = 1 ]; }
get_mode() { [ -f "$MODEFILE" ] && cat "$MODEFILE" || echo "observe"; }
tick() { if background_switching_enabled; then schedule_tick; fi; }
case "${1:-status}" in stop|panic) stop_agents ;; esac
t "tick observe-only does not call switch actuators" "_st_tick_observe_safe"
t "tick switching can be explicitly opted in" "_st_tick_switch_optin"
"""
    network.NETMODE_SCRIPT.parent.mkdir(parents=True)
    network.NETMODE_SCRIPT.write_text(netmode_text, encoding="utf-8")
    network.LIVE_NETMODE_SCRIPT.parent.mkdir(parents=True)
    network.LIVE_NETMODE_SCRIPT.write_text(netmode_text, encoding="utf-8")
    network.LIVE_MODE_FILE.write_text("observe\n", encoding="utf-8")
    network.NETMETER_PLIST.parent.mkdir(parents=True)
    network.NETMETER_PLIST.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.user.netmeter</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>netmode.sh</string><string>tick</string></array>
<key>StartInterval</key><integer>300</integer>
<key>RunAtLoad</key><false/>
<key>Disabled</key><true/>
</dict></plist>
""",
        encoding="utf-8",
    )

    def fake_run(args, *, timeout=10):
        text = " ".join(args)
        if "print-disabled" in text:
            return {
                "args": args,
                "returncode": 0,
                "stdout": '"com.user.netmeter" => disabled\n"com.user.netmode.netwatch" => disabled\n',
                "stderr": "",
                "timed_out": False,
            }
        if args[:2] == ["launchctl", "list"]:
            return {"args": args, "returncode": 0, "stdout": "", "stderr": "", "timed_out": False}
        if args[:3] == ["route", "-n", "get"]:
            return {
                "args": args,
                "returncode": 0,
                "stdout": "gateway: 192.168.1.1\ninterface: en0\n",
                "stderr": "",
                "timed_out": False,
            }
        return {"args": args, "returncode": 0, "stdout": "", "stderr": "", "timed_out": False}

    network.run_command = fake_run

    snapshot = network.build_snapshot()
    markdown = network.render_markdown(snapshot)
    network.write_outputs(snapshot, markdown)

    assert snapshot["status"] == "healthy"
    assert snapshot["blockers"] == []
    assert snapshot["tracked_netmode"]["ok"] is True
    assert snapshot["live_netmode"]["ok"] is True
    assert snapshot["netmeter_plist"]["ok"] is True
    assert snapshot["launchd"]["labels"]["com.user.netmeter"]["disabled"] is True
    assert "single-lane failure mode" in markdown
    assert "Default route: `en0` via `192.168.1.1`" in markdown
    assert network.DOC_PATH.exists()
    assert network.PRIVATE_INDEX.exists()


def test_dispatch_health_records_live_root_and_async_drift(tmp_path: Path):
    dispatch = _load(DISPATCH_HEALTH_SCRIPT, "dispatch_health")
    dispatch.ROOT = tmp_path
    dispatch.HOME = tmp_path
    dispatch.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    dispatch.PRIVATE_INDEX = dispatch.PRIVATE_ROOT / "lifecycle" / "dispatch-health.json"
    dispatch.DOC_PATH = tmp_path / "docs" / "dispatch-health.md"
    dispatch.LIVE_ROOT = tmp_path / "live-limen"
    dispatch.HEARTBEAT_PLIST = tmp_path / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist"

    dispatch.read_plist = lambda path: {
        "present": True,
        "path": str(path),
        "keep_alive": True,
        "run_at_load": True,
        "env": {"LIMEN_ROOT": str(dispatch.LIVE_ROOT), "LIMEN_DISPATCH_ASYNC": "0"},
    }
    dispatch.launchd_snapshot = lambda: {
        "present": True,
        "running": True,
        "state": "running",
        "pid": "123",
        "env": {"LIMEN_ROOT": str(dispatch.LIVE_ROOT)},
    }

    def fake_git_snapshot(path: Path):
        if path == dispatch.LIVE_ROOT:
            return {
                "path": str(path),
                "present": True,
                "is_git": True,
                "branch": "feature/live",
                "head": "abc",
                "origin_main": "def",
                "matches_origin_main": False,
                "ahead_origin_main": 1,
                "behind_origin_main": 7,
                "status_summary": "## feature/live...origin/main [ahead 1, behind 7]",
                "dirty_entries": 2,
                "dirty_paths": ["scripts/netmode.sh", "tasks.yaml"],
                "dirty_truncated": False,
            }
        return {
            "path": str(path),
            "present": True,
            "is_git": True,
            "branch": "codex/conductor",
            "head": "def",
            "origin_main": "def",
            "matches_origin_main": True,
            "ahead_origin_main": 0,
            "behind_origin_main": 0,
            "status_summary": "## codex/conductor",
            "dirty_entries": 0,
            "dirty_paths": [],
            "dirty_truncated": False,
        }

    dispatch.git_snapshot = fake_git_snapshot
    dispatch.watchdog_snapshot = lambda: {"healthy": True, "first_line": "[watchdog] HEALTHY"}
    dispatch.async_probe_snapshot = lambda enabled, **kwargs: {
        "requested": enabled,
        "ok": True,
        "timed_out": False,
        "last_line": "would launch 0",
        "skipped_down_lanes": ["gemini", "jules"],
        "skipped_down_reasons": {
            "gemini": {
                "source": "usage",
                "health": "exhausted",
                "signal": "dispatch-count",
                "remaining": 0,
                "possible": 10,
            },
            "jules": {
                "source": "usage",
                "health": "exhausted",
                "signal": "count",
                "remaining": 0,
                "possible": 100,
            },
        },
    }

    snapshot = dispatch.build_snapshot(type("Args", (), {"probe_async": True})())
    markdown = dispatch.render_markdown(snapshot)
    dispatch.write_outputs(snapshot, markdown)

    blocker_ids = {item["id"] for item in snapshot["blockers"]}
    assert snapshot["status"] == "blocked"
    assert "live-root-not-at-origin-main" in blocker_ids
    assert "live-root-dirty" in blocker_ids
    assert "heartbeat-loaded-env-drift" in blocker_ids
    assert "Dispatch/heartbeat health is not proven by tests in a detached worktree alone." in markdown
    assert "Async skipped down lanes: `gemini, jules`" in markdown
    assert "`gemini`: usage health `exhausted`; signal `dispatch-count`; remaining `0` of `10`." in markdown
    assert "`jules`: usage health `exhausted`; signal `count`; remaining `0` of `100`." in markdown
    assert dispatch.DOC_PATH.exists()
    assert dispatch.PRIVATE_INDEX.exists()


def test_dispatch_health_blocks_when_generated_plist_drifts_from_installed(tmp_path: Path):
    dispatch = _load(DISPATCH_HEALTH_SCRIPT, "dispatch_health_generated_plist_drift")
    live_root = tmp_path / "live-limen"
    scratch = tmp_path / "Scratch" / "limen-worktrees"
    local = tmp_path / "Workspace" / ".limen-worktrees"
    snapshot = {
        "generated_heartbeat_plist": {
            "present": True,
            "env": {
                "LIMEN_ROOT": str(live_root),
                "LIMEN_WORKTREES": str(scratch),
                "LIMEN_WORKTREE_ROOT": str(scratch),
                "LIMEN_DISPATCH_ASYNC": "1",
                "LIMEN_DISPATCH_LANES": "auto",
                "LIMEN_ASYNC_MAX": "8",
            },
        },
        "heartbeat_plist": {
            "present": True,
            "keep_alive": True,
            "env": {
                "LIMEN_ROOT": str(live_root),
                "LIMEN_WORKTREES": str(local),
                "LIMEN_WORKTREE_ROOT": str(local),
                "LIMEN_DISPATCH_ASYNC": "1",
                "LIMEN_DISPATCH_LANES": "auto",
                "LIMEN_ASYNC_MAX": "1",
            },
        },
        "launchd": {
            "running": True,
            "state": "running",
            "env": {
                "LIMEN_WORKTREES": str(local),
                "LIMEN_WORKTREE_ROOT": str(local),
                "LIMEN_DISPATCH_ASYNC": "1",
                "LIMEN_DISPATCH_LANES": "auto",
                "LIMEN_ASYNC_MAX": "1",
            },
        },
        "live_root_git": {
            "present": True,
            "branch": "main",
            "head": "abc",
            "origin_main": "abc",
            "matches_origin_main": True,
            "dirty_entries": 0,
        },
        "watchdog": {"healthy": True},
        "async_probe": {"requested": False},
        "prompt_packets": {"conductor_required_packets": 0},
        "always_working": {"present": True, "required_open_count": 0},
    }

    blockers = dispatch.derive_blockers(snapshot)

    drift = [item for item in blockers if item["id"] == "heartbeat-generated-plist-env-drift"]
    assert drift
    assert "LIMEN_WORKTREES" in drift[0]["evidence"]
    assert "LIMEN_ASYNC_MAX" in drift[0]["evidence"]


def test_dispatch_health_blocks_on_unresolved_prompt_packets(tmp_path: Path):
    dispatch = _load(DISPATCH_HEALTH_SCRIPT, "dispatch_health_prompt_gate")
    dispatch.ROOT = tmp_path
    dispatch.HOME = tmp_path
    dispatch.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    dispatch.PRIVATE_INDEX = dispatch.PRIVATE_ROOT / "lifecycle" / "dispatch-health.json"
    dispatch.PROMPT_PACKET_INDEX = dispatch.PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
    dispatch.PROMPT_PACKET_DOC = tmp_path / "docs" / "prompt-packet-ledger.md"
    dispatch.ALWAYS_WORKING_INDEX = dispatch.PRIVATE_ROOT / "lifecycle" / "always-working.json"
    dispatch.ALWAYS_WORKING_DOC = tmp_path / "docs" / "always-working.md"
    dispatch.DOC_PATH = tmp_path / "docs" / "dispatch-health.md"
    dispatch.LIVE_ROOT = tmp_path
    dispatch.HEARTBEAT_PLIST = tmp_path / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist"

    dispatch.PROMPT_PACKET_INDEX.parent.mkdir(parents=True)
    dispatch.PROMPT_PACKET_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-06T00:00:00+00:00",
                "recorded_packets": [],
                "open_packets": [
                    {
                        "id": "packet-prompt-batch-critical-stalled-review-001-github_review",
                        "family": "github_review",
                        "dispatchability": "needs-owner-repo",
                        "agent_fit": "codex conducts; opencode/gemini inspect bounded PR evidence",
                        "verification": "python3 scripts/prompt-packet-ledger.py --write",
                    },
                    {
                        "id": "packet-prompt-batch-critical-stalled-review-001-technical_debt_ci",
                        "family": "technical_debt_ci",
                        "dispatchability": "ready-after-predicate",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    dispatch.ALWAYS_WORKING_INDEX.write_text(
        json.dumps(
            {
                "status": "clear",
                "required_open_count": 0,
                "blocked_count": 0,
                "done_count": 1,
                "next_item_id": None,
                "items": [],
            }
        ),
        encoding="utf-8",
    )

    dispatch.read_plist = lambda path: {
        "present": True,
        "path": str(path),
        "keep_alive": True,
        "run_at_load": True,
        "env": {"LIMEN_DISPATCH_ASYNC": "0", "LIMEN_DISPATCH_LANES": "auto"},
    }
    dispatch.launchd_snapshot = lambda: {
        "present": True,
        "running": True,
        "state": "running",
        "pid": "123",
        "env": {"LIMEN_DISPATCH_ASYNC": "0", "LIMEN_DISPATCH_LANES": "auto"},
    }
    dispatch.git_snapshot = lambda path: {
        "path": str(path),
        "present": True,
        "is_git": True,
        "branch": "main",
        "head": "abc",
        "origin_main": "abc",
        "matches_origin_main": True,
        "ahead_origin_main": 0,
        "behind_origin_main": 0,
        "status_summary": "## main...origin/main",
        "dirty_entries": 0,
        "dirty_paths": [],
        "dirty_truncated": False,
    }
    dispatch.watchdog_snapshot = lambda: {"healthy": True, "first_line": "[watchdog] HEALTHY"}
    dispatch.async_probe_snapshot = lambda enabled, **_: {"requested": enabled, "ok": True, "timed_out": False}

    snapshot = dispatch.build_snapshot(type("Args", (), {"probe_async": False})())
    markdown = dispatch.render_markdown(snapshot)

    assert snapshot["status"] == "blocked"
    assert snapshot["prompt_packets"]["open_packets"] == 2
    assert snapshot["prompt_packets"]["conductor_required_packets"] == 1
    assert {item["id"] for item in snapshot["blockers"]} == {"prompt-packets-need-conductor"}
    assert "Prompt Packet Gate" in markdown
    assert "packet-prompt-batch-critical-stalled-review-001-github_review" in markdown
    assert "prompt-packets-need-conductor" in markdown


def test_dispatch_health_parses_async_skipped_down_lanes():
    dispatch = _load(DISPATCH_HEALTH_SCRIPT, "dispatch_health_async_skips")

    output = "── skipping down lanes: ['gemini', 'jules']\n── async: would launch 0"

    assert dispatch.parse_async_skipped_down_lanes(output) == ["gemini", "jules"]


def test_dispatch_health_explains_skipped_down_lanes_from_live_artifacts(tmp_path: Path):
    dispatch = _load(DISPATCH_HEALTH_SCRIPT, "dispatch_health_async_skip_reasons")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "lanes-down.txt").write_text("agy  # oauth browser preflight\n", encoding="utf-8")
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "gemini": {
                        "health": "exhausted",
                        "signal": "dispatch-count",
                        "unit": "runs",
                        "remaining": 0,
                        "possible": 10,
                    },
                    "codex": {
                        "health": "ok",
                        "signal": "vendor-rate-limit",
                        "remaining": 85,
                        "possible": 100,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    reasons = dispatch.skipped_down_lane_reasons(["agy", "gemini", "jules"], tmp_path)

    assert reasons["agy"] == {
        "source": "manual",
        "path": "logs/lanes-down.txt",
        "note": "oauth browser preflight",
    }
    assert reasons["gemini"]["source"] == "usage"
    assert reasons["gemini"]["health"] == "exhausted"
    assert reasons["gemini"]["remaining"] == 0
    assert reasons["jules"] == {"source": "unknown"}


def test_dispatch_health_ignores_generated_receipt_dirty_paths():
    dispatch = _load(DISPATCH_HEALTH_SCRIPT, "dispatch_health_receipt_dirty_filter")

    dirty = dispatch.parse_dirty(
        "\n".join(
            [
                "## main...origin/main",
                " M docs/conductor-tranche.md",
                " M docs/dispatch-health.md",
                " M docs/live-root-gate.md",
                " M docs/session-attack-paths.md",
                " M docs/session-lifecycle-blockers.md",
                " M tasks.yaml",
            ]
        ),
        dispatch.IGNORED_GENERATED_RECEIPTS,
    )

    assert dirty["dirty_entries"] == 1
    assert dirty["dirty_paths"] == ["tasks.yaml"]
    assert dirty["ignored_dirty_entries"] == 5


def test_live_root_gate_records_operator_stop_conditions(tmp_path: Path):
    gate = _load(LIVE_ROOT_GATE_SCRIPT, "live_root_gate")
    gate.ROOT = tmp_path
    gate.HOME = tmp_path
    gate.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    gate.PRIVATE_INDEX = gate.PRIVATE_ROOT / "lifecycle" / "live-root-gate.json"
    gate.DOC_PATH = tmp_path / "docs" / "live-root-gate.md"
    gate.LIVE_ROOT = tmp_path / "live-limen"
    gate.RELEASE_BRANCH = "main"
    gate.HEARTBEAT_PLIST = tmp_path / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist"
    gate.LAUNCHD_LABEL = "com.limen.heartbeat"

    gate.git_snapshot = lambda root, release_branch="main": {
        "path": str(root),
        "present": True,
        "is_git": True,
        "branch": "feature/live" if root == gate.LIVE_ROOT else "codex/conductor",
        "release_branch": release_branch,
        "release_ref": f"origin/{release_branch}",
        "head": "abc" if root == gate.LIVE_ROOT else "def",
        "release_head": "def",
        "matches_release": root != gate.LIVE_ROOT,
        "ahead_release": 1 if root == gate.LIVE_ROOT else 0,
        "behind_release": 8 if root == gate.LIVE_ROOT else 0,
        "status_summary": "## feature/live...origin/main",
        "unique_commit_count": 1 if root == gate.LIVE_ROOT else 0,
        "patch_equivalent_commit_count": 0,
        "unique_commits": ["abc"],
        "patch_equivalent_commits": [],
        "local_log": ["abc live root draft"],
        "dirty_entries": 3 if root == gate.LIVE_ROOT else 0,
        "tracked_dirty": ["scripts/netmode.sh", "tasks.yaml"] if root == gate.LIVE_ROOT else [],
        "untracked": ["organs/media/KERNEL.md"] if root == gate.LIVE_ROOT else [],
        "dirty_paths": ["scripts/netmode.sh", "tasks.yaml", "organs/media/KERNEL.md"] if root == gate.LIVE_ROOT else [],
    }
    gate.read_plist = lambda path: {
        "present": True,
        "path": str(path),
        "env": {"LIMEN_ROOT": str(gate.LIVE_ROOT), "LIMEN_DISPATCH_ASYNC": "0"},
    }
    gate.launchd_snapshot = lambda: {
        "running": True,
        "state": "running",
        "pid": "123",
        "env": {"LIMEN_ROOT": str(gate.LIVE_ROOT)},
    }

    snapshot = gate.build_snapshot(type("Args", (), {"fetch": False})())
    markdown = gate.render_markdown(snapshot)
    gate.write_outputs(snapshot, markdown)

    ids = {item["id"] for item in snapshot["blockers"]}
    assert snapshot["status"] == "blocked"
    assert "live-root-not-release-branch" in ids
    assert "live-root-unique-commits" in ids
    assert "live-root-task-board-dirty" in ids
    assert "heartbeat-loaded-env-drift" in ids
    assert "Stop before `git reset`, branch switch" in markdown
    assert "Human-Gated Command Packet" in markdown
    assert gate.DOC_PATH.exists()
    assert gate.PRIVATE_INDEX.exists()


def test_live_root_gate_ignores_generated_receipt_dirty_paths():
    gate = _load(LIVE_ROOT_GATE_SCRIPT, "live_root_gate_receipt_dirty_filter")

    dirty = gate.parse_dirty(
        "\n".join(
            [
                "## main...origin/main",
                " M docs/conductor-tranche.md",
                " M docs/dispatch-health.md",
                " M docs/live-root-gate.md",
                " M docs/session-attack-paths.md",
                " M docs/session-lifecycle-blockers.md",
                " M tasks.yaml",
            ]
        ),
        gate.IGNORED_GENERATED_RECEIPTS,
    )

    assert dirty["dirty_entries"] == 1
    assert dirty["tracked_dirty"] == ["tasks.yaml"]
    assert dirty["ignored_dirty_entries"] == 5


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
    blockers.worktree_debt_report = lambda root: {"debt": 1, "total": 2, "items": []}

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
    local_pressure = next(item for item in snapshot["blockers"] if item["id"] == "local-lifecycle-disk-pressure")
    assert local_pressure["details"]["worktree_debt"] == 1
    assert local_pressure["details"]["worktree_debt_target"] == 0
    assert local_pressure["details"]["worktree_debt_complete"] is False
    assert "worktree_debt_cap" not in local_pressure["details"]
    assert "session-pressure-hook-not-wired" not in ids
    assert snapshot["coverage"]["session_pressure_hook_wired"] is True
    assert snapshot["coverage"]["capability_substrate"]["skill_files"] == 1
    assert snapshot["coverage"]["capability_substrate"]["receipt"]["present"] is False
    assert "Session pressure hook wired: `True`" in markdown
    assert "secret-value" not in markdown
    assert blockers.DOC_PATH.exists()
    assert blockers.PRIVATE_INDEX.exists()


def test_session_blockers_filter_remote_missing_branches_with_live_scanner_receipts(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_remote_missing_filter")
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
    blockers.DEFAULT_CAPABILITY_ROOTS = ()
    blockers.worktree_debt_report = lambda root: {
        "total": 3,
        "debt": 1,
        "items": [
            {"name": "owner-blocked-root", "reason": "owner-blocker", "debt": False},
            {"name": "active-root", "reason": "active(<24h)", "debt": False},
            {"name": "dirty-root", "reason": "dirty", "debt": True},
        ],
    }

    blockers.PROMPT_INDEX.parent.mkdir(parents=True)
    blockers.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [],
                "worktree_report": {"debt": 2, "total": 2},
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "remote_branches_missing": 3,
                        "receipts": [
                            {"name": "owner-blocked-root", "remote_branch": "missing"},
                            {"name": "active-root", "remote_branch": "missing"},
                            {"name": "dirty-root", "remote_branch": "missing"},
                        ],
                    },
                    "task_prs": {"counts": {}},
                },
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

    snapshot = blockers.build_snapshot()
    paths = {item["id"]: item for item in snapshot["blockers"]}
    blocker = paths["worktree-remote-branches-missing"]

    assert blocker["details"]["remote_branches_missing"] == 1
    assert blocker["details"]["raw_remote_branches_missing"] == 3
    assert blocker["details"]["closed_by_live_scanner"] == ["owner-blocked-root", "active-root"]
    assert blocker["details"]["unresolved_roots"] == ["dirty-root"]


def test_session_blockers_filter_remote_missing_branches_with_preservation_receipts(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_remote_missing_preservation_receipt")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.CAPABILITY_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    blockers.PROMPT_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    blockers.CODEX_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    blockers.CORPUS_INVENTORY = blockers.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    blockers.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    blockers.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    blockers.PROJECT_SETTINGS = tmp_path / ".claude" / "settings.json"
    blockers.DOC_PATH = tmp_path / "docs" / "session-lifecycle-blockers.md"
    blockers.DEFAULT_CAPABILITY_ROOTS = ()
    blockers.worktree_debt_report = lambda root: {
        "total": 0,
        "debt": 0,
        "items": [],
    }

    blockers.PROMPT_INDEX.parent.mkdir(parents=True)
    blockers.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [],
                "worktree_report": {"debt": 0, "total": 0},
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "remote_branches_missing": 1,
                        "receipts": [{"name": "reclaimed-root", "remote_branch": "missing"}],
                    },
                    "task_prs": {"counts": {}},
                },
                "cloud": {"enabled": True, "runtime_url_configured": True, "env_flags": {}},
            }
        ),
        encoding="utf-8",
    )
    blockers.PRESERVATION_RECEIPTS.parent.mkdir(parents=True)
    blockers.PRESERVATION_RECEIPTS.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "reclaimed-root",
                        "lane": "remote-default-proof",
                        "status": "default_branch_preserved",
                    }
                ]
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

    snapshot = blockers.build_snapshot()
    ids = {item["id"] for item in snapshot["blockers"]}

    assert "worktree-remote-branches-missing" not in ids


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


def test_session_blockers_promotes_unhealthy_network_receipt(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_network_health")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.CAPABILITY_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    blockers.NETWORK_HEALTH_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "network-health.json"
    blockers.PROMPT_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    blockers.CODEX_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    blockers.CORPUS_INVENTORY = blockers.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    blockers.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    blockers.PROJECT_SETTINGS = tmp_path / ".claude" / "settings.json"
    blockers.DOC_PATH = tmp_path / "docs" / "session-lifecycle-blockers.md"
    blockers.DEFAULT_CAPABILITY_ROOTS = ()

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
    blockers.NETWORK_HEALTH_INDEX.parent.mkdir(parents=True, exist_ok=True)
    blockers.NETWORK_HEALTH_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T12:00:00+00:00",
                "status": "needs_attention",
                "blockers": [{"id": "network-legacy-netmeter-agent-active"}],
                "mode": {"mode": "observe"},
                "route": {"interface": "en0", "gateway": "192.168.1.1"},
            }
        ),
        encoding="utf-8",
    )

    snapshot = blockers.build_snapshot()
    markdown = blockers.render_markdown(snapshot)

    ids = {item["id"] for item in snapshot["blockers"]}
    assert "local-network-substrate-unhealthy" in ids
    assert snapshot["coverage"]["local_network_substrate"]["status"] == "needs_attention"
    assert (
        "Local network substrate: status `needs_attention`, mode `observe`, route `en0` via `192.168.1.1`." in markdown
    )


def test_session_blockers_promotes_unhealthy_dispatch_receipt(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_dispatch_health")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.CAPABILITY_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    blockers.NETWORK_HEALTH_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "network-health.json"
    blockers.DISPATCH_HEALTH_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "dispatch-health.json"
    blockers.LIVE_ROOT_GATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "live-root-gate.json"
    blockers.CONSOLIDATION_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"
    blockers.PROMPT_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    blockers.CODEX_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    blockers.CORPUS_INVENTORY = blockers.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    blockers.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    blockers.PROJECT_SETTINGS = tmp_path / ".claude" / "settings.json"
    blockers.DOC_PATH = tmp_path / "docs" / "session-lifecycle-blockers.md"
    blockers.DEFAULT_CAPABILITY_ROOTS = ()

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
    blockers.NETWORK_HEALTH_INDEX.parent.mkdir(parents=True, exist_ok=True)
    blockers.NETWORK_HEALTH_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T12:00:00+00:00",
                "status": "healthy",
                "blockers": [],
                "mode": {"mode": "observe"},
                "route": {"interface": "en0", "gateway": "192.168.1.1"},
            }
        ),
        encoding="utf-8",
    )
    blockers.DISPATCH_HEALTH_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T12:00:00+00:00",
                "status": "blocked",
                "blockers": [
                    {"id": "live-root-not-at-origin-main", "evidence": "live root diverged"},
                    {"id": "live-root-dirty", "evidence": "live root has dirty files"},
                ],
                "launchd": {"state": "running", "pid": "123"},
                "live_root_git": {
                    "branch": "feature/live",
                    "matches_origin_main": False,
                    "dirty_entries": 2,
                },
                "async_probe": {"requested": True, "ok": True},
            }
        ),
        encoding="utf-8",
    )
    blockers.LIVE_ROOT_GATE_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T12:00:00+00:00",
                "status": "blocked",
                "operator_gate_required": True,
                "blockers": [{"id": "live-root-unique-commits"}],
                "live_root_git": {
                    "branch": "feature/live",
                    "release_branch": "main",
                    "unique_commit_count": 1,
                    "dirty_entries": 2,
                },
                "launchd": {"state": "running"},
                "launchd_env_drift": [{"key": "LIMEN_DISPATCH_ASYNC"}],
            }
        ),
        encoding="utf-8",
    )

    snapshot = blockers.build_snapshot()
    markdown = blockers.render_markdown(snapshot)

    ids = {item["id"] for item in snapshot["blockers"]}
    assert "dispatch-heartbeat-substrate-unhealthy" in ids
    assert snapshot["coverage"]["dispatch_substrate"]["status"] == "blocked"
    assert snapshot["coverage"]["live_root_gate"]["status"] == "blocked"
    assert "Dispatch substrate: status `blocked`, launchd `running`, live root `feature/live`" in markdown
    assert "Live root gate: status `blocked`, branch `feature/live`, unique commits `1`" in markdown


def test_session_blockers_records_github_consolidation_and_app_gates(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_consolidation_gates")
    blockers.ROOT = tmp_path
    blockers.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    blockers.PRIVATE_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    blockers.CAPABILITY_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
    blockers.CONSOLIDATION_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"
    blockers.PROMPT_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    blockers.CODEX_INDEX = blockers.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    blockers.CORPUS_INVENTORY = blockers.PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
    blockers.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    blockers.PROJECT_SETTINGS = tmp_path / ".claude" / "settings.json"
    blockers.DOC_PATH = tmp_path / "docs" / "session-lifecycle-blockers.md"
    blockers.DEFAULT_CAPABILITY_ROOTS = (tmp_path / "missing-capabilities",)

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
    blockers.CONSOLIDATION_INDEX.parent.mkdir(parents=True, exist_ok=True)
    blockers.CONSOLIDATION_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-28T12:00:00+00:00",
                "consolidation": {"source_repos": 34, "collision_groups": 13},
                "owner_rewrite": {"task_repo_refs_to_rewrite": 49, "local_remotes_to_rewrite": 8},
                "app_identity": {
                    "gh_app_token_which": "pat (GITHUB_TOKEN fallback)",
                    "app_token_wired": False,
                    "limen_app_installed": False,
                    "installed_app_slugs": ["claude", "google-labs-jules"],
                },
                "gates": {"blocking": ["name-collisions", "limen-bot-token-not-wired"]},
            }
        ),
        encoding="utf-8",
    )

    snapshot = blockers.build_snapshot()
    markdown = blockers.render_markdown(snapshot)

    ids = {item["id"] for item in snapshot["blockers"]}
    assert "github-consolidation-collisions" in ids
    assert "github-app-limen-bot-not-wired" in ids
    assert snapshot["coverage"]["github_consolidation"]["collision_groups"] == 13
    assert snapshot["coverage"]["github_consolidation"]["app_token_wired"] is False
    assert "GitHub consolidation gate: `34` source repos, `13` collision groups" in markdown


def test_session_blockers_points_to_transfer_after_collisions_clear(tmp_path: Path):
    blockers = _load(BLOCKERS_SCRIPT, "session_blockers_post_collision_clear")
    blockers.CONSOLIDATION_INDEX = (
        tmp_path / ".limen-private" / "session-corpus" / "lifecycle" / "consolidation-gates.json"
    )
    blockers.CONSOLIDATION_INDEX.parent.mkdir(parents=True)
    blockers.CONSOLIDATION_INDEX.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-06T12:00:00+00:00",
                "consolidation": {"source_repos": 36, "collision_groups": 0},
                "owner_rewrite": {"task_repo_refs_to_rewrite": 62, "local_remotes_to_rewrite": 23},
                "app_identity": {
                    "gh_app_token_which": "pat (GITHUB_TOKEN fallback)",
                    "app_token_wired": False,
                    "limen_app_installed": False,
                    "installed_app_slugs": ["claude", "google-labs-jules"],
                },
                "collision_packet": {"complete": True},
                "gates": {
                    "blocking": [
                        "limen-bot-token-not-wired",
                        "limen-bot-app-not-installed",
                        "post-transfer-owner-rewrite-pending",
                    ],
                    "can_run_transfer_apply_after_human_gate": True,
                },
            }
        ),
        encoding="utf-8",
    )

    collected: list[dict[str, object]] = []
    coverage = blockers.consolidation_gate_blockers(collected)
    route = str(collected[0]["route"])

    assert coverage["collision_groups"] == 0
    assert collected[0]["id"] == "github-consolidation-collisions"
    assert collected[0]["details"]["transfer_apply_gate_open"] is True
    assert "0 name-collision groups remain" in str(collected[0]["evidence"])
    assert "consolidate-github.py --apply" in route
    assert "COLLISION-RENAMES.md" not in route


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


def test_session_attack_paths_prioritize_github_consolidation_over_generic_local_pressure(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_github_consolidation")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    attack.worktree_debt_report = lambda root: {"total": 0, "debt": 0, "items": []}

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps({"sources": [], "worktree_report": {"debt": 0, "items": []}}), encoding="utf-8"
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "local-lifecycle-disk-pressure",
                        "category": "local_lean",
                        "status": "parked",
                        "route": "Drain after preservation proof.",
                    },
                    {
                        "id": "github-consolidation-collisions",
                        "category": "github_consolidation",
                        "status": "needs_human_gate",
                        "route": "Resolve collisions before transfer.",
                    },
                    {
                        "id": "github-app-limen-bot-not-wired",
                        "category": "github_app_identity",
                        "status": "needs_human_gate",
                        "route": "Wire limen bot after App setup.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"local_total_bytes": 0}), encoding="utf-8")

    snapshot = attack.build_snapshot()
    markdown = attack.render_markdown(snapshot, limit=10)

    ids_by_rank = [item["id"] for item in snapshot["ranked_paths"]]
    assert ids_by_rank.index("github-consolidation-collisions") < ids_by_rank.index("local-lifecycle-disk-pressure")
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}
    assert paths["github-consolidation-collisions"]["lane"] == "consolidation-gate"
    assert paths["github-app-limen-bot-not-wired"]["lane"] == "human-gate"
    assert "github-consolidation-collisions" in markdown


def test_session_attack_paths_demote_completed_github_consolidation_packet_to_human_gate(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_completed_github_consolidation")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    attack.worktree_debt_report = lambda root: {"total": 0, "debt": 0, "items": []}

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps({"sources": [], "worktree_report": {"debt": 0, "items": []}}), encoding="utf-8"
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "local-lifecycle-disk-pressure",
                        "category": "local_lean",
                        "status": "parked",
                        "route": "Drain after preservation proof.",
                    },
                    {
                        "id": "github-consolidation-collisions",
                        "category": "github_consolidation",
                        "status": "needs_human_gate",
                        "route": "Await human mutation gate.",
                        "details": {"collision_packet_complete": True},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"local_total_bytes": 0}), encoding="utf-8")

    snapshot = attack.build_snapshot()
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}
    ids_by_rank = [item["id"] for item in snapshot["ranked_paths"]]

    assert ids_by_rank.index("local-lifecycle-disk-pressure") < ids_by_rank.index("github-consolidation-collisions")
    assert paths["github-consolidation-collisions"]["lane"] == "human-gate"
    assert paths["github-consolidation-collisions"]["score"] == 52


def test_session_attack_paths_parks_cloud_runtime_until_deploy_task(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_cloud_runtime_parked")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    attack.worktree_debt_report = lambda root: {"total": 0, "debt": 0, "items": []}

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps({"sources": [], "worktree_report": {"debt": 0, "items": []}}), encoding="utf-8"
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "cloud-runtime-endpoint-unconfigured",
                        "category": "cloud_runtime",
                        "status": "parked",
                        "route": "Keep separate from session intake.",
                    },
                    {
                        "id": "remote-task-pr-receipt-errors",
                        "category": "remote_receipt",
                        "status": "needs_refresh",
                        "route": "Refresh remote proof before closure.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"local_total_bytes": 0}), encoding="utf-8")

    snapshot = attack.build_snapshot()
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}

    assert paths["cloud-runtime-endpoint-unconfigured"]["lane"] == "parked"
    assert paths["remote-task-pr-receipt-errors"]["lane"] == "blocker"


def test_session_attack_paths_parks_local_pressure_when_worktree_debt_zero(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_local_lean_zero_debt")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    attack.worktree_debt_report = lambda root: {"total": 4, "debt": 0, "items": []}

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps({"sources": [], "worktree_report": {"debt": 0, "items": []}}), encoding="utf-8"
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "local-lifecycle-disk-pressure",
                        "category": "local_lean",
                        "status": "parked",
                        "route": "Keep visible, but drain only after preservation proof.",
                        "details": {"worktree_debt": 0, "worktree_debt_target": 0, "worktree_debt_complete": True},
                    },
                    {
                        "id": "worktree-lifecycle-debt",
                        "category": "worktree_lifecycle",
                        "status": "parked",
                        "route": "Preserve or owner-record each root.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"local_total_bytes": 6 * 1024**3}), encoding="utf-8")

    snapshot = attack.build_snapshot()
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}
    ids_by_rank = [item["id"] for item in snapshot["ranked_paths"]]

    assert paths["local-lifecycle-disk-pressure"]["lane"] == "parked"
    assert paths["local-lifecycle-disk-pressure"]["score"] == 34
    assert ids_by_rank.index("worktree-lifecycle-debt") < ids_by_rank.index("local-lifecycle-disk-pressure")


def test_session_attack_paths_keep_local_pressure_actionable_when_worktree_debt_nonzero(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_local_lean_nonzero_debt")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    attack.worktree_debt_report = lambda root: {"total": 11, "debt": 7, "items": []}

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps({"sources": [], "worktree_report": {"debt": 7, "items": []}}), encoding="utf-8"
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(
        json.dumps(
            {
                "blockers": [
                    {
                        "id": "local-lifecycle-disk-pressure",
                        "category": "local_lean",
                        "status": "parked",
                        "route": "Drain after preservation proof.",
                        "details": {"worktree_debt": 7, "worktree_debt_target": 0, "worktree_debt_complete": False},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"local_total_bytes": 6 * 1024**3}), encoding="utf-8")

    snapshot = attack.build_snapshot()
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}

    assert paths["local-lifecycle-disk-pressure"]["lane"] == "drain"
    assert paths["local-lifecycle-disk-pressure"]["score"] == 74


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


def test_session_attack_paths_human_gates_operator_acceptance_receipts(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_operator_acceptance")
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
                    "debt": 1,
                    "items": [{"name": "operator-gated-root", "reason": "dirty", "debt": False}],
                },
                "sessions_by_worktree": {"operator-gated-root": 1},
                "prompt_events_by_worktree": {"operator-gated-root": 100},
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "receipts": [
                            {"name": "operator-gated-root", "remote_branch": "missing", "prs": []},
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
                        "root": "operator-gated-root",
                        "status": "private_patch_preserved",
                        "private_receipt": ".limen-private/session-corpus/lifecycle/worktree-preserve/demo/receipt.json",
                        "next_action": "Reclaim only after normal operator acceptance.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = attack.build_snapshot()
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}

    assert paths["operator-gated-root"]["lane"] == "human-gate"
    assert paths["operator-gated-root"]["agent_fit"] == "human/codex-prep"
    assert paths["operator-gated-root"]["operator_acceptance_required"] is True


def test_session_attack_paths_human_gates_receipts_requiring_owner_packet(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_owner_packet_gate")
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
                    "debt": 1,
                    "items": [{"name": "owner-packet-root", "reason": "owner-blocker", "debt": False}],
                },
                "sessions_by_worktree": {"owner-packet-root": 1},
                "prompt_events_by_worktree": {"owner-packet-root": 20},
                "remote": {
                    "enabled": True,
                    "worktrees": {
                        "receipts": [
                            {"name": "owner-packet-root", "remote_branch": "missing", "prs": []},
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
                        "root": "owner-packet-root",
                        "status": "history_mismatch_patch_preserved",
                        "private_receipt": ".limen-private/session-corpus/lifecycle/worktree-preserve/demo/receipt.json",
                        "next_action": "Do not open a direct PR from this branch. If needed, create a new narrow owner packet.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = attack.build_snapshot()
    paths = {item["id"]: item for item in snapshot["ranked_paths"]}

    assert paths["owner-packet-root"]["lane"] == "human-gate"
    assert paths["owner-packet-root"]["agent_fit"] == "human/codex-prep"
    assert paths["owner-packet-root"]["owner_packet_required"] is True


def test_session_attack_paths_prefers_live_worktree_report_over_stale_prompt_snapshot(tmp_path: Path):
    attack = _load(ATTACK_PATHS_SCRIPT, "session_attack_paths_live_worktrees")
    attack.ROOT = tmp_path
    attack.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    attack.PROMPT_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    attack.CODEX_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
    attack.BLOCKER_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
    attack.PRESSURE_INDEX = tmp_path / "logs" / "session-lifecycle-pressure.json"
    attack.DOC_PATH = tmp_path / "docs" / "session-attack-paths.md"
    attack.PRIVATE_INDEX = attack.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    attack.PRESERVATION_RECEIPTS = tmp_path / "docs" / "worktree-preservation-receipts.json"
    attack.worktree_debt_report = lambda root: {
        "total": 1,
        "debt": 1,
        "by_reason": {"dirty": 1},
        "items": [{"name": "live-root", "reason": "dirty", "debt": True, "path": str(tmp_path / "live-root")}],
    }

    attack.PROMPT_INDEX.parent.mkdir(parents=True)
    attack.PROMPT_INDEX.write_text(
        json.dumps(
            {
                "sources": [{"source": "codex-sessions", "files": 1, "prompt_events": 10}],
                "worktree_report": {
                    "debt": 8,
                    "items": [
                        {"name": "live-root", "reason": "not-a-git-dir", "debt": True},
                        {"name": "stale-root", "reason": "not-a-git-dir", "debt": True},
                    ],
                },
                "sessions_by_worktree": {"live-root": 1, "stale-root": 99},
                "prompt_events_by_worktree": {"live-root": 20, "stale-root": 999},
                "remote": {
                    "enabled": True,
                    "worktrees": {"receipts": [{"name": "live-root", "remote_branch": "missing", "prs": []}]},
                },
            }
        ),
        encoding="utf-8",
    )
    attack.CODEX_INDEX.write_text(json.dumps({"session_count": 0, "families": []}), encoding="utf-8")
    attack.BLOCKER_INDEX.write_text(json.dumps({"blockers": []}), encoding="utf-8")
    attack.PRESSURE_INDEX.parent.mkdir(parents=True)
    attack.PRESSURE_INDEX.write_text(json.dumps({"worktrees": {"bytes": 2 * 1024**3}}), encoding="utf-8")

    snapshot = attack.build_snapshot()
    markdown = attack.render_markdown(snapshot, limit=10)

    ids = [item["id"] for item in snapshot["ranked_paths"]]
    assert snapshot["coverage"]["worktree_debt"] == 1
    assert ids == ["live-root"]
    assert "stale-root" not in markdown
    assert "Worktree debt roots: `1`" in markdown


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


def test_conductor_tranche_skips_family_for_concrete_worktree_lifecycle_packet(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_skips_family")
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
                        "id": "session_lifecycle",
                        "kind": "family",
                        "lane": "family",
                        "score": 99,
                        "agent_fit": "codex",
                        "next_action": "Keep corpus/session ledgers current.",
                    },
                    {
                        "id": "worktree-lifecycle-debt",
                        "kind": "blocker",
                        "lane": "blocker",
                        "category": "worktree_lifecycle",
                        "score": 70,
                        "agent_fit": "codex",
                        "next_action": "Preserve or owner-record each root.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()
    markdown = tranche.render_markdown(snapshot)

    packet = snapshot["packet"]
    assert packet["id"] == "tranche-worktree-lifecycle-debt"
    assert packet["selected_path_id"] == "worktree-lifecycle-debt"
    assert "session_lifecycle" in snapshot["skipped_unactionable_path_ids"]
    assert "scripts/worktree-debt.py" in packet["allowed_files"]
    assert "remaining worktree lifecycle blocker" in markdown


def test_conductor_tranche_skips_human_gate_for_autonomous_work_packet(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_skips_human_gate")
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
                        "id": "github-app-limen-bot-not-wired",
                        "kind": "blocker",
                        "lane": "human-gate",
                        "category": "github_app_identity",
                        "score": 58,
                        "agent_fit": "human/codex-prep",
                        "next_action": "Create/install the App.",
                    },
                    {
                        "id": "gh-organvm-object-lessons-19-605a",
                        "kind": "worktree",
                        "lane": "remote-proof",
                        "score": 49,
                        "agent_fit": "codex first",
                        "next_action": "Verify remote/default preservation.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()

    assert snapshot["packet"]["selected_path_id"] == "gh-organvm-object-lessons-19-605a"
    assert "github-app-limen-bot-not-wired" in snapshot["skipped_unactionable_path_ids"]
    assert snapshot["packet"]["repo_worktree"].startswith("Owner worktree")


def test_conductor_tranche_skips_operator_gated_worktree(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_operator_gated_worktree")
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
                        "id": "operator-gated-root",
                        "kind": "worktree",
                        "lane": "human-gate",
                        "score": 88,
                        "agent_fit": "human/codex-prep",
                        "operator_acceptance_required": True,
                        "next_action": "Reclaim only after normal operator acceptance.",
                    },
                    {
                        "id": "private-raw-materialization-not-receipted",
                        "kind": "blocker",
                        "lane": "blocker",
                        "category": "private_absorption",
                        "score": 30,
                        "agent_fit": "codex",
                        "next_action": "Run the bounded materialization receipt.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()

    assert snapshot["packet"]["selected_path_id"] == "private-raw-materialization-not-receipted"
    assert "operator-gated-root" in snapshot["skipped_unactionable_path_ids"]


def test_conductor_tranche_skips_preserved_active_and_owner_blocker_worktrees(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_skips_preserved_worktrees")
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
                        "id": "preserved-pr-root",
                        "kind": "worktree",
                        "lane": "remote-pr-open",
                        "reason": "remote-pr-open",
                        "score": 90,
                        "agent_fit": "codex first",
                        "next_action": "Review and merge PR only after owner approval.",
                    },
                    {
                        "id": "active-claude-root",
                        "kind": "worktree",
                        "lane": "remote-proof",
                        "reason": "active(<24h)",
                        "score": 80,
                        "agent_fit": "codex first",
                        "next_action": "Verify later after the active agent window closes.",
                    },
                    {
                        "id": "owner-blocked-root",
                        "kind": "worktree",
                        "lane": "owner-blocker",
                        "reason": "owner-blocker",
                        "score": 70,
                        "agent_fit": "human/codex-prep",
                        "next_action": "Do not auto-port without a named owner packet.",
                    },
                    {
                        "id": "default-proof-root",
                        "kind": "worktree",
                        "lane": "remote-proof",
                        "reason": "remote-default-proof",
                        "score": 60,
                        "agent_fit": "codex first",
                        "next_action": "Verify remote/default preservation.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()

    assert snapshot["packet"]["selected_path_id"] == "default-proof-root"
    assert snapshot["skipped_unactionable_path_ids"] == [
        "preserved-pr-root",
        "active-claude-root",
        "owner-blocked-root",
    ]


def test_conductor_tranche_records_no_autonomous_path_when_all_ranked_paths_skipped(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_no_autonomous_path")
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
                        "id": "session_lifecycle",
                        "kind": "family",
                        "lane": "family",
                        "score": 99,
                        "agent_fit": "codex",
                        "next_action": "Keep corpus/session ledgers current.",
                    },
                    {
                        "id": "operator-gated-root",
                        "kind": "worktree",
                        "lane": "human-gate",
                        "score": 80,
                        "agent_fit": "human/codex-prep",
                        "next_action": "Reclaim only after normal operator acceptance.",
                    },
                    {
                        "id": "credential-codex-auth-sessions",
                        "kind": "blocker",
                        "lane": "parked",
                        "category": "auth_credentials",
                        "score": 6,
                        "next_action": "Keep parked.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()
    markdown = tranche.render_markdown(snapshot)

    assert snapshot["packet"]["selected_path_id"] == "no-autonomous-actionable-path"
    assert snapshot["packet"]["id"] == "tranche-no-autonomous-actionable-path"
    assert set(snapshot["skipped_unactionable_path_ids"]) == {
        "session_lifecycle",
        "operator-gated-root",
        "credential-codex-auth-sessions",
    }
    assert "no ranked path is autonomously actionable" in markdown


def test_conductor_tranche_emits_github_consolidation_packet(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_github_consolidation")
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
                        "id": "github-consolidation-collisions",
                        "kind": "blocker",
                        "lane": "consolidation-gate",
                        "category": "github_consolidation",
                        "score": 78,
                        "agent_fit": "codex/human-gate",
                        "next_action": "Resolve collisions before transfer.",
                    },
                    {
                        "id": "local-lifecycle-disk-pressure",
                        "kind": "blocker",
                        "lane": "drain",
                        "category": "local_lean",
                        "score": 74,
                        "agent_fit": "codex",
                        "next_action": "Drain after preservation proof.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()
    markdown = tranche.render_markdown(snapshot)

    packet = snapshot["packet"]
    assert packet["id"] == "tranche-github-consolidation-collisions"
    assert packet["selected_path_id"] == "github-consolidation-collisions"
    assert "scripts/consolidation-gates.py" in packet["allowed_files"]
    assert "python3 scripts/consolidation-gates.py --write" in packet["verification"]
    assert "Stop before `gh repo rename`" in packet["stop_condition"]
    assert "GitHub/org consolidation enforcement path" in markdown


def test_conductor_tranche_emits_local_network_packet(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_local_network")
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
                        "id": "local-network-substrate-unhealthy",
                        "kind": "blocker",
                        "lane": "blocker",
                        "category": "local_network_substrate",
                        "score": 76,
                        "agent_fit": "codex",
                        "next_action": "Repair through the netmode owner path.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()
    markdown = tranche.render_markdown(snapshot)

    packet = snapshot["packet"]
    assert packet["id"] == "tranche-local-network-substrate-unhealthy"
    assert packet["selected_path_id"] == "local-network-substrate-unhealthy"
    assert "scripts/network-health.py" in packet["allowed_files"]
    assert "bash scripts/netmode.sh selftest" in packet["verification"]
    assert "Stop before changing routes" in packet["stop_condition"]
    assert "one-lane symptom patches" in markdown


def test_conductor_tranche_emits_capability_substrate_packet(tmp_path: Path):
    tranche = _load(TRANCHE_SCRIPT, "conductor_tranche_capability_substrate")
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
                        "id": "capability-substrate-not-resurfaced",
                        "kind": "blocker",
                        "lane": "blocker",
                        "category": "capability_substrate",
                        "score": 48,
                        "agent_fit": "codex",
                        "next_action": "Run capability-substrate-ledger.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = tranche.build_snapshot()

    packet = snapshot["packet"]
    assert packet["selected_path_id"] == "capability-substrate-not-resurfaced"
    assert "scripts/capability-substrate-ledger.py" in packet["allowed_files"]
    assert "python3 scripts/capability-substrate-ledger.py --write" in packet["verification"]
    assert "Stop before reading private skill bodies" in packet["stop_condition"]


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


def test_session_orientation_board_can_read_pinned_snapshot(tmp_path: Path, monkeypatch):
    orient = _load(ORIENT_SCRIPT, "session_orient_board_snapshot")
    orient.ROOT = tmp_path
    (tmp_path / "tasks.yaml").write_text(
        """
tasks:
  - id: live
    status: open
""",
        encoding="utf-8",
    )
    snapshot = tmp_path / "snapshot-tasks.yaml"
    snapshot.write_text(
        """
tasks:
  - id: snap-a
    status: open
  - id: snap-b
    status: done
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_ORIENT_TASKS", str(snapshot))

    board = orient.section_board()

    assert board == "**Board** — 1 open · 1 done"


def test_session_orientation_git_section_can_be_pinned(monkeypatch):
    orient = _load(ORIENT_SCRIPT, "session_orient_git_snapshot")
    monkeypatch.setenv("LIMEN_ORIENT_GIT_SECTION", "**Git** — pinned · clean")

    assert orient.section_git() == "**Git** — pinned · clean"


def test_done_session_orient_pins_generators_to_checkout_root():
    script = DONE_ORIENT_SCRIPT.read_text(encoding="utf-8")

    assert 'LIMEN_ROOT="$ROOT" python3 "$PRESSURE_GEN" --write' in script
    assert 'LIMEN_ROOT="$ROOT" python3 "$GEN")' in script
    assert 'LIMEN_ORIENT_TASKS="$tasks_snapshot"' in script
    assert 'LIMEN_ORIENT_GIT_SECTION="$git_section"' in script
