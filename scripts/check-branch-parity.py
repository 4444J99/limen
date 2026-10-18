#!/usr/bin/env python3
"""check-branch-parity.py — is each local branch PRESERVED, and are the correction receipts well-formed?

Born from the parity T2 deletion correction (#3039, handoff #3046): an audit certified 70 local branches
"preserved on the remote", deleted them, and reported "complete parity" on four defective predicates. Each
defect is a rule here, with its own test (cli/tests/test_check_branch_parity.py):

  D1  existence is not preservation. A branch is CONTAINED only when a real remote-tracking ref
      (refs/remotes/*) contains its tip. `branch.<n>.remote = .` makes a branch its own upstream and is
      reported SELF_UPSTREAM; it is never evidence. Ten branches carried it.
  D2  silence is not equivalence. Every git call's exit status is read. `git cherry` exits 128 on a missing
      ref; a pipeline that turns that into "0 unlanded" is the defect, so a failing call is ERROR.
  D3  identity is the full 40-hex OID. A prefix in a ledger or a tip is rejected, not widened.
  D4  ownership/state is re-read at the moment of use. `classify()` resolves its inputs fresh on every call
      and holds no snapshot; any future mutator must call it immediately before acting.

Plus the vacuum rule: a predicate that inspected nothing is UNMEASURED (exit 2), never green.

What UNPRESERVED means, and does not: the tip is in no remote-tracking ref, is no advertised PR head, and
`git cherry` finds patches (compared PER COMMIT by patch-id) absent from origin/main. Two things follow.
A multi-commit branch that was SQUASH-merged shows its commits as unmatched, so UNPRESERVED can be a false
positive for landed work — the safe direction (a flag, never a false clean), but a finding to inspect, not
proof of loss. And it does not know about a deliberate retention decision: a branch quarantined in place on
purpose (the pre-D3 lineage, which publishes nothing) is reported exactly like an accident, because no
committed registry of retained-by-decision refs exists to tell them apart. This script never invents one.

Two modes, and they prove DIFFERENT things:

  --ledgers  (default; offline; what CI runs) validates the committed correction receipts only: shape, row
             counts, 40-hex OIDs, uniqueness, restored ⊆ recovery. It is a RECEIPT VALIDATOR. A green
             --ledgers is NOT a parity claim about any branch.
  --live     measures the actual local estate: every local branch is classified, and every restored row is
             checked against the refs that exist now. This is the drift measurement; CI cannot run it
             because a CI checkout has no local branches. It is a closeout-time call.

Exit: 0 every measurement passed · 1 an unpreserved branch / drifted or missing restore / invalid ledger ·
2 unmeasured (nothing inspected, a git call failed, or a probe was unavailable).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPT_DIR = ROOT / "docs" / "receipts" / "session-closeout-parity-t2-deletion-correction-20261018"

# The receipts are an immutable record of one deletion event, so their cardinalities are constants of that
# event. A different count means the receipt was edited, or the reader matched nothing: either way, not green.
EXPECTED_RESTORED = 19
EXPECTED_RECOVERY = 70
LEDGER_HEADER = ["branch", "full_oid", "remote_ref", "pr", "pr_state", "obj_local", "quarantine_epoch"]
PR_STATES = {"OPEN", "MERGED", "CLOSED", "NONE"}

OID_RE = re.compile(r"[0-9a-f]{40}")
PULL_RE = re.compile(r"refs/pull/(\d+)/head")
SHA256_RE = re.compile(r"[0-9a-f]{64}")

PRESERVED = {"CONTAINED", "PR_HEAD", "PATCH_EQUIVALENT"}


@dataclass
class Result:
    branch: str
    verdict: str  # CONTAINED | PR_HEAD | PATCH_EQUIVALENT | UNPRESERVED | UNMEASURED | ERROR
    tip: str = ""
    detail: str = ""
    self_upstream: bool = False


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    code: int = 0

    def say(self, line: str) -> None:
        self.lines.append(line)

    def raise_to(self, code: int) -> None:
        # 1 (a real finding) outranks 2 (unmeasured) only if nothing worse is known; keep the max severity
        # ordering 0 < 2 < 1 so a measured failure is never downgraded to "unmeasured".
        order = {0: 0, 2: 1, 1: 2}
        if order[code] > order[self.code]:
            self.code = code


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Run git and return (returncode, stdout). The status is the caller's to read — never swallowed."""
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return done.returncode, done.stdout


