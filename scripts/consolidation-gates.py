#!/usr/bin/env python3
"""Refresh the read-only GitHub consolidation gate receipt.

This is the local proof layer before any irreversible GitHub action. It runs only
dry-run/status probes, parses the gate counts, and writes:

* docs/consolidation/GATES.md for public-safe handoff;
* .limen-private/session-corpus/lifecycle/consolidation-gates.json for the
  conductor selector.

It never runs repo rename, transfer, owner rewrite --apply, App install, or
credential writes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
DOC_PATH = ROOT / "docs" / "consolidation" / "GATES.md"
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "consolidation-gates.json"

COMMAND_TIMEOUT = int(os.environ.get("LIMEN_CONSOLIDATION_GATE_TIMEOUT", "180"))
RUNBOOK = ROOT / "docs" / "consolidation" / "RUNBOOK.md"
COLLISION_RENAMES = ROOT / "docs" / "consolidation" / "COLLISION-RENAMES.md"
SCOPE_AND_APP = ROOT / "docs" / "consolidation" / "SCOPE-AND-APP.md"


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def run_command(args: list[str], *, env: dict[str, str] | None = None, timeout: int = COMMAND_TIMEOUT) -> dict[str, Any]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "args": args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
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
        return {
            "args": args,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
        }


def command_text(command: dict[str, Any]) -> str:
    return " ".join(str(part) for part in command.get("args") or [])


def parse_int(pattern: str, text: str, *, default: int = 0) -> int:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return default
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return default


def parse_consolidation(command: dict[str, Any]) -> dict[str, Any]:
    stdout = str(command.get("stdout") or "")
    collisions: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        match = re.search(r"'([^']+)':\s*(.+)$", line)
        if not match:
            continue
        repos = [part.strip() for part in match.group(2).split(",") if part.strip()]
        collisions.append({"name": match.group(1), "repos": repos})
    collision_groups = parse_int(r"name collisions.*:\s*(\d+)", stdout)
    return {
        "command": {
            "args": command.get("args") or [],
            "returncode": command.get("returncode"),
            "timed_out": bool(command.get("timed_out")),
        },
        "source_repos": parse_int(r"\b(\d+)\s+repos across\s+\d+\s+owners", stdout),
        "source_owners": parse_int(r"\d+\s+repos across\s+(\d+)\s+owners", stdout),
        "collision_groups": collision_groups,
        "collision_examples": collisions[:25],
        "apply_gate_open": command.get("returncode") == 0 and collision_groups == 0,
        "dry_run_output_present": "DRY-RUN" in stdout,
    }


def parse_owner_rewrite(command: dict[str, Any]) -> dict[str, Any]:
    stdout = str(command.get("stdout") or "")
    return {
        "command": {
            "args": command.get("args") or [],
            "returncode": command.get("returncode"),
            "timed_out": bool(command.get("timed_out")),
        },
        "task_repo_refs_to_rewrite": parse_int(r"tasks\.yaml repo: refs to rewrite =\s*(\d+)", stdout),
        "deploy_literal_to_fix": "1 to fix" in stdout,
        "local_remotes_to_rewrite": parse_int(r"origin on an OLD owner =\s*(\d+)", stdout),
        "post_transfer_only": True,
        "dry_run_output_present": "DRY-RUN" in stdout,
    }


def parse_app_identity(which_command: dict[str, Any], installations_command: dict[str, Any]) -> dict[str, Any]:
    which = str(which_command.get("stdout") or "").strip()
    slugs = [
        line.strip()
        for line in str(installations_command.get("stdout") or "").splitlines()
        if line.strip()
    ]
    limen_slugs = {"limen-bot", "limen-conductor", "limen"}
    return {
        "gh_app_token_which": which or "unavailable",
        "app_token_wired": which.startswith("app "),
        "installations_command": {
            "args": installations_command.get("args") or [],
            "returncode": installations_command.get("returncode"),
            "timed_out": bool(installations_command.get("timed_out")),
        },
        "installed_app_slugs": slugs,
        "limen_app_installed": any(slug in limen_slugs for slug in slugs),
    }


def parse_collision_packet(path: Path | None = None) -> dict[str, Any]:
    path = path or COLLISION_RENAMES
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"path": str(path), "present": False, "keepers": {}, "rename_commands": []}

    keepers: dict[str, str] = {}
    rename_commands: list[dict[str, str]] = []
    for line in text.splitlines():
        keeper = re.match(r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", line)
        if keeper:
            keepers[keeper.group(1)] = keeper.group(2)
            continue
        rename = re.search(r"\bgh\s+repo\s+rename\s+(\S+)\s+--repo\s+(\S+)", line)
        if rename:
            source_repo = rename.group(2)
            owner = source_repo.split("/", 1)[0] if "/" in source_repo else ""
            rename_commands.append(
                {
                    "source_repo": source_repo,
                    "target_name": rename.group(1),
                    "target_repo": f"{owner}/{rename.group(1)}" if owner else rename.group(1),
                }
            )
    return {
        "path": str(path),
        "present": True,
        "keepers": keepers,
        "rename_commands": rename_commands,
    }


def target_is_free(command: dict[str, Any]) -> bool | None:
    if command.get("returncode") == 0:
        return False
    text = f"{command.get('stdout') or ''}\n{command.get('stderr') or ''}".lower()
    if "could not resolve to a repository" in text or "not found" in text:
        return True
    return None


def validate_collision_packet(
    consolidation: dict[str, Any],
    packet: dict[str, Any],
) -> dict[str, Any]:
    collisions = [item for item in consolidation.get("collision_examples") or [] if isinstance(item, dict)]
    keepers = packet.get("keepers") or {}
    commands = packet.get("rename_commands") or []
    collision_count = int(consolidation.get("collision_groups") or 0)
    if collision_count == 0 and not collisions:
        return {
            "path": packet.get("path"),
            "present": bool(packet.get("present")),
            "live_collision_groups": 0,
            "live_collision_groups_parsed": 0,
            "keeper_rows": len(keepers),
            "rename_commands": len(commands),
            "required_rename_commands": 0,
            "missing_keepers": [],
            "invalid_keepers": [],
            "missing_rename_commands": [],
            "extra_rename_commands": [],
            "target_checks": [],
            "target_conflicts": [],
            "target_unknown": [],
            "complete": True,
        }
    command_by_repo = {str(command.get("source_repo")): command for command in commands if command.get("source_repo")}
    missing_keepers: list[str] = []
    invalid_keepers: list[dict[str, Any]] = []
    missing_rename_commands: list[dict[str, str]] = []
    required_source_repos: set[str] = set()

    for collision in collisions:
        name = str(collision.get("name") or "")
        repos = [str(repo) for repo in collision.get("repos") or []]
        keeper = keepers.get(name)
        if not keeper:
            missing_keepers.append(name)
            continue
        if keeper not in repos:
            invalid_keepers.append({"collision": name, "keeper": keeper, "live_repos": repos})
        for repo in repos:
            if repo == keeper:
                continue
            required_source_repos.add(repo)
            if repo not in command_by_repo:
                missing_rename_commands.append({"collision": name, "source_repo": repo})

    extra_rename_commands = [
        command
        for command in commands
        if command.get("source_repo") and command.get("source_repo") not in required_source_repos
    ]
    target_checks = []
    for command in commands:
        target_repo = str(command.get("target_repo") or "")
        if not target_repo:
            continue
        probe = run_command(["gh", "repo", "view", target_repo, "--json", "nameWithOwner"], timeout=30)
        target_checks.append(
            {
                "source_repo": command.get("source_repo"),
                "target_repo": target_repo,
                "returncode": probe.get("returncode"),
                "timed_out": bool(probe.get("timed_out")),
                "free": target_is_free(probe),
            }
        )

    target_conflicts = [item for item in target_checks if item.get("free") is False]
    target_unknown = [item for item in target_checks if item.get("free") is None]
    complete = (
        packet.get("present")
        and not missing_keepers
        and not invalid_keepers
        and not missing_rename_commands
        and not extra_rename_commands
        and not target_conflicts
        and not target_unknown
        and len(collisions) == int(consolidation.get("collision_groups") or 0)
    )
    return {
        "path": packet.get("path"),
        "present": bool(packet.get("present")),
        "live_collision_groups": int(consolidation.get("collision_groups") or 0),
        "live_collision_groups_parsed": len(collisions),
        "keeper_rows": len(keepers),
        "rename_commands": len(commands),
        "required_rename_commands": len(required_source_repos),
        "missing_keepers": missing_keepers,
        "invalid_keepers": invalid_keepers,
        "missing_rename_commands": missing_rename_commands,
        "extra_rename_commands": extra_rename_commands,
        "target_checks": target_checks,
        "target_conflicts": target_conflicts,
        "target_unknown": target_unknown,
        "complete": bool(complete),
    }


def build_snapshot() -> dict[str, Any]:
    py_env = {"PYTHONPATH": str(ROOT / "cli" / "src")}
    consolidation_command = run_command([sys.executable, "scripts/consolidate-github.py"], env=py_env)
    rewrite_command = run_command([sys.executable, "scripts/rewrite-owners.py"], env=py_env)
    app_which_command = run_command(["bash", "scripts/gh-app-token.sh", "--which"])
    installations_command = run_command(
        ["gh", "api", "/orgs/organvm/installations", "--jq", ".installations[] | .app_slug"],
        timeout=60,
    )

    consolidation = parse_consolidation(consolidation_command)
    owner_rewrite = parse_owner_rewrite(rewrite_command)
    app_identity = parse_app_identity(app_which_command, installations_command)
    collision_packet = validate_collision_packet(consolidation, parse_collision_packet())

    blocking_gates = []
    if consolidation["command"]["returncode"] != 0 or not consolidation["dry_run_output_present"]:
        blocking_gates.append("consolidation-dry-run-unavailable")
    if consolidation["collision_groups"] > 0:
        blocking_gates.append("name-collisions")
    if not collision_packet["complete"]:
        blocking_gates.append("collision-packet-incomplete")
    if not app_identity["app_token_wired"]:
        blocking_gates.append("limen-bot-token-not-wired")
    if not app_identity["limen_app_installed"]:
        blocking_gates.append("limen-bot-app-not-installed")
    if owner_rewrite["task_repo_refs_to_rewrite"] or owner_rewrite["local_remotes_to_rewrite"]:
        blocking_gates.append("post-transfer-owner-rewrite-pending")

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "consolidate_github": command_text(consolidation_command),
            "rewrite_owners": command_text(rewrite_command),
            "gh_app_token_which": command_text(app_which_command),
            "org_installations": command_text(installations_command),
        },
        "consolidation": consolidation,
        "collision_packet": collision_packet,
        "owner_rewrite": owner_rewrite,
        "app_identity": app_identity,
        "gates": {
            "blocking": blocking_gates,
            "human_approval_required": True,
            "can_run_transfer_apply_after_human_gate": consolidation["apply_gate_open"],
            "can_run_owner_rewrite_after_transfer": owner_rewrite["post_transfer_only"]
            and consolidation["apply_gate_open"],
        },
        "receipts": {
            "runbook": str(RUNBOOK),
            "collision_renames": str(COLLISION_RENAMES),
            "scope_and_app": str(SCOPE_AND_APP),
            "private_index": str(PRIVATE_INDEX),
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    consolidation = snapshot["consolidation"]
    rewrite = snapshot["owner_rewrite"]
    app = snapshot["app_identity"]
    packet = snapshot["collision_packet"]
    blocking = snapshot["gates"]["blocking"]
    collisions = consolidation.get("collision_examples") or []
    collision_lines = [
        f"- `{item.get('name')}`: {', '.join(f'`{repo}`' for repo in item.get('repos') or [])}"
        for item in collisions[:15]
    ]
    if not collision_lines:
        collision_lines = ["- none"]
    installed = ", ".join(f"`{slug}`" for slug in app.get("installed_app_slugs") or []) or "none"
    blocking_text = ", ".join(f"`{gate}`" for gate in blocking) or "none"
    collision_gate_step = (
        "1. Collision names are resolved; keep `docs/consolidation/COLLISION-RENAMES.md` as the historical rename receipt."
        if int(consolidation.get("collision_groups") or 0) == 0
        else "1. Resolve collision names from `docs/consolidation/COLLISION-RENAMES.md`."
    )
    lines = [
        "# GitHub Consolidation Gates",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Rule",
        "",
        "- This is a read-only gate receipt for the conductor selector.",
        "- Do not run repo rename, repo transfer, owner rewrite `--apply`, App install, or credential writes from this receipt alone.",
        "- Human approval is still required for any irreversible GitHub/org/App/credential action.",
        "",
        "## Current Gate State",
        "",
        "| Gate | Value |",
        "|---|---|",
        f"| Source repos outside `organvm` | `{consolidation.get('source_repos', 0)}` |",
        f"| Source owners scanned | `{consolidation.get('source_owners', 0)}` |",
        f"| Name collision groups | `{consolidation.get('collision_groups', 0)}` |",
        f"| Collision packet complete | `{packet.get('complete')}` |",
        f"| Collision packet keeper rows | `{packet.get('keeper_rows', 0)}` |",
        f"| Collision packet rename commands | `{packet.get('rename_commands', 0)}` / required `{packet.get('required_rename_commands', 0)}` |",
        f"| Rename target conflicts/unknown | `{len(packet.get('target_conflicts') or [])}` / `{len(packet.get('target_unknown') or [])}` |",
        f"| Transfer apply gate open | `{consolidation.get('apply_gate_open')}` |",
        f"| `tasks.yaml` repo refs to rewrite post-transfer | `{rewrite.get('task_repo_refs_to_rewrite', 0)}` |",
        f"| Local remotes to rewrite post-transfer | `{rewrite.get('local_remotes_to_rewrite', 0)}` |",
        f"| Deploy literal to fix post-transfer | `{rewrite.get('deploy_literal_to_fix')}` |",
        f"| `gh-app-token --which` | `{app.get('gh_app_token_which')}` |",
        f"| `limen[bot]` App installed | `{app.get('limen_app_installed')}` |",
        f"| App token wired | `{app.get('app_token_wired')}` |",
        f"| Installed org Apps | {installed} |",
        f"| Blocking gates | {blocking_text} |",
        "",
        "## Collision Examples",
        "",
        *collision_lines,
        "",
        "## Collision Packet Check",
        "",
        f"- Packet path: `{relpath(Path(packet.get('path') or COLLISION_RENAMES))}`.",
        f"- Live collision groups parsed: `{packet.get('live_collision_groups_parsed', 0)}` / `{packet.get('live_collision_groups', 0)}`.",
        f"- Missing keeper rows: `{len(packet.get('missing_keepers') or [])}`.",
        f"- Invalid keeper rows: `{len(packet.get('invalid_keepers') or [])}`.",
        f"- Missing rename commands: `{len(packet.get('missing_rename_commands') or [])}`.",
        f"- Extra rename commands: `{len(packet.get('extra_rename_commands') or [])}`.",
        f"- Rename target conflicts: `{len(packet.get('target_conflicts') or [])}`.",
        f"- Rename target probes unknown: `{len(packet.get('target_unknown') or [])}`.",
        "",
        "## Exact Gates",
        "",
        collision_gate_step,
        "2. Re-run `PYTHONPATH=cli/src python3 scripts/consolidate-github.py` and require `name collisions (must rename before transfer): 0`.",
        "3. Only after the human transfer gate, run `PYTHONPATH=cli/src python3 scripts/consolidate-github.py --apply`.",
        "4. Only after transfer, run `PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply --emit-remotes /tmp/limen-remotes.sh`.",
        "5. Wire `limen[bot]` only after the GitHub App exists, is installed on `organvm`, and `GITHUB_APP_ID`/`GITHUB_APP_PRIVATE_KEY` are hydrated.",
        "6. Require `bash scripts/gh-app-token.sh --which` to report `app (limen[bot] installation token)` before calling the App path wired.",
        "",
        "## Probe Commands",
        "",
        f"- Consolidation dry-run: `{snapshot['inputs']['consolidate_github']}`",
        f"- Owner rewrite dry-run: `{snapshot['inputs']['rewrite_owners']}`",
        f"- App token path probe: `{snapshot['inputs']['gh_app_token_which']}`",
        f"- Org App installation probe: `{snapshot['inputs']['org_installations']}`",
        "",
        "## Private Output",
        "",
        f"- Private gate index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps parsed counts and command metadata only; no secret values are read or stored.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh read-only GitHub consolidation gates.")
    parser.add_argument("--write", action="store_true", help="write tracked and private gate receipts")
    args = parser.parse_args()

    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "consolidation-gates: "
        f"{snapshot['consolidation']['source_repos']} source repos; "
        f"{snapshot['consolidation']['collision_groups']} collision groups; "
        f"blocking {len(snapshot['gates']['blocking'])}"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
