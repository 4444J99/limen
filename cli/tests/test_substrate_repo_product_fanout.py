from __future__ import annotations

import importlib.util
import json
import subprocess
from argparse import Namespace
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(script_name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / script_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(*args: str, cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")


def test_substrate_ledger_uses_env_roots_without_stale_drive_blocker(tmp_path: Path, monkeypatch) -> None:
    active = tmp_path / "active-root"
    active.mkdir()
    missing = tmp_path / "missing-root"
    monkeypatch.setenv("LIMEN_STORAGE_ROOTS", f"{active}{','}{missing}")
    mod = _load("substrate-ledger.py", "substrate_ledger_under_test")

    snap = mod.build_snapshot(
        config_path=tmp_path / "missing-config.json",
        include_mounted=False,
        free_floor_gib=0,
        usage_ceiling_pct=100,
    )

    by_path = {Path(row["path"]).name: row for row in snap["roots"]}
    assert by_path["active-root"]["status"] == "active"
    assert by_path["missing-root"]["status"] == "missing"
    assert snap["status"] == "ready"
    assert "4444-iivii" not in json.dumps(snap)


def test_repo_surface_ledger_discovers_nested_repos_and_duplicate_remotes(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    repo_a = root / "app-a"
    repo_b = repo_a / "nested" / "app-b"
    repo_b.mkdir(parents=True)
    repo_a.mkdir(exist_ok=True)
    for repo in (repo_a, repo_b):
        _git("init", "-q", cwd=repo)
        _git("remote", "add", "origin", "git@example.invalid:owner/shared.git", cwd=repo)
        (repo / "package.json").write_text('{"scripts":{"test":"true"}}\n', encoding="utf-8")

    for env_name in ("LIMEN_REPO_ROOTS", "LIMEN_WORKSPACE_ROOT", "LIMEN_WORKTREE_ROOT"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("LIMEN_REPO_ROOTS", str(root))
    mod = _load("repo-surface-ledger.py", "repo_surface_ledger_under_test")

    snap = mod.build_snapshot(max_depth=5)

    assert snap["repo_count"] == 2
    assert any(group["repo_count"] == 2 for group in snap["duplicate_remotes"])
    assert all("package:test" in row["test_surfaces"] for row in snap["repos"])
    assert snap["classification_summary"]["unclassified_count"] == 0
    assert snap["classification_summary"]["nested_repo_count"] == 1
    assert snap["classification_summary"]["disposition_counts"]["consolidate"] == 2
    assert {row["classification"]["location"] for row in snap["repos"]} == {"nested", "workspace"}
    assert {row["classification"]["remote"] for row in snap["repos"]} == {"remote-other"}

    public = json.dumps(mod.public_snapshot(snap), sort_keys=True)
    assert "git@example.invalid" not in public
    assert "owner/shared.git" not in public


def test_salvage_map_clusters_duplicate_remote_and_product_surfaces(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    repo_a = root / "product-a"
    repo_b = root / "product-a-copy"
    for repo, remote in (
        (repo_a, "git@github.com:organvm/product-a.git"),
        (repo_b, "https://github.com/organvm/product-a.git"),
    ):
        repo.mkdir(parents=True)
        _git("init", "-q", cwd=repo)
        _git("remote", "add", "origin", remote, cwd=repo)
        (repo / "README.md").write_text("# Shared Product\n", encoding="utf-8")
        (repo / "package.json").write_text(
            json.dumps({"name": "shared-product", "scripts": {"test": "node --test"}}),
            encoding="utf-8",
        )

    monkeypatch.setenv("LIMEN_REPO_ROOTS", str(root))
    repo_mod = _load("repo-surface-ledger.py", "repo_surface_ledger_salvage_test")
    salvage_mod = _load("salvage-yard-map.py", "salvage_yard_map_under_test")

    repo_snapshot = repo_mod.build_snapshot(max_depth=4)
    salvage = salvage_mod.build_salvage_map(
        repo_snapshot,
        {"plan_source_proof": {"source_plan_hashes": ["abc123"]}},
    )

    duplicate_clusters = [cluster for cluster in salvage["clusters"] if cluster["repo_count"] == 2]
    assert len(duplicate_clusters) == 1
    assert duplicate_clusters[0]["disposition"] == "consolidate"
    assert set(salvage["source_plan_hashes"]) == {"abc123"}
    public = json.dumps(salvage_mod.public_salvage_map(salvage), sort_keys=True)
    assert "git@github.com" not in public
    assert "RAW_PRIVATE_PLAN_BODY" not in public


def test_product_ledger_keeps_global_work_active_when_one_product_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    private = tmp_path / ".limen-private" / "session-corpus" / "lifecycle"
    private.mkdir(parents=True)
    (tmp_path / "tasks.yaml").write_text(
        yaml.safe_dump(
            {
                "tasks": [
                    {
                        "id": "BLOCKED",
                        "title": "blocked local product",
                        "target_agent": "codex",
                        "status": "failed_blocked",
                        "created": "2026-06-30",
                    },
                    {
                        "id": "REV",
                        "title": "open revenue product",
                        "target_agent": "codex",
                        "status": "open",
                        "labels": ["revenue", "product"],
                        "repo": "owner/revenue",
                        "created": "2026-06-30",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "value-repos.json").write_text(json.dumps({"repos": ["owner/revenue"]}), encoding="utf-8")
    (tmp_path / "positioning-seeds.json").write_text(json.dumps({"repos": {"owner/revenue": {}}}), encoding="utf-8")
    (private / "prompt-lifecycle-index.json").write_text(
        json.dumps({"sessions": [{"session_key": "session-a", "source": "codex-sessions"}]}),
        encoding="utf-8",
    )
    (private / "salvage-yard-map.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "SY-open",
                        "canonical_repo": "owner/open",
                        "repo_count": 2,
                        "disposition": "consolidate",
                        "children": [{"repo": "owner/open-copy"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    mod = _load("product-ledger.py", "product_ledger_under_test")
    snap = mod.build_snapshot()
    blocked_rows = [row for row in snap["products"] if row["blocked"]]

    assert snap["blocked_count"] == 1
    assert snap["global_status"] == "active"
    assert {row["state"] for row in blocked_rows} == {"blocked_local"}
    assert any(row["outward_path"] in {"revenue-path", "seo-proof"} for row in snap["next_unblocked"])
    assert any(row["source_kind"] == "salvage-yard" for row in snap["products"])
    assert all(not row["blocked"] for row in snap["next_unblocked"])


def test_current_session_fanout_creates_capability_selected_planners_and_executors(tmp_path: Path, monkeypatch) -> None:
    session = tmp_path / "session.jsonl"
    user_plan = "# Prior Product Plan\n\n## Summary\n- Build 1000 alpha omega products from every prompt.\n"
    assistant_plan = (
        "# Assistant Fanout Plan\n\n"
        "## Summary\n"
        "- Use 10 peer planner worktrees plus contrib mirror and no reset spend.\n"
    )
    duplicate_plan = assistant_plan
    newest_plan = (
        "# Newest Revenue Plan\n\n## Summary\n- Route money, SEO, lead, and sell-ready work to reachable lanes.\n"
    )
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:00:00Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "text": (
                                        "A previous agent produced the plan below to accomplish "
                                        "the user's task.\n\n"
                                        f"{user_plan}"
                                    )
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:01:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": f"<proposed_plan>\n{assistant_plan}</proposed_plan>"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:02:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": f"<proposed_plan>\n{duplicate_plan}</proposed_plan>"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:03:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": f"<proposed_plan>\n{newest_plan}</proposed_plan>"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    mod = _load("current-session-fanout.py", "current_session_fanout_under_test")
    monkeypatch.setattr(
        mod,
        "lane_selection",
        lambda selector, rows=None, capability="execute": (
            ["codex", "opencode"] if capability == "conduct" else ["opencode", "github_actions"]
        ),
    )

    snap = mod.build_snapshot(
        Namespace(
            session=str(session),
            source_agent="codex",
            min_planners=10,
            planner_lanes="auto",
            executor_lanes="auto",
            conductor_agent="auto",
            include_contrib=True,
            allow_reset_spend=False,
        )
    )

    assert snap["status"] == "ready"
    assert snap["plan_event_count"] == 4
    assert snap["unique_plan_count"] == 3
    assert snap["duplicate_plan_count"] == 1
    assert snap["unconsolidated_plan_hashes"] == []
    assert [event["title"] for event in snap["plan_events"]] == [
        "Newest Revenue Plan",
        "Assistant Fanout Plan",
        "Assistant Fanout Plan",
        "Prior Product Plan",
    ]
    assert snap["plan_events"][2]["duplicate"] is True
    expected_plan_hashes = [event["hash"] for event in snap["unique_plan_sources"]]
    assert len(snap["planner_packets"]) == 10
    assert {packet["target_agent"] for packet in snap["planner_packets"]} == {"codex", "opencode"}
    assert {packet["target_agent"] for packet in snap["executor_packets"]} == {"opencode", "github_actions"}
    assert snap["no_reset_spend"] is True
    assert all(packet["spend_guard"] == "no-reset-spend" for packet in snap["planner_packets"])
    assert all(
        packet["source_plan_hashes"] == expected_plan_hashes
        for packet in snap["planner_packets"] + snap["executor_packets"]
    )
    assert all(packet["executor_criteria"] for packet in snap["planner_packets"] + snap["executor_packets"])
    assert all(packet["verification_predicates"] for packet in snap["planner_packets"] + snap["executor_packets"])
    assert all(str(session) in packet["verification_predicates"][0] for packet in snap["planner_packets"])
    assert any(
        "product-ledger.py" in predicate
        for packet in snap["planner_packets"] + snap["executor_packets"]
        for predicate in packet["verification_predicates"]
    )

    markdown = mod.render_markdown(snap)
    assert "## Plan Source Proof" in markdown
    assert "## Executor Criteria" in markdown
    assert "Verification predicates" in markdown
    assert "Prior Product Plan" in markdown
    assert "Assistant Fanout Plan" in markdown
    assert "Newest Revenue Plan" in markdown
    assert "duplicate" in markdown
    assert "Unconsolidated plan events: 0" in markdown
    for plan_hash in expected_plan_hashes:
        assert plan_hash in markdown


def test_current_session_fanout_keeps_explicit_executor_lane_list_without_inventing_all_fallback(
    monkeypatch,
) -> None:
    mod = _load("current-session-fanout.py", "current_session_fanout_lanes_under_test")

    assert mod.lane_selection("opencode,agy,github-actions") == ["opencode", "agy", "github_actions"]
    expected = [agent for agent in mod.paid_agent_order() if "execute" in mod.execution_profiles()[agent].capabilities]
    assert mod.lane_selection("all") == expected


def test_current_session_fanout_task_seed_waterfalls_into_queue(tmp_path: Path, monkeypatch) -> None:
    session = tmp_path / "session.jsonl"
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-30T00:00:00Z",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "A previous agent produced the plan below to accomplish "
                                "the user's task.\n\n"
                                "# Waterfall Product Fanout\n\n"
                                "## Summary\n"
                                "- Turn this current session into multiple product workstreams.\n"
                            )
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tasks_path = tmp_path / "tasks.yaml"
    tasks_path.write_text(yaml.safe_dump({"tasks": []}), encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_CURRENT_SESSION_FANOUT_REPO", "owner/fanout")
    mod = _load("current-session-fanout.py", "current_session_fanout_seed_under_test")
    monkeypatch.setattr(
        mod,
        "lane_selection",
        lambda selector, rows=None, capability="execute": (
            ["claude", "opencode"] if capability == "conduct" else ["opencode", "github_actions"]
        ),
    )

    snap = mod.build_snapshot(
        Namespace(
            session=str(session),
            source_agent="claude",
            min_planners=3,
            planner_lanes="auto",
            executor_lanes="auto",
            conductor_agent="auto",
            include_contrib=False,
            allow_reset_spend=False,
            seed_tasks=True,
            apply_task_seed=False,
            tasks=str(tasks_path),
        )
    )

    assert snap["task_seed_count"] == 5
    assert snap["task_seed_repo"] == "owner/fanout"
    planners = [task for task in snap["task_seed"] if task["packet_type"] == "planner_packet"]
    executors = [task for task in snap["task_seed"] if task["packet_type"] == "executor_packet"]
    assert len(planners) == 3
    assert len(executors) == 2
    assert {task["target_agent"] for task in planners} == {"claude", "opencode"}
    assert all(task["depends_on"] == [] for task in planners)
    assert all(task["depends_on"] for task in executors)
    assert all("no-reset-spend" in task["labels"] for task in planners)
    assert all(task["status"] == "open" for task in snap["task_seed"])
    assert all(task["executor_criteria"] for task in snap["task_seed"])
    assert all(task["verification_predicates"] for task in snap["task_seed"])
    assert all("Executor criteria:" in task["context"] for task in snap["task_seed"])
    assert all("Verification predicates:" in task["context"] for task in snap["task_seed"])
    assert all(task["root_run_id"] == snap["root_run_id"] for task in snap["task_seed"])
    assert all(task["runtime_env"]["LIMEN_AGENT"] == task["target_agent"] for task in snap["task_seed"])
    assert all(task["runtime_env"]["LIMEN_INITIATOR_AGENT"] == "claude" for task in snap["task_seed"])

    apply_result = mod.apply_task_seed(snap, tasks_path)
    assert apply_result["status"] == "blocked", apply_result
    assert apply_result["appended"] == 0
    assert apply_result["skipped"] == 0
    assert apply_result["mode"] == "conduct-required"
    second_apply = mod.apply_task_seed(snap, tasks_path)
    assert second_apply["appended"] == 0
    assert second_apply["skipped"] == 0

    board = yaml.safe_load(tasks_path.read_text(encoding="utf-8"))
    assert len(board["tasks"]) == 0

    markdown = mod.render_markdown(snap)
    assert "## Task Seed" in markdown
    assert "Seed tasks: 5" in markdown
    assert "Direct task-seed activation is retired" in markdown
