from __future__ import annotations

import importlib.util
import json
import subprocess
import tomllib
from pathlib import Path

from limen.host_admission import AdmissionController

ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = ROOT / "scripts" / "hooks" / "codex-host-admission.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("codex_host_admission_hook", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pressure(**overrides):
    payload = {
        "observed_epoch": 100.0,
        "backblaze_cpu_percent": 0.0,
        "backblaze_rss_bytes": 0,
        "swap_used_bytes": 0,
        "memory_bytes": 16 * 1024**3,
        "disk_mib_per_second_samples": [0.0, 0.0],
        "vitals_action": "ok",
        "sensor_errors": [],
    }
    payload.update(overrides)
    return payload


def controller(tmp_path: Path, observations=None) -> AdmissionController:
    observations = observations or [pressure()]
    return AdmissionController(
        tmp_path / "state",
        clock=lambda: 100.0,
        alive=lambda pid: pid > 0,
        identity=lambda pid: f"start-{pid}",
        descendant=lambda _pid, _ancestor: False,
        pressure_probe=lambda: observations.pop(0),
        thresholds={
            "backblaze_cpu_percent": 50,
            "backblaze_rss_bytes": 1024**3,
            "swap_fraction": 0.25,
            "swap_growth_bytes_per_minute": 512 * 1024**2,
            "disk_mib_per_second": 100,
        },
    )


def payload(event: str, session: str = "session-a", **extra):
    return {
        "hook_event_name": event,
        "session_id": session,
        "turn_id": "turn-a",
        "cwd": str(ROOT),
        "permission_mode": "default",
        "tool_name": "Bash",
        **extra,
    }


def linked_worktrees(tmp_path: Path) -> tuple[Path, Path, Path]:
    main = tmp_path / "repo"
    first = tmp_path / "first"
    second = tmp_path / "second"
    main.mkdir()
    commands = [
        ["git", "init", "-q", "-b", "main", str(main)],
        ["git", "-C", str(main), "config", "user.email", "test@example.com"],
        ["git", "-C", str(main), "config", "user.name", "Test"],
    ]
    for command in commands:
        subprocess.run(command, check=True)
    (main / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(main), "commit", "-qm", "fixture"], check=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-qb", "first", str(first)], check=True)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-qb", "second", str(second)], check=True)
    return main, first, second


