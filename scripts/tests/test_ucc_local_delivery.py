import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def module():
    path = Path(__file__).resolve().parents[1] / "ucc-cloudflare-delivery.py"
    spec = importlib.util.spec_from_file_location("ucc_local_delivery", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize("failure", [None, "permissions", "duplicate", "missing", "symlink", "malformed"])
def test_cached_custody(monkeypatch, tmp_path, failure):
    mod = module()
    monkeypatch.setattr(mod.Path, "home", lambda: tmp_path)
    cache = tmp_path / ".limen.env"
    text = "export CLOUDFLARE_API_TOKEN='test-only-private'\n"
    if failure == "duplicate":
        text *= 2
    elif failure == "missing":
        text = "OTHER=present\n"
    elif failure == "malformed":
        text = "CLOUDFLARE_API_TOKEN=one two\n"
    cache.write_text(text)
    cache.chmod(0o644 if failure == "permissions" else 0o600)
    if failure == "symlink":
        cache.rename(tmp_path / "target")
        cache.symlink_to(tmp_path / "target")
    if failure:
        with pytest.raises((ValueError, OSError)):
            mod.cached_candidate()
    else:
        assert mod.cached_candidate() == "test-only-private"


@pytest.mark.parametrize("mode", ["preflight", "apply"])
@pytest.mark.parametrize(
    "failure", [None, "ci", "account", "scope", "user", "repo", "admin", "write", "readback", "transport"]
)
def test_local_delivery_boundaries(monkeypatch, capsys, mode, failure):
    mod = module()
    token = "test-only-private"  # allow-secret: inert test value, never a credential
    monkeypatch.setattr(mod, "cached_candidate", lambda: token)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    if failure == "ci":
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GH_TOKEN", "unrelated")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "unrelated")
    calls, writes = [], []

    def run(command, **kwargs):
        calls.append(command)
        assert token not in command
        assert "GH_TOKEN" not in kwargs["env"]
        assert "CLOUDFLARE_API_TOKEN" not in kwargs["env"]
        if failure == "transport":
            raise OSError(token)
        endpoint = command[-1]
        if endpoint == "user":
            payload = mod.LOCAL_PRINCIPAL | ({"id": 0} if failure == "user" else {})
        elif endpoint.endswith(mod.SECRET_NAME):
            payload = {"name": mod.SECRET_NAME, "updated_at": None if failure == "readback" else "2026-09-17T00:00:00Z"}
        else:
            payload = {
                "full_name": "wrong" if failure == "repo" else mod.TARGET,
                "archived": False,
                "permissions": {"admin": failure != "admin"},
            }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    monkeypatch.setattr(mod.subprocess, "run", run)

    def write(repo, name, value, **kwargs):
        assert (repo, name, value) == (mod.TARGET, mod.SECRET_NAME, token)
        assert "GH_TOKEN" not in kwargs["env"]
        writes.append(name)
        return failure != "write"

    hydrate = SimpleNamespace(
        verify_cloudflare_delivery=lambda entry, candidate: (failure != "scope", "result"), gh_secret_set=write
    )
    entry = {"enabled": True, "cloudflare_delivery_account": "wrong" if failure == "account" else mod.ACCOUNT}
    expected_failure = failure and not (mode == "preflight" and failure in ("write", "readback"))
    assert mod.local_delivery(hydrate, entry, mode) == (1 if expected_failure else 0)
    if mode == "preflight" or failure in ("ci", "account", "scope", "user", "repo", "admin", "transport"):
        assert writes == []
    assert token not in capsys.readouterr().out
