#!/usr/bin/env python3
"""VERIFY resolver — selection and execution over the GATES registry.

The registry (institutio/governance/gates.yaml) declares every verification gate;
this resolver derives behavior from it. Scoped verification and the whole matrix stop
being two scripts and become two selections over the same data:

  verify.py --changed [--base REF]   the scoped push gate: compute the changed set
                                     (merge-base vs origin/main + staged + unstaged +
                                     untracked), run exactly the implicated gates —
                                     cheap tier first (no lock), heavy unserialized next,
                                     then the serialized tail under the machine-wide
                                     flock verify-whole.sh also holds. Skips are named.
                                     Exit 0 ⟺ every implicated gate passed.
                                     CI hardening (issue #1048): --require-base (or env
                                     LIMEN_VERIFY_REQUIRE_BASE=1) fails CLOSED — an
                                     unresolvable merge-base or an empty changed set is a
                                     hard error, never the silent local fallback, and a
                                     deploy-trigger diff escalates to the whole matrix
                                     (LIMEN_VERIFY_WHOLE_CMD, default verify-whole.sh)
                                     unless LIMEN_VERIFY_NO_DEPLOY_ESCALATION=1, which keeps
                                     the run scoped — CI's pull_request lane sets it because
                                     merge-policy.sh already refuses a website-sensitive
                                     merge until the full CI matrix is green, so pre-running
                                     the matrix per PR commit was pure duplication.
                                     --skip-ci-covered CI_JOB defers gates whose ci_job
                                     mirror lives in a different workflow job (they run
                                     there on the same PR; merge-policy holds on any red).
                                     --integration is the merge-queue composition gate:
                                     require an exact base, run every implicated scoped
                                     gate on the synthetic latest-base tree, and reuse the
                                     immutable PR-head matrix instead of escalating to a
                                     second whole-repo run.
  verify.py --explain [PATH...]      selection only, no execution — which gates these
                                     paths implicate (default: the changed set).
  verify.py --print-files SET        expand a file_set over tracked files (consumed by
                                     verify-whole.sh once its ratchet arms).
  verify.py --deploy-regex           the ERE equivalent of deploy_triggers (consumed by
                                     merge-policy.sh once its ratchet arms).
  verify.py --list [--json]          dump the gate table.
  verify.py --full                   exec verify-whole.sh (back-compat).

Path semantics are GitHub Actions path-filter globs (`**` crosses slashes, `*` does not),
identical to scripts/check-gates.py. scripts/check-gates.py is the drift predicate that
holds the registry to the workflows and consumers; this resolver trusts a green registry.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "gates.yaml"


class HostAdmissionFailure(RuntimeError):
    """The real Limen checkout denied its heavy verification tail."""


@contextmanager
def heavy_admission(*, owner: str, surface: str):
    """Load the host boundary only in a full checkout.

    Resolver contract fixtures intentionally copy only ``scripts/verify.py`` and
    the gate registry. They have no executable heavy surface and no admission
    module to bypass. A real checkout always carries both files; if its import is
    broken, fail closed.
    """

    module = ROOT / "cli" / "src" / "limen" / "host_admission.py"
    service = ROOT / "scripts" / "host-work-admission.py"
    if not module.is_file() and not service.is_file():
        yield
        return
    if not module.is_file() or not service.is_file():
        raise HostAdmissionFailure("host admission installation is incomplete")
    sys.path.insert(0, str(ROOT / "cli" / "src"))
    try:
        from limen.host_admission import AdmissionDenied, hold_lease
    except ModuleNotFoundError as exc:
        raise HostAdmissionFailure(f"host admission import failed: {exc}") from exc
    try:
        with hold_lease("heavy", owner=owner, surface=surface):
            yield
    except AdmissionDenied as exc:
        reasons = ",".join(exc.decision.get("reasons") or ["host-admission-denied"])
        raise HostAdmissionFailure(reasons) from exc
    except ValueError as exc:
        if str(exc) != "lease owner PID/start identity is unavailable":
            raise
        raise HostAdmissionFailure(str(exc)) from exc


def glob_to_regex(glob: str) -> re.Pattern[str]:
    out, i = [], 0
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


def load_registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text())


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def resolve_merge_base(base: str | None) -> str:
    for candidate in [base] if base else ["origin/main", "main"]:
        try:
            return git("merge-base", candidate, "HEAD").strip()
        except subprocess.CalledProcessError:
            continue
    return ""


def resolve_commit(ref: str) -> str:
    try:
        return git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        return ""


def integration_base(base: str | None) -> str:
    """Return the immutable queue base only when it is HEAD's exact merge-base."""
    if not base:
        return ""
    supplied = resolve_commit(base)
    merge_base = resolve_merge_base(base)
    if not supplied or not merge_base or supplied != merge_base:
        return ""
    try:
        git("merge-base", "--is-ancestor", supplied, "HEAD")
    except subprocess.CalledProcessError:
        return ""
    return supplied


