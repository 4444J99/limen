"""Shared pytest fixtures for the CLI test suite.

Isolate ``os.environ`` around every test. Several tests (e.g. the async-dispatch
``_load`` helper) set process env vars *directly* — ``os.environ["LIMEN_…"] = …`` —
rather than through pytest's ``monkeypatch``. Those writes never get rolled back, so
they leak into whatever test runs next and cause order-dependent failures that only
surface in the full suite (e.g. a leaked ``LIMEN_WORKTREE_DEBT_GATE=0`` silently
disables the lifecycle-debt gate for later ``test_dispatch``/``test_generate_backlog``
cases). Snapshotting and restoring the environment per test makes the suite
order-independent without rewriting every direct writer.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pytest


# Editable installs point at the primary checkout and are not worktree-safe.
# Always test the exact checkout that owns this conftest before test modules
# import ``limen`` during collection.
LOCAL_SRC = str(Path(__file__).resolve().parents[1] / "src")
if LOCAL_SRC not in sys.path:
    sys.path.insert(0, LOCAL_SRC)


@pytest.fixture
def approved_execution_policy(tmp_path, monkeypatch):
    """Tests explicitly name admitted work; unlisted work still fails closed."""

    def approve(*keys):
        root = tmp_path / "execution-authority"
        (root / "logs").mkdir(parents=True, exist_ok=True)
        policy = {
            "mode": "dispatch",
            "approved_priorities": [
                {
                    "outcome_id": key,
                    "enabled": True,
                    "work_keys": [key],
                    "resource_limits": {"branch": 1, "worktree": 2, "issue": 1},
                }
                for key in keys
            ],
        }
        (root / "logs/autonomy-policy.json").write_text(json.dumps(policy))
        monkeypatch.setenv("LIMEN_LIVE_ROOT", str(root))
        return policy

    return approve


@pytest.fixture(scope="session")
def _stable_agent_host_fixture(tmp_path_factory) -> str:
    root = tmp_path_factory.mktemp("stable-agent-host")
    application = root / "Applications/DomusAgentHost.app"
    host = application / "Contents/MacOS/DomusAgentHost"
    host.parent.mkdir(parents=True)
    requirement = 'cdhash H"' + "a" * 40 + '"'
    status = json.dumps(
        {
            "schema": "domus.agent_host_status.v1",
            "ok": True,
            "bundle_id": "org.organvm.domus.agent-host",
            "bundle_path": str(application),
            "executable_path": str(host),
            "stable_path": True,
            "signature_valid": True,
            "designated_requirement": requirement,
            "cdhash": "a" * 40,
        }
    )
    host.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = status ] && [ "$2" = --json ]; then\n'
        f"  printf '%s\\n' '{status}'\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = verify-lifetime ]; then\n'
        '  [ -p "/dev/fd/${DOMUS_AGENT_HOST_LIFETIME_FD:?}" ]\n'
        "  exit\n"
        "fi\n"
        "exit 64\n"
    )
    host.chmod(0o755)
    receipt = application.parent / ".DomusAgentHost.designated-requirement"
    receipt.write_text(requirement + "\n")
    return str(host)


@pytest.fixture(autouse=True)
def _async_dispatch_explicit_admission_opt_out(request, monkeypatch):
    """Keep async machinery tests focused when they explicitly disable admission.

    ``test_async_dispatch`` predates the execution-priority and value-tier gates and
    deliberately sets ``LIMEN_DISPATCH_ADMISSION=0`` inside its per-test loader so
    those tests exercise reservation/harvest mechanics instead of operator policy.
    Production now checks priority inside ``_dispatchable`` before the general switch
    and filters automatic candidates through the value tier. Preserve those fail-closed
    production rules: admit only this module's synthetic ``x/y`` repository and stub
    only its synthetic task-priority check plus the exact admission seam imported by
    ``dispatch-async.py``.
    """
    if Path(str(request.node.path)).name != "test_async_dispatch.py":
        return

    monkeypatch.setenv("LIMEN_VALUE_REPOS", "x/y")

    import limen.dispatch as dispatch

    real_check = dispatch.dispatch_admission_check
    real_require_priority = dispatch.require_approved_priority

    def dispatch_admission_check(*args, **kwargs):
        if os.environ.get("LIMEN_DISPATCH_ADMISSION") == "0":
            return {
                "allow": True,
                "dispatch_allowed": True,
                "state": "disabled",
                "reason": "test_only_admission_opt_out",
            }
        return real_check(*args, **kwargs)

    def require_approved_priority(work_key, *args, **kwargs):
        if os.environ.get("LIMEN_DISPATCH_ADMISSION") == "0" and str(work_key).startswith("T"):
            return {"test_only_admission_opt_out": True, "work_key": str(work_key)}
        return real_require_priority(work_key, *args, **kwargs)

    monkeypatch.setattr(dispatch, "dispatch_admission_check", dispatch_admission_check)
    monkeypatch.setattr(dispatch, "require_approved_priority", require_approved_priority)


@pytest.fixture(autouse=True)
def _restore_os_environ(tmp_path, tmp_path_factory, _stable_agent_host_fixture, monkeypatch):
    """Give each test one isolated explicit keeper and restore its environment."""
    saved = dict(os.environ)
    os.environ.pop("LIMEN_CONDUCT_URL", None)
    os.environ.pop("LIMEN_CONDUCT_TOKEN", None)
    os.environ["LIMEN_CONDUCT_STATE"] = str(tmp_path / "conduct.sqlite3")
    # Dispatch reloads LIMEN_ENV after fixture setup. Never let that reload
    # resurrect the operator's authenticated broker or provider credentials.
    environment = tmp_path_factory.mktemp("broker-isolation") / "limen.env"
    environment.write_text("")
    environment.chmod(0o600)
    os.environ["LIMEN_ENV"] = str(environment)
    os.environ["LIMEN_CONDUCT_ENV_FILE"] = str(environment.with_name("absent-conduct.env"))
    original_open = urllib.request.OpenerDirector.open

    def isolated_open(opener, fullurl, *args, **kwargs):
        url = fullurl.full_url if isinstance(fullurl, urllib.request.Request) else fullurl
        path = urllib.parse.urlsplit(url).path
        if path.startswith(("/api/conduct/", "/api/board/")):
            raise AssertionError("test attempted real broker access; use the temporary keeper or mock transport")
        return original_open(opener, fullurl, *args, **kwargs)

    # Guard below urlopen so transport unit tests can still install their mocks.
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", isolated_open)
    # Hermetic runs never reach the phone. _notify's body-gate already withholds osascript
    # for non-organism roots; this belt keeps the suite silent even for a future notifier
    # that bypasses _notify or a test handed an organism-shaped fixture root.
    os.environ["LIMEN_NOTIFY"] = "0"
    # Test processes model the already-supervised runtime. Dedicated stable-host
    # tests pass explicit environment mappings to exercise first-entry behavior;
    # the rest of the suite must not depend on a machine-global app installation.
    read_fd, write_fd = os.pipe()
    lifetime = os.fstat(write_fd)
    identity = f"{'0' * 16}:{lifetime.st_dev}:{lifetime.st_ino}"
    os.environ["DOMUS_AGENT_HOST_ACTIVE"] = "1"
    os.environ["DOMUS_AGENT_HOST_LIFETIME_FD"] = str(write_fd)
    os.environ["DOMUS_AGENT_HOST_LIFETIME_ID"] = identity
    os.environ.pop("LIMEN_AGENT_HOST_BIN", None)
    os.environ["DOMUS_AGENT_HOST_BIN"] = _stable_agent_host_fixture
    try:
        yield
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass
        os.environ.clear()
        os.environ.update(saved)
