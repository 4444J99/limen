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

import pytest


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
def _restore_os_environ(tmp_path, _stable_agent_host_fixture):
    """Give each test one isolated explicit keeper and restore its environment."""
    saved = dict(os.environ)
    os.environ.pop("LIMEN_CONDUCT_URL", None)
    os.environ.pop("LIMEN_CONDUCT_TOKEN", None)
    os.environ["LIMEN_CONDUCT_STATE"] = str(tmp_path / "conduct.sqlite3")
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
