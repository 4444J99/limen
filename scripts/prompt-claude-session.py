#!/usr/bin/env python3
"""Deliver a prompt to a live background Claude session from any other lane (Codex, Gemini, ...).

Why this exists: a peer that is not Claude Code has no SendMessage tool, and two obvious routes are
closed on purpose -- Computer Use refuses terminal apps, and the host admission hook denies a
`claude` invocation whose cwd is not inside a linked git worktree (`workspace-scope-unavailable`).
This script is the compliant third route: resolve the target from `claude agents --json`, then run
`claude --bg --resume <sessionId> -- <prompt>` *from the target's own worktree*, which is exactly the
scope the hook demands. It never touches a terminal, and delivery is not acknowledgement.

Exit codes: 0 delivered, 2 refused before sending, 3 `claude` failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))
from limen.host_admission import worktree_scope  # noqa: E402

CLAUDE_BIN = "claude"
LIST_TIMEOUT_SECONDS = 20
SEND_TIMEOUT_SECONDS = 60

Runner = Callable[..., subprocess.CompletedProcess]


class Refused(Exception):
    """The send was refused before `claude` was invoked."""


def list_sessions(run: Runner = subprocess.run) -> list[dict[str, Any]]:
    result = run(
        [CLAUDE_BIN, "agents", "--json"],
        capture_output=True,
        text=True,
        timeout=LIST_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise Refused(f"`claude agents --json` failed (exit {result.returncode}): {result.stderr.strip()[:200]}")
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Refused(f"`claude agents --json` was not JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise Refused("`claude agents --json` did not return a list")
    return [row for row in rows if isinstance(row, dict)]


def describe(row: dict[str, Any]) -> str:
    return f"{row.get('name')!r} [{row.get('id')}] {row.get('kind')}/{row.get('status')}"


def resolve_target(sessions: Sequence[dict[str, Any]], query: str) -> dict[str, Any]:
    """Exact name, else exact id/sessionId, else a unique id/sessionId/name prefix. Never guess."""
    needle = query.strip()
    if not needle:
        raise Refused("empty --to")
    tiers = (
        [r for r in sessions if r.get("name") == needle],
        [r for r in sessions if needle in (r.get("id"), r.get("sessionId"))],
        [r for r in sessions if any(str(r.get(key) or "").startswith(needle) for key in ("id", "sessionId", "name"))],
    )
    for matches in tiers:
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise Refused(f"{needle!r} is ambiguous: " + "; ".join(describe(m) for m in matches))
    known = "; ".join(describe(r) for r in sessions) or "none"
    raise Refused(f"no live session matches {needle!r}. Live sessions: {known}")


def check_deliverable(target: dict[str, Any], *, allow_copy: bool) -> Path:
    """Return the cwd to run `claude` from, or raise Refused with the exact reason."""
    if target.get("kind") != "background":
        raise Refused(
            f"{describe(target)} is not a background session; interactive sessions belong to a human "
            "and are never prompted by a peer"
        )
    if target.get("status") == "busy" and not allow_copy:
        raise Refused(
            f"{describe(target)} is busy: resuming a running session forks a copy and splits "
            "ownership. Wait for idle, or pass --allow-copy to fork deliberately"
        )
    cwd = Path(str(target.get("cwd") or ""))
    try:
        scope = worktree_scope(cwd)
    except (ValueError, OSError) as exc:
        raise Refused(
            f"target cwd {str(cwd)!r} is not a resolvable git checkout ({exc}); the host admission "
            "hook would deny `claude` from there"
        ) from exc
    if not scope.linked:
        raise Refused(
            f"target cwd {str(cwd)!r} is the shared checkout, not a linked worktree; the host "
            "admission hook admits mutations only from a linked worktree"
        )
    return cwd


def deliver(
    target: dict[str, Any],
    prompt: str,
    *,
    allow_copy: bool = False,
    dry_run: bool = False,
    run: Runner = subprocess.run,
) -> dict[str, Any]:
    cwd = check_deliverable(target, allow_copy=allow_copy)
    argv = [CLAUDE_BIN, "--bg", "--resume", str(target["sessionId"]), "--", prompt]
    receipt: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {key: target.get(key) for key in ("id", "sessionId", "name", "kind", "status")},
        "cwd": str(cwd),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_bytes": len(prompt.encode()),
        "argv": argv[:-1] + ["<prompt>"],
        "dry_run": dry_run,
        "delivered": False,
        "acknowledged": False,
        "note": "delivery is not acknowledgement; read `claude logs <id>` for the session's reply",
        "read_back": f"{CLAUDE_BIN} logs {target.get('id')}",
    }
    if dry_run:
        return receipt
    result = run(argv, cwd=cwd, capture_output=True, text=True, timeout=SEND_TIMEOUT_SECONDS, check=False)
    receipt["exit_code"] = result.returncode
    receipt["claude_stdout"] = result.stdout.strip()[:500]
    receipt["claude_stderr"] = result.stderr.strip()[:500]
    receipt["delivered"] = result.returncode == 0
    return receipt


def read_prompt(prompt_file: str) -> str:
    text = sys.stdin.read() if prompt_file == "-" else Path(prompt_file).read_text(encoding="utf-8")
    if not text.strip():
        raise Refused("prompt is empty")
    return text


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--to", required=True, help="target session name, id, sessionId, or unique prefix")
    parser.add_argument("--prompt-file", required=True, help="file holding the prompt, or - for stdin")
    parser.add_argument("--allow-copy", action="store_true", help="permit resuming a busy session (forks a copy)")
    parser.add_argument("--dry-run", action="store_true", help="resolve and validate, print the receipt, send nothing")
    parser.add_argument("--receipt", help="also write the JSON receipt to this path")
    args = parser.parse_args(argv)

    try:
        target = resolve_target(list_sessions(), args.to)
        receipt = deliver(
            target,
            read_prompt(args.prompt_file),
            allow_copy=args.allow_copy,
            dry_run=args.dry_run,
        )
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 3

    rendered = json.dumps(receipt, indent=2)
    print(rendered)
    if args.receipt:
        Path(args.receipt).write_text(rendered + "\n", encoding="utf-8")
    return 0 if receipt["delivered"] or receipt["dry_run"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
