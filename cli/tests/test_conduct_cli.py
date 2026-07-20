from __future__ import annotations

from click.testing import CliRunner

from limen.conduct.cli import conduct_group


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
