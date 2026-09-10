"""Finite process-group observations owned by a probe-created session leader."""

from __future__ import annotations

import os
import signal
import subprocess
import time


def identity(pid):
    try:
        from limen.host_admission import process_identity

        value = process_identity(pid)
        # Second-resolution ps start times cannot exclude rapid PID reuse.
        return value if value and not value.startswith("ps-start:") else None
    except ImportError:
        return None


def group_snapshot(pgid):
    result = subprocess.run(
        ["ps", "-axo", "pid=,pgid=,rss=,stat="], capture_output=True, text=True, timeout=0.5, check=True
    )
    members = {}
    for line in result.stdout.splitlines():
        pid, group, rss, state = line.split()
        if int(group) == pgid and not state.startswith("Z"):
            members[int(pid)] = {"identity": identity(int(pid)), "rss_bytes": int(rss) * 1024}
    return members


class Custody:
    def __init__(self, process):
        self.process = process
        self.observed = {}
        self.samples = 0
        self.peak_count = 0
        self.peak_rss = 0
        self.unavailable = False

    def sample(self):
        try:
            members = group_snapshot(self.process.pid)
            if self.process.poll() is None:
                # The live Popen leader proves this group still belongs to us.
                self.observed.update({pid: row["identity"] for pid, row in members.items() if row["identity"]})
            self.samples += 1
            self.peak_count = max(self.peak_count, len(members))
            self.peak_rss = max(self.peak_rss, sum(row["rss_bytes"] for row in members.values()))
            return members
        except (OSError, ValueError, subprocess.SubprocessError):
            self.unavailable = True
            return None

    def close(self):
        deadline = time.monotonic() + 2
        members = self.sample()
        try:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
            elif members:
                # After leader exit, signal only previously witnessed identities.
                # Unknown descendants remain visible, never treated as ours from UID.
                for pid, row in members.items():
                    if (
                        row["identity"]
                        and self.observed.get(pid) == row["identity"]
                        and identity(pid) == row["identity"]
                    ):
                        os.kill(pid, signal.SIGKILL)
            self.process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except ProcessLookupError:
            pass
        except (PermissionError, subprocess.TimeoutExpired):
            return "fail"
        if members is None:
            return "unmeasured"
        while time.monotonic() < deadline:
            remaining = self.sample()
            if remaining is None:
                return "unmeasured"
            if not remaining:
                return "pass"
            if any(not row["identity"] or self.observed.get(pid) != row["identity"] for pid, row in remaining.items()):
                return "unmeasured"
            time.sleep(0.025)
        return "fail"

    def report(self):
        return {
            "samples": self.samples,
            "sampled_peak_processes": self.peak_count if self.samples else None,
            "sampled_peak_rss_bytes": self.peak_rss if self.samples else None,
            "measurement": "unmeasured" if self.unavailable or not self.samples else "sampled",
        }
