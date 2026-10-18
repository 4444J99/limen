"""The organ-owned broker credential cache, read without executing it (issue 2966)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from limen import session_closeout as closeout
from limen.conduct import env_cache
from limen.conduct.client import BrokerUnavailable, HttpConductClient, client_from_env

REPO = Path(__file__).resolve().parents[2]
URL = "https://broker.example"
CACHE = f"""# credential organ output
export LIMEN_CONDUCT_URL="{URL}"
LIMEN_CONDUCT_TOKEN='tok en'
LIMEN_CONDUCT_TOKEN_CLAUDE=lane-token
LIMEN_SELF_HEAL=1
"""


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LIMEN_CONDUCT_URL", "LIMEN_CONDUCT_TOKEN", "LIMEN_CONDUCT_STATE", "LIMEN_CONDUCT_ENV_FILE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def write_cache(path: Path, text: str = CACHE, mode: int = 0o600) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def test_reads_exactly_the_url_and_token(tmp_path):
    cache = write_cache(tmp_path / "limen.env")
    assert env_cache.read_conduct_credentials({"LIMEN_CONDUCT_ENV_FILE": str(cache)}) == (URL, "tok en")


def test_the_file_is_parsed_never_executed(tmp_path):
    marker = tmp_path / "executed"
    cache = write_cache(tmp_path / "limen.env", f"LIMEN_CONDUCT_URL=$(touch {marker})\n" + CACHE)
    assert env_cache.read_conduct_credentials({"LIMEN_CONDUCT_ENV_FILE": str(cache)}) == (URL, "tok en")
    assert not marker.exists()


def test_last_assignment_wins_like_a_sourced_file(tmp_path):
    cache = write_cache(tmp_path / "limen.env", CACHE + "LIMEN_CONDUCT_TOKEN=second\n")
    assert env_cache.read_conduct_credentials({"LIMEN_CONDUCT_ENV_FILE": str(cache)}) == (URL, "second")


def test_no_cache_is_not_an_error_here(tmp_path):
    assert env_cache.read_conduct_credentials({"LIMEN_CONDUCT_ENV_FILE": str(tmp_path / "absent")}) is None


def test_unsafe_cache_is_a_named_blocker(tmp_path):
    good = write_cache(tmp_path / "good.env")
    loose = write_cache(tmp_path / "loose.env", mode=0o644)
    link = tmp_path / "link.env"
    link.symlink_to(good)
    directory = tmp_path / "dir.env"
    directory.mkdir()
    for path in (loose, link, directory):
        with pytest.raises(BrokerUnavailable, match=re.escape(env_cache.UNSAFE)):
            env_cache.read_conduct_credentials({"LIMEN_CONDUCT_ENV_FILE": str(path)})


@pytest.mark.parametrize("text", ["", "LIMEN_CONDUCT_URL=https://broker.example\n", "LIMEN_CONDUCT_TOKEN=only\n"])
def test_incomplete_cache_is_a_named_blocker(tmp_path, text):
    cache = write_cache(tmp_path / "limen.env", text)
    with pytest.raises(BrokerUnavailable, match=re.escape(env_cache.INCOMPLETE)):
        env_cache.read_conduct_credentials({"LIMEN_CONDUCT_ENV_FILE": str(cache)})


def test_ownership_predicate_matches_the_shell_hydrator(tmp_path):
    """workstream_hydrate_conduct_environment keeps an inline copy (it is serialized into kickstart.sh)."""
    script = (REPO / "scripts/lib/workstream-capsule.sh").read_text(encoding="utf-8")
    function = script[script.index("workstream_hydrate_conduct_environment() {") :]
    shell_predicate = re.search(r"python3 -c '\n(.*?)\n' \"\$cache\"", function, re.DOTALL)
    assert shell_predicate, "the shell ownership predicate moved; update this parity test with it"

    good = write_cache(tmp_path / "good.env")
    link = tmp_path / "link.env"
    link.symlink_to(good)
    directory = tmp_path / "dir.env"
    directory.mkdir()
    cases = [
        good,
        write_cache(tmp_path / "loose.env", mode=0o644),
        write_cache(tmp_path / "tight.env", mode=0o400),
        link,
        directory,
        tmp_path / "absent.env",
    ]
    for path in cases:
        shell_ok = (
            subprocess.run([sys.executable, "-c", shell_predicate.group(1), str(path)], check=False).returncode == 0
        )
        assert env_cache.ownership_ok(path) is shell_ok, path.name


def test_client_from_env_ignores_the_cache_unless_asked(clean_env, tmp_path):
    clean_env.setenv("LIMEN_CONDUCT_ENV_FILE", str(write_cache(tmp_path / "limen.env")))
    with pytest.raises(BrokerUnavailable):
        client_from_env()


def test_client_from_env_hydrates_without_touching_the_environment(clean_env, tmp_path):
    clean_env.setenv("LIMEN_CONDUCT_ENV_FILE", str(write_cache(tmp_path / "limen.env")))
    client = client_from_env(hydrate_cache=True)
    assert isinstance(client, HttpConductClient)
    assert (client.endpoint, client.token) == (URL, "tok en")
    assert "LIMEN_CONDUCT_URL" not in os.environ and "LIMEN_CONDUCT_TOKEN" not in os.environ


def test_explicit_environment_outranks_the_cache(clean_env, tmp_path):
    clean_env.setenv("LIMEN_CONDUCT_ENV_FILE", str(write_cache(tmp_path / "limen.env")))
    clean_env.setenv("LIMEN_CONDUCT_URL", "https://explicit.example")
    client = client_from_env(hydrate_cache=True)
    assert (client.endpoint, client.token) == ("https://explicit.example", "tok en")


def test_explicit_local_state_adapter_bypasses_the_cache(clean_env, tmp_path):
    clean_env.setenv("LIMEN_CONDUCT_ENV_FILE", str(write_cache(tmp_path / "limen.env", mode=0o644)))
    clean_env.setenv("LIMEN_CONDUCT_STATE", str(tmp_path / "state.db"))
    assert type(client_from_env(hydrate_cache=True)).__name__ == "LocalConductClient"


def test_closeout_reports_a_named_blocker_not_a_traceback(clean_env, tmp_path, capsys):
    clean_env.setenv("LIMEN_CONDUCT_ENV_FILE", str(write_cache(tmp_path / "limen.env", mode=0o644)))
    code = closeout.main(
        ["--session-id", "s", "--worktree", str(tmp_path), "--receipt", str(tmp_path / "r.json"), "--json"]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["status"] == "unmeasured" and result["error_type"] == "BrokerUnavailable"
    assert result["reason"] == env_cache.UNSAFE
