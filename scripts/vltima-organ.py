#!/usr/bin/env python3
"""VLTIMA organ: membrane, metabolism, owner certainty, and packets.

This script is the safe control-plane wrapper. It can run the existing cadence
when explicitly asked, but its default write path refreshes only VLTIMA-owned
doctrine, packet, and state surfaces. It never mutates tasks.yaml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
).expanduser()
STATE_PATH = ROOT / "logs" / "vltima-organ-state.json"
IDEAL_DOC = ROOT / "docs" / "VLTIMA-IDEAL-FORM.md"

PUBLIC_PRIVATE_SURFACES = (
    (
        ROOT / "docs" / "vltima-absorb-cadence.md",
        PRIVATE_ROOT / "lifecycle" / "vltima-absorb-cadence.json",
        "absorption cadence",
    ),
    (
        ROOT / "docs" / "vltima-prior-excavations.md",
        PRIVATE_ROOT / "lifecycle" / "vltima-prior-excavations.json",
        "prior excavations",
    ),
    (
        ROOT / "docs" / "vltima-result-digest.md",
        PRIVATE_ROOT / "lifecycle" / "vltima-result-digest.json",
        "result digest",
    ),
    (
        ROOT / "docs" / "vltima-owner-certainty.md",
        PRIVATE_ROOT / "lifecycle" / "vltima-owner-certainty.json",
        "owner certainty",
    ),
    (
        ROOT / "docs" / "vltima-action-packets.md",
        PRIVATE_ROOT / "lifecycle" / "vltima-action-packets.json",
        "action packets",
    ),
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _load_script(name: str, filename: str):
    script = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_command(command: list[str], *, timeout: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
        return {
            "command": " ".join(command),
            "returncode": proc.returncode,
            "status": "ok" if proc.returncode == 0 else "failed",
            "stdout_tail": [line for line in proc.stdout.splitlines() if line.strip()][-8:],
            "stderr_tail": [line for line in proc.stderr.splitlines() if line.strip()][-8:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "returncode": None,
            "status": "timeout",
            "stdout_tail": [line for line in (exc.stdout or "").splitlines() if line.strip()][-8:],
            "stderr_tail": [line for line in (exc.stderr or "").splitlines() if line.strip()][-8:],
        }


def generated_marker(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:12]:
            if line.startswith("Generated:"):
                return line
    except FileNotFoundError:
        pass
    return ""


def surface_checks() -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for public, private, label in PUBLIC_PRIVATE_SURFACES:
        if private.exists() and not public.exists():
            issues.append(
                {
                    "surface": label,
                    "severity": "error",
                    "reason": f"private index exists but public doctrine is missing: {public.relative_to(ROOT)}",
                }
            )
        if public.exists() and "/Users/" in public.read_text(encoding="utf-8", errors="ignore"):
            issues.append(
                {
                    "surface": label,
                    "severity": "error",
                    "reason": f"public doctrine leaks an absolute user path: {public.relative_to(ROOT)}",
                }
            )
    prior = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-prior-excavations.json", default={}) or {}
    digest = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-result-digest.json", default={}) or {}
    owner = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-owner-certainty.json", default={}) or {}
    if prior.get("mismatches"):
        issues.append({"surface": "prior excavations", "severity": "error", "reason": "prior mismatches are not empty"})
    if digest.get("mismatch_surfaces"):
        issues.append({"surface": "result digest", "severity": "error", "reason": "digest mismatch surfaces are not empty"})
    if owner.get("coverage", {}).get("unowned_dispatchable_count", 0):
        issues.append({"surface": "owner certainty", "severity": "error", "reason": "unowned dispatchable claims exist"})
    return issues


def build_state(
    *,
    include_github_meta: bool,
    cadence_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-prior-excavations.json", default={}) or {}
    digest = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-result-digest.json", default={}) or {}
    owner = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-owner-certainty.json", default={}) or {}
    packets = load_json(PRIVATE_ROOT / "lifecycle" / "vltima-action-packets.json", default={}) or {}
    issues = surface_checks()
    github_meta: dict[str, Any] = {"requested": include_github_meta, "mode": "not-requested"}
    if include_github_meta:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, text=True, capture_output=True)
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, text=True, capture_output=True)
        github_meta = {
            "requested": True,
            "mode": "metadata-only",
            "origin": remote.stdout.strip() if remote.returncode == 0 else "",
            "branch": branch.stdout.strip() if branch.returncode == 0 else "",
        }
    return {
        "generated_at": now_iso(),
        "status": "ok" if not issues else "failed",
        "decision": "VLTIMA derives action only from current, owner-certified, redacted evidence",
        "privacy": {
            "raw_bodies_read": False,
            "tasks_yaml_mutated": False,
            "remote_mode": github_meta["mode"],
        },
        "coverage": {
            "prior_generated_at": prior.get("generated_at"),
            "digest_generated_at": digest.get("generated_at"),
            "owner_generated_at": owner.get("generated_at"),
            "packet_generated_at": packets.get("generated_at"),
            "prior_surface_count": prior.get("coverage", {}).get("surface_count", 0),
            "digest_claim_count": digest.get("coverage", {}).get("claim_count", 0),
            "packet_count": packets.get("coverage", {}).get("packet_count", 0),
            "issues": len(issues),
        },
        "github_meta": github_meta,
        "issues": issues,
        "cadence_result": cadence_result,
        "public_surfaces": [
            {
                "label": label,
                "public": str(public.relative_to(ROOT)),
                "public_exists": public.exists(),
                "private": str(private.relative_to(ROOT)) if private.is_relative_to(ROOT) else str(private),
                "private_exists": private.exists(),
                "generated": generated_marker(public),
            }
            for public, private, label in PUBLIC_PRIVATE_SURFACES
        ],
    }


def render_ideal_doc(state: dict[str, Any]) -> str:
    coverage = state["coverage"]
    lines = [
        "# VLTIMA Ideal Form",
        "",
        f"Generated: `{state['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- VLTIMA is the control layer that turns raw movement into owner-certified action.",
        "- The membrane is explicit: raw/private material stays private; public doctrine is redacted.",
        "- Old material can become lineage or ore, but only current evidence can become doctrine.",
        "- Doctrine becomes work only through bounded packets with owner, scope, receipt, and verification.",
        "",
        "## Current Distance",
        "",
        f"- Prior surfaces: `{coverage['prior_surface_count']}`.",
        f"- Result claims: `{coverage['digest_claim_count']}`.",
        f"- Candidate packets: `{coverage['packet_count']}`.",
        f"- Open VLTIMA check issues: `{coverage['issues']}`.",
        "",
        "## Autopoietic Loop",
        "",
        "1. Capture local and app movement as redacted evidence.",
        "2. Register prior excavations before adding scanners.",
        "3. Digest results into temporal authority classes.",
        "4. Derive owner certainty before action.",
        "5. Packetize only owner-certified current doctrine.",
        "6. Verify receipts and feed the next loop.",
        "",
        "## Non-Negotiables",
        "",
        "- No `tasks.yaml` mutation in v1.",
        "- No raw prompt bodies in tracked docs.",
        "- No private materialization without `--materialize-private`.",
        "- No dispatch without a future explicit enqueue gate.",
    ]
    return "\n".join(lines) + "\n"


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    IDEAL_DOC.parent.mkdir(parents=True, exist_ok=True)
    IDEAL_DOC.write_text(render_ideal_doc(state), encoding="utf-8")


def refresh_owner_and_packets(*, limit: int) -> tuple[dict[str, Any], dict[str, Any]]:
    owner_mod = _load_script("vltima_owner_certainty_organ", "vltima-owner-certainty.py")
    packet_mod = _load_script("vltima_packetize_organ", "vltima-packetize.py")
    certainty = owner_mod.build_certainty()
    owner_mod.write_outputs(certainty, owner_mod.render_markdown(certainty))
    packets = packet_mod.build_packets(certainty, limit=limit)
    packet_mod.write_outputs(packets, packet_mod.render_markdown(packets))
    return certainty, packets


def print_status(state: dict[str, Any]) -> None:
    coverage = state["coverage"]
    print(
        "vltima-organ: "
        f"{state['status']}; issues={coverage['issues']} "
        f"claims={coverage['digest_claim_count']} packets={coverage['packet_count']}"
    )
    for issue in state["issues"][:8]:
        print(f"  {issue['severity']}: {issue['surface']}: {issue['reason']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run, check, or report the VLTIMA organ.")
    parser.add_argument("--plan", action="store_true", help="print the non-mutating organ plan")
    parser.add_argument("--write", action="store_true", help="write VLTIMA owner/packet/state surfaces")
    parser.add_argument("--check", action="store_true", help="read-only predicate over current VLTIMA surfaces")
    parser.add_argument("--status", action="store_true", help="print current VLTIMA status")
    parser.add_argument("--json", action="store_true", help="print state JSON")
    parser.add_argument("--run-cadence", action="store_true", help="run vltima-absorb-cadence.py --write first")
    parser.add_argument("--materialize-private", action="store_true", help="pass --materialize-private to cadence")
    parser.add_argument("--include-github-meta", action="store_true", help="include local GitHub metadata only")
    parser.add_argument("--packet-limit", type=int, default=40, help="maximum packet candidates")
    parser.add_argument("--timeout", type=int, default=900, help="timeout for optional cadence run")
    args = parser.parse_args()

    if args.plan:
        print(
            "vltima-organ plan:\n"
            "1. optional cadence refresh (--run-cadence)\n"
            "2. owner certainty from vltima-result-digest.json\n"
            "3. action packet candidates from owned current doctrine\n"
            "4. state + ideal-form docs\n"
            "5. read-only check; no tasks.yaml mutation"
        )
        return 0

    cadence_result = None
    if args.run_cadence:
        command = ["python3", "scripts/vltima-absorb-cadence.py", "--write"]
        if args.materialize_private:
            command.append("--materialize-private")
        cadence_result = run_command(command, timeout=args.timeout)
        if cadence_result["status"] != "ok":
            state = build_state(include_github_meta=args.include_github_meta, cadence_result=cadence_result)
            state["status"] = "failed"
            state["issues"].append({"surface": "absorption cadence", "severity": "error", "reason": "cadence refresh failed"})
            if args.write:
                write_state(state)
            if args.json:
                print(json.dumps(state, indent=2, sort_keys=True))
            else:
                print_status(state)
            return 1

    refresh_error = ""
    if args.write:
        try:
            refresh_owner_and_packets(limit=args.packet_limit)
        except FileNotFoundError as exc:
            refresh_error = f"owner/packet refresh failed: {exc}"
        state = build_state(include_github_meta=args.include_github_meta, cadence_result=cadence_result)
        if refresh_error:
            state["status"] = "failed"
            state["issues"].append({"surface": "owner certainty", "severity": "error", "reason": refresh_error})
            state["coverage"]["issues"] = len(state["issues"])
        write_state(state)
    else:
        state = build_state(include_github_meta=args.include_github_meta, cadence_result=cadence_result)

    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        print_status(state)
    return 0 if state["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
