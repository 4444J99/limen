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
  I  pytest hermetic — registered pytest commands ignore host Git config and editor surfaces

Run directly (``scripts/check-gates.py``) or via pr-gate / verify-whole.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml


def _load_verify():
    """The registry's own reader, loaded by path — one definition of what a trigger path IS.

    A second copy of the bare-glob-vs-{path,note} normalization here is exactly the shape
    _root.py was extracted to kill: one wrong answer surviving in two places. verify.py owns
    the registry semantics; this checker holds the registry to them.
    """
    spec = importlib.util.spec_from_file_location(
        "_limen_verify_for_gates", Path(__file__).resolve().parent / "verify.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trigger_globs = _load_verify().trigger_globs

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "gates.yaml"
WORKFLOWS = ROOT / ".github" / "workflows"
PYTEST_WRAPPER = "scripts/run-pytest-hermetic.sh"

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
_HERMETIC_PYTEST_ENV = {
    "GIT_CONFIG_GLOBAL=/dev/null",
    "GIT_CONFIG_SYSTEM=/dev/null",
    "XDG_CONFIG_HOME=/dev/null",
    "GIT_EDITOR=true",
    "GIT_SEQUENCE_EDITOR=true",
    "VISUAL=true",
    "EDITOR=true",
}

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
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def _gh_json(path: str) -> object | None:
    """One bounded, read-only GitHub API call. Every failure mode is None, not an exception:
    no gh, no auth, no network, rate limit, malformed body. Callers REPORT the absence — an
    unobservable fact must never read as a verified one."""
    try:
        out = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github+json", path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def _repo_slug() -> str | None:
    """owner/repo from origin, not from `gh repo view` — this repo has several remotes and
    gh refuses to guess between them."""
    out = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True, check=False)
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?\s*$", out.stdout.strip())
    return m.group(1) if out.returncode == 0 and m else None


