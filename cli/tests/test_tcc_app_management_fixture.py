"""Bounded deletion and renamed-runner contracts for the TCC fixture."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/tcc-app-management-fixture.py"


def test_fixture_updates_and_deletes_only_its_disposable_application(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    invocation_log = tmp_path / "hosted-runners.log"
    host = tmp_path / "domus-agent-host"
    host.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'test "$1" = ensure\n'
        'test "$2" = --\n'
        'printf \'%s\\n\' "${3##*/}" >> "$FIXTURE_INVOCATION_LOG"\n'
        "shift 2\n"
        'exec "$@"\n'
    )
    host.chmod(0o700)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--host", str(host), "--json"],
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "HOME": str(home),
            "FIXTURE_INVOCATION_LOG": str(invocation_log),
        },
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "fixture_bundle_id": result["fixture_bundle_id"],
        "fixture_deleted": True,
        "host_interface": "ensure",
        "ok": True,
        "runner_labels": [
            "uvx-renamed",
            "node-renamed",
            "python-renamed",
            "portable-ruby-renamed",
        ],
        "schema": "limen.tcc_app_management_fixture.v1",
    }
    assert invocation_log.read_text().splitlines() == [
        "uvx-renamed",
        "node-renamed",
        "python-renamed",
        "portable-ruby-renamed",
        "portable-ruby-renamed",
    ]
    assert list((home / "Applications").iterdir()) == []
