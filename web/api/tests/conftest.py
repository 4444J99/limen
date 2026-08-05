"""Suite-wide test isolation for web/api/tests (mirror of cli/tests/conftest.py).

CI runs ``pytest web/api/tests cli/tests`` — web/api FIRST — so any env a web/api test leaks lands in
the cli suite that follows (the exact order that first exposed the debt-gate leak). web/api currently
sets env only via ``monkeypatch`` (which auto-reverts), so this is defense-in-depth: snapshot
``os.environ`` before every test and restore it after, guaranteeing the API suite can never leak into
cli/tests regardless of how a future test is written. ``scripts/check-test-hygiene.py`` enforces that
this fixture stays present in every test root.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _restore_os_environ():
    saved = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)
