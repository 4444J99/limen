#!/usr/bin/env python3
"""Prepare the human gate for reconciling the live Limen checkout.

This receipt is intentionally read-only. It inspects the daemon checkout,
release branch, and launchd heartbeat state, then writes a public handoff doc
plus a private JSON index. It does not switch branches, reset, stash, commit,
edit tasks.yaml, or reload launchd.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "live-root-gate.json"
DOC_PATH = ROOT / "docs" / "live-root-gate.md"
LIVE_ROOT = Path(os.environ.get("LIMEN_LIVE_ROOT", HOME / "Workspace" / "limen"))
RELEASE_BRANCH = os.environ.get("LIMEN_RELEASE_BRANCH", "main")
HEARTBEAT_PLIST = Path(
    os.environ.get("LIMEN_HEARTBEAT_PLIST", HOME / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist")
)
LAUNCHD_LABEL = os.environ.get("LIMEN_HEARTBEAT_LABEL", "com.limen.heartbeat")


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }
    except OSError as exc:
        return {"args": args, "returncode": None, "stdout": "", "stderr": str(exc), "timed_out": False}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def command_text(args: list[str]) -> str:
    return " ".join(args)


def git_output(root: Path, args: list[str], timeout: int = 20) -> str | None:
    result = run_command(["git", "-C", str(root), *args], timeout=timeout)
    if result.get("returncode") == 0:
        return str(result.get("stdout") or "").strip()
    return None


def parse_ahead_behind(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    parts = text.split()
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return int(parts[0]), int(parts[1])
    return None, None


def parse_dirty(status_text: str) -> dict[str, Any]:
    lines = [line for line in status_text.splitlines() if line and not line.startswith("## ")]
    tracked: list[str] = []
    untracked: list[str] = []
    for line in lines:
        path = line[3:] if len(line) > 3 else line
        if line.startswith("?? "):
            untracked.append(path)
        else:
            tracked.append(path)
    return {
        "dirty_entries": len(lines),
        "tracked_dirty": tracked,
        "untracked": untracked,
        "dirty_paths": tracked + untracked,
    }


def git_snapshot(root: Path, release_branch: str = RELEASE_BRANCH) -> dict[str, Any]:
    status_text = git_output(root, ["status", "--porcelain=v1", "--branch"]) or ""
    dirty = parse_dirty(status_text)
    release_ref = f"origin/{release_branch}"
    head = git_output(root, ["rev-parse", "HEAD"])
    release_head = git_output(root, ["rev-parse", release_ref])
    ahead, behind = parse_ahead_behind(git_output(root, ["rev-list", "--left-right", "--count", f"HEAD...{release_ref}"]))
    cherry_text = git_output(root, ["cherry", release_ref, "HEAD"]) or ""
    cherry_lines = [line for line in cherry_text.splitlines() if line.strip()]
    unique_commits = [line[2:] for line in cherry_lines if line.startswith("+ ")]
    patch_equivalent_commits = [line[2:] for line in cherry_lines if line.startswith("- ")]
    local_log = git_output(root, ["log", "--oneline", "--decorate=no", f"{release_ref}..HEAD", "--"], timeout=12) or ""
    return {
        "path": str(root),
        "present": root.exists(),
        "is_git": (root / ".git").exists() or bool(git_output(root, ["rev-parse", "--git-dir"])),
        "branch": git_output(root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "release_branch": release_branch,
        "release_ref": release_ref,
        "head": head,
        "release_head": release_head,
        "matches_release": bool(head and release_head and head == release_head),
        "ahead_release": ahead,
        "behind_release": behind,
        "status_summary": status_text.splitlines()[0] if status_text.splitlines() else "",
        "unique_commit_count": len(unique_commits),
        "patch_equivalent_commit_count": len(patch_equivalent_commits),
        "unique_commits": unique_commits[:20],
        "patch_equivalent_commits": patch_equivalent_commits[:20],
        "local_log": local_log.splitlines()[:20],
        **dirty,
    }


def read_plist(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ValueError) as exc:
        return {"present": False, "path": str(path), "error": str(exc)}
    env = data.get("EnvironmentVariables") or {}
    return {
        "present": True,
        "path": str(path),
        "label": data.get("Label"),
        "keep_alive": data.get("KeepAlive"),
        "run_at_load": data.get("RunAtLoad"),
        "env": {
            "LIMEN_ROOT": env.get("LIMEN_ROOT"),
            "LIMEN_DISPATCH_ASYNC": env.get("LIMEN_DISPATCH_ASYNC"),
            "LIMEN_LANES": env.get("LIMEN_LANES"),
            "LIMEN_LOCAL_LIMIT": env.get("LIMEN_LOCAL_LIMIT"),
        },
    }


def parse_launchd_print(text: str) -> dict[str, Any]:
    env: dict[str, str] = {}
    in_env = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "environment = {":
            in_env = True
            continue
        if in_env and stripped == "}":
            in_env = False
            continue
        if in_env:
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*) => (.*)", stripped)
            if match and match.group(1).startswith("LIMEN_"):
                env[match.group(1)] = match.group(2)
    state_match = re.search(r"^\s*state = (.+)$", text, re.MULTILINE)
    pid_match = re.search(r"^\s*pid = ([0-9]+)$", text, re.MULTILINE)
    return {
        "present": bool(text.strip()),
        "running": bool(state_match and state_match.group(1).strip() == "running"),
        "state": state_match.group(1).strip() if state_match else "missing",
        "pid": pid_match.group(1) if pid_match else None,
        "env": env,
    }


def launchd_snapshot() -> dict[str, Any]:
    result = run_command(["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], timeout=8)
    parsed = parse_launchd_print(str(result.get("stdout") or ""))
    parsed["probe"] = {"returncode": result.get("returncode"), "timed_out": result.get("timed_out")}
    return parsed


def env_drift(plist: dict[str, Any], loaded: dict[str, Any]) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    plist_env = plist.get("env") or {}
    loaded_env = loaded.get("env") or {}
    for key in ("LIMEN_ROOT", "LIMEN_DISPATCH_ASYNC", "LIMEN_LANES", "LIMEN_LOCAL_LIMIT"):
        if plist_env.get(key) != loaded_env.get(key):
            drift.append({"key": key, "plist": plist_env.get(key), "loaded": loaded_env.get(key)})
    return drift


def derive_blockers(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    live = snapshot["live_root_git"]
    drift = snapshot["launchd_env_drift"]
    if not live.get("present"):
        blockers.append({"id": "live-root-missing", "evidence": "Configured live root does not exist."})
    elif not live.get("is_git"):
        blockers.append({"id": "live-root-not-git", "evidence": "Configured live root is not a git checkout."})
    else:
        if live.get("branch") != live.get("release_branch"):
            blockers.append(
                {
                    "id": "live-root-not-release-branch",
                    "evidence": f"live root is on {live.get('branch')}, not {live.get('release_branch')}.",
                }
            )
        if not live.get("matches_release"):
            blockers.append(
                {
                    "id": "live-root-not-at-release",
                    "evidence": (
                        f"live root head {str(live.get('head') or '')[:12]} differs from "
                        f"{live.get('release_ref')} {str(live.get('release_head') or '')[:12]}."
                    ),
                }
            )
        if int(live.get("unique_commit_count") or 0):
            blockers.append(
                {
                    "id": "live-root-unique-commits",
                    "evidence": f"{live.get('unique_commit_count')} local commit(s) are not patch-equivalent to release.",
                }
            )
        if int(live.get("dirty_entries") or 0):
            blockers.append(
                {
                    "id": "live-root-dirty",
                    "evidence": f"live root has {live.get('dirty_entries')} dirty entries.",
                }
            )
        if "tasks.yaml" in (live.get("tracked_dirty") or []):
            blockers.append(
                {
                    "id": "live-root-task-board-dirty",
                    "evidence": "live tasks.yaml is dirty and daemon-owned; preserve it before any release convergence.",
                }
            )
    if drift:
        keys = ", ".join(item["key"] for item in drift)
        blockers.append({"id": "heartbeat-loaded-env-drift", "evidence": f"loaded launchd env differs from plist for {keys}."})
    return blockers


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    if args.fetch:
        fetch = run_command(["git", "-C", str(LIVE_ROOT), "fetch", "--quiet", "origin", RELEASE_BRANCH], timeout=60)
    else:
        fetch = {"args": [], "returncode": None, "timed_out": False, "skipped": True}
    plist = read_plist(HEARTBEAT_PLIST)
    loaded = launchd_snapshot()
    snapshot: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fetch": {
            "requested": bool(args.fetch),
            "returncode": fetch.get("returncode"),
            "timed_out": fetch.get("timed_out"),
            "skipped": fetch.get("skipped", False),
        },
        "live_root_git": git_snapshot(LIVE_ROOT, RELEASE_BRANCH),
        "verified_worktree": git_snapshot(ROOT, RELEASE_BRANCH),
        "heartbeat_plist": plist,
        "launchd": loaded,
        "launchd_env_drift": env_drift(plist, loaded),
    }
    blockers = derive_blockers(snapshot)
    snapshot["blockers"] = blockers
    snapshot["status"] = "ready" if not blockers else "blocked"
    snapshot["operator_gate_required"] = bool(blockers)
    snapshot["release_reconcile_allowed_without_human"] = False
    snapshot["launchd_reload_allowed_without_human"] = False
    return snapshot


def render_markdown(snapshot: dict[str, Any]) -> str:
    live = snapshot["live_root_git"]
    verified = snapshot["verified_worktree"]
    plist = snapshot["heartbeat_plist"]
    loaded = snapshot["launchd"]
    drift = snapshot["launchd_env_drift"]
    blockers = snapshot["blockers"]
    blocking_text = ", ".join(f"`{item['id']}`" for item in blockers) or "none"
    lines = [
        "# Live Root Gate",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        f"Status: `{snapshot['status']}`",
        "",
        "## Rule",
        "",
        "- This is an operator gate for the live Limen checkout and heartbeat LaunchAgent.",
        "- It does not switch branches, reset, stash, commit, edit tasks.yaml, or reload launchd.",
        "- Treat tasks.yaml as daemon-owned live state; preserve it before release convergence.",
        "",
        "## Gate State",
        "",
        f"- Operator gate required: `{snapshot['operator_gate_required']}`.",
        f"- Release reconcile allowed without human: `{snapshot['release_reconcile_allowed_without_human']}`.",
        f"- Launchd reload allowed without human: `{snapshot['launchd_reload_allowed_without_human']}`.",
        f"- Blocking gates: {blocking_text}.",
        "",
        "## Live Root",
        "",
        f"- Path: `{relpath(Path(live.get('path') or LIVE_ROOT))}`.",
        f"- Branch: `{live.get('branch')}`; release branch `{live.get('release_branch')}`.",
        f"- HEAD: `{live.get('head')}`.",
        f"- Release head: `{live.get('release_head')}`.",
        f"- Matches release: `{live.get('matches_release')}`; ahead `{live.get('ahead_release')}` behind `{live.get('behind_release')}`.",
        f"- Unique local commits: `{live.get('unique_commit_count')}`; patch-equivalent commits: `{live.get('patch_equivalent_commit_count')}`.",
        f"- Dirty entries: `{live.get('dirty_entries')}`.",
    ]
    if live.get("local_log"):
        lines += ["", "### Local Commits", ""]
        for line in live.get("local_log") or []:
            lines.append(f"- `{line}`")
    if live.get("dirty_paths"):
        lines += ["", "### Dirty Paths", ""]
        for path in live.get("dirty_paths") or []:
            lines.append(f"- `{path}`")
    lines += [
        "",
        "## Heartbeat",
        "",
        f"- Plist: `{relpath(Path(plist.get('path') or HEARTBEAT_PLIST))}` present `{plist.get('present')}`.",
        f"- Loaded launchd state: `{loaded.get('state')}` pid `{loaded.get('pid')}`.",
    ]
    if drift:
        lines += ["", "### Loaded Env Drift", ""]
        for item in drift:
            lines.append(f"- `{item['key']}`: plist `{item.get('plist')}`; loaded `{item.get('loaded')}`.")
    else:
        lines.append("- Loaded env matches plist for tracked LIMEN_* keys.")

    lines += [
        "",
        "## Verified Worktree",
        "",
        f"- Path: `{relpath(Path(verified.get('path') or ROOT))}`.",
        f"- Branch: `{verified.get('branch')}`.",
        f"- Matches release: `{verified.get('matches_release')}`.",
        "",
        "## Stop Conditions",
        "",
        "- Stop before `git reset`, branch switch, stash drop, task-board write, launchd bootout/bootstrap/kickstart, or async enablement.",
        "- Stop if `git cherry origin/main HEAD` reports any `+` commits until the operator decides whether to preserve, cherry-pick, or abandon them.",
        "- Stop if `tasks.yaml` is dirty until the daemon-owned queue has been explicitly preserved.",
        "- Stop if heartbeat has live child work; reload only between beats.",
        "",
        "## Human-Gated Command Packet",
        "",
        "Run these only after operator approval, in order, stopping on any mismatch:",
        "",
        "```bash",
        f"LIVE_ROOT={str(LIVE_ROOT)!r}",
        f"HEARTBEAT_LABEL={LAUNCHD_LABEL!r}",
        'git -C "$LIVE_ROOT" status --branch --short',
        'git -C "$LIVE_ROOT" cherry origin/main HEAD',
        'git -C "$LIVE_ROOT" diff --name-status',
        'git -C "$LIVE_ROOT" ls-files --others --exclude-standard',
        'python3 scripts/dispatch-health.py --write --probe-async',
        'python3 scripts/live-root-gate.py --write',
        "# After preserving or intentionally discarding live-root-only state:",
        '# launchctl kickstart -k "gui/$(id -u)/$HEARTBEAT_LABEL"',
        "# Then require dispatch-health status healthy before enabling async.",
        "```",
        "",
        "## Refresh Commands",
        "",
        f"- Refresh this gate: `{command_text(['python3', 'scripts/live-root-gate.py', '--write'])}`",
        "- Refresh with remote tracking update: `python3 scripts/live-root-gate.py --write --fetch`",
        "- Refresh dispatch health: `python3 scripts/dispatch-health.py --write --probe-async`",
        "- Verify watchdog: `python3 scripts/watchdog.py --dry-run`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the live-root reconciliation gate receipt.")
    parser.add_argument("--write", action="store_true", help="write tracked and private gate receipts")
    parser.add_argument("--fetch", action="store_true", help="fetch origin release branch before inspecting")
    args = parser.parse_args()
    snapshot = build_snapshot(args)
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = f"live-root-gate: {snapshot['status']} with {len(snapshot['blockers'])} blocker(s)"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
