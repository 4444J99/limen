#!/usr/bin/env python3
"""Render/check PSP launch inputs from their existing snapshot and one shared contract.

This only prepares local documentation. It never grants authority, dispatches work,
publishes a surface, starts a monitor, or validates completion receipts. The dated
snapshot remains planning evidence; every rendered input requires live refresh.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path("docs/positioning/program/recalibration")
CONTRACT = DIRECTORY / "launch-contract.json"
SNAPSHOT = DIRECTORY / "2026-09-08-snapshot.json"
OUTPUT = DIRECTORY / "2026-09-08-launch-prompts.md"
PLAN = Path(".codex/plans/2026-09-08-psp-alpha-omega-recalibration.md")
PROGRAM = Path("institutio/positioning/program.yaml")
ISSUE_MAP = Path("institutio/positioning/github-map.json")
SHARED_KEYS = ("inputs", "freshness", "authority", "isolation", "provider", "verification", "evidence")
CONTRACT_KEYS = {
    "schema_version", "authority_sources", "shared", "r00_scope", "r00_admission",
    "r00_instructions", "package_admission", "reuse", "package_overrides",
    "execution", "closeout", "resume", "relay",
}


class ContractError(ValueError):
    """The source or rendered handoff lost a required contract boundary."""


def exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError(f"{label}: required fields differ")


def prose(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or "```" in value or "\n" in value:
        raise ContractError(f"{label}: expected one nonempty plain-text paragraph")


def require(text: str, fragments: tuple[str, ...], label: str) -> None:
    """Protect the ratified boundaries even when both source and output are edited."""
    if any(fragment not in text for fragment in fragments):
        raise ContractError(f"{label}: protected boundary missing")


def validate(contract: dict, snapshot: dict, program: dict, issue_map: dict) -> None:
    exact_keys(contract, CONTRACT_KEYS, "launch contract")
    if contract["schema_version"] != "psp.launch_contract.v1":
        raise ContractError("unsupported launch contract schema")
    if contract["authority_sources"] != ["AGENTS.md", str(PLAN), str(PROGRAM)]:
        raise ContractError("canonical authority sources differ")
    exact_keys(contract["shared"], set(SHARED_KEYS), "shared contract")
    for key in SHARED_KEYS:
        prose(contract["shared"][key], f"shared.{key}")
    for key in CONTRACT_KEYS - {"authority_sources", "shared", "package_overrides"}:
        prose(contract[key], key)
    shared = contract["shared"]
    require(shared["inputs"], ("current AGENTS.md", "current repository version", str(SNAPSHOT)), "inputs")
    require(shared["freshness"], ("dated planning evidence, not dispatch authority", "re-query current ownership", "admission and exact acceptance", "before mutation"), "freshness")
    require(shared["authority"], ("autonomous dispatch requires its own broker reservation", "These prompts grant no publication, send, spend, account-action or monitoring authority.", "No fake leases, hidden fanout, task-projection edits or human-atom closures."), "authority")
    require(shared["verification"], ("preserve their scope-bound evidence", "Do not rerun all research, all tests, all receipts or the full estate census"), "verification")
    require(shared["provider"], ("live capabilities and budget", "identity and authority do not transfer", "cheapest adequate currently available model"), "provider")
    require(shared["evidence"], ("artifact link", "exact tested/accepted heads", "real exit evidence", "actual authority source"), "evidence")
    require(contract["execution"], ("One exact-tree scoped verification batch", "merge rail only when authorized", "No synchronous CI/review waits or unchanged green reruns"), "execution")
    require(contract["resume"], ("complete current launch block", "package-specific authority and observation boundaries", "remaining run ceiling"), "resume")
    exact_keys(contract["package_overrides"], {"R05", "R10"}, "package boundaries")
    for package, boundary in contract["package_overrides"].items():
        exact_keys(boundary, {"boundary_label", "boundary", "exit"}, package)
        for key, value in boundary.items():
            prose(value, f"{package}.{key}")
    r05 = contract["package_overrides"]["R05"]
    require(r05["boundary"], ("Preparation-only unless separate recorded owner authority", "exact deployment target and release", "rollback plan is recorded", "identity/domain/account gates", "grants no publication authority"), "R05 deployment")
    require(r05["exit"], ("actual live deployed/browser/link/capture receipts", "after authorized deployment", "missing or failed receipts leave acceptance outstanding", "rollback verification"), "R05 acceptance")
    r10 = contract["package_overrides"]["R10"]
    require(r10["boundary"], ("Preparation, templates and controlled-fixture tests may finish now", "owning inputs and protocol are ready", "Four consecutive weekly reviews", "two consecutive monthly audits", "actual strategy review", "respective elapsed observation periods", "preparation or synthetic data cannot satisfy them", "Do not start autonomous monitoring without separate recorded user scheduling authority"), "R10 observation")
    require(r10["exit"], ("declared prerequisite leaves", "source evidence", "pending periods explicitly outstanding"), "R10 acceptance")

    if snapshot.get("status") != "planning_snapshot_not_dispatch_authority":
        raise ContractError("snapshot must remain planning evidence")
    packets, leaves = snapshot.get("packets", []), snapshot.get("leaves", [])
    if [row.get("id") for row in packets] != [f"R{i:02}" for i in range(12)]:
        raise ContractError("package identities/order differ")
    canonical = {leaf["id"] for phase in program["phases"] for leaf in phase["work"]}
    ids = [row["id"] for row in leaves]
    if len(ids) != len(set(ids)) or set(ids) != canonical:
        raise ContractError("snapshot must preserve each canonical leaf exactly once")
    for leaf in leaves:
        if leaf["issue"] != issue_map["issues"][leaf["id"]]["number"]:
            raise ContractError(f"issue identity differs: {leaf['id']}")
        if leaf.get("packet") not in {"BASELINE", *(row["id"] for row in packets)}:
            raise ContractError("leaf has unknown package")
    for packet in packets:
        assigned = [row["id"] for row in leaves if row.get("packet") == packet["id"]]
        if packet["leaf_ids"] != assigned:
            raise ContractError(f"leaf scope differs: {packet['id']}")
        if packet["effort"] not in {"low", "medium", "high"}:
            raise ContractError("unknown effort")
        if type(packet["per_run_timebox_minutes"]) is not int or not 0 < packet["per_run_timebox_minutes"] <= 45:
            raise ContractError("invalid bounded run ceiling")
        if packet["maximum_corrective_batches"] != 1:
            raise ContractError("corrective allowance differs")
        for key in ("title", "profile", "deliverable", "exit"):
            prose(packet[key], f"{packet['id']}.{key}")


def render(contract: dict, snapshot: dict, program: dict, issue_map: dict) -> str:
    validate(contract, snapshot, program, issue_map)
    shared = "\n".join(contract["shared"][key] for key in SHARED_KEYS)
    lines = [
        "# Bounded cross-agent launch prompts", "",
        "<!-- Generated by scripts/positioning-launch-prompts.py; edit launch-contract.json and the named snapshot inputs, then run --write. -->", "",
        "Use the next eligible block, not the entire conversation. Start with R00. Each copied block carries its shared contract; no surrounding preamble is needed. A run ceiling is not a promise to finish a package.", "",
        "Source: [launch contract](launch-contract.json) and [dated planning snapshot](2026-09-08-snapshot.json). The current AGENTS.md and canonical program remain authoritative. Regenerate with `python3 scripts/positioning-launch-prompts.py --write`; check with `--check`.", "",
    ]
    for packet in snapshot["packets"]:
        package = packet["id"]
        limits = f"Profile: {packet['profile']}. Effort: {packet['effort']}. Actual model: live capability selection / provider Auto. Run-slice ceiling: {packet['per_run_timebox_minutes']} minutes; at most one evidence-driven corrective batch; no child fanout."
        scope = contract["r00_scope"] if package == "R00" else ", ".join(
            f"{leaf} (#{issue_map['issues'][leaf]['number']})" for leaf in packet["leaf_ids"]
        ) + "."
        lines.extend([f"## {package} — {packet['title']}", "", "Copy this block as the task input:", "", "```text",
                      f"Continue PSP package {package} from {PLAN}.", shared, limits,
                      contract["r00_admission"] if package == "R00" else contract["package_admission"],
                      f"Scope: {scope}", f"Deliverable: {packet['deliverable']}"])
        override = contract["package_overrides"].get(package)
        if override:
            lines.append(f"{override['boundary_label']}: {override['boundary']}")
        lines.extend([f"Exit: {override['exit'] if override else packet['exit']}",
                      contract["r00_instructions"] if package == "R00" else contract["reuse"],
                      contract["execution"], contract["closeout"], "```", ""])
    lines.extend(["## Resume after usage or provider change", "", "```text", contract["resume"],
                  f"Recalibration plan: {PLAN}.", shared, contract["execution"], "```", "",
                  "## Minimal end-of-run relay", "", contract["relay"], ""])
    return "\n".join(lines)


def expected(root: Path) -> str:
    contract = json.loads((root / CONTRACT).read_text())
    for source in ("AGENTS.md", PLAN, PROGRAM):
        if not (root / source).is_file():
            raise ContractError(f"missing authority source: {source}")
    return render(contract, json.loads((root / SNAPSHOT).read_text()),
                  yaml.safe_load((root / PROGRAM).read_text()), json.loads((root / ISSUE_MAP).read_text()))


def check(root: Path) -> None:
    rendered = expected(root)
    path = root / OUTPUT
    if not path.is_file() or path.read_text() != rendered:
        raise ContractError("launch prompts drifted; run python3 scripts/positioning-launch-prompts.py --write")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check generated parity without writing (default)")
    mode.add_argument("--write", action="store_true", help="regenerate only the local launch Markdown")
    args = parser.parse_args(argv)
    try:
        if args.write:
            (ROOT / OUTPUT).write_text(expected(ROOT))
        else:
            check(ROOT)
    except (ContractError, KeyError, TypeError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: 12 package inputs and resume preserve canonical identity, authority and freshness boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
