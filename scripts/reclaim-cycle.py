#!/usr/bin/env python3
"""Run one bounded, fail-closed worktree reclaim cycle.

Full reclaim is an exact-plan transaction: derive the canonical JSON plan, validate its
SHA-256, and apply only that SHA within the same overall deadline. Generated-only cleanup
does not use the candidate manifest and therefore remains a single reaper invocation.

The controller intentionally returns nonzero for malformed output, timeouts, plan drift,
or any reaper failure. Heartbeat callers may continue the wider beat after logging that
failure; a later beat then retries from a freshly derived plan.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


SHA256_RE = re.compile(r"[0-9a-f]{64}")
TIMEOUT_EXIT = 124


def _positive_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return parsed


def _positive_lines(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("output lines must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("output lines must be greater than zero")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply eligible reclaim work")
    parser.add_argument(
        "--generated-only",
        action="store_true",
        help="run the reaper's generated-payload cleanup exactly once",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        required=True,
        help="maximum seconds for the entire cycle, including check and apply",
    )
    parser.add_argument(
        "--output-lines",
        type=_positive_lines,
        default=4,
        help="maximum captured reaper lines emitted per phase (default: 4)",
    )
    parser.add_argument(
        "--reaper",
        type=Path,
        default=Path(__file__).with_name("reclaim-worktrees.py"),
        help=argparse.SUPPRESS,
    )
    return parser


def _tail(text: str | bytes | None, limit: int) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return "\n".join(text.rstrip().splitlines()[-limit:])


def _emit_capture(stdout: str | bytes | None, stderr: str | bytes | None, limit: int) -> None:
    for captured in (stdout, stderr):
        tail = _tail(captured, limit)
        if tail:
            print(tail, file=sys.stderr)


def _fail(message: str, code: int = 2) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _run_phase(
    command: list[str],
    *,
    phase: str,
    deadline: float,
    output_lines: int,
) -> subprocess.CompletedProcess[str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _fail(f"reclaim-cycle: timeout phase={phase} (cycle deadline exhausted)", TIMEOUT_EXIT)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        _emit_capture(stdout or exc.stdout, stderr or exc.stderr, output_lines)
        _fail(f"reclaim-cycle: timeout phase={phase}", TIMEOUT_EXIT)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _run_one_pass(
    command: list[str],
    *,
    phase: str,
    deadline: float,
    output_lines: int,
) -> int:
    result = _run_phase(command, phase=phase, deadline=deadline, output_lines=output_lines)
    _emit_capture(result.stdout, result.stderr, output_lines)
    if result.returncode != 0:
        print(f"reclaim-cycle: {phase}-failed rc={result.returncode}", file=sys.stderr)
    return result.returncode


def _validated_plan_sha(stdout: str, *, output_lines: int) -> str:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        tail = _tail(stdout, output_lines)
        if tail:
            print(tail, file=sys.stderr)
        _fail("reclaim-cycle: invalid-plan-json")
    if not isinstance(payload, dict):
        _fail("reclaim-cycle: invalid-plan-json (top level is not an object)")
    plan_sha = payload.get("plan_sha256")
    if not isinstance(plan_sha, str) or SHA256_RE.fullmatch(plan_sha) is None:
        _fail("reclaim-cycle: invalid-plan-sha")
    return plan_sha


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    reaper = args.reaper.expanduser().resolve()
    if not reaper.is_file():
        _fail(f"reclaim-cycle: reaper-not-found path={reaper}")

    deadline = time.monotonic() + args.timeout
    base = [sys.executable, str(reaper)]

    if args.generated_only:
        command = [*base, "--generated-only"]
        if args.apply:
            command.append("--apply")
        return _run_one_pass(
            command,
            phase="generated-only",
            deadline=deadline,
            output_lines=args.output_lines,
        )

    if not args.apply:
        return _run_one_pass(
            base,
            phase="full-preview",
            deadline=deadline,
            output_lines=args.output_lines,
        )

    check = _run_phase(
        [*base, "--check", "--json"],
        phase="check",
        deadline=deadline,
        output_lines=args.output_lines,
    )
    if check.returncode != 0:
        _emit_capture(check.stdout, check.stderr, args.output_lines)
        _fail(f"reclaim-cycle: check-failed rc={check.returncode}", check.returncode)
    if check.stderr:
        _emit_capture(None, check.stderr, args.output_lines)
    plan_sha = _validated_plan_sha(check.stdout, output_lines=args.output_lines)

    apply = _run_phase(
        [*base, "--apply", "--expected-plan-sha", plan_sha],
        phase="apply",
        deadline=deadline,
        output_lines=args.output_lines,
    )
    _emit_capture(apply.stdout, apply.stderr, args.output_lines)
    if apply.returncode != 0:
        print(
            f"reclaim-cycle: apply-failed rc={apply.returncode} plan_sha256={plan_sha}",
            file=sys.stderr,
        )
        return apply.returncode
    print(f"reclaim-cycle: applied plan_sha256={plan_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
