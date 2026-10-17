"""Exercise whole-verifier live admission without running its expensive gates."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class VerifyWholeLiveModeTests(unittest.TestCase):
    def run_verifier(self, mode: str | None, live_exit: int) -> tuple[int, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            (fixture / "scripts/lib").mkdir(parents=True)
            (fixture / "bin").mkdir()
            verifier = fixture / "scripts/verify-whole.sh"
            verifier.write_text((ROOT / "scripts/verify-whole.sh").read_text())
            (fixture / "scripts/lib/host-admission.sh").write_text(
                "host_admission_acquire() { :; }\nhost_admission_exit_trap() { :; }\n"
            )
            # Replace only the invoked gates, retaining the real verifier's
            # control flow and set -e behavior. The next gate is a stop sentinel
            # so no downstream builds, live endpoints, or source files are used.
            stub = fixture / "bin/gate"
            stub.write_text(
                "#!/bin/sh\n"
                'printf "%s %s\\n" "${0##*/}" "$*" >> "$CALL_LOG"\n'
                'if [ "${0##*/}" = python3 ] && '
                '[ "$1" = scripts/positioning-research-adjudication.py ] && '
                '[ "$2" = --verify-live ]; then exit "$LIVE_EXIT"; fi\n'
                'if [ "${0##*/}" = bash ] && '
                '[ "$1" = scripts/tests/enactment-audit.test.sh ]; then exit 42; fi\n'
                "exit 0\n"
            )
            stub.chmod(0o755)
            for name in ("python3", "bash", "plutil"):
                (fixture / "bin" / name).symlink_to(stub)
            call_log = fixture / "calls.log"
            env = {
                "PATH": f"{fixture / 'bin'}:{os.defpath}",
                "HOME": str(fixture),
                "CALL_LOG": str(call_log),
                "LIVE_EXIT": str(live_exit),
                "LIMEN_VERIFY_NO_LOCK": "1",
            }
            if mode is not None:
                env["LIMEN_VERIFY_LIVE"] = mode
            result = subprocess.run(
                ["/bin/bash", str(verifier)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertIn(result.returncode, (23, 42), result.stdout + result.stderr)
            return result.returncode, call_log.read_text().splitlines()

    def test_disabled_live_probe_does_not_block_source_verification(self) -> None:
        for mode in (None, "0"):
            with self.subTest(mode=mode):
                code, calls = self.run_verifier(mode, live_exit=23)
                self.assertEqual(code, 42)
                self.assertNotIn(
                    "python3 scripts/positioning-research-adjudication.py --verify-live",
                    calls,
                )

    def test_enabled_live_probe_runs_before_following_source_gate(self) -> None:
        code, calls = self.run_verifier("1", live_exit=0)
        self.assertEqual(code, 42)
        live_call = "python3 scripts/positioning-research-adjudication.py --verify-live"
        self.assertEqual(calls.count(live_call), 1)
        self.assertLess(
            calls.index(live_call),
            calls.index("bash scripts/tests/enactment-audit.test.sh"),
        )

    def test_enabled_live_probe_preserves_failure(self) -> None:
        code, calls = self.run_verifier("1", live_exit=23)
        self.assertEqual(code, 23)
        self.assertNotIn("bash scripts/tests/enactment-audit.test.sh", calls)


if __name__ == "__main__":
    unittest.main()
