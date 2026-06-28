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

    blocking_gates = []
    if consolidation["command"]["returncode"] != 0 or not consolidation["dry_run_output_present"]:
        blocking_gates.append("consolidation-dry-run-unavailable")
    if consolidation["collision_groups"] > 0:
        blocking_gates.append("name-collisions")
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
        "## Exact Gates",
        "",
        "1. Resolve collision names from `docs/consolidation/COLLISION-RENAMES.md`.",
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