def changed_set(base: str | None) -> list[str]:
    """Branch diff vs merge-base + staged + unstaged + untracked, existing-or-tracked only."""
    paths: set[str] = set()
    merge_base = resolve_merge_base(base)
    if merge_base:
        paths.update(git("diff", "--name-only", merge_base, "HEAD").splitlines())
    paths.update(git("diff", "--name-only").splitlines())
    paths.update(git("diff", "--name-only", "--cached").splitlines())
    paths.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    tracked = set(git("ls-files").splitlines())
    return sorted(p for p in paths if p and ((ROOT / p).exists() or p in tracked))


def gate_paths(gate_id: str, gate: dict, file_sets: dict) -> list[str]:
    if gate.get("kind") == "file_set":
        return list(file_sets[gate["file_set"]].get("include") or [])
    return list(gate.get("paths") or [])


def select(registry: dict, changed: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (selected gate ids in registry order, skipped [(id, reason)])."""
    file_sets = registry.get("file_sets") or {}
    selected, skipped = [], []
    for gate_id, gate in (registry.get("gates") or {}).items():
        if gate.get("scoped", True) is False:
            skipped.append((gate_id, "whole-matrix only"))
            continue
        regexes = [glob_to_regex(g) for g in gate_paths(gate_id, gate, file_sets)]
        if any(r.match(p) for p in changed for r in regexes):
            selected.append(gate_id)
        else:
            skipped.append((gate_id, "no implicated change"))
    return selected, skipped


def deploy_hits(registry: dict, changed: list[str]) -> list[str]:
    hits = []
    for trigger in (registry.get("deploy_triggers") or {}).values():
        for g in trigger.get("paths") or []:
            regex = glob_to_regex(g)
            hits.extend(p for p in changed if regex.match(p))
    return sorted(set(hits))


def expand_file_set(registry: dict, name: str) -> list[str]:
    spec = (registry.get("file_sets") or {})[name]
    tracked = git("ls-files").splitlines()
    excluded = {e.get("path") if isinstance(e, dict) else e for e in spec.get("exclude") or []}
    files: list[str] = []
    for pattern in spec.get("include") or []:
        regex = glob_to_regex(pattern)
        files.extend(f for f in tracked if regex.match(f) and f not in excluded)
    return sorted(set(files))


def deploy_regex(registry: dict) -> str:
    parts = []
    for trigger in (registry.get("deploy_triggers") or {}).values():
        for g in trigger.get("paths") or []:
            parts.append(glob_to_regex(g).pattern)
    return "(" + "|".join(parts) + ")" if parts else ""


def run_command(command: str) -> int:
    return subprocess.run(["bash", "-c", command], cwd=ROOT).returncode


def run_gate(gate_id: str, gate: dict, registry: dict, changed: list[str]) -> bool:
    print(f"\n==> {gate_id}: {gate['note']}")
    if gate.get("kind") == "per_file":
        for path in changed:
            template = (gate.get("per_file") or {}).get(Path(path).suffix)
            if template and (ROOT / path).is_file():
                if run_command(template.format(file=shlex.quote(path))) != 0:
                    print(f"FAILED: {gate_id} on {path}", file=sys.stderr)
                    return False
        return True
    if gate.get("kind") == "file_set":
        files = expand_file_set(registry, gate["file_set"])
        command = gate["command_template"].format(files=" ".join(map(shlex.quote, files)))
    else:
        command = gate["command"]
    if run_command(command) != 0:
        print(f"FAILED: {gate_id}", file=sys.stderr)
        return False
    return True


def cmd_changed(
    registry: dict,
    base: str | None,
    *,
    require_base: bool = False,
    skip_ci_covered: str | None = None,
    integration: bool = False,
) -> int:
    if integration:
        exact_base = integration_base(base)
        if not exact_base:
            supplied = resolve_commit(base) if base else ""
            merge_base = resolve_merge_base(base)
            detail = (
                f"supplied={supplied or 'unresolved'}, merge-base={merge_base or 'unresolved'}"
                if base
                else "no --base was supplied"
            )
            print(
                "integration-base: --integration requires the supplied --base commit to be "
                f"an ancestor of HEAD and its exact merge-base ({detail}); refusing to "
                "verify against a substituted common ancestor.",
                file=sys.stderr,
            )
            return 1
        # Pin the validated object ID so a movable ref cannot change between the
        # exactness check and changed-set construction.
        base = exact_base
    if require_base and not resolve_merge_base(base):
        print(
            f"require-base: no merge-base resolves against {base or 'origin/main'} — "
            "refusing to fail open (fetch enough history or fix --base).",
            file=sys.stderr,
        )
        return 1
    changed = changed_set(base)
    if not changed:
        if require_base:
            print(
                "require-base: base resolved but the changed set is empty — a real PR diff "
                "is never empty, so this is a resolution anomaly; refusing to fail open.",
                file=sys.stderr,
            )
            return 1
        print("No changes vs the base and no local modifications — nothing to verify.")
        return 0
    print(f"Changed paths ({len(changed)}):")
    for p in changed:
        print(f"  {p}")

    if require_base and not integration and deploy_hits(registry, changed):
        if os.environ.get("LIMEN_VERIFY_NO_DEPLOY_ESCALATION") == "1":
            print(
                "deploy-trigger paths in the diff — whole-matrix escalation suppressed "
                "(LIMEN_VERIFY_NO_DEPLOY_ESCALATION=1): running scoped gates only; "
                "merge-policy.sh still requires the full green matrix before a "
                "website-sensitive merge."
            )
        else:
            whole = os.environ.get("LIMEN_VERIFY_WHOLE_CMD") or str(ROOT / "scripts" / "verify-whole.sh")
            print(f"deploy-trigger paths in the diff — escalating to the whole matrix: {whole}")
            sys.stdout.flush()
            os.execv("/bin/bash", ["bash", whole])

    gates = registry.get("gates") or {}
    selected, skipped = select(registry, changed)
    for gate_id, reason in skipped:
        print(f"skipped: {gate_id} ({reason})")
    if skip_ci_covered:
        deferred = [g for g in selected if gates[g].get("ci_job") and gates[g]["ci_job"] != skip_ci_covered]
        selected = [g for g in selected if g not in deferred]
        for gate_id in deferred:
            print(f"deferred: {gate_id} (covered by {gates[gate_id]['ci_job']})")

    tiers = {"cheap": [], "heavy": [], "serialized": []}
    for gate_id in selected:
        gate = gates[gate_id]
        if gate.get("serialize"):
            tiers["serialized"].append(gate_id)
        else:
            tiers[gate.get("tier", "cheap")].append(gate_id)

    os.environ["PYTHONPATH"] = f"{ROOT / 'cli' / 'src'}" + (
        os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""
    )
    for gate_id in tiers["cheap"]:
        if not run_gate(gate_id, gates[gate_id], registry, changed):
            return 1
    needs_heavy = bool(tiers["heavy"] or tiers["serialized"])
    admission = (
        heavy_admission(
            owner=f"limen-verify-{os.getpid()}",
            surface="verify-scoped",
        )
        if needs_heavy
        else nullcontext()
    )
    try:
        with admission:
            for gate_id in tiers["heavy"]:
                if not run_gate(gate_id, gates[gate_id], registry, changed):
                    return 1
            if tiers["serialized"]:
                lock_path = os.environ.get(
                    "LIMEN_VERIFY_LOCK_FILE",
                    os.path.join(os.environ.get("TMPDIR", "/tmp"), "limen-verify-whole.lock"),
                )
                with open(lock_path, "w") as lock:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError:
                        print(f"Another verification holds {lock_path} — waiting…")
                        fcntl.flock(lock, fcntl.LOCK_EX)
                    for gate_id in tiers["serialized"]:
                        if not run_gate(gate_id, gates[gate_id], registry, changed):
                            return 1
    except HostAdmissionFailure as exc:
        print(f"Host admission denied scoped heavy verification: {exc}", file=sys.stderr)
        return 75

    hits = deploy_hits(registry, changed)
    if hits:
        if integration:
            print(
                "\nINTEGRATION: deploy-trigger paths were composed against the exact queue base.\n"
                "Every implicated scoped gate ran here; the immutable PR-head matrix remains\n"
                "a separate prerequisite and is not repeated on base-only movement."
            )
        else:
            print(
                "\nNOTE: diff touches deploy-trigger paths — the PR is website-sensitive.\n"
                "merge-policy.sh will require green CI (the full matrix) before merge; run\n"
                "scripts/verify-whole.sh (or let CI run it) before merging. Scoped green is a\n"
                "push gate, not a deploy gate."
            )
    print("\nScoped verification passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--changed", action="store_true")
    mode.add_argument("--explain", nargs="*", metavar="PATH")
    mode.add_argument("--print-files", metavar="SET")
    mode.add_argument("--deploy-regex", action="store_true")
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--base", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-base",
        action="store_true",
        help="fail closed: merge-base must resolve and the changed set must be non-empty "
        "(also via LIMEN_VERIFY_REQUIRE_BASE=1); deploy-trigger diffs escalate to the whole matrix "
        "unless LIMEN_VERIFY_NO_DEPLOY_ESCALATION=1",
    )
    parser.add_argument(
        "--skip-ci-covered",
        metavar="CI_JOB",
        default=None,
        help="defer selected gates whose ci_job mirror is a different workflow job than CI_JOB "
        "(e.g. pr-gate.yml:pr-gate) — they run in their own workflow on the same PR",
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="merge-queue composition mode: require --base to resolve to an ancestor of HEAD "
        "that is its exact merge-base, run every implicated scoped gate, and do not repeat "
        "the whole PR-head matrix for deploy-trigger paths",
    )
    args = parser.parse_args()

    if args.full:
        os.execv("/bin/bash", ["bash", str(ROOT / "scripts" / "verify-whole.sh")])

    registry = load_registry()
    if args.changed:
        if args.integration and args.skip_ci_covered:
            parser.error("--integration cannot be combined with --skip-ci-covered")
        return cmd_changed(
            registry,
            args.base,
            require_base=args.integration or args.require_base or os.environ.get("LIMEN_VERIFY_REQUIRE_BASE") == "1",
            skip_ci_covered=args.skip_ci_covered,
            integration=args.integration,
        )
    if args.explain is not None:
        paths = args.explain or changed_set(args.base)
        selected, _ = select(registry, paths)
        print("\n".join(selected))
        return 0
    if args.print_files:
        print("\n".join(expand_file_set(registry, args.print_files)))
        return 0
    if args.deploy_regex:
        print(deploy_regex(registry))
        return 0
    if args.list:
        gates = registry.get("gates") or {}
        if args.json:
            print(json.dumps(gates, indent=2))
        else:
            for gate_id, gate in gates.items():
                tier = "serialized" if gate.get("serialize") else gate.get("tier", "cheap")
                scope = "scoped" if gate.get("scoped", True) else "whole-only"
                print(f"{gate_id:24} {tier:10} {scope:10} {gate['note']}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