def _remote_tracking_refs(repo: Path) -> tuple[list[str], str]:
    rc, out = _git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/")
    if rc != 0:
        return [], f"for-each-ref refs/remotes exited {rc}"
    refs = [r for r in out.splitlines() if r and not r.endswith("/HEAD")]
    return refs, ""


def containing_remote_refs(repo: Path, oid: str) -> tuple[list[str] | None, str]:
    """Remote-tracking refs whose history contains ``oid`` (D1). ``None`` means the call failed (D2)."""
    if not OID_RE.fullmatch(oid):
        return None, f"not a 40-hex OID: {oid!r}"
    rc, out = _git(repo, "for-each-ref", "--contains", oid, "--format=%(refname)", "refs/remotes/")
    if rc != 0:
        return None, f"for-each-ref --contains exited {rc}"
    return [r for r in out.splitlines() if r and not r.endswith("/HEAD")], ""


def classify(
    repo: Path, branch: str, *, pull_heads: set[str] | None = None, base_ref: str = "refs/remotes/origin/main"
) -> Result:
    """Classify one local branch. Resolves everything fresh (D4); never reads a cached snapshot."""
    rc, out = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")
    tip = out.strip()
    if rc != 0 or not OID_RE.fullmatch(tip):
        return Result(branch, "ERROR", detail=f"refs/heads/{branch} does not resolve to a full OID (rc={rc})")

    rc, out = _git(repo, "config", "--get", f"branch.{branch}.remote")
    self_upstream = rc == 0 and out.strip() == "."
    if rc not in (0, 1):  # 1 = key unset, which is fine; anything else is a failed call
        return Result(branch, "ERROR", tip, f"git config exited {rc}", self_upstream)

    # Cheap first probe: most landed branches are ancestors of origin/main. rc 0/1 are answers; any other
    # status (128 = missing ref) is a failed call, not "no" (D2). Only a "no" pays for the full scan below.
    rc, _ = _git(repo, "merge-base", "--is-ancestor", tip, base_ref)
    if rc == 0:
        return Result(branch, "CONTAINED", tip, base_ref, self_upstream)
    if rc != 1:
        return Result(branch, "ERROR", tip, f"merge-base --is-ancestor {base_ref} exited {rc}", self_upstream)

    refs, err = containing_remote_refs(repo, tip)
    if refs is None:
        return Result(branch, "ERROR", tip, err, self_upstream)
    if refs:
        return Result(branch, "CONTAINED", tip, refs[0], self_upstream)

    if pull_heads is None:
        # Not contained anywhere we can see, and the PR-head advertisement was not supplied: we cannot say
        # "unpreserved" without having measured every probe, so we do not.
        return Result(branch, "UNMEASURED", tip, "PR-head advertisement unavailable (use --live)", self_upstream)
    if tip in pull_heads:
        return Result(branch, "PR_HEAD", tip, "advertised by a refs/pull/*/head", self_upstream)

    rc, out = _git(repo, "cherry", base_ref, tip)
    if rc != 0:
        return Result(branch, "ERROR", tip, f"git cherry {base_ref} exited {rc}", self_upstream)
    ahead = [ln for ln in out.splitlines() if ln.startswith("+")]
    if not ahead:
        return Result(branch, "PATCH_EQUIVALENT", tip, f"every patch present in {base_ref}", self_upstream)
    return Result(branch, "UNPRESERVED", tip, f"{len(ahead)} patch(es) not in any remote ref or PR head", self_upstream)


def advertised_pull_heads(repo: Path) -> tuple[set[str] | None, str]:
    rc, out = _git(repo, "ls-remote", "origin", "refs/pull/*/head")
    if rc != 0:
        return None, f"git ls-remote origin exited {rc}"
    heads = {ln.split("\t", 1)[0] for ln in out.splitlines() if "\t" in ln}
    return heads, ""


# ── ledgers ─────────────────────────────────────────────────────────────────────────────────────────────


def _read_tsv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle, delimiter="\t"))


