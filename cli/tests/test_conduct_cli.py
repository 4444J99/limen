from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
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
            "17",
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
    assert observed["evaluation_timeout_seconds"] == 17


def test_campaign_run_emits_one_structured_invalid_boundary(monkeypatch, tmp_path) -> None:
    capsule = tmp_path / "workstream.json"
    capsule.write_text("{}\n", encoding="utf-8")

    def reject(**_kwargs):
        raise CampaignSupervisorError("exact remote main moved")

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
        "reason": "exact remote main moved",
        "schema": "limen.campaign_supervisor_result.v1",
        "successor_required": False,
        "terminal_predicate": "omega",
    }
