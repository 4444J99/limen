from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from limen.host_admission import AdmissionController
from limen.host_admission_capabilities import host_admission_capabilities

ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = ROOT / "scripts" / "hooks" / "codex-host-admission.py"
FIXTURE_ROOT = ROOT / "cli" / "tests" / "fixtures" / "codex-hooks" / "0.144.6"
CLAUDE_HOOK_PATH = ROOT / "scripts" / "hooks" / "claude-host-admission.py"


def load_hook(path: Path = HOOK_PATH):
    spec = importlib.util.spec_from_file_location(f"{path.stem.replace('-', '_')}_test_module", path)
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


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_capability_probe_is_exact_fast_and_side_effect_free(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH), "--capabilities"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=1,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == host_admission_capabilities()
    assert set(json.loads(result.stdout)) == {
        "schema",
        "reader_protocol",
        "policy_revision",
        "state_schemas",
        "lease_kinds",
        "stable_action_denial",
        "single_rejection_channel",
        "migration",
    }
    assert list(tmp_path.iterdir()) == []


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


def test_user_prompt_submit_never_acquires_global_execution_lease(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    monkeypatch.setattr(
        hook,
        "codex_owner_pid",
        lambda: (_ for _ in ()).throw(AssertionError("session start must not resolve a lease owner")),
    )
    requests = [
        payload("UserPromptSubmit"),
        payload("UserPromptSubmit", session="session-b"),
        payload("UserPromptSubmit", permission_mode="plan"),
        {"hook_event_name": "UserPromptSubmit", "permission_mode": "default"},
    ]
    assert all(hook.handle(request, controller=service) is None for request in requests)
    assert service.status(probe=False)["leases"] == []


def test_installed_client_fixtures_all_admit_session_start(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    requests = [
        fixture("user-prompt-submit-plan.json"),
        fixture("user-prompt-submit-default.json"),
        fixture("user-prompt-submit-bypass-boundary.json"),
    ]
    missing_mode = fixture("user-prompt-submit-default.json")
    missing_mode.pop("permission_mode")
    requests.append(missing_mode)

    assert all(hook.handle(request, controller=service, owner_pid=101) is None for request in requests)
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

    freeform = hook.handle(
        payload(
            "PreToolUse",
            cwd=str(first),
            tool_name="apply_patch",
            tool_input="*** Add File: ../outside.txt\n+unsafe\n",
        ),
        controller=service,
        owner_pid=101,
    )
    assert freeform["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-outside-worktree"
    assert service.status(probe=False)["leases"] == []


def test_structured_tool_workdir_overrides_session_startup_cwd(tmp_path: Path) -> None:
    hook = load_hook()
    main, first, _second = linked_worktrees(tmp_path)
    service = controller(tmp_path / "admission")
    request = payload(
        "PreToolUse",
        cwd=str(main),
        tool_name="Edit",
        tool_input={
            "workdir": str(first),
            "file_path": str(first / "tracked.txt"),
        },
    )
    assert hook.handle(request, controller=service, owner_pid=101) is None
    lease = service.status(probe=False)["leases"][0]
    assert lease["kind"].startswith("execution:")

    patch_service = controller(tmp_path / "patch-admission")
    patch_request = payload(
        "PreToolUse",
        cwd=str(main),
        tool_name="apply_patch",
        tool_input={
            "workdir": str(first),
            "patch": "*** Add File: nested/new.txt\n+safe\n",
        },
    )
    assert hook.handle(patch_request, controller=patch_service, owner_pid=202) is None


def test_conflicting_or_missing_effective_cwd_fails_closed(tmp_path: Path) -> None:
    hook = load_hook()
    _main, first, second = linked_worktrees(tmp_path)
    service = controller(tmp_path / "admission")
    conflicting = payload(
        "PreToolUse",
        cwd="",
        tool_name="Edit",
        tool_input={
            "workdir": str(first),
            "cwd": str(second),
            "file_path": str(first / "tracked.txt"),
        },
    )
    output = hook.handle(conflicting, controller=service, owner_pid=101)
    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "conflicting-tool-cwd"

    missing = payload(
        "PreToolUse",
        cwd="",
        tool_name="Edit",
        tool_input={"file_path": str(first / "tracked.txt")},
    )
    output = hook.handle(missing, controller=service, owner_pid=101)
    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "effective-cwd-unavailable"

    missing_target = payload(
        "PreToolUse",
        cwd=str(first),
        tool_name="apply_patch",
        tool_input={},
    )
    output = hook.handle(missing_target, controller=service, owner_pid=101)
    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-unavailable"
    assert service.status(probe=False)["leases"] == []


def test_git_c_and_cd_redirection_resolve_the_actual_write_scope(tmp_path: Path) -> None:
    hook = load_hook()
    main, first, second = linked_worktrees(tmp_path)

    git_service = controller(tmp_path / "git-admission")
    git_request = payload(
        "PreToolUse",
        cwd=str(main),
        tool_input={"command": f"git -C {first} checkout -b topic"},
    )
    assert hook.handle(git_request, controller=git_service, owner_pid=101) is None

    redirection_service = controller(tmp_path / "redirection-admission")
    redirected = payload(
        "PreToolUse",
        cwd=str(main),
        tool_input={"command": f"cd {second} && printf ok > receipt.txt"},
    )
    assert hook.handle(redirected, controller=redirection_service, owner_pid=202) is None

    outside_service = controller(tmp_path / "outside-admission")
    escaped = payload(
        "PreToolUse",
        cwd=str(main),
        tool_input={"command": f"cd {first} && printf unsafe > ../outside.txt"},
    )
    output = hook.handle(escaped, controller=outside_service, owner_pid=101)
    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-outside-worktree"
    assert outside_service.status(probe=False)["leases"] == []


def test_git_admin_targets_cannot_escape_the_leased_worktree(tmp_path: Path) -> None:
    hook = load_hook()
    _main, first, _second = linked_worktrees(tmp_path)
    outside = tmp_path / "outside"
    commands = [
        f"git --git-dir={outside / '.git'} checkout -b topic",
        f"git --work-tree={outside} checkout -b topic",
        f"GIT_DIR={outside / '.git'} git checkout -b topic",
        f"GIT_WORK_TREE={outside} git checkout -b topic",
    ]

    for index, command in enumerate(commands):
        service = controller(tmp_path / f"git-admin-admission-{index}")
        output = hook.handle(
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_input={"command": command},
            ),
            controller=service,
            owner_pid=101,
        )
        assert output["hookSpecificOutput"]["permissionDecisionReason"] == "unsupported-git-admin-target"
        assert service.status(probe=False)["leases"] == []


def test_background_substitution_and_plan_only_mutations_are_denied(tmp_path: Path) -> None:
    hook = load_hook()
    _main, first, _second = linked_worktrees(tmp_path)
    cases = [
        (
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_input={"command": "printf unsafe > out.txt &"},
            ),
            "background-command",
        ),
        (
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_input={"command": "printf $(date) > out.txt"},
            ),
            "command-substitution-or-multiline",
        ),
        (
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_name="Edit",
                execution_profile={"planning_only": True, "build_allowed": False},
                tool_input={"file_path": str(first / "tracked.txt")},
            ),
            "plan-only-mutation",
        ),
    ]
    for index, (request, reason) in enumerate(cases):
        service = controller(tmp_path / f"admission-{index}")
        output = hook.handle(request, controller=service, owner_pid=101)
        assert output["hookSpecificOutput"]["permissionDecisionReason"] == reason
        assert service.status(probe=False)["leases"] == []