def validate_rows(name: str, rows: list[list[str]], expected: int, report: Report) -> list[list[str]]:
    """Shape rules shared by both ledgers. Returns the rows (possibly unusable) after reporting findings."""
    if len(rows) != expected:
        report.say(f"FAIL  {name}: {len(rows)} data row(s), expected exactly {expected} (matched nothing is not clean)")
        report.raise_to(1)
    seen_branch: set[str] = set()
    for number, row in enumerate(rows, start=1):
        where = f"{name} row {number}"
        if len(row) != len(LEDGER_HEADER):
            report.say(f"FAIL  {where}: {len(row)} column(s), expected {len(LEDGER_HEADER)}")
            report.raise_to(1)
            continue
        branch, oid, ref, pr, state, obj_local, epoch = row
        if not branch.strip():
            report.say(f"FAIL  {where}: empty branch name")
            report.raise_to(1)
        elif branch in seen_branch:
            report.say(f"FAIL  {where}: duplicate branch {branch!r}")
            report.raise_to(1)
        seen_branch.add(branch)
        if not OID_RE.fullmatch(oid):
            report.say(f"FAIL  {where}: {branch!r} OID is not a full 40-hex ({len(oid)} chars: {oid!r})")
            report.raise_to(1)
        pull = PULL_RE.fullmatch(ref)
        if not pull:
            report.say(f"FAIL  {where}: remote_ref {ref!r} is not refs/pull/<n>/head")
            report.raise_to(1)
        if state not in PR_STATES:
            report.say(f"FAIL  {where}: pr_state {state!r} not in {sorted(PR_STATES)}")
            report.raise_to(1)
        elif state == "NONE":
            if pr != "-":
                report.say(f"FAIL  {where}: pr_state NONE must carry pr '-', got {pr!r}")
                report.raise_to(1)
        elif not pull or pr != pull.group(1):
            report.say(f"FAIL  {where}: pr column {pr!r} disagrees with {ref!r}")
            report.raise_to(1)
        if obj_local not in {"yes", "no"}:
            report.say(f"FAIL  {where}: obj_local {obj_local!r} not yes/no")
            report.raise_to(1)
        if not epoch.strip():
            report.say(f"FAIL  {where}: empty quarantine_epoch")
            report.raise_to(1)
    return rows


def check_evidence(receipt_dir: Path, report: Report) -> None:
    path = receipt_dir / "evidence-sha256.txt"
    if not path.is_file():
        report.say(f"FAIL  {path.name}: missing")
        report.raise_to(1)
        return
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        report.say(f"FAIL  {path.name}: no digests recorded (matched nothing is not clean)")
        report.raise_to(1)
        return
    verified = unverifiable = 0
    for ln in lines:
        digest, _, rel = ln.partition("  ")
        if not SHA256_RE.fullmatch(digest) or not rel:
            report.say(f"FAIL  {path.name}: malformed line {ln!r}")
            report.raise_to(1)
            continue
        target = ROOT / rel
        if not target.is_file():
            unverifiable += 1
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            report.say(f"FAIL  {rel}: digest does not match {path.name}")
            report.raise_to(1)
        else:
            verified += 1
    report.say(
        f"note  evidence: {len(lines)} digest(s) recorded, {verified} verified here, "
        f"{unverifiable} UNVERIFIABLE-IN-CI (gitignored private files; never counted as a pass)"
    )


def run_ledgers(receipt_dir: Path, report: Report) -> tuple[list[list[str]], list[list[str]]]:
    restored_path = receipt_dir / "restored-branches.tsv"
    recovery_path = receipt_dir / "recovery-ledger.tsv"
    for path in (restored_path, recovery_path):
        if not path.is_file():
            report.say(f"FAIL  {path.name}: missing from {receipt_dir}")
            report.raise_to(1)
    if report.code:
        return [], []

    restored = validate_rows(restored_path.name, _read_tsv(restored_path), EXPECTED_RESTORED, report)

    recovery_all = _read_tsv(recovery_path)
    if not recovery_all or recovery_all[0] != LEDGER_HEADER:
        report.say(
            f"FAIL  {recovery_path.name}: header is {recovery_all[0] if recovery_all else None!r}, expected {LEDGER_HEADER}"
        )
        report.raise_to(1)
        recovery_rows: list[list[str]] = []
    else:
        recovery_rows = validate_rows(recovery_path.name, recovery_all[1:], EXPECTED_RECOVERY, report)

    by_branch = {row[0]: row for row in recovery_rows if row}
    for number, row in enumerate(restored, start=1):
        if by_branch.get(row[0]) != row:
            report.say(
                f"FAIL  {restored_path.name} row {number}: {row[0]!r} is not an identical row of the recovery ledger"
            )
            report.raise_to(1)

    check_evidence(receipt_dir, report)
    if report.code == 0:
        report.say(
            f"ok    ledgers: {len(restored)} restored, {len(recovery_rows)} recovered, shapes and OIDs valid "
            "(ledger integrity only — NOT a parity claim about any branch)"
        )
    return restored, recovery_rows


