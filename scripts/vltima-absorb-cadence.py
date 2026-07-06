#!/usr/bin/env python3
"""Run the VLTIMA continual absorption cadence.

Default mode is a dry-run plan. Use ``--write`` to execute the safe redacted
cadence. Use ``--materialize-private`` only when the operator intentionally
wants the raw local app material copied into the ignored private object store.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
).expanduser()
DOC_PATH = ROOT / "docs" / "vltima-absorb-cadence.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "vltima-absorb-cadence.json"
WORKSPACE_CHECKOUT_RE = re.compile(r"/(?:Users|home)/[^/\s`]+/Workspace/limen(?=/|$)")


@dataclass(frozen=True)
class CadenceStep:
    id: str
    phase: str
    command: tuple[str, ...]
    reason: str
    optional: bool = False


BASE_STEPS: tuple[CadenceStep, ...] = (
    CadenceStep(
        id="capture",
        phase="capture",
        command=("python3", "scripts/session-corpus-ledger.py", "--write", "--all"),
        reason="absorb local AI app movement into redacted corpus/source coverage",
    ),
    CadenceStep(
        id="crosswalk",
        phase="crosswalk",
        command=("python3", "scripts/prompt-lifecycle-ledger.py", "--write", "--all"),
        reason="relate brainstorm/session movement to worktrees, tasks, and receipts",
    ),
    CadenceStep(
        id="blockers",
        phase="classify-pressure",
        command=("python3", "scripts/session-blockers-ledger.py", "--write"),
        reason="surface parked blockers before routing or delegation",
    ),
    CadenceStep(
        id="pressure",
        phase="classify-pressure",
        command=("python3", "scripts/session-lifecycle-pressure.py", "--write"),
        reason="record local/remote lifecycle pressure as a receipt",
    ),
    CadenceStep(
        id="attack-paths",
        phase="rank-and-packetize",
        command=("python3", "scripts/session-attack-paths.py", "--write"),
        reason="rank paths from current evidence without making old material authoritative",
    ),
    CadenceStep(
        id="priority-map",
        phase="rank-and-packetize",
        command=("python3", "scripts/prompt-priority-map.py", "--write"),
        reason="turn ranked paths into priority bands and review batches",
    ),
    CadenceStep(
        id="command-center",
        phase="distill",
        command=("python3", "scripts/corpus-command-center.py", "--write"),
        reason="distill prompts, artifacts, tasks, products, and inbound positioning",
    ),
    CadenceStep(
        id="substrate-ledger",
        phase="reconcile-mismatches",
        command=("python3", "scripts/substrate-ledger.py", "--write"),
        reason="publish the tracked substrate result so the surface is not private-only",
    ),
    CadenceStep(
        id="agent-reconstruction-review",
        phase="reconcile-mismatches",
        command=("python3", "scripts/agent-reconstruction-review.py", "--write"),
        reason="refresh stale reconstruction review output before trusting lineage/dormant rows",
    ),
    CadenceStep(
        id="prior-excavations",
        phase="register",
        command=("python3", "scripts/vltima-prior-excavations.py", "--write"),
        reason="refresh the map of prior excavations after owner results move",
    ),
    CadenceStep(
        id="result-digest",
        phase="digest",
        command=("python3", "scripts/vltima-result-digest.py", "--write"),
        reason="refresh temporal authority classification after all result receipts update",
    ),
)

MATERIALIZE_STEP = CadenceStep(
    id="materialize-private",
    phase="materialize-private",
    command=("python3", "scripts/session-corpus-ledger.py", "--write", "--all", "--materialize"),
    reason="copy raw local app material into ignored private object store",
    optional=True,
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def shell_join(command: tuple[str, ...]) -> str:
    return " ".join(command)


def tail(text: str, *, limit: int = 12) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def public_line(text: Any) -> str:
    line = str(text)
    root_aliases = {
        str(ROOT),
        str(Path.cwd()),
        str((Path.home() / "Workspace" / "limen").expanduser()),
        os.environ.get("LIMEN_ROOT", ""),
        os.environ.get("LIMEN_LIVE_ROOT", ""),
    }
    for alias in sorted((item for item in root_aliases if item), key=len, reverse=True):
        line = line.replace(alias, "$LIMEN_ROOT")
    line = WORKSPACE_CHECKOUT_RE.sub("$LIMEN_ROOT", line)
    line = line.replace(str(Path.home()), "~")
    return line


def cadence_steps(*, materialize_private: bool) -> list[CadenceStep]:
    steps = list(BASE_STEPS)
    if materialize_private:
        steps.insert(1, MATERIALIZE_STEP)
    return steps


def run_step(step: CadenceStep, *, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(step.command),
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        duration = round(time.monotonic() - started, 3)
        return {
            "id": step.id,
            "phase": step.phase,
            "command": shell_join(step.command),
            "reason": step.reason,
            "optional": step.optional,
            "returncode": proc.returncode,
            "duration_seconds": duration,
            "stdout_tail": tail(proc.stdout),
            "stderr_tail": tail(proc.stderr),
            "status": "ok" if proc.returncode == 0 else "failed",
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 3)
        return {
            "id": step.id,
            "phase": step.phase,
            "command": shell_join(step.command),
            "reason": step.reason,
            "optional": step.optional,
            "returncode": None,
            "duration_seconds": duration,
            "stdout_tail": tail(exc.stdout or ""),
            "stderr_tail": tail(exc.stderr or ""),
            "status": "timeout",
        }


def build_receipt(
    *,
    execute: bool,
    materialize_private: bool,
    stop_on_failure: bool,
    timeout: int,
) -> dict[str, Any]:
    steps = cadence_steps(materialize_private=materialize_private)
    results: list[dict[str, Any]] = []
    if execute:
        for step in steps:
            result = run_step(step, timeout=timeout)
            results.append(result)
            if stop_on_failure and result["status"] != "ok":
                break
    else:
        for step in steps:
            results.append(
                {
                    "id": step.id,
                    "phase": step.phase,
                    "command": shell_join(step.command),
                    "reason": step.reason,
                    "optional": step.optional,
                    "status": "planned",
                }
            )
    status = "planned"
    if execute:
        status = (
            "ok" if all(result["status"] == "ok" for result in results) and len(results) == len(steps) else "failed"
        )
    return {
        "generated_at": now_iso(),
        "status": status,
        "mode": "write" if execute else "dry-run",
        "materialize_private": materialize_private,
        "stop_on_failure": stop_on_failure,
        "step_count": len(steps),
        "results": results,
        "privacy": {
            "raw_materialization_opt_in": materialize_private,
            "tracked_output": "docs/vltima-absorb-cadence.md",
            "private_index": str(PRIVATE_INDEX),
        },
    }


def render_markdown(receipt: dict[str, Any]) -> str:
    lines = [
        "# VLTIMA Absorption Cadence",
        "",
        f"Generated: `{receipt['generated_at']}`",
        f"Status: `{receipt['status']}`",
        f"Mode: `{receipt['mode']}`",
        f"Materialize private raw inputs: `{receipt['materialize_private']}`",
        "",
        "## Contract",
        "",
        "- Local AI app chats, projects, plans, tasks, histories, and app-store movement are continual corpus input.",
        "- The cadence absorbs movement as private/redacted evidence first; brainstorms do not become current authority by default.",
        "- `--materialize-private` is explicit because it copies raw local material into the ignored private object store.",
        "- This runner does not edit `tasks.yaml`, delete repos, clean branches, push remotes, or handle credentials.",
        "",
        "## Steps",
        "",
        "| Step | Phase | Status | Command | Reason |",
        "|---|---|---|---|---|",
    ]
    for result in receipt["results"]:
        command = str(result["command"]).replace("|", "\\|")
        reason = str(result["reason"]).replace("|", "\\|")
        lines.append(f"| `{result['id']}` | `{result['phase']}` | `{result['status']}` | `{command}` | {reason} |")
    lines += [
        "",
        "## Receipt Tails",
        "",
    ]
    for result in receipt["results"]:
        stdout_tail = result.get("stdout_tail") or []
        stderr_tail = result.get("stderr_tail") or []
        if not stdout_tail and not stderr_tail:
            continue
        lines.append(f"### `{result['id']}`")
        if stdout_tail:
            lines.append("")
            lines.append("stdout:")
            lines.append("```")
            lines.extend(public_line(line) for line in stdout_tail)
            lines.append("```")
        if stderr_tail:
            lines.append("")
            lines.append("stderr:")
            lines.append("```")
            lines.extend(public_line(line) for line in stderr_tail)
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(receipt: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or print the VLTIMA absorption cadence.")
    parser.add_argument("--write", action="store_true", help="execute the cadence and write receipts")
    parser.add_argument("--json", action="store_true", help="print receipt JSON")
    parser.add_argument("--materialize-private", action="store_true", help="include private raw materialization")
    parser.add_argument(
        "--continue-on-error", action="store_true", help="run later steps even if an earlier command fails"
    )
    parser.add_argument("--timeout", type=int, default=900, help="timeout per step in seconds")
    args = parser.parse_args()
    receipt = build_receipt(
        execute=args.write,
        materialize_private=args.materialize_private,
        stop_on_failure=not args.continue_on_error,
        timeout=args.timeout,
    )
    markdown = render_markdown(receipt)
    if args.write:
        write_outputs(receipt, markdown)
        print(f"vltima-absorb-cadence: {receipt['status']}; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    elif args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("vltima-absorb-cadence: dry-run")
    return 0 if receipt["status"] in {"ok", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
