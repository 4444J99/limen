"""The direct cloud tunnel cannot bypass its local authentication precondition."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ianva/scripts/ianva-tunnel.sh"


@pytest.mark.parametrize("code", ["200", "301", "404", "500", "000", "401", "403"])
def test_tunnel_launch_requires_unauthenticated_rejection(tmp_path, code):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, body in {
        "curl": '#!/bin/sh\nprintf "%s" "$PROBE_CODE"\n',
        "cloudflared": '#!/bin/sh\nprintf "%s\\n" "$@" > "$LAUNCH_RECEIPT"\n',
    }.items():
        path = binaries / name
        path.write_text(body)
        path.chmod(0o755)
    receipt = tmp_path / "launched"
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "--named", "fixture"],
        env={
            **os.environ,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "PROBE_CODE": code,
            "LAUNCH_RECEIPT": str(receipt),
            "IANVA_TUNNEL_FORCE": "1",
            "IANVA_PORT": "17666",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    allowed = code in {"401", "403"}
    assert (result.returncode == 0) is allowed
    assert receipt.exists() is allowed
    if allowed:
        assert receipt.read_text().splitlines() == ["tunnel", "--url", "http://127.0.0.1:17666", "run", "fixture"]