def test_codex_and_claude_adapters_share_action_policy(tmp_path: Path) -> None:
    codex = load_hook()
    claude = load_hook(CLAUDE_HOOK_PATH)
    main, first, _second = linked_worktrees(tmp_path)
    requests = [
        payload(
            "PreToolUse",
            cwd=str(main),
            tool_input={"command": f"cd {first} && printf unsafe > ../outside.txt"},
        ),
        payload(
            "PreToolUse",
            cwd=str(first),
            tool_input={"command": "printf unsafe > out.txt &"},
        ),
        payload(
            "PreToolUse",
            cwd="",
            tool_name="Write",
            tool_input={"file_path": str(first / "new.txt")},
        ),
    ]
    for index, request in enumerate(requests):
        codex_output = codex.handle(
            request,
            controller=controller(tmp_path / f"codex-{index}"),
            owner_pid=101,
        )
        claude_output = claude.handle(
            request,
            controller=controller(tmp_path / f"claude-{index}"),
            owner_pid=202,
        )
        assert (
            codex_output["hookSpecificOutput"]["permissionDecisionReason"]
            == claude_output["hookSpecificOutput"]["permissionDecisionReason"]
        )


def test_codex_and_claude_admit_all_structured_write_targets(tmp_path: Path) -> None:
    codex = load_hook()
    claude = load_hook(CLAUDE_HOOK_PATH)
    _main, first, _second = linked_worktrees(tmp_path)
    cases = [
        ("Edit", "file_path", first / "tracked.txt"),
        ("MultiEdit", "file_path", first / "tracked.txt"),
        ("NotebookEdit", "notebook_path", first / "notes.ipynb"),
        ("Write", "file_path", first / "new.txt"),
    ]

    for adapter_index, adapter in enumerate((codex, claude)):
        for case_index, (tool_name, path_key, target) in enumerate(cases):
            service = controller(tmp_path / f"structured-{adapter_index}-{case_index}")
            request = payload(
                "PreToolUse",
                cwd=str(first),
                tool_name=tool_name,
                tool_input={path_key: str(target)},
            )
            assert adapter.handle(request, controller=service, owner_pid=101 + adapter_index) is None

            escaped_service = controller(tmp_path / f"structured-escape-{adapter_index}-{case_index}")
            escaped = adapter.handle(
                request | {"tool_input": {path_key: str(tmp_path / "outside")}},
                controller=escaped_service,
                owner_pid=201 + adapter_index,
            )
            assert escaped["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-outside-worktree"

        conflicting_aliases = adapter.handle(
            payload(
                "PreToolUse",
                cwd=str(first),
                tool_name="NotebookEdit",
                tool_input={
                    "file_path": str(first / "decoy.txt"),
                    "notebook_path": str(tmp_path / "outside.ipynb"),
                },
            ),
            controller=controller(tmp_path / f"structured-aliases-{adapter_index}"),
            owner_pid=301 + adapter_index,
        )
        assert conflicting_aliases["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-outside-worktree"


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

    escape = first / "escape"
    escape.symlink_to(tmp_path, target_is_directory=True)
    escape_service = controller(tmp_path / "escape-admission")
    escaped = hook.handle(
        payload(
            "PreToolUse",
            cwd=str(first),
            tool_name="Write",
            tool_input={"file_path": str(escape / "outside.txt")},
        ),
        controller=escape_service,
        owner_pid=303,
    )
    assert escaped["hookSpecificOutput"]["permissionDecisionReason"] == "write-target-outside-worktree"


def test_nested_repository_growth_blocks_subsequent_write_without_deleting_state(tmp_path: Path) -> None:
    hook = load_hook()
    _main, first, _second = linked_worktrees(tmp_path)
    nested = first / "nested"
    subprocess.run(["git", "init", "-q", str(nested)], check=True)
    service = controller(tmp_path / "admission")

    output = hook.handle(
        payload(
            "PreToolUse",
            cwd=str(first),
            tool_name="Edit",
            tool_input={"file_path": str(first / "tracked.txt")},
        ),
        controller=service,
        owner_pid=101,
    )

    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "nested-repository"
    assert service.status(probe=False)["leases"] == []
    assert (nested / ".git").exists()


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
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == "unparseable-mutation-capable-compound"
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
    assert CLAUDE_HOOK_PATH.is_file()


def test_project_config_caps_threads_and_depth() -> None:
    config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert config["agents"] == {"max_threads": 3, "max_depth": 1}


def test_capabilities_cli_is_fast_versioned_json_without_hook_input() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH), "--capabilities"],
        capture_output=True,
        text=True,
        timeout=2,
        check=True,
    )
    capabilities = json.loads(result.stdout)
    assert set(capabilities) == {
        "schema",
        "reader_protocol",
        "policy_revision",
        "state_schemas",
        "lease_kinds",
        "stable_action_denial",
        "single_rejection_channel",
        "migration",
    }
    assert capabilities["schema"] == "limen.codex_host_admission_capabilities.v1"
    assert capabilities["state_schemas"]["scoped"] == "limen.host_admission_scoped_state.v1"
    assert capabilities["stable_action_denial"] is True


