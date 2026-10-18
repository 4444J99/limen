#!/usr/bin/env python3
"""Deliver a prompt to a live background Claude session from any other lane (Codex, Gemini, ...).

Why this exists: a peer that is not Claude Code has no SendMessage tool, and two obvious routes are
closed on purpose -- Computer Use refuses terminal apps, and the host admission hook denies a
`claude` invocation whose cwd is not inside a linked git worktree (`workspace-scope-unavailable`).
This script is the compliant third route: resolve the target from `claude agents --json`, then run
`claude --bg --resume <sessionId> -- <prompt>` *from the target's own worktree*, which is exactly the
scope the hook demands of that child. It never touches a terminal, and delivery is not
acknowledgement.

Invoke it as `python3 scripts/prompt-claude-session.py ...`: the caller's own admission hook
classifies that exact form as a sanctioned control (`_SANCTIONED_SCRIPTS`), so the caller needs no
linked-worktree cwd or writer lease just to run it. A bare shebang invocation is not recognised.

Exit codes: 0 delivered and receiver verified (or dry run), 2 refused before sending, 3 `claude`
failed or timed out (delivery unknown), 4 sent but the receiving session could not be verified or
a fork received it.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))
from limen.host_admission import worktree_scope  # noqa: E402

CLAUDE_BIN = "claude"
LIST_TIMEOUT_SECONDS = 20
SEND_TIMEOUT_SECONDS = 60
MIN_SCRUB_LINE = 8

Runner = Callable[..., subprocess.CompletedProcess]
Lister = Callable[[], list[dict[str, Any]]]


class Refused(Exception):
    """The send was refused before `claude` was invoked."""


def list_sessions(run: Runner = subprocess.run) -> list[dict[str, Any]]:
    try:
        result = run(
            [CLAUDE_BIN, "agents", "--json"],
            capture_output=True,
            text=True,
            timeout=LIST_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise Refused(f"`claude agents --json` timed out after {LIST_TIMEOUT_SECONDS}s") from exc
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
    raw_cwd = target.get("cwd")
    # An absent cwd must never become Path("") == ".": that would validate the *caller's* checkout.
    if not isinstance(raw_cwd, str) or not raw_cwd.strip() or not Path(raw_cwd).is_absolute():
        raise Refused(f"{describe(target)} reports no absolute cwd ({raw_cwd!r}); refusing to guess a checkout")
    cwd = Path(raw_cwd)
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


def scrub(text: str, prompt: str) -> str:
    """Remove the prompt (whole, and every substantial line) from text that will be stored or printed."""
    out = text.replace(prompt, "<prompt>")
    for line in prompt.splitlines():
        stripped = line.strip()
        if len(stripped) >= MIN_SCRUB_LINE:
            out = out.replace(stripped, "<prompt-line>")
    return out


def _lock_path(session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"limen-prompt-claude-session-{digest}.lock"


def _verify_receiver(
    before: set[str], after: Sequence[dict[str, Any]], target: dict[str, Any], *, allow_copy: bool
) -> dict[str, Any]:
    """Decide from two session listings which session actually received the prompt."""
    new_rows = [row for row in after if row.get("sessionId") not in before]
    original = next((row for row in after if row.get("sessionId") == target["sessionId"]), None)
    forks = [{key: row.get(key) for key in ("id", "sessionId", "name", "cwd")} for row in new_rows]
    if new_rows:
        same_cwd = [row for row in new_rows if row.get("cwd") == target.get("cwd")]
        deliberate = allow_copy and len(same_cwd) == 1 and len(new_rows) == 1
        return {
            "forked": True,
            "identity_verified": deliberate,
            "receiving_session": forks[0] if deliberate else None,
            "fork_sessions": forks,
        }
    return {
        "forked": False,
        "identity_verified": original is not None,
        "receiving_session": {key: original.get(key) for key in ("id", "sessionId", "name", "status")}
        if original
        else None,
        "fork_sessions": [],
    }


def deliver(
    target: dict[str, Any],
    prompt: str,
    *,
    allow_copy: bool = False,
    dry_run: bool = False,
    run: Runner = subprocess.run,
    lister: Lister | None = None,
) -> dict[str, Any]:
    """Validate against a fresh listing, send once, then verify who received it.

    The listing the caller resolved from may be seconds old; a target that went busy in between would
    make `--resume` fork a copy. So the row is re-read immediately before the send, the send is
    serialized per target, and the sessions are listed again afterwards to prove the receiver.
    """
    list_now: Lister = lister or list_sessions
    fresh = next((row for row in list_now() if row.get("sessionId") == target.get("sessionId")), None)
    if fresh is None:
        raise Refused(f"{describe(target)} is no longer a live session")
    cwd = check_deliverable(fresh, allow_copy=allow_copy)
    argv = [CLAUDE_BIN, "--bg", "--resume", str(fresh["sessionId"]), "--", prompt]
    receipt: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {key: fresh.get(key) for key in ("id", "sessionId", "name", "kind", "status")},
        "status_at_send": fresh.get("status"),
        "cwd": str(cwd),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_bytes": len(prompt.encode()),
        "argv": argv[:-1] + ["<prompt>"],
        "dry_run": dry_run,
        "delivered": False,
        "acknowledged": False,
        "forked": False,
        "identity_verified": False,
        "receiving_session": None,
        "note": "delivery is not acknowledgement; read `claude logs <id>` for the session's reply",
        "read_back": f"{CLAUDE_BIN} logs {fresh.get('id')}",
    }
    if dry_run:
        return receipt

    with _lock_path(str(fresh["sessionId"])).open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refused(f"another send to {describe(fresh)} is in progress; not racing it") from exc
        before = {str(row.get("sessionId")) for row in list_now()}
        try:
            result = run(argv, cwd=cwd, capture_output=True, text=True, timeout=SEND_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            # str(TimeoutExpired) embeds argv, i.e. the prompt; report the fact, never the exception.
            receipt["error"] = f"claude timed out after {SEND_TIMEOUT_SECONDS}s; delivery is unknown"
            return receipt
        receipt["exit_code"] = result.returncode
        receipt["claude_stdout"] = scrub(result.stdout or "", prompt).strip()[:500]
        receipt["claude_stderr"] = scrub(result.stderr or "", prompt).strip()[:500]
        if result.returncode != 0:
            return receipt
        try:
            receipt.update(_verify_receiver(before, list_now(), fresh, allow_copy=allow_copy))
        except Refused as exc:
            receipt["error"] = f"receiver unverified: {exc}"
        receipt["delivered"] = not receipt["forked"] or receipt["identity_verified"]
    return receipt


def read_prompt(prompt_file: str) -> str:
    text = sys.stdin.read() if prompt_file == "-" else Path(prompt_file).read_text(encoding="utf-8")
    if not text.strip():
        raise Refused("prompt is empty")
    return text


def exit_code(receipt: dict[str, Any]) -> int:
    if receipt["dry_run"]:
        return 0
    if "exit_code" not in receipt or receipt["exit_code"] != 0:
        return 3
    return 0 if receipt["delivered"] and receipt["identity_verified"] else 4


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
        # Never print str(exc): a SubprocessError carries the full command, prompt included.
        detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else type(exc).__name__
        print(f"FAILED: {detail}", file=sys.stderr)
        return 3

    rendered = json.dumps(receipt, indent=2)
    print(rendered)
    if args.receipt:
        Path(args.receipt).write_text(rendered + "\n", encoding="utf-8")
    return exit_code(receipt)


if __name__ == "__main__":
    raise SystemExit(main())
