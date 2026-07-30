from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from limen.conduct.broker import ConductError
from limen.conduct.client import HttpConductClient
from limen.conduct.campaign_relay import CampaignRelayError
from limen.conduct.cli import conduct_group
from limen.conduct.supervisor import CampaignSupervisorError


class RecordingClient:
    def __init__(self) -> None:
        self.session = None

    def register(self, session):
        self.session = session
        return session.model_dump(mode="json")


def test_register_projects_canonical_execution_profile(monkeypatch, tmp_path) -> None:
    client = RecordingClient()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    result = CliRunner().invoke(
        conduct_group,
        [
            "register",
            "--agent",
            "opencode",
            "--session-id",
            "native-session",
            "--worktree",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert client.session is not None
    assert client.session.transport == "ianva-http"
    assert client.session.native_fanout is True
    assert client.session.harvest_method == "conduct-report"
    assert client.session.meter == "logs/usage.json#/vendors/opencode"
    assert {"conduct", "execute", "code", "review"} <= client.session.capabilities


def test_register_explicit_metadata_overrides_profile(monkeypatch) -> None:
    client = RecordingClient()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    result = CliRunner().invoke(
        conduct_group,
        [
            "register",
            "--agent",
            "codex",
            "--session-id",
            "direct-session",
            "--transport",
            "native-cli",
            "--no-native-fanout",
            "--harvest-method",
            "manual-receipt",
            "--meter",
            "live-meter",
            "--native-session-id",
            "provider-session",
            "--native-run-id",
            "provider-run",
            "--human-protected",
        ],
    )
    assert result.exit_code == 0, result.output
    assert client.session.transport == "native-cli"
    assert client.session.native_fanout is False
    assert client.session.native_session_id == "provider-session"
    assert client.session.identity.native_run_id == "provider-run"
    assert client.session.human_protected is True


class OwnedWorktreeClient:
    """First register 409s naming a dead owner; records every attempt."""

    def __init__(self) -> None:
        self.attempts = []

    def register(self, session):
        self.attempts.append(session)
        if len(self.attempts) == 1:
            raise ConductError(
                "conduct broker rejected request (409): "
                '{"detail": "worktree is already owned by healthy session old-boot-71272"}'
            )
        return session.model_dump(mode="json")


def _invoke_register(tmp_path):
    return CliRunner().invoke(
        conduct_group,
        ["register", "--agent", "claude", "--session-id", "reopen-boot", "--worktree", str(tmp_path)],
    )


def test_register_supersedes_dead_owner_after_ownership_conflict(monkeypatch, tmp_path) -> None:
    client = OwnedWorktreeClient()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    monkeypatch.setattr("limen.conduct.cli.foreign_worktree_occupant", lambda worktree: None)
    result = _invoke_register(tmp_path)
    assert result.exit_code == 0, result.output
    assert len(client.attempts) == 2
    assert client.attempts[0].supersedes is None
    assert client.attempts[1].supersedes == "old-boot-71272"


def test_register_conflict_reraised_when_worktree_has_live_occupant(monkeypatch, tmp_path) -> None:
    client = OwnedWorktreeClient()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    monkeypatch.setattr("limen.conduct.cli.foreign_worktree_occupant", lambda worktree: 4242)
    result = _invoke_register(tmp_path)
    assert result.exit_code != 0
    assert len(client.attempts) == 1


def test_register_conflict_reraised_when_probe_unavailable(monkeypatch, tmp_path) -> None:
    client = OwnedWorktreeClient()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    monkeypatch.setattr("limen.conduct.cli.foreign_worktree_occupant", lambda worktree: -1)
    result = _invoke_register(tmp_path)
    assert result.exit_code != 0
    assert len(client.attempts) == 1


def test_register_non_ownership_conflict_is_not_retried(monkeypatch, tmp_path) -> None:
    class RejectingClient:
        def __init__(self) -> None:
            self.attempts = 0

        def register(self, session):
            self.attempts += 1
            raise ConductError("conduct broker rejected request (409): session_id is already bound")

    client = RejectingClient()
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    monkeypatch.setattr("limen.conduct.cli.foreign_worktree_occupant", lambda worktree: None)
    result = _invoke_register(tmp_path)
    assert result.exit_code != 0
    assert client.attempts == 1


def test_campaign_run_projects_identity_and_bounded_supervisor_result(monkeypatch, tmp_path) -> None:
    capsule = tmp_path / "workstream.json"
    capsule.write_text("{}\n", encoding="utf-8")
    client = object()
    observed = {}

    def supervise(**kwargs):
        observed.update(kwargs)
        return {
            "schema": "limen.campaign_supervisor_result.v1",
            "boundary": "continue",
            "campaign_id": "fixture",
        }

    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    monkeypatch.setattr("limen.conduct.cli.run_campaign", supervise)
    result = CliRunner().invoke(
        conduct_group,
        [
            "campaign",
            "run",
            "--capsule",
            str(capsule),
            "--agent",
            "codex",
            "--session-id",
            "campaign-session",
            "--evaluation-timeout",
            "300",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["boundary"] == "continue"
    assert observed["client"] is client
    assert observed["root"] == Path.cwd()
    assert observed["capsule"] == capsule
    assert observed["identity"].agent == "codex"
    assert observed["identity"].session_id == "campaign-session"
    assert observed["terminal_predicate"] == "omega"
    assert observed["evaluation_timeout_seconds"] == 300
    assert observed["wake_deadline_monotonic_ns"] is None


def test_canary_full_mesh_uses_public_receipt_path(monkeypatch, tmp_path) -> None:
    client = HttpConductClient("https://limen-runtime.example", "fixture-token")
    observed = {}

    def run(**kwargs):
        observed.update(kwargs)
        return {
            "schema_version": "limen.conduct_full_mesh_canary.v1",
            "status": "passed",
        }

    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)
    monkeypatch.setattr("limen.conduct.cli.run_full_mesh_canary", run)
    receipt = tmp_path / "receipt.json"
    result = CliRunner().invoke(
        conduct_group,
        ["canary", "full-mesh", "--receipt", str(receipt)],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "passed"
    assert observed == {"client": client, "receipt_path": receipt}


@pytest.mark.parametrize(
    "error",
    [
        ConductError(f"remote failure\n{'x' * 4096}"),
        ValueError(f"invalid receipt\n{'x' * 4096}"),
        OSError(f"filesystem failure\n{'x' * 4096}"),
    ],
)
def test_canary_full_mesh_bounds_expected_errors(monkeypatch, tmp_path, error) -> None:
    client = HttpConductClient("https://limen-runtime.example", "fixture-token")
    monkeypatch.setattr("limen.conduct.cli.client_from_env", lambda: client)

    def reject(**_kwargs):
        raise error

    monkeypatch.setattr("limen.conduct.cli.run_full_mesh_canary", reject)
    result = CliRunner().invoke(
        conduct_group,
        ["canary", "full-mesh", "--receipt", str(tmp_path / "receipt.json")],
    )

    assert result.exit_code == 1
    assert result.output.startswith(f"Error: {str(error).splitlines()[0]} ")
    assert "\n" not in result.output.rstrip("\n")
    assert len(result.output.rstrip("\n")) <= len("Error: ") + 1024


def test_hidden_canary_executor_edge_uses_its_own_client_and_process_environment(
    monkeypatch,
) -> None:
    request = object()
    client = HttpConductClient("https://limen-runtime.example", "executor-token")
    observed = {}

    class Acknowledgement:
        @staticmethod
        def to_payload():
            return {
                "schema_version": "limen.conduct_canary_native_edge_ack.v1",
                "edge_id": "edge",
            }

    monkeypatch.setattr(
        "limen.conduct.cli.read_native_canary_request",
        lambda _stream: request,
    )
    monkeypatch.setattr(
        "limen.conduct.cli.executor_client_from_environ",
        lambda observed_request, _environment: client if observed_request is request else None,
    )

    def execute(observed_request, **kwargs):
        observed["request"] = observed_request
        observed.update(kwargs)
        return Acknowledgement()

    monkeypatch.setattr("limen.conduct.cli.execute_native_canary_edge", execute)
    result = CliRunner().invoke(
        conduct_group,
        ["canary", "executor-edge"],
        input="{}\n",
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["edge_id"] == "edge"
    assert observed["request"] is request
    assert observed["client"] is client
    assert observed["environ"] is not None


@pytest.mark.parametrize(
    ("error", "reason", "successor_required"),
    [
        (
            CampaignSupervisorError("exact remote main moved"),
            "exact remote main moved",
            False,
        ),
        (
            CampaignRelayError(
                "relay_store_unavailable",
                "campaign relay store is unavailable",
            ),
            "relay_store_unavailable: campaign relay store is unavailable",
            True,
        ),
    ],
)
def test_campaign_run_emits_one_structured_invalid_boundary(
    monkeypatch,
    tmp_path,
    error,
    reason,
    successor_required,
) -> None:
    capsule = tmp_path / "workstream.json"
    capsule.write_text("{}\n", encoding="utf-8")

    def reject(**_kwargs):
        if isinstance(error, CampaignRelayError):
            try:
                raise OSError("/private/secret/campaign-relay")
            except OSError as cause:
                raise error from cause
        raise error

    monkeypatch.setattr("limen.conduct.cli.client_from_env", object)
    monkeypatch.setattr("limen.conduct.cli.run_campaign", reject)
    result = CliRunner().invoke(
        conduct_group,
        [
            "campaign",
            "run",
            "--capsule",
            str(capsule),
            "--agent",
            "codex",
            "--session-id",
            "campaign-session",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "boundary": "invalid",
        "reason": reason,
        "schema": "limen.campaign_supervisor_result.v1",
        "successor_required": successor_required,
        "terminal_predicate": "omega",
    }
    assert "/private/secret" not in result.output
