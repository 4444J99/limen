from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location("bind_running", ROOT / "scripts/bind-running-claude-session.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_binding(tmp_path):
    repo = tmp_path / "repo"
    worktree = repo / ".claude/worktrees/demo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "fixture",
    )
    git("worktree", "add", "--detach", str(worktree), "HEAD")
    job = tmp_path / "job"
    job.mkdir(mode=0o700)
    cache = tmp_path / "credentials"
    cache.write_text(
        "LIMEN_CONDUCT_URL=https://example.invalid\nLIMEN_CONDUCT_TOKEN=wrong-default\nLIMEN_CONDUCT_TOKEN_CLAUDE=claude-only\n"
    )
    cache.chmod(0o600)
    hook = repo / "scripts/hooks/conduct-register.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/bin/sh\nexit 0\n")
    env = {"CLAUDE_JOB_DIR": str(job), "LIMEN_CONDUCT_ENV_FILE": str(cache)}
    return repo, worktree, env


def test_binds_raw_native_id_through_hook_and_checks_live_record(tmp_path, monkeypatch):
    module = load_script()
    repo, worktree, env = fixture_binding(tmp_path)
    observed = {}

    def run(args, **kwargs):
        observed.update(args=args, **kwargs)
        return SimpleNamespace(returncode=0)

    class Client:
        def __init__(self, url, token, **kwargs):
            assert url == "https://example.invalid"
            assert token == "claude-only"  # allow-secret: synthetic fixture, never a credential

        def capabilities(self):
            return {
                "sessions": [
                    {
                        "session_id": "throwaway-native-id",
                        "identity": {"agent": "claude"},
                        "worktree": str(worktree),
                        "human_protected": True,
                        "healthy": True,
                    }
                ]
            }

    monkeypatch.setattr(module, "run_hook", run)
    monkeypatch.setattr(module, "HttpConductClient", Client)
    result = module.bind_running(repo, "throwaway-native-id", worktree, env)
    assert result["status"] == "bound"
    assert json.loads(observed["input"]) == {"session_id": "throwaway-native-id", "cwd": str(worktree)}
    assert observed["args"] == ["bash", str(repo / "scripts/hooks/conduct-register.sh")]
    assert "LIMEN_CONDUCT_TOKEN" not in observed["env"]
    assert observed["env"]["LIMEN_CONDUCT_TOKEN_CLAUDE"] == "claude-only"


@pytest.mark.parametrize("kind", ["missing-lane", "unsafe-cache", "outside", "missing-job"])
def test_refuses_unsafe_binding_before_hook(tmp_path, monkeypatch, kind):
    module = load_script()
    repo, worktree, env = fixture_binding(tmp_path)
    cache = Path(env["LIMEN_CONDUCT_ENV_FILE"])
    if kind == "missing-lane":
        cache.write_text("LIMEN_CONDUCT_URL=https://example.invalid\nLIMEN_CONDUCT_TOKEN=wrong-default\n")
    elif kind == "unsafe-cache":
        cache.chmod(0o644)
    elif kind == "outside":
        worktree = repo
    else:
        env.pop("CLAUDE_JOB_DIR")
    monkeypatch.setattr(module, "run_hook", lambda *a, **k: pytest.fail("unsafe registration attempted"))
    with pytest.raises(module.BindingError):
        module.bind_running(repo, "throwaway-native-id", worktree, env)


def test_hook_exit_zero_is_not_live_binding_proof(tmp_path, monkeypatch):
    module = load_script()
    repo, worktree, env = fixture_binding(tmp_path)
    monkeypatch.setattr(module, "run_hook", lambda *a, **k: SimpleNamespace(returncode=0))

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def capabilities(self):
            return {"sessions": []}

    monkeypatch.setattr(module, "HttpConductClient", Client)
    with pytest.raises(module.BindingError, match="live-claude-binding-unconfirmed"):
        module.bind_running(repo, "throwaway-native-id", worktree, env)


def test_existing_hook_preserves_raw_id_with_throwaway_cli(tmp_path, monkeypatch):
    module = load_script()
    repo, worktree, env = fixture_binding(tmp_path)
    (repo / "scripts/lib").mkdir()
    import shutil

    shutil.copy2(ROOT / "scripts/hooks/conduct-register.sh", repo / "scripts/hooks/conduct-register.sh")
    shutil.copy2(ROOT / "scripts/lib/workstream-capsule.sh", repo / "scripts/lib/workstream-capsule.sh")
    capture = tmp_path / "arguments"
    cli = tmp_path / "limen-fixture"
    cli.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$CAPTURE_PATH"\n')
    cli.chmod(0o755)
    env.update(LIMEN_CLI_BIN=str(cli), CAPTURE_PATH=str(capture), PATH=os.environ["PATH"])

    class Client:
        def __init__(self, url, token, **kwargs):
            assert token == "claude-only"  # allow-secret: synthetic fixture, never a credential

        def capabilities(self):
            return {
                "sessions": [
                    {
                        "session_id": "throwaway-native-id",
                        "identity": {"agent": "claude"},
                        "worktree": str(worktree),
                        "human_protected": True,
                        "healthy": True,
                    }
                ]
            }

    monkeypatch.setattr(module, "HttpConductClient", Client)
    assert module.bind_running(repo, "throwaway-native-id", worktree, env)["status"] == "bound"
    args = capture.read_text().splitlines()
    assert args[args.index("--session-id") + 1] == "throwaway-native-id"
    assert args[args.index("--agent") + 1] == "claude"
    assert "--human-protected" in args
    assert "claude-only" not in capture.read_text()


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity", {"agent": "codex"}),
        ("healthy", False),
        ("human_protected", False),
        ("worktree", "/foreign"),
    ],
)
def test_rejects_wrong_or_unhealthy_live_identity(tmp_path, monkeypatch, field, value):
    module = load_script()
    repo, worktree, env = fixture_binding(tmp_path)
    monkeypatch.setattr(module, "run_hook", lambda *a, **k: SimpleNamespace(returncode=0))
    record = {
        "session_id": "throwaway-native-id",
        "identity": {"agent": "claude"},
        "worktree": str(worktree),
        "human_protected": True,
        "healthy": True,
    }
    record[field] = value

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def capabilities(self):
            return {"sessions": [record]}

    monkeypatch.setattr(module, "HttpConductClient", Client)
    with pytest.raises(module.BindingError, match="live-claude-binding-unconfirmed"):
        module.bind_running(repo, "throwaway-native-id", worktree, env)
