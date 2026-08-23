"""Shared pytest fixtures for E2E test suite.

Provides environment isolation around every test.
"""

import os
import pytest


@pytest.fixture(autouse=True)
def _restore_os_environ():
    """Snapshot and restore os.environ per test."""
    saved = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)