def test_project_delegate_requires_compatible_immutable_runtime(tmp_path: Path) -> None:
    hook = load_hook()
    incompatible = tmp_path / "incompatible.py"
    incompatible.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "if sys.argv[1:] == ['--capabilities']:\n"
        "    print(json.dumps({'schema': 'old'}))\n"
        "else:\n"
        "    print(json.dumps({'systemMessage': 'must not run'}))\n",
        encoding="utf-8",
    )

    with pytest.raises(hook.ImmutableRuntimeError, match="runtime-capabilities-incompatible"):
        hook.delegate_immutable(incompatible, json.dumps(fixture("user-prompt-submit-default.json")))


def test_project_delegate_uses_compatible_immutable_runtime(tmp_path: Path) -> None:
    hook = load_hook()
    target = tmp_path / "immutable.py"
    capabilities = json.dumps(hook.host_admission_capabilities(), sort_keys=True)
    target.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        f"CAPABILITIES = {capabilities!r}\n"
        "if sys.argv[1:] == ['--capabilities']:\n"
        "    print(CAPABILITIES)\n"
        "else:\n"
        "    payload = json.load(sys.stdin)\n"
        "    print(json.dumps({'systemMessage': 'immutable:' + payload['hook_event_name']}))\n",
        encoding="utf-8",
    )

    output = hook.delegate_immutable(
        target,
        json.dumps(fixture("user-prompt-submit-default.json")),
    )

    assert output == {"systemMessage": "immutable:UserPromptSubmit"}