def test_user_prompt_submit_allows_concurrent_roots_when_action_denial_is_supported(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    assert (
        hook.handle(
            payload("UserPromptSubmit"),
            controller=service,
            owner_pid=101,
            feature_probe=lambda: True,
        )
        is None
    )
    assert (
        hook.handle(
            payload("UserPromptSubmit", session="session-b"),
            controller=service,
            owner_pid=202,
            feature_probe=lambda: True,
        )
        is None
    )
    assert service.status(probe=False)["leases"] == []


def test_feature_probe_fallback_retains_legacy_root_lock(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    assert (
        hook.handle(
            payload("UserPromptSubmit"),
            controller=service,
            owner_pid=101,
            feature_probe=lambda: False,
        )
        is None
    )

    denied = hook.handle(
        payload("UserPromptSubmit", session="session-b"),
        controller=service,
        owner_pid=202,
        feature_probe=lambda: False,
    )
    assert denied["continue"] is False
    assert "execution-lease-held" in denied["stopReason"]
    assert "systemMessage" not in denied
    assert len(service.status(probe=False)["leases"]) == 1


def test_plan_mode_never_acquires_execution_lease(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    request = payload("UserPromptSubmit", permission_mode="plan")
    assert hook.handle(request, controller=service, owner_pid=101, feature_probe=lambda: False) is None
    assert service.status(probe=False)["leases"] == []


def test_pre_tool_use_hard_denies_guarded_heavy_call_under_pressure(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path, [pressure(backblaze_cpu_percent=90)])
    output = hook.handle(
        payload(
            "PreToolUse",
            tool_input={"command": "bash scripts/verify-whole.sh"},
        ),
        controller=service,
        owner_pid=101,
    )
    assert set(output) == {"hookSpecificOutput"}
    specific = output["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "backblaze-cpu" in specific["permissionDecisionReason"]


def test_pre_tool_use_read_only_command_never_acquires_writer(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    output = hook.handle(
        payload("PreToolUse", tool_input={"command": "git status --short"}),
        controller=service,
        owner_pid=101,
    )
    assert output is None
    assert service.status(probe=False)["leases"] == []


def test_same_worktree_has_one_writer_but_disjoint_worktrees_run_concurrently(tmp_path: Path) -> None:
    hook = load_hook()
    main, first, second = linked_worktrees(tmp_path)
    del main
    service = controller(tmp_path / "admission")
    first_write = payload(
        "PreToolUse",
        cwd=str(first),
        tool_name="Edit",
        tool_input={"file_path": str(first / "tracked.txt")},
    )
    assert hook.handle(first_write, controller=service, owner_pid=101) is None

    same_scope = hook.handle(
        first_write | {"session_id": "session-b"},
        controller=service,
        owner_pid=202,
    )
    assert same_scope["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert same_scope["hookSpecificOutput"]["permissionDecisionReason"] == "workspace-writer-lease-held"

    second_write = first_write | {
        "cwd": str(second),
        "session_id": "session-b",
        "tool_input": {"file_path": str(second / "tracked.txt")},
    }
    assert hook.handle(second_write, controller=service, owner_pid=202) is None
    leases = service.status(probe=False)["leases"]
    assert len(leases) == 2
    assert len({lease["kind"] for lease in leases}) == 2
    assert all(lease["kind"].startswith("execution:") for lease in leases)


def test_primary_checkout_write_and_out_of_scope_target_are_denied(tmp_path: Path) -> None:
    hook = load_hook()
    main, first, _second = linked_worktrees(tmp_path)
    service = controller(tmp_path / "admission")

    shared = hook.handle(
        payload(
            "PreToolUse",
            cwd=str(main),
            tool_name="Write",
            tool_input={"file_path": str(main / "new.txt")},
        ),
        controller=service,
        owner_pid=101,
    )
    assert shared["hookSpecificOutput"]["permissionDecisionReason"] == "shared-checkout-write"

    escaped = hook.handle(
        payload(
            "PreToolUse",
            cwd=str(first),
            tool_name="apply_patch",
            tool_input={"patch": "*** Add File: ../outside.txt\n+unsafe\n"},
        ),
        controller=service,
        owner_pid=101,
    )
    assert escaped["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-outside-worktree"
    assert service.status(probe=False)["leases"] == []


def test_symlink_aliases_resolve_to_the_same_writer_scope(tmp_path: Path) -> None:
    hook = load_hook()
    _main, first, _second = linked_worktrees(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(first, target_is_directory=True)
    service = controller(tmp_path / "admission")
    assert (
        hook.handle(
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_name="Edit",
                tool_input={"file_path": str(first / "tracked.txt")},
            ),
            controller=service,
            owner_pid=101,
        )
        is None
    )
    denied = hook.handle(
        payload(
            "PreToolUse",
            session="session-b",
            cwd=str(alias),
            tool_name="Edit",
            tool_input={"file_path": str(alias / "tracked.txt")},
        ),
        controller=service,
        owner_pid=202,
    )
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "workspace-writer-lease-held"


def test_ambiguous_or_mutation_capable_bash_is_treated_as_a_write(tmp_path: Path) -> None:
    hook = load_hook()
    main, first, _second = linked_worktrees(tmp_path)
    service = controller(tmp_path / "admission")
    denied = hook.handle(
        payload(
            "PreToolUse",
            cwd=str(main),
            tool_input={"command": "git status && unknown-command"},
        ),
        controller=service,
        owner_pid=101,
    )
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "shared-checkout-write"
    assert (
        hook.handle(
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_input={"command": "git checkout -b topic"},
            ),
            controller=service,
            owner_pid=101,
        )
        is None
    )
    assert len(service.status(probe=False)["leases"]) == 1


def test_unguarded_heavy_call_names_the_sanctioned_equivalent(tmp_path: Path) -> None:
    hook = load_hook()
    output = hook.handle(
        payload("PreToolUse", tool_input={"command": "npm test"}),
        controller=controller(tmp_path),
        owner_pid=101,
    )
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "unguarded-heavy" in reason
    assert "scripts/verify-scoped.sh" in reason


def test_subagent_start_is_advisory_and_names_finite_bounds(tmp_path: Path) -> None:
    hook = load_hook()
    output = hook.handle(
        payload("SubagentStart"),
        controller=controller(tmp_path),
        owner_pid=101,
    )
    assert "continue" not in output
    assert "max_threads=3" in output["systemMessage"]
    assert "max_depth=1" in output["systemMessage"]
    assert output["hookSpecificOutput"]["hookEventName"] == "SubagentStart"


def test_stop_allows_at_most_one_explicit_closeout_continuation(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    _, worktree, _ = linked_worktrees(tmp_path)
    write = payload(
        "PreToolUse",
        cwd=str(worktree),
        tool_name="Edit",
        tool_input={"file_path": str(worktree / "tracked.txt")},
    )
    assert hook.handle(write, controller=service, owner_pid=101) is None

    first = hook.handle(
        payload("Stop", cwd=str(worktree), stop_hook_active=False),
        controller=service,
        owner_pid=101,
        closeout_probe=lambda _cwd: True,
    )
    assert first["continue"] is False
    assert "One bounded closeout pass" in first["stopReason"]
    assert "systemMessage" not in first
    assert len(service.status(probe=False)["leases"]) == 1

    final = hook.handle(
        payload("Stop", cwd=str(worktree), stop_hook_active=True),
        controller=service,
        owner_pid=101,
        closeout_probe=lambda _cwd: True,
    )
    assert final is None
    assert service.status(probe=False)["leases"] == []


def test_hook_config_wires_required_events_and_dynamic_worktree_root() -> None:
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    hooks = config["hooks"]
    assert {"UserPromptSubmit", "PreToolUse", "SubagentStart", "Stop"} <= set(hooks)
    assert "apply_patch" in hooks["PreToolUse"][0]["matcher"]
    assert "Edit" in hooks["PreToolUse"][0]["matcher"]
    assert "Write" in hooks["PreToolUse"][0]["matcher"]
    commands = [handler["command"] for groups in hooks.values() for group in groups for handler in group["hooks"]]
    assert all("git rev-parse --show-toplevel" in command for command in commands)
    assert not any("/Users/" in command for command in commands)


def test_project_config_caps_threads_and_depth() -> None:
    config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert config["agents"] == {"max_threads": 3, "max_depth": 1}


def test_hook_runner_prefers_codex_project_root() -> None:
    runner = (ROOT / "scripts" / "hooks" / "codex-hook-runner.sh").read_text(encoding="utf-8")
    assert runner.index('"${CODEX_PROJECT_DIR:-}"') < runner.index('"${CLAUDE_PROJECT_DIR:-}"')
