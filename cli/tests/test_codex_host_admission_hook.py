from __future__ import annotations

import importlib.util
import json
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
        **extra,
    }


def test_user_prompt_submit_hard_stops_second_non_plan_root(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    assert hook.handle(payload("UserPromptSubmit"), controller=service, owner_pid=101) is None

    denied = hook.handle(
        payload("UserPromptSubmit", session="session-b"),
        controller=service,
        owner_pid=202,
    )
    assert denied["continue"] is False
    assert "execution-lease-held" in denied["stopReason"]
    assert len(service.status(probe=False)["leases"]) == 1


def test_plan_mode_never_acquires_execution_lease(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    request = payload("UserPromptSubmit", permission_mode="plan")
    assert hook.handle(request, controller=service, owner_pid=101) is None
    assert service.status(probe=False)["leases"] == []


def test_pre_tool_use_emits_supported_advisory_denial_payload(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path, [pressure(backblaze_cpu_percent=90)])
    output = hook.handle(
        payload("PreToolUse", tool_input={"command": "bash scripts/verify-whole.sh"}),
        controller=service,
        owner_pid=101,
    )
    assert set(output) == {"systemMessage"}
    assert "backblaze-cpu" in output["systemMessage"]
    assert "guarded entrypoint will fail closed" in output["systemMessage"]


def test_pre_tool_use_ignores_narrow_non_heavy_command(tmp_path: Path) -> None:
    hook = load_hook()
    service = controller(tmp_path)
    output = hook.handle(
        payload("PreToolUse", tool_input={"command": "pytest cli/tests/test_host_admission.py -q"}),
        controller=service,
        owner_pid=101,
    )
    assert output is None


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
    start = payload("UserPromptSubmit")
    assert hook.handle(start, controller=service, owner_pid=101) is None

    first = hook.handle(
        payload("Stop", stop_hook_active=False),
        controller=service,
        owner_pid=101,
        closeout_probe=lambda _cwd: True,
    )
    assert first["continue"] is False
    assert "One bounded closeout pass" in first["stopReason"]
    assert len(service.status(probe=False)["leases"]) == 1

    final = hook.handle(
        payload("Stop", stop_hook_active=True),
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
    commands = [handler["command"] for groups in hooks.values() for group in groups for handler in group["hooks"]]
    assert all("git rev-parse --show-toplevel" in command for command in commands)
    assert not any("/Users/" in command for command in commands)


def test_project_config_caps_threads_and_depth() -> None:
    config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert config["agents"] == {"max_threads": 3, "max_depth": 1}


def test_hook_runner_prefers_codex_project_root() -> None:
    runner = (ROOT / "scripts" / "hooks" / "codex-hook-runner.sh").read_text(encoding="utf-8")
    assert runner.index('"${CODEX_PROJECT_DIR:-}"') < runner.index('"${CLAUDE_PROJECT_DIR:-}"')