def test_incompatible_runtime_never_blocks_session_start_and_denies_mutation_once() -> None:
    hook = load_hook()
    error = hook.ImmutableRuntimeError("runtime-capabilities-timeout")

    prompt = hook._runtime_unavailable(fixture("user-prompt-submit-default.json"), error)
    tool = hook._runtime_unavailable(
        payload("PreToolUse", tool_input={"command": "git checkout -b topic"}),
        error,
    )
    observe = hook._runtime_unavailable(
        payload("PreToolUse", tool_input={"command": "git status --short"}),
        error,
    )
    sanctioned = hook._runtime_unavailable(
        payload("PreToolUse", tool_input={"command": "limen dispatch"}),
        error,
    )

    assert prompt is None
    assert set(tool) == {"hookSpecificOutput"}
    assert set(sanctioned) == {"hookSpecificOutput"}
    assert observe is None
    assert "domus-limen-runtime status" in tool["hookSpecificOutput"]["permissionDecisionReason"]


def test_runtime_interpreter_uses_installed_runtime_venv(tmp_path: Path) -> None:
    hook = load_hook()
    runtime = tmp_path / "runtime"
    target = runtime / "scripts" / "hooks" / "codex-host-admission.py"
    interpreter = runtime / "venv" / "bin" / "python"
    target.parent.mkdir(parents=True)
    interpreter.parent.mkdir(parents=True)
    target.write_text("# hook\n", encoding="utf-8")
    interpreter.write_text("# interpreter\n", encoding="utf-8")

    assert hook._runtime_interpreter(target) == str(interpreter)


def test_unavailable_runtime_still_releases_exact_owned_stop_lease(tmp_path: Path) -> None:
    hook = load_hook()
    _main, worktree, _second = linked_worktrees(tmp_path)
    service = controller(tmp_path / "admission")
    request = payload("Stop", cwd=str(worktree))
    owner = hook._turn_owner(request)
    assert owner is not None
    scope = hook.worktree_scope(worktree)
    service.acquire(scope.lease_kind, owner=owner, surface="test", pid=101)

    output = hook._runtime_unavailable(
        request,
        hook.ImmutableRuntimeError("runtime-capabilities-timeout"),
        controller=service,
        owner_pid=101,
    )

    assert output is None
    assert service.status(probe=False)["leases"] == []


def test_malformed_store_emits_exactly_one_redacted_rejection_channel(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _main, worktree, _second = linked_worktrees(tmp_path)
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    (root / "state.json").write_text(
        json.dumps({"schema": "limen.host_admission_state.v0", "leases": [], "pressure": None}),
        encoding="utf-8",
    )
    request = payload(
        "PreToolUse",
        cwd=str(worktree),
        tool_input={"command": "git checkout -b topic"},
    )
    hook = load_hook()
    monkeypatch.setenv("LIMEN_HOST_ADMISSION_ROOT", str(root))
    monkeypatch.setattr(hook, "codex_owner_pid", lambda: os.getpid())
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(request)))
    assert hook.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert set(output) == {"hookSpecificOutput"}
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "invalid_field=schema" in reason
    assert "reader_protocol=limen.host_admission_reader.v2" in reason
    assert "writer_protocol=limen.host_admission_state.v0" in reason
    assert "pid_identity=" in reason
    assert "host-work-admission.py diagnose" in reason
    assert "systemMessage" not in output and "stopReason" not in output


def test_hook_runner_prefers_codex_project_root() -> None:
    runner = (ROOT / "scripts" / "hooks" / "codex-hook-runner.sh").read_text(encoding="utf-8")
    assert runner.index('"${CODEX_PROJECT_DIR:-}"') < runner.index('"${CLAUDE_PROJECT_DIR:-}"')
    assert "--delegate-immutable" not in runner