# ── live ────────────────────────────────────────────────────────────────────────────────────────────────


def run_live(repo: Path, restored: list[list[str]], report: Report) -> None:
    rc, out = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    if rc != 0:
        report.say(f"UNMEASURED  could not list local branches (for-each-ref exited {rc})")
        report.raise_to(2)
        return
    branches = [b for b in out.splitlines() if b]
    remote_refs, err = _remote_tracking_refs(repo)
    if err or not remote_refs:
        report.say(
            f"UNMEASURED  no usable remote-tracking refs ({err or 'none exist'}) — nothing to prove containment against"
        )
        report.raise_to(2)
        return
    if not branches:
        report.say("UNMEASURED  zero local branches inspected — a predicate that read nothing cannot report clean")
        report.raise_to(2)
        return
    pulls, err = advertised_pull_heads(repo)
    if pulls is None:
        report.say(f"UNMEASURED  {err}; PR-head probe unavailable, branches outside every remote ref stay UNMEASURED")
        report.raise_to(2)

    results = [classify(repo, b, pull_heads=pulls) for b in branches]
    counts: dict[str, int] = {}
    for item in results:
        counts[item.verdict] = counts.get(item.verdict, 0) + 1
    report.say(
        f"note  live: {len(results)} local branch(es): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )
    for item in results:
        if item.verdict in PRESERVED:
            continue
        flag = " [SELF_UPSTREAM]" if item.self_upstream else ""
        report.say(f"{item.verdict:<11} {item.branch} {item.tip}{flag} — {item.detail}")
        report.raise_to(1 if item.verdict == "UNPRESERVED" else 2)

    check_restored_live(repo, restored, pulls, report)


def check_restored_live(repo: Path, restored: list[list[str]], pulls: set[str] | None, report: Report) -> None:
    ok = advanced = drifted = missing = 0
    for row in restored:
        branch, oid = row[0], row[1]
        rc, out = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}")
        tip = out.strip()
        if rc == 0 and OID_RE.fullmatch(tip):
            if tip == oid:
                ok += 1
                continue
            rc, _ = _git(repo, "merge-base", "--is-ancestor", oid, tip)
            if rc == 0:
                advanced += 1
            elif rc == 1:
                drifted += 1
                report.say(f"DRIFTED     {branch}: tip {tip} no longer contains recorded {oid}")
                report.raise_to(1)
            else:
                report.say(f"UNMEASURED  {branch}: merge-base --is-ancestor exited {rc}")
                report.raise_to(2)
            continue
        refs, err = containing_remote_refs(repo, oid)
        if refs is None:
            report.say(f"UNMEASURED  {branch}: {err}")
            report.raise_to(2)
        elif refs or (pulls is not None and oid in pulls):
            report.say(
                f"note  {branch}: local ref absent, recorded OID {oid} is still advertised remotely (restorable)"
            )
        else:
            missing += 1
            report.say(f"MISSING     {branch}: no local ref and {oid} is in no remote ref or PR head")
            report.raise_to(1)
    report.say(
        f"note  restored: {len(restored)} target(s) — at recorded OID {ok}, advanced {advanced}, "
        f"drifted {drifted}, missing {missing}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledgers", action="store_true", help="validate the committed correction receipts (default)")
    parser.add_argument("--live", action="store_true", help="measure the real local estate (closeout-time)")
    parser.add_argument(
        "--repo", type=Path, default=ROOT, help="repository to measure with --live (default: this checkout)"
    )
    parser.add_argument("--receipt-dir", type=Path, default=RECEIPT_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    report = Report()
    restored, _ = run_ledgers(args.receipt_dir, report)
    if args.live:
        run_live(args.repo, restored, report)
    for line in report.lines:
        print(line)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