def _latest_run_steps(workflow_file: str) -> list[tuple[str, str | None]] | None:
    """(step identity, conclusion) for the newest COMPLETED push-run of a workflow on the
    default branch — the runner's own account of what it did, which is the only authority on
    whether a rail actually deployed. None ⇒ could not observe (see _gh_json)."""
    slug = _repo_slug()
    if not slug:
        return None
    runs = _gh_json(
        f"repos/{slug}/actions/workflows/{workflow_file}/runs?branch=main&event=push&status=completed&per_page=1"
    )
    if not isinstance(runs, dict) or not runs.get("workflow_runs"):
        return None
    jobs = _gh_json(f"repos/{slug}/actions/runs/{runs['workflow_runs'][0]['id']}/jobs")
    if not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list):
        return None
    return [
        (step.get("name") or "<unnamed>", step.get("conclusion"))
        for job in jobs["jobs"]
        for step in (job.get("steps") or [])
    ]


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
        if set(wf_paths) != set(trigger_globs(trigger)):
            fail(
                "C",
                f"deploy_triggers.{name}: registry paths {sorted(trigger_globs(trigger))} "
                f"!= workflow on.push.paths {sorted(wf_paths)}",
            )
    for wf in sorted(WORKFLOWS.glob("deploy*.yml")):
        if wf.name not in registered_workflows:
            fail("C", f"{wf.name} is a deploy workflow but has no deploy_triggers entry")

    # --- J: every deploy-trigger path is justified, not inherited --------------
    unjustified: list[str] = []
    # Check C proves the registry MIRRORS the workflow. It cannot prove the workflow is right,
    # and for `cli/**` in the api trigger it was not: that glob rode in with the original
    # buildout commit and misclassified every cli PR as website-sensitive for months, because
    # parity faithfully preserved a path nothing in the build could consume. So each path must
    # now be inside what the job actually builds, or say in writing how it reaches the artifact.
    for name, trigger in triggers.items():
        globs = trigger_globs(trigger)
        if not globs:
            continue  # workflow_dispatch-only triggers deploy nothing on merge
        source = trigger.get("build_source")
        if not source:
            fail("J", f"deploy_triggers.{name}: needs `build_source` — what the deploy job builds")
            continue
        if not (ROOT / source).exists():
            fail("J", f"deploy_triggers.{name}: build_source {source!r} does not exist")
        for entry in trigger.get("paths") or []:
            path = entry.get("path") if isinstance(entry, dict) else entry
            if path == trigger["workflow"] or path.startswith(f"{source}/"):
                continue  # inside the build, or the deploy definition itself
            note = str(entry.get("note") or "").strip() if isinstance(entry, dict) else ""
            if not note:
                fail(
                    "J",
                    f"deploy_triggers.{name}: {path!r} is outside build_source {source!r} — "
                    "give it a `note` saying how it reaches the deployed artifact, or drop it "
                    "(from the workflow too; check C is set-equality)",
                )
            elif note.startswith("UNJUSTIFIED"):
                # Reported, never failed: the path IS a defect, and the registry now says so
                # out loud instead of a glob sitting there looking deliberate. Failing here
                # would only pressure the next author into writing a fictional justification.
                unjustified.append(f"deploy_triggers.{name}: {path!r} — {note.split('.')[0]}.")

    # --- K: a dormant deploy rail proves it — in shape, then in state ----------
    # Check J asks whether a path reaches the built artifact. K asks whether the job can ship
    # that artifact AT ALL. Declaring `state: dormant` strips the website-sensitive hold from
    # every path in the trigger, so the claim carries real merge authority and is earned twice:
    #
    #   SHAPE (offline, always) — every step in the workflow is gated on the arming var, or is
    #   listed in `ungated_steps` with a note. That is a proof rather than a heuristic: if no
    #   step can run without the secret, then no secret means no effect, whatever a green
    #   check says. It needs no network, so the merge decision stays deterministic.
    #
    #   STATE (online, best-effort) — the latest completed push-run on the default branch must
    #   show those steps `skipped`. This is the half that catches RE-ARMING: the secret landing
    #   while the registry still says dormant. It cannot be proven offline (secret existence is
    #   live state), so an unreachable API is REPORTED, never silently passed.
    unobserved: list[str] = []
    for name, trigger in triggers.items():
        arming = trigger.get("arming")
        if not isinstance(arming, dict) or arming.get("state") != "dormant":
            continue  # armed is the default and needs no proof — it only over-protects
        var, secret = arming.get("var"), arming.get("secret")  # allow-secret: names, not values
        if not var or not secret:
            fail("K", f"deploy_triggers.{name}: dormant arming needs both `secret` and `var`")
            continue
        if not str(arming.get("note") or "").strip():
            fail("K", f"deploy_triggers.{name}: dormant arming needs a `note` carrying the evidence")
        allowed = {}
        for entry in arming.get("ungated_steps") or []:
            if not str(entry.get("note") or "").strip():
                fail("K", f"deploy_triggers.{name}: ungated step {entry.get('step')!r} needs a `note`")
            allowed[entry.get("step")] = entry

        doc = workflow_doc(ROOT / trigger["workflow"])
        jobs = doc.get("jobs") or {}
        bound = any(secret in str((job.get("env") or {}).get(var, "")) for job in jobs.values())
        if not bound:
            fail("K", f"deploy_triggers.{name}: no job binds {var} to secrets.{secret} in {trigger['workflow']}")
        # An effect step is gated on the var being 'true'. The `== 'false'` branch is the
        # skip NOTICE, which by design runs precisely when the rail is dormant — counting it
        # as an effect would make a correctly-dormant rail fail its own check.
        effect_steps: list[str] = []
        for job in jobs.values():
            for step in job.get("steps") or []:
                ident = step.get("name") or step.get("uses") or "<unnamed>"
                cond = str(step.get("if") or "")
                if var in cond:
                    if re.search(rf"{re.escape(var)}\s*==\s*'true'", cond):
                        effect_steps.append(ident)
                elif ident not in allowed:
                    fail(
                        "K",
                        f"deploy_triggers.{name}: step {ident!r} runs whether or not {secret} "
                        f"exists — the rail cannot be called dormant. Gate it on {var}, or "
                        "record it under `ungated_steps` with a note saying why it is inert",
                    )
        # STATE — corroborate the claim against what the runner actually did. Matching is by
        # step NAME, so `uses:`-only steps (reported as "Run <action>") are outside this half;
        # the named effect steps are the decisive ones and they are covered.
        observed = _latest_run_steps(Path(trigger["workflow"]).name)
        if observed is None:
            unobserved.append(f"deploy_triggers.{name}: no reachable run history for {trigger['workflow']}")
            continue
        ran = sorted(
            {ident for ident, conclusion in observed if ident in effect_steps and conclusion not in ("skipped", None)}
        )
        if ran:
            fail(
                "K",
                f"deploy_triggers.{name}: declared dormant, but the latest run EXECUTED {ran} — "
                f"{secret} now exists. The rail is armed: set `state: armed` so merges to these "
                "paths are held to a green rollup again",
            )

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
        if "--deploy-regex" not in policy or re.search(r"^DASHBOARD_RE=", policy, re.MULTILINE):
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
            for path_glob in trigger_globs(trigger):
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

    # --- I: Python test gates cannot inherit host Git/editor state -----------
    wrapper = (ROOT / PYTEST_WRAPPER).read_text(encoding="utf-8")
    missing_wrapper_env = sorted(token for token in _HERMETIC_PYTEST_ENV if token not in wrapper)
    if missing_wrapper_env:
        fail("I", f"{PYTEST_WRAPPER}: lacks hermetic environment {missing_wrapper_env}")
    for gate_id, gate in gates.items():
        command = str(gate.get("command") or "")
        if "-m pytest" not in command and PYTEST_WRAPPER not in command:
            continue
        if PYTEST_WRAPPER not in shlex.split(command):
            fail("I", f"{gate_id}: pytest command must use {PYTEST_WRAPPER}")

    if unjustified:
        # Printed on the OK path too — a recorded defect that only shows up when something
        # else fails is a defect nobody reads.
        print(f"check-gates: {len(unjustified)} deploy-trigger path(s) recorded UNJUSTIFIED:")
        for line in unjustified:
            print(f"  · {line}")

    if unobserved:
        # Dormancy's SHAPE half passed offline; its STATE half could not be observed here.
        # Said out loud, because "I checked and it is dormant" and "I could not check" are
        # otherwise indistinguishable in this output — the corpus-retrieval failure mode.
        print(f"check-gates: {len(unobserved)} dormant rail(s) shape-proven but state-UNVERIFIED:")
        for line in unobserved:
            print(f"  · {line}")

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
