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

import os

import pytest


@pytest.fixture(autouse=True)
def _restore_os_environ(tmp_path):
    """Give each test one isolated explicit keeper and restore its environment."""
    saved = dict(os.environ)
    os.environ.pop("LIMEN_CONDUCT_URL", None)
    os.environ.pop("LIMEN_CONDUCT_TOKEN", None)
    os.environ["LIMEN_CONDUCT_STATE"] = str(tmp_path / "conduct.sqlite3")
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)
