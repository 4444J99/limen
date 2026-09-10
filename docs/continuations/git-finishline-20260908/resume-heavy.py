#!/usr/bin/env python3
"""Resume only denied recovery shards through the existing admitted gate runner."""
import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    receipt = json.loads((HERE / "completion-execution.json").read_text())
    tested = receipt["tested_head"]
    subprocess.run(["git", "merge-base", "--is-ancestor", tested, "HEAD"], cwd=ROOT, check=True)
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", tested, "--", ".",
         ":(exclude)docs/continuations/git-finishline-20260908"], cwd=ROOT, text=True,
    ).splitlines()
    if changed:
        raise SystemExit("production inputs changed; resolve implicated shards before resuming")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "cli/src"))
    os.environ["PYTHONPATH"] = str(ROOT / "cli/src") + os.pathsep + os.environ.get("PYTHONPATH", "")
    spec = importlib.util.spec_from_file_location("recovery_verify", ROOT / "scripts/verify.py")
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)
    registry = runner.load_registry()
    gates = registry["gates"]
    pending = ["worker-check", "pytest-cli", "pytest-api", "web-build"]
    if set(receipt["pending_gates"]) != set(pending):
        raise SystemExit("pending gate inventory changed; reconcile receipts first")
    parallel = [g for g in pending if not gates[g].get("serialize")]
    serial = [g for g in pending if gates[g].get("serialize")]

    def wave(ids, jobs):
        return runner.run_gate_wave(ids, gates, registry, [], jobs=jobs, timeout_seconds=180,
                                    output_limit_bytes=65536, wave_name="recovery-heavy")

    try:
        with runner.heavy_admission(owner=f"recovery-verify-{os.getpid()}", surface="verify-scoped"):
            if not wave(parallel, 2):
                return 1
            lock_path = os.environ.get("LIMEN_VERIFY_LOCK_FILE", os.path.join(
                os.environ.get("TMPDIR", "/tmp"), "limen-verify-whole.lock"))
            with open(lock_path, "w") as lock:
                deadline = time.monotonic() + 180
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise SystemExit("serialized verification lock timed out")
                        time.sleep(0.05)
                for gate in serial:
                    if not wave([gate], 1):
                        return 1
    except runner.HostAdmissionFailure as exc:
        print(f"Host admission denied recovery verification: {exc}", file=sys.stderr)
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
