#!/usr/bin/env python3
"""GATES drift predicate — holds institutio/governance/gates.yaml to the repo.

The registry declares every verification gate (command, implicating paths, cost tier,
serialization) plus the deploy-trigger mirror and the derived file sets. This predicate
proves the declaration and the repo have not drifted apart. Exit 0 ⟺ no drift.

Named checks (mirrors scripts/check-params.py's ratchet discipline):
  A  schema validity — required fields, tier enum, command/kind exclusivity, noted excludes
  B  command existence — every repo path a gate command references exists
  C  deploy-trigger parity — registry paths == deploy*.yml `on.push.paths`, exactly;
     every deploy-prefixed workflow is registered
  D  ci_job references resolve — the workflow file exists and contains the job id
  E  CI filter coverage — a change implicating a gate must trigger its mirrored CI job
  F  consumers derive (ratchet-armed) — verify-scoped/merge-policy/verify-whole carry no
     literal copies once their `ratchets:` flag is true
  G  CLAUDE.md parity (ratchet-armed as claude_md_pointer) — until armed, every registered
     deploy-trigger path literal still appears in the charter; once armed, the charter
     carries the registry pointer instead of path lists
  H  file_sets sanity — every include matches ≥1 tracked file; excludes exist and are noted

Run directly (``scripts/check-gates.py``) or via pr-gate / verify-whole.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "gates.yaml"
WORKFLOWS = ROOT / ".github" / "workflows"

VALID_TIERS = {"cheap", "heavy"}
VALID_KINDS = {"per_file", "file_set"}
RATCHET_KEYS = {
    "verify_scoped_wrapper",
    "merge_policy_derives",
    "verify_whole_derives",
    "claude_md_pointer",
}
# Repo-path prefixes that must exist when they appear as command tokens.
_PATH_TOKEN = re.compile(r"^(scripts|organs|web|cli|mcp|ianva|container|spec|moneta)/|^\.github/")

failures: list[str] = []


def fail(check: str, message: str) -> None:
    failures.append(f"  ✗ [{check}] {message}")


def glob_to_regex(glob: str) -> re.Pattern[str]:
    """GitHub Actions path-filter semantics: `**` crosses slashes, `*` does not."""
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def sample_path(glob: str) -> str:
    """A concrete path that the glob matches — used to test coverage by other globs."""
    return glob.replace("**", "x/x").replace("*", "x")


def workflow_doc(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text())
    # YAML 1.1 parses a bare `on:` key as boolean True.
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    return doc


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text())
    gates: dict = registry.get("gates") or {}
    ratchets: dict = registry.get("ratchets") or {}
    triggers: dict = registry.get("deploy_triggers") or {}
    file_sets: dict = registry.get("file_sets") or {}
    tracked = tracked_files()

    # --- A: schema validity -------------------------------------------------
    if set(ratchets) - RATCHET_KEYS or not all(isinstance(v, bool) for v in ratchets.values()):
        fail("A", f"ratchets must be booleans among {sorted(RATCHET_KEYS)}")
    for gate_id, gate in gates.items():
        kind = gate.get("kind")
        has_command = "command" in gate
        if kind is None and not has_command:
            fail("A", f"{gate_id}: needs `command` or `kind`")
        if kind is not None and kind not in VALID_KINDS:
            fail("A", f"{gate_id}: unknown kind {kind!r}")
        if kind == "per_file" and not gate.get("per_file"):
            fail("A", f"{gate_id}: kind per_file requires `per_file` commands")
        if kind == "file_set":
            if gate.get("file_set") not in file_sets:
                fail("A", f"{gate_id}: file_set {gate.get('file_set')!r} not declared")
            if "{files}" not in gate.get("command_template", ""):
                fail("A", f"{gate_id}: kind file_set requires a `command_template` with {{files}}")
        if gate.get("tier", "cheap") not in VALID_TIERS:
            fail("A", f"{gate_id}: tier must be one of {sorted(VALID_TIERS)}")
        for field in ("owner", "note"):
            if not gate.get(field):
                fail("A", f"{gate_id}: `{field}` is required")
        paths = gate.get("paths")
        if kind == "file_set":
            if paths is not None:
                fail("A", f"{gate_id}: file_set gates derive their paths from the set — drop `paths`")
        elif not (isinstance(paths, list) and paths and all(isinstance(p, str) for p in paths)):
            fail("A", f"{gate_id}: `paths` must be a non-empty list of globs")

    # --- B: command path tokens exist ----------------------------------------
    for gate_id, gate in gates.items():
        command = gate.get("command") or gate.get("command_template") or ""
        for token in shlex.split(command):
            if _PATH_TOKEN.match(token) and not (ROOT / token).exists():
                fail("B", f"{gate_id}: command references missing path {token}")

    # --- C: deploy-trigger parity --------------------------------------------
    registered_workflows = set()
    for name, trigger in triggers.items():
        wf_path = ROOT / trigger["workflow"]
        registered_workflows.add(wf_path.name)
        if not wf_path.exists():
            fail("C", f"deploy_triggers.{name}: workflow {trigger['workflow']} missing")
            continue
        wf_paths = (workflow_doc(wf_path).get("on", {}).get("push") or {}).get("paths") or []
        if set(wf_paths) != set(trigger.get("paths") or []):
            fail(
                "C",
                f"deploy_triggers.{name}: registry paths {sorted(trigger.get('paths') or [])} "
                f"!= workflow on.push.paths {sorted(wf_paths)}",
            )
    for wf in sorted(WORKFLOWS.glob("deploy*.yml")):
        if wf.name not in registered_workflows:
            fail("C", f"{wf.name} is a deploy workflow but has no deploy_triggers entry")

    # --- D + E: ci_job resolves; CI filters cover the gate's paths ------------
    for gate_id, gate in gates.items():
        ci_job = gate.get("ci_job")
        if not ci_job:
            continue
        wf_name, _, job_id = ci_job.partition(":")
        wf_path = WORKFLOWS / wf_name
        if not wf_path.exists():
            fail("D", f"{gate_id}: ci_job workflow {wf_name} missing")
            continue
        doc = workflow_doc(wf_path)
        if job_id not in (doc.get("jobs") or {}):
            fail("D", f"{gate_id}: ci_job {ci_job} — no job {job_id!r} in {wf_name}")
            continue
        pr_filter = (doc.get("on", {}).get("pull_request") or {}).get("paths")
        if not pr_filter:
            continue  # unfiltered workflow runs on every PR — trivially covers
        filter_regexes = [glob_to_regex(g) for g in pr_filter]
        for path_glob in gate.get("paths") or []:
            sample = sample_path(path_glob)
            if not any(r.match(sample) for r in filter_regexes):
                fail(
                    "E",
                    f"{gate_id}: path {path_glob!r} would not trigger {ci_job} "
                    f"(uncovered by {wf_name} pull_request paths)",
                )

    # --- F: consumers actually derive (armed per ratchet) ---------------------
    if ratchets.get("verify_scoped_wrapper"):
        scoped = (ROOT / "scripts" / "verify-scoped.sh").read_text()
        if "verify.py" not in scoped or len(scoped.splitlines()) > 20:
            fail("F", "verify-scoped.sh must be a thin wrapper over scripts/verify.py --changed")
    if ratchets.get("merge_policy_derives"):
        policy = (ROOT / "scripts" / "merge-policy.sh").read_text()
        if "--deploy-regex" not in policy or re.search(r"^DASHBOARD_RE=", policy, re.M):
            fail("F", "merge-policy.sh must derive DEPLOY_RE via scripts/verify.py --deploy-regex")
    if ratchets.get("verify_whole_derives"):
        whole = (ROOT / "scripts" / "verify-whole.sh").read_text()
        if "--print-files" not in whole or "py_compile web/api/main.py" in whole:
            fail("F", "verify-whole.sh must derive its file lists via scripts/verify.py --print-files")

    # --- G: CLAUDE.md parity (pointer once claude_md_pointer arms) ------------
    charter = (ROOT / "CLAUDE.md").read_text()
    if ratchets.get("claude_md_pointer"):
        if "institutio/governance/gates.yaml" not in charter:
            fail("G", "CLAUDE.md must point at institutio/governance/gates.yaml")
    else:
        for trigger in triggers.values():
            for path_glob in trigger.get("paths") or []:
                if path_glob.rstrip("*/") not in charter:
                    fail("G", f"CLAUDE.md deploy-trigger prose is missing {path_glob!r}")

    # --- H: file_sets sanity ---------------------------------------------------
    for set_name, spec in file_sets.items():
        for pattern in spec.get("include") or []:
            regex = glob_to_regex(pattern)
            if not any(regex.match(f) for f in tracked):
                fail("H", f"file_sets.{set_name}: include {pattern!r} matches no tracked file")
        for entry in spec.get("exclude") or []:
            if isinstance(entry, str) or not entry.get("note"):
                fail("H", f"file_sets.{set_name}: exclude entries need a path AND a note")
            elif entry.get("path") not in tracked:
                fail("H", f"file_sets.{set_name}: exclude {entry.get('path')!r} is not tracked (dead exclude)")

    if failures:
        print(f"GATES DRIFT: {len(failures)} finding(s) — registry and repo disagree:")
        print("\n".join(failures))
        return 1
    armed = sorted(k for k, v in ratchets.items() if v)
    print(
        f"check-gates: OK — {len(gates)} gates, {len(triggers)} deploy triggers, "
        f"{len(file_sets)} file sets; ratchets armed: {armed or 'none'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
