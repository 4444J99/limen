#!/usr/bin/env python3
"""Focused verifier for TABVLARIVS/VLTIMA recordkeeper-kernel work.

This is the inner-loop gate for the universal-kernel/recordkeeper branch. It
checks the keeper and kernel contracts without paying the whole-system cost of
``scripts/verify-whole.sh`` on every edit.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Gate:
    id: str
    label: str
    command: tuple[str, ...]
    required: bool = True
    timeout_seconds: int = 120


@dataclass(frozen=True)
class GateResult:
    id: str
    label: str
    command: tuple[str, ...]
    required: bool
    returncode: int
    elapsed_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def _pythonpath(root: Path, env: dict[str, str]) -> str:
    cli_src = str(root / "cli" / "src")
    ambient = env.get("PYTHONPATH")
    return f"{cli_src}:{ambient}" if ambient else cli_src


def gate_plan(root: Path, *, include_event_proof: bool, require_event_proof: bool, min_streak: int) -> list[Gate]:
    python = sys.executable
    pytest_common = ("-q", "-p", "no:cacheprovider")
    gates = [
        Gate(
            id="py-compile",
            label="compile keeper/kernel Python surfaces",
            command=(
                python,
                "-m",
                "py_compile",
                "cli/src/limen/cli.py",
                "cli/src/limen/materialize.py",
                "cli/src/limen/tabularius.py",
                "scripts/validate-vltima-kernel.py",
                "scripts/check-tabularius-writers.py",
                "scripts/check-tabularius-event-proof.py",
                "scripts/tabularius-organ.py",
                "scripts/verify-recordkeeper-kernel.py",
            ),
            timeout_seconds=60,
        ),
        Gate(
            id="vltima-tests",
            label="VLTIMA projection and workstream tests",
            command=(
                python,
                "-m",
                "pytest",
                "cli/tests/test_vltima_kernel.py",
                "cli/tests/test_generate_organ_backlog.py",
                "cli/tests/test_workstream.py",
                "cli/tests/test_workstream_command.py",
                *pytest_common,
            ),
        ),
        Gate(
            id="tabularius-tests",
            label="TABVLARIVS keeper tests",
            command=(
                python,
                "-m",
                "pytest",
                "cli/tests/test_tabularius.py",
                "cli/tests/test_tabularius_organ.py",
                "cli/tests/test_tabularius_event_proof.py",
                "cli/tests/test_tabularius_writer_audit.py",
                *pytest_common,
            ),
        ),
        Gate(
            id="contract-schemas",
            label="portable JSON schema contracts",
            command=("node", "scripts/validate-contract-schemas.mjs"),
            timeout_seconds=60,
        ),
        Gate(
            id="writer-audit",
            label="TABVLARIVS single-writer audit",
            command=(python, "scripts/check-tabularius-writers.py", "--max-legacy", "0"),
            timeout_seconds=60,
        ),
        Gate(
            id="vltima-projection",
            label="VLTIMA canonical projection freshness",
            command=(python, "scripts/validate-vltima-kernel.py", "--check-projection", "--quiet"),
            timeout_seconds=60,
        ),
        Gate(
            id="vltima-cli",
            label="VLTIMA CLI projection check",
            command=(python, "-m", "limen.cli", "vltima-kernel", "--check-projection"),
            timeout_seconds=60,
        ),
    ]
    if include_event_proof or require_event_proof:
        gates.append(
            Gate(
                id="event-proof",
                label="live TABVLARIVS event proof streak",
                command=(
                    python,
                    "scripts/check-tabularius-event-proof.py",
                    "--min-streak",
                    str(min_streak),
                ),
                required=require_event_proof,
                timeout_seconds=30,
            )
        )
    return gates


def run_gate(root: Path, gate: Gate) -> GateResult:
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath(root, env)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            gate.command,
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=gate.timeout_seconds,
        )
        elapsed = time.perf_counter() - started
        return GateResult(
            id=gate.id,
            label=gate.label,
            command=gate.command,
            required=gate.required,
            returncode=completed.returncode,
            elapsed_seconds=elapsed,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        return GateResult(
            id=gate.id,
            label=gate.label,
            command=gate.command,
            required=gate.required,
            returncode=124,
            elapsed_seconds=elapsed,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"timed out after {gate.timeout_seconds}s",
            timed_out=True,
        )


def run_gates(root: Path, gates: Iterable[Gate], jobs: int) -> list[GateResult]:
    ordered = list(gates)
    results_by_id: dict[str, GateResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
        futures = {executor.submit(run_gate, root, gate): gate for gate in ordered}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results_by_id[result.id] = result
    return [results_by_id[gate.id] for gate in ordered]


def required_failures(results: Iterable[GateResult]) -> list[GateResult]:
    return [result for result in results if result.required and not result.ok]


def advisory_failures(results: Iterable[GateResult]) -> list[GateResult]:
    return [result for result in results if not result.required and not result.ok]


def _shell_join(command: tuple[str, ...]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def print_result(result: GateResult) -> None:
    status = "PASS" if result.ok else ("ADVISORY" if not result.required else "FAIL")
    required = "required" if result.required else "advisory"
    print(f"{status} {result.id} [{required}] {result.elapsed_seconds:.2f}s - {result.label}")
    if not result.ok:
        print(f"  command: {_shell_join(result.command)}")
        detail = (result.stderr or result.stdout).strip()
        if detail:
            for line in detail.splitlines()[-8:]:
                print(f"  {line}")


def result_payload(results: Iterable[GateResult]) -> dict[str, object]:
    result_list = list(results)
    return {
        "kind": "limen.recordkeeper-kernel-verification",
        "ok": not required_failures(result_list),
        "required_failures": [result.id for result in required_failures(result_list)],
        "advisory_failures": [result.id for result in advisory_failures(result_list)],
        "gates": [
            {
                **asdict(result),
                "command": list(result.command),
                "ok": result.ok,
            }
            for result in result_list
        ],
    }


def write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the focused TABVLARIVS/VLTIMA verification gate.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repo root to verify")
    parser.add_argument("--jobs", type=positive_int, default=min(4, os.cpu_count() or 1), help="parallel gate jobs")
    parser.add_argument("--include-event-proof", action="store_true", help="run live event proof as advisory")
    parser.add_argument("--require-event-proof", action="store_true", help="require live event proof to pass")
    parser.add_argument("--event-proof-min-streak", type=positive_int, default=3, help="required event proof streak")
    parser.add_argument("--json-output", action="store_true", help="emit machine-readable results")
    parser.add_argument("--report-file", type=Path, default=None, help="write machine-readable results to this path")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    gates = gate_plan(
        root,
        include_event_proof=args.include_event_proof,
        require_event_proof=args.require_event_proof,
        min_streak=args.event_proof_min_streak,
    )
    started = time.perf_counter()
    results = run_gates(root, gates, jobs=args.jobs)
    elapsed = time.perf_counter() - started
    payload = result_payload(results)
    payload["elapsed_seconds"] = elapsed
    if args.report_file:
        write_report(args.report_file.expanduser(), payload)
    if args.json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"recordkeeper-kernel: {len(results)} gate(s), jobs={args.jobs}")
        for result in results:
            print_result(result)
        if not args.include_event_proof and not args.require_event_proof:
            print("SKIP event-proof [final] use --include-event-proof or --require-event-proof when live keeper state exists")
        print(f"recordkeeper-kernel: elapsed {elapsed:.2f}s")

    failures = required_failures(results)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
