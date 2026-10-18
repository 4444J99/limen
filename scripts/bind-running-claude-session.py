#!/usr/bin/env python3
"""Bind a running Claude background job through its existing registration hook."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.conduct.client import ConductError, HttpConductClient
from limen.conduct.env_cache import cache_path, ownership_ok, parse_assignments


def run_hook(*args, **kwargs):
    return subprocess.run(*args, **kwargs)


class BindingError(ValueError):
    pass


def bind_running(root: Path, session_id: str, worktree: Path, environ: Mapping[str, str]) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}", session_id):
        raise BindingError("native-session-id-invalid")
    root = root.resolve(strict=True)
    worktree = worktree.absolute()
    if worktree.resolve(strict=True) != worktree:
        raise BindingError("native-worktree-symlink")
    _, marker, name = str(worktree).partition("/.claude/worktrees/")
    if not marker or not name or "/" in name or not worktree.is_dir():
        raise BindingError("claude-background-worktree-required")

    def git(path: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()

    if git(worktree, "rev-parse", "--show-toplevel") != str(worktree) or git(
        worktree, "rev-parse", "--path-format=absolute", "--git-common-dir"
    ) != git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"):
        raise BindingError("claude-worktree-repository-mismatch")
    job = Path(environ.get("CLAUDE_JOB_DIR", ""))
    if not environ.get("CLAUDE_JOB_DIR") or job.is_symlink() or not job.is_dir() or job.stat().st_uid != os.getuid():
        raise BindingError("running-claude-job-directory-required")
    credentials = {}
    cache = cache_path(environ)
    if cache.exists() or cache.is_symlink():
        if not ownership_ok(cache):
            raise BindingError("conduct-credential-cache-unsafe")
        try:
            credentials = parse_assignments(
                cache.read_text(), frozenset({"LIMEN_CONDUCT_URL", "LIMEN_CONDUCT_TOKEN_CLAUDE"})
            )
        except (OSError, UnicodeError):
            raise BindingError("conduct-credential-cache-unreadable") from None
    url = environ.get("LIMEN_CONDUCT_URL") or credentials.get("LIMEN_CONDUCT_URL")
    token = (  # allow-secret: runtime lookup of the owned lane credential, no literal value
        environ.get("LIMEN_CONDUCT_TOKEN_CLAUDE") or credentials.get("LIMEN_CONDUCT_TOKEN_CLAUDE")
    )
    if not url or not token:
        raise BindingError("claude-lane-credential-required")
    hook = root / "scripts/hooks/conduct-register.sh"
    if hook.is_symlink() or not hook.is_file():
        raise BindingError("claude-registration-hook-unavailable")
    client = HttpConductClient(url, token, timeout=15)
    before = client.capabilities()
    principal = before.get("authenticated_principal", {})
    if principal.get("agent") != "claude" or not {"conductor", "executor"}.intersection(principal.get("roles", [])):
        raise BindingError("claude-lane-principal-unconfirmed")
    if any(
        row.get("session_id") == session_id and row.get("identity", {}).get("agent") != "claude"
        for row in before.get("sessions", [])
    ):
        raise BindingError("live-claude-binding-unconfirmed")
    child_env = dict(environ)
    child_env.pop("LIMEN_CONDUCT_TOKEN", None)
    child_env.update(LIMEN_CONDUCT_URL=url, LIMEN_CONDUCT_TOKEN_CLAUDE=token)
    run_hook(
        ["bash", str(hook)],
        input=json.dumps({"session_id": session_id, "cwd": str(worktree)}),
        env=child_env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    sessions = client.capabilities().get("sessions", [])
    matches = [row for row in sessions if row.get("session_id") == session_id]
    if len(matches) != 1:
        raise BindingError("live-claude-binding-unconfirmed")
    record = matches[0]
    if (
        record.get("identity", {}).get("agent") != "claude"
        or record.get("worktree") != str(worktree)
        or record.get("human_protected") is not True
        or record.get("healthy") is not True
    ):
        raise BindingError("live-claude-binding-unconfirmed")
    return {"status": "bound", "session_id": session_id, "agent": "claude", "human_protected": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id", required=True, help="Exact native Claude session ID; never invent a replacement."
    )
    parser.add_argument("--worktree", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = bind_running(ROOT, args.session_id, args.worktree, os.environ)
    except BindingError as exc:
        print(json.dumps({"status": "unmeasured", "reason": str(exc)}))
        return 2
    except (ConductError, OSError, subprocess.SubprocessError):
        print(json.dumps({"status": "unmeasured", "reason": "claude-hook-or-live-readback-unavailable"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
