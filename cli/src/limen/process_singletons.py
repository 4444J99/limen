"""Bounded native witnesses for explicitly declared detached service helpers.

These witnesses are candidates, not ownership exemptions. The assessor must
also positively classify the pinned vendor peer and preserve native-thread
precedence before a singleton can become a shared service.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

from limen.process_ownership import Process, native_details

SERENA_TRAY_COMMAND = "from serena.dashboard import SerenaDashboardTrayManager; SerenaDashboardTrayManager().run()"
SERENA_TRAY_PORT = 24224


def vendor_files_unchanged(files: object) -> bool:
    """Recheck bounded regular vendor files captured by the source resolver."""
    if not isinstance(files, dict) or not files or len(files) > 8:
        return False
    try:
        for name, checksum in files.items():
            path = Path(name)
            if (
                not path.is_absolute()
                or path.is_symlink()
                or not path.is_file()
                or path.stat().st_size > 32 * 1024 * 1024
            ):
                return False
            if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                return False
        return True
    except (OSError, TypeError, ValueError):
        return False


def exact_loopback_listener(output: bytes, pid: int) -> bool:
    """Accept one exact lsof PID/listener, never a port-name substring."""
    try:
        lines = output.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return False
    pids = [line for line in lines if line.startswith("p")]
    names = [line for line in lines if line.startswith("n")]
    return pids == [f"p{pid}"] and names == [f"n127.0.0.1:{SERENA_TRAY_PORT}"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def serena_tray_alive(process: Process, identity) -> bool:
    """Tie typed health to one unchanged native process and its own listener.

    No proxy, redirect, unbounded body, alternate address, or PID reuse is
    accepted. Failure leaves ownership unresolved rather than stopping a process.
    """
    if (
        not process.readable
        or not process.started
        or len(process.argv) != 3
        or process.argv[1:] != ("-c", SERENA_TRAY_COMMAND)
        or identity(process.pid) != process.started
    ):
        return False
    try:
        if native_details(process.pid)[0] != process.argv:
            return False  # exec can change argv without changing PID/start time.
        listener = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-a", "-p", str(process.pid), "-iTCP:24224", "-sTCP:LISTEN", "-Fpn"],
            capture_output=True,
            timeout=3,
            check=False,
        )
        if listener.returncode or not exact_loopback_listener(listener.stdout, process.pid):
            return False
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        with opener.open("http://127.0.0.1:24224/health", timeout=2) as response:
            if response.status != 200:
                return False
            body = response.read(257)
            if len(body) > 256 or json.loads(body) != {"status": "alive"}:
                return False
        return identity(process.pid) == process.started and native_details(process.pid)[0] == process.argv
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
