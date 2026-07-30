"""Tests for the heartbeat's bounded canonical-campaign wake adapter."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from limen.bounded_subprocess import BoundedSubprocessError
from limen.conduct.campaign_wake import (
    CampaignWakeError,
    NoActiveCampaign,
    discover_active_capsule,
    wake_campaign,
)
from limen.conduct.supervisor import CampaignSupervisorError
from limen.workstream_contract import RECEIPT_MODULES, new_contract, new_contract_v2


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _receipt(root: Path, slug: str, *, started: int, deadline: int) -> Path:
    contract = new_contract_v2(
        "8h",
        agent="codex",
        model="fixture-model",
        reasoning_effort="fixture-effort",
        sandbox="danger-full-access",
    )
    contract["runway"].update(
        {
            "started_epoch": started,
            "deadline_epoch": deadline,
            "started_at": datetime.fromtimestamp(started, UTC).isoformat(timespec="seconds"),
            "deadline_at": datetime.fromtimestamp(deadline, UTC).isoformat(timespec="seconds"),
        }
    )
    path = root / "docs" / "continuations" / slug / "workstream.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "branch": f"work/{slug}",
                "contract": contract,
                "private_capsule": {
                    "content": "redacted",
                    "modules": list(RECEIPT_MODULES),
                },
                "schema": "limen.workstream.receipt.v1",
                "slug": slug,
                "workstream": "institutional-omega",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def wake_repo(tmp_path: Path) -> tuple[Path, int]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "wake@example.invalid")
    _git(root, "config", "user.name", "Wake Test")
    now = 2_000_000_000
    _receipt(root, "epoch-old", started=now - 25_200, deadline=now + 3600)
    _receipt(root, "epoch-new", started=now - 21_600, deadline=now + 7200)
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    return root, now


def test_discovery_selects_latest_active_tracked_capsule(wake_repo) -> None:
    root, now = wake_repo
    capsule, remaining = discover_active_capsule(
        root,
        workstream="institutional-omega",
        now_epoch=now,
    )
    assert capsule.parent.name == "epoch-new"
    assert remaining == 7200


def test_discovery_accepts_an_admitted_provider_neutral_v1_contract(wake_repo) -> None:
    root, now = wake_repo
    path = root / "docs" / "continuations" / "epoch-new" / "workstream.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    provider_neutral = new_contract("8h")
    provider_neutral["runway"] = payload["contract"]["runway"]
    payload["contract"] = provider_neutral
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    capsule, remaining = discover_active_capsule(
        root,
        workstream="institutional-omega",
        now_epoch=now,
    )
    assert capsule == path
    assert remaining == 7200


def test_wake_rejects_a_drifted_provider_neutral_v1_contract_before_runner(wake_repo) -> None:
    root, now = wake_repo
    path = root / "docs" / "continuations" / "epoch-new" / "workstream.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    provider_neutral = new_contract("8h")
    provider_neutral["runway"] = payload["contract"]["runway"]
    provider_neutral["conductor"]["provider_and_model"] = "pinned"
    payload["contract"] = provider_neutral
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CampaignWakeError, match="workstream conductor contract is invalid"):
        wake_campaign(
            root,
            workstream="institutional-omega",
            now_epoch=now,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            runner=lambda *_args, **_kwargs: pytest.fail("runner must not execute"),
        )


def test_wake_rejects_an_unadmitted_provider_neutral_v1_contract_before_runner(wake_repo) -> None:
    root, now = wake_repo
    path = root / "docs" / "continuations" / "epoch-new" / "workstream.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["contract"] = new_contract("8h")
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CampaignWakeError, match="has not been admitted"):
        wake_campaign(
            root,
            workstream="institutional-omega",
            now_epoch=now,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            runner=lambda *_args, **_kwargs: pytest.fail("runner must not execute"),
        )


def test_wake_invokes_only_the_canonical_supervisor(wake_repo) -> None:
    root, now = wake_repo
    observed = {}

    def run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "schema": "limen.campaign_supervisor_result.v1",
                    "boundary": "continue",
                    "campaign_id": "fixture",
                    "exact_head": "a" * 40,
                }
            ),
            "",
        )

    result = wake_campaign(
        root,
        now_epoch=now,
        timeout_seconds=300,
        environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
        preflight=lambda _root: {"head": "a" * 40},
        runner=run,
    )
    assert result["boundary"] == "continue"
    assert result["capsule"] == "docs/continuations/epoch-new/workstream.json"
    command = observed["command"]
    assert command[1:6] == ["-m", "limen", "conduct", "campaign", "run"]
    assert "dispatch" not in command
    assert command[command.index("--session-id") + 1] == "heartbeat-session"
    assert command[command.index("--evaluation-timeout") + 1] == "300"
    deadline = int(command[command.index("--wake-deadline-monotonic-ns") + 1])
    assert deadline > time.monotonic_ns()
    assert 0 < observed["kwargs"]["timeout"] <= 300


@pytest.mark.parametrize("timeout_seconds", [1, 299, 7201])
def test_wake_rejects_timeouts_outside_the_public_relay_safe_range(
    wake_repo,
    timeout_seconds: int,
) -> None:
    root, now = wake_repo

    with pytest.raises(CampaignWakeError, match="between 300 and 7200"):
        wake_campaign(
            root,
            now_epoch=now,
            timeout_seconds=timeout_seconds,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            runner=lambda *_args, **_kwargs: pytest.fail("runner must not execute"),
        )


def test_ready_successor_routes_its_exact_publication_base_to_supervisor(
    wake_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, now = wake_repo
    observed: dict[str, object] = {}
    commit = "b" * 40
    base = "a" * 40

    def no_local(*_args, **_kwargs):
        raise NoActiveCampaign("fixture has no local active capsule")

    def ready_successor(*_args, **kwargs):
        observed["relay_deadline_monotonic"] = kwargs["deadline_monotonic"]
        return SimpleNamespace(
            capsule_path="docs/continuations/ready-fixture/workstream.json",
            remaining_seconds=3600,
            receipt=SimpleNamespace(
                publication_commit=commit,
                publication_parent=base,
                successor_branch="work/ready-fixture",
            ),
        )

    def run(command, **_kwargs):
        observed["command"] = command
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "schema": "limen.campaign_supervisor_result.v1",
                    "boundary": "continue",
                    "exact_head": "c" * 40,
                }
            ),
            "",
        )

    monkeypatch.setattr("limen.conduct.campaign_wake.discover_active_capsule", no_local)
    monkeypatch.setattr(
        "limen.conduct.campaign_wake.discover_ready_relay",
        ready_successor,
    )
    wake_campaign(
        root,
        now_epoch=now,
        environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
        preflight=lambda _root: {"head": "c" * 40},
        runner=run,
    )

    command = observed["command"]
    assert isinstance(command, list)
    assert command[command.index("--capsule-commit") + 1] == commit
    assert command[command.index("--capsule-base") + 1] == base
    wake_deadline_monotonic_ns = int(command[command.index("--wake-deadline-monotonic-ns") + 1])
    assert wake_deadline_monotonic_ns > 0
    relay_deadline_monotonic = observed["relay_deadline_monotonic"]
    assert isinstance(relay_deadline_monotonic, float)
    assert abs(wake_deadline_monotonic_ns - int(relay_deadline_monotonic * 1_000_000_000)) <= 1024


def test_default_runner_closes_oversized_output_during_execution(
    wake_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, now = wake_repo
    selected = root / "docs" / "continuations" / "epoch-new" / "workstream.json"

    monkeypatch.setattr(
        "limen.conduct.campaign_wake.discover_active_capsule",
        lambda *_args, **_kwargs: (selected, 7200),
    )

    def overflow(*_args, **_kwargs):
        raise BoundedSubprocessError("output")

    monkeypatch.setattr(
        "limen.conduct.campaign_wake.run_bounded_subprocess",
        overflow,
    )
    with pytest.raises(CampaignWakeError, match="supervisor output exceeded"):
        wake_campaign(
            root,
            now_epoch=now,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            preflight=lambda _root: {"head": "a" * 40},
        )


def test_missing_conductor_identity_never_invokes_a_runner(wake_repo) -> None:
    root, now = wake_repo
    with pytest.raises(CampaignWakeError, match="LIMEN_AGENT and LIMEN_SESSION_ID"):
        wake_campaign(
            root,
            now_epoch=now,
            environ={},
            runner=lambda *_args, **_kwargs: pytest.fail("runner must not execute"),
        )


def test_remote_default_preflight_failure_is_a_bounded_wake_error(wake_repo) -> None:
    root, now = wake_repo

    def fail_preflight(_root):
        raise CampaignSupervisorError("checkout is not exact remote default")

    with pytest.raises(CampaignWakeError, match="campaign preflight failed"):
        wake_campaign(
            root,
            now_epoch=now,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            preflight=fail_preflight,
            runner=lambda *_args, **_kwargs: pytest.fail("runner must not execute"),
        )


def test_supervisor_output_and_exit_must_agree(wake_repo) -> None:
    root, now = wake_repo

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            json.dumps(
                {
                    "schema": "limen.campaign_supervisor_result.v1",
                    "boundary": "continue",
                    "exact_head": "a" * 40,
                }
            ),
            "",
        )

    with pytest.raises(CampaignWakeError, match="exit and boundary"):
        wake_campaign(
            root,
            now_epoch=now,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            preflight=lambda _root: {"head": "a" * 40},
            runner=run,
        )


def test_supervisor_success_must_name_the_preflight_exact_head(wake_repo) -> None:
    root, now = wake_repo

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "schema": "limen.campaign_supervisor_result.v1",
                    "boundary": "continue",
                    "exact_head": "b" * 40,
                }
            ),
            "",
        )

    with pytest.raises(CampaignWakeError, match="exact head differs"):
        wake_campaign(
            root,
            now_epoch=now,
            environ={"LIMEN_AGENT": "codex", "LIMEN_SESSION_ID": "heartbeat-session"},
            preflight=lambda _root: {"head": "a" * 40},
            runner=run,
        )


def test_heartbeat_scripts_do_not_launch_static_dispatch_engines() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in ("heartbeat.sh", "heartbeat-loop.sh"):
        source = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "scripts/campaign-heartbeat.py" in source
        assert "dispatch-parallel.py" not in source
        assert "dispatch-async.py" not in source
        assert "python3 -m limen dispatch" not in source
